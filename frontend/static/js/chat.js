/* ─────────────────────────────────────────
   chat.js — SOC Guidance Office Chatbot
   Frontend logic: messaging, bounded server-owned continuity,
   emotion badges, and escalation display.
───────────────────────────────────────── */

let currentTopic = "";
let currentLanguage = "";
let currentEmotion = "";
let currentFlagged = false;
let isAwaitingReply = false;

// A short typing state makes ordinary exchanges feel conversational without
// adding a noticeable wait after the server has already produced a reply.
// Safety replies still bypass this entirely.
const MIN_NORMAL_REPLY_TYPING_MS = 300;
const MAX_NORMAL_REPLY_TYPING_MS = 700;

let inactivityTimer = null;
// Student chat is intentionally the only surface that uses this shorter idle
// policy. Staff and administrator dashboard sessions keep their normal
// server-side session behavior.
const STUDENT_INACTIVITY_TIMEOUT = 20 * 60 * 1000;
const INACTIVITY_RETRY_DELAY = 60 * 1000;
let inactivityDeadline = 0;
let inactivityLogoutInProgress = false;
const legacyProtectedStorageKeys = [
  "hau_escalations",
  "hau_escalation_event",
  "hau_escalation_staff_msg",
  "hau_escalation_user_msg",
];

legacyProtectedStorageKeys.forEach((key) => localStorage.removeItem(key));
sessionStorage.removeItem("current_escalation");

// ── DOM References ──
const chatArea = document.getElementById("chat-area");

const input = document.getElementById("msg-input");
const sendButton = document.getElementById("send-message");
const quickReplyButtons = Array.from(
  document.querySelectorAll("[data-quick-message]"),
);
const API_BASE = window.location.origin;

// iOS Safari both resizes and pans the visual viewport when its software
// keyboard opens. Keep the chat shell matched to that visible area and offset
// it by Safari's pan so the header remains anchored while the chat pane is the
// sole scroller. Apply each viewport event immediately: delaying it by an
// animation frame leaves a visible moment where Safari has panned the page but
// the shell has not yet caught up.
let lastViewportMetrics = {};

function syncChatVisibleViewport() {
  const viewport = window.visualViewport;
  if (!viewport) return;

  const metrics = {
    height: `${Math.round(viewport.height)}px`,
    offsetTop: `${Math.round(viewport.offsetTop)}px`,
    offsetLeft: `${Math.round(viewport.offsetLeft)}px`,
  };
  const root = document.documentElement;

  if (metrics.height !== lastViewportMetrics.height) {
    root.style.setProperty("--chat-visible-height", metrics.height);
  }
  if (metrics.offsetTop !== lastViewportMetrics.offsetTop) {
    root.style.setProperty("--chat-visible-offset-top", metrics.offsetTop);
  }
  if (metrics.offsetLeft !== lastViewportMetrics.offsetLeft) {
    root.style.setProperty("--chat-visible-offset-left", metrics.offsetLeft);
  }
  lastViewportMetrics = metrics;
}

function bindChatVisibleViewport() {
  syncChatVisibleViewport();
  window.visualViewport?.addEventListener("resize", syncChatVisibleViewport);
  window.visualViewport?.addEventListener("scroll", syncChatVisibleViewport);
  window.addEventListener("orientationchange", syncChatVisibleViewport);
}

function dismissMobileKeyboardFromChat(event) {
  // Keep interactive controls interactive. Use a completed click rather than
  // pointerdown: iOS begins a chat-history scroll with pointerdown, so blurring
  // there would close the keyboard before the student can read older messages.
  if (
    !window.matchMedia("(hover: none), (pointer: coarse)").matches ||
    document.activeElement !== input ||
    event.target.closest(
      "button, a, input, textarea, select, label, [contenteditable='true']",
    )
  ) {
    return;
  }

  input.blur();
}

function bindMobileKeyboardDismissal() {
  document
    .querySelector(".chatbot-page .page")
    ?.addEventListener("click", dismissMobileKeyboardFromChat);
}

function setChatTurnPending(isPending) {
  isAwaitingReply = isPending;
  input.disabled = isPending;
  sendButton.disabled = isPending;
  quickReplyButtons.forEach((button) => {
    button.disabled = isPending;
  });
  chatArea.setAttribute("aria-busy", String(isPending));
}

function normalReplyTypingDelay() {
  return (
    MIN_NORMAL_REPLY_TYPING_MS +
    Math.floor(
      Math.random() *
        (MAX_NORMAL_REPLY_TYPING_MS - MIN_NORMAL_REPLY_TYPING_MS + 1),
    )
  );
}

function waitForMinimumTypingTime(startedAt, minimumDelay) {
  const remaining = minimumDelay - (Date.now() - startedAt);
  if (remaining <= 0) return Promise.resolve();
  return new Promise((resolve) => window.setTimeout(resolve, remaining));
}

function serializeChat() {
  const rows = Array.from(chatArea.querySelectorAll(".msg-row"));
  return rows.map((r) => {
    const isUser = r.classList.contains("user");
    const bubble = r.querySelector(".bubble");
    const timeEl = r.querySelector(".bubble-time");
    return {
      from: isUser ? "user" : "bot",
      text: bubble ? bubble.innerText : "",
      time: timeEl ? timeEl.textContent : "",
    };
  });
}

function scheduleInactivityCheck() {
  clearTimeout(inactivityTimer);

  const remaining = Math.max(0, inactivityDeadline - Date.now());
  inactivityTimer = setTimeout(endStudentSessionForInactivity, remaining);
}

async function endStudentSessionForInactivity() {
  if (inactivityLogoutInProgress || Date.now() < inactivityDeadline) {
    return;
  }

  // Do not interrupt a submitted message or leave its server request without
  // a visible result. Re-check shortly after that turn completes instead.
  if (isAwaitingReply) {
    inactivityTimer = setTimeout(
      endStudentSessionForInactivity,
      INACTIVITY_RETRY_DELAY,
    );
    return;
  }

  inactivityLogoutInProgress = true;
  setChatTurnPending(true);

  const finalized = await finalizeConversation({ resetUI: false });

  if (!finalized) {
    inactivityLogoutInProgress = false;
    setChatTurnPending(false);
    inactivityDeadline = Date.now() + INACTIVITY_RETRY_DELAY;
    scheduleInactivityCheck();
    return;
  }

  console.log("Conversation finalized due to student inactivity.");
  window.endAuthenticatedSession?.({
    finalize: false,
    reason: "inactive",
  });
}

function recordChatActivity() {
  if (inactivityLogoutInProgress) return;
  inactivityDeadline = Date.now() + STUDENT_INACTIVITY_TIMEOUT;
  scheduleInactivityCheck();
}

function checkInactivityAfterVisibilityChange() {
  if (!document.hidden && inactivityDeadline > 0) {
    scheduleInactivityCheck();
  }
}

function getTime() {
  return new Date().toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
}

// ── Auto-grow textarea ──
input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 100) + "px";
});

// ── Send on Enter (Shift+Enter = new line) ──
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// ─────────────────────────────
// UTILITIES
// ─────────────────────────────

function scrollToBottom() {
  chatArea.scrollTop = chatArea.scrollHeight;
}

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function linkifyUrls(text) {
  if (!text) return "";

  return String(text).replace(/https?:\/\/[^\s<]+/g, (rawUrl) => {
    const trimmed = rawUrl.replace(/[),.;!?]+$/, "");
    const trailing = rawUrl.slice(trimmed.length);
    return `<a href="${trimmed}" target="_blank" rel="noopener noreferrer">${trimmed}</a>${trailing}`;
  });
}

// ─────────────────────────────
// APPEND MESSAGES
// ─────────────────────────────

function appendUserMessage(text) {
  const row = document.createElement("div");
  row.className = "msg-row user";
  row.innerHTML = `
    <div class="bubble-wrap">
      <div class="bubble">${escapeHtml(text)}</div>
      <span class="bubble-time">${getTime()}</span>
    </div>`;
  chatArea.appendChild(row);
  scrollToBottom();
}

function appendBotMessage(htmlContent, emotionLabel, feedbackToken = "") {
  const row = document.createElement("div");
  row.className = "msg-row bot";

  const formattedContent = DOMPurify.sanitize(
    marked.parse(linkifyUrls(htmlContent)),
  );

  let badge = "";
  if (emotionLabel === "negative") {
    badge = `<span class="emotion-badge negative">Negative emotion detected</span>`;
  } else if (emotionLabel === "neutral") {
    badge = `<span class="emotion-badge neutral">Routine inquiry</span>`;
  }

  row.innerHTML = `
    <div class="avatar" aria-label="CTRL4 assistant">🦊</div>
    <div class="bubble-wrap">
      <div class="bubble">${formattedContent}${badge ? "<br>" + badge : ""}</div>
      <span class="bubble-time">${getTime()}</span>
    </div>`;
  if (feedbackToken) {
    const feedback = createFeedbackControl(feedbackToken);
    row.querySelector(".bubble-wrap")?.appendChild(feedback);
  }
  chatArea.appendChild(row);
  scrollToBottom();
}

function createFeedbackControl(feedbackToken) {
  const wrap = document.createElement("div");
  wrap.className = "chatbot-feedback-actions";

  const buttons = [
    { kind: "helpful", label: "Mark this reply as helpful" },
    { kind: "not_helpful", label: "Share feedback about this reply" },
  ];
  buttons.forEach(({ kind, label }) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chatbot-feedback-icon";
    button.appendChild(createThumbIcon(kind));
    button.setAttribute("aria-label", label);
    button.title = label;
    button.addEventListener("click", () => {
      openFeedbackDialog(feedbackToken, kind, () => {
        wrap.querySelectorAll(".chatbot-feedback-icon").forEach((icon) => {
          icon.disabled = true;
          icon.classList.toggle("selected", icon === button);
        });
        button.setAttribute("aria-label", "Feedback received");
        button.title = "Feedback received";
      });
    });
    wrap.appendChild(button);
  });
  return wrap;
}

function createThumbIcon(direction) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.9");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  if (direction === "not_helpful") svg.classList.add("thumb-down");

  const handle = document.createElementNS("http://www.w3.org/2000/svg", "path");
  handle.classList.add("thumb-divider");
  handle.setAttribute("d", "M7 10v12");
  const handPath =
    "M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z";
  const fill = document.createElementNS("http://www.w3.org/2000/svg", "path");
  fill.classList.add("thumb-fill");
  fill.setAttribute("d", handPath);
  const outline = document.createElementNS(
    "http://www.w3.org/2000/svg",
    "path",
  );
  outline.classList.add("thumb-outline");
  outline.setAttribute("d", handPath);
  svg.append(fill, outline, handle);
  return svg;
}

function openFeedbackDialog(feedbackToken, direction, onSubmitted) {
  document.getElementById("chatbot-feedback-dialog")?.remove();

  const categories =
    direction === "helpful"
      ? [
          ["helpful", "Helpful"],
          ["clear_useful", "Clear and useful"],
          ["other", "Other"],
        ]
      : [
          ["not_helpful", "Not helpful"],
          ["incorrect_information", "Incorrect or incomplete"],
          ["did_not_understand", "Did not understand me"],
          ["safety_concern", "This reply felt unsafe"],
          ["other", "Other"],
        ];
  const overlay = document.createElement("div");
  overlay.id = "chatbot-feedback-dialog";
  overlay.className = "chatbot-feedback-modal";
  overlay.setAttribute("role", "presentation");
  const dialog = document.createElement("section");
  dialog.className = "chatbot-feedback-dialog";
  dialog.setAttribute("role", "dialog");
  dialog.setAttribute("aria-modal", "true");
  dialog.setAttribute("aria-labelledby", "chatbot-feedback-title");

  const titleRow = document.createElement("div");
  titleRow.className = "chatbot-feedback-dialog-header";
  const title = document.createElement("h2");
  title.id = "chatbot-feedback-title";
  title.textContent = "Share feedback";
  const close = document.createElement("button");
  close.type = "button";
  close.className = "chatbot-feedback-close";
  close.textContent = "×";
  close.setAttribute("aria-label", "Close feedback dialog");
  titleRow.append(title, close);

  const categoryList = document.createElement("div");
  categoryList.className = "chatbot-feedback-categories";
  const note = document.createElement("textarea");
  note.maxLength = 500;
  note.rows = 4;
  note.placeholder = "Share details (optional)";
  note.setAttribute("aria-label", "Optional feedback details");
  const safetyNote = document.createElement("p");
  safetyNote.className = "chatbot-feedback-safety-note";
  safetyNote.textContent =
    "This feedback form is not monitored for emergencies. Do not include urgent or private details.";
  const status = document.createElement("p");
  status.className = "chatbot-feedback-status";
  status.setAttribute("role", "status");
  const submit = document.createElement("button");
  submit.type = "button";
  submit.className = "chatbot-feedback-submit";
  submit.textContent = "Submit";
  submit.disabled = true;

  let selectedCategory = "";
  categories.forEach(([value, label]) => {
    const category = document.createElement("button");
    category.type = "button";
    category.className = "chatbot-feedback-category";
    category.textContent = `+ ${label}`;
    category.addEventListener("click", () => {
      selectedCategory = value;
      categoryList
        .querySelectorAll(".chatbot-feedback-category")
        .forEach((button) =>
          button.classList.toggle("selected", button === category),
        );
      submit.disabled = false;
      status.textContent = "";
    });
    categoryList.appendChild(category);
  });

  const closeDialog = () => {
    overlay.remove();
    document.removeEventListener("keydown", onEscape);
  };
  close.addEventListener("click", closeDialog);
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) closeDialog();
  });
  const onEscape = (event) => {
    if (event.key === "Escape") {
      closeDialog();
    }
  };
  document.addEventListener("keydown", onEscape);
  submit.addEventListener("click", async () => {
    if (!selectedCategory) return;
    submit.disabled = true;
    status.textContent = "Submitting feedback...";
    try {
      const response = await fetch(`${API_BASE}/chat/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          response_token: feedbackToken,
          category: selectedCategory,
          comment: note.value.trim(),
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.message || "Unable to save feedback.");
      }
      closeDialog();
      onSubmitted();
    } catch (error) {
      status.textContent = error.message || "Unable to save feedback.";
      submit.disabled = false;
    }
  });

  dialog.append(titleRow, categoryList, note, safetyNote, status, submit);
  overlay.appendChild(dialog);
  document.body.appendChild(overlay);
  categoryList.querySelector("button")?.focus();
}

function showTypingIndicator() {
  const row = document.createElement("div");
  row.className = "typing-row";
  row.id = "typing-indicator";
  row.innerHTML = `
    <div class="avatar" aria-label="CTRL4 assistant">🦊</div>
    <div class="typing-bubble">
      <div class="dot"></div>
      <div class="dot"></div>
      <div class="dot"></div>
    </div>`;
  chatArea.appendChild(row);
  scrollToBottom();
}

function removeTypingIndicator() {
  const el = document.getElementById("typing-indicator");
  if (el) el.remove();
}

// ─────────────────────────────
// SEND MESSAGE
// ─────────────────────────────

async function sendMessage() {
  if (isAwaitingReply || input.disabled) return;

  const text = input.value.trim();
  if (!text) return;

  setChatTurnPending(true);

  // Clear input
  input.value = "";
  input.style.height = "auto";

  // Show user message
  appendUserMessage(text);

  recordChatActivity();

  // Show typing indicator
  showTypingIndicator();

  const typingStartedAt = Date.now();
  const minimumTypingDelay = normalReplyTypingDelay();

  try {
    const response = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        conversation: serializeChat(),
      }),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error(data.message || "Unable to generate a response.");
    }

    const result = data.data || {};

    // Safety replies must never wait for the simulated typing duration.
    if (!result.escalated) {
      await waitForMinimumTypingTime(typingStartedAt, minimumTypingDelay);
    }
    removeTypingIndicator();

    appendBotMessage(
      result.response || "Sorry, I could not generate a response.",
      result.emotion || "",
      result.feedback_token || "",
    );

    currentTopic = result.topic || currentTopic;
    currentLanguage = result.language || currentLanguage;
    currentEmotion = result.emotion || currentEmotion;
    currentFlagged = Boolean(result.escalated);

    recordChatActivity();
  } catch (_) {
    removeTypingIndicator();
    appendBotMessage(
      "Sorry, I am having trouble connecting right now. Please try again.",
      "",
    );
  } finally {
    setChatTurnPending(false);
    input.focus();
  }
}

function showAppointmentPrompt() {
  const existing = document.getElementById("appointment-confirmation");
  if (existing) existing.remove();

  const overlay = document.createElement("div");
  overlay.id = "appointment-confirmation";
  overlay.className = "confirmation-popup";
  overlay.innerHTML = `
    <div class="confirmation-card">
      <h3>Book an appointment?</h3>
      <p>You’ll be taken to the appointment request form where you can submit your details for guidance support.</p>
      <div class="confirmation-actions">
        <button type="button" class="cancel-btn">Cancel</button>
        <button type="button" class="confirm-btn">Open form</button>
      </div>
    </div>`;

  document.body.appendChild(overlay);

  overlay
    .querySelector(".cancel-btn")
    .addEventListener("click", () => overlay.remove());
  overlay.querySelector(".confirm-btn").addEventListener("click", () => {
    overlay.remove();
    window.location.href = "/appointment";
  });
}

function sendQuick(text) {
  if (isAwaitingReply || input.disabled) return;
  if (/book an appointment/i.test(text)) {
    showAppointmentPrompt();
    return;
  }
  input.value = text;
  sendMessage();
}

async function finalizeConversation({ resetUI = true } = {}) {
  const conversation = serializeChat();

  if (conversation.length === 0) {
    return true;
  }

  try {
    const response = await fetch(`${API_BASE}/chat/finalize`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        conversation,
        topic: currentTopic,
        language: currentLanguage,
        emotion: currentEmotion,
        flagged: currentFlagged,
      }),
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error(data.error || "Unable to finalize conversation.");
    }

    clearTimeout(inactivityTimer);

    currentTopic = "";
    currentLanguage = "";
    currentEmotion = "";
    currentFlagged = false;

    if (resetUI) {
      chatArea.innerHTML = `
        <div class="date-divider">
          <span>Today</span>
        </div>`;
      input.value = "";
      input.style.height = "auto";
      input.placeholder = "Type your message here...";

      initializeChat();
    }

    return true;
  } catch (error) {
    console.error("Conversation finalization failed:", error);
    return false;
  }
}

window.finalizeConversation = finalizeConversation;

const exportBtn = document.getElementById("export-chat-btn");
if (exportBtn) {
  exportBtn.remove();
}

const endConversationBtn = document.getElementById("end-conversation-btn");
if (endConversationBtn) {
  endConversationBtn.remove();
}

// -----------------------------------------
// Initial Welcome Message
// -----------------------------------------

const user = JSON.parse(sessionStorage.getItem("hau_user") || "{}");

const firstName = (user.name || "there").trim().split(" ")[0];

const WELCOME_MESSAGE = `Hello, ${firstName}! Welcome to CTRL4.
I'm your AI Guidance Assistant, here to support you with personal concerns, academic challenges, and questions about Guidance Office services.
Take your time—what would you like to talk about today?`;

function loadActiveChat() {
  try {
    const state = document.getElementById("active-chat-state");
    const items = state ? JSON.parse(state.textContent || "[]") : [];
    return Array.isArray(items) ? items : [];
  } catch (_) {
    // The server remains authoritative. Malformed page state starts a new
    // visible exchange without writing protected content to browser storage.
    return [];
  }
}

function restoreVisibleChat(items) {
  items.forEach((item) => {
    if (!item || typeof item.text !== "string") return;
    if (item.from === "user") {
      appendUserMessage(item.text);
    } else if (item.from === "bot") {
      appendBotMessage(item.text);
    }
  });
}

async function initializeChat() {
  setChatTurnPending(true);

  const activeChat = loadActiveChat();
  if (activeChat.length > 0) {
    restoreVisibleChat(activeChat);
    setChatTurnPending(false);
    input.focus();
    return;
  }

  // Show typing indicator
  showTypingIndicator();
  const typingDelay = 800 + Math.random() * 500;
  setTimeout(() => {
    // Remove typing indicator
    removeTypingIndicator();

    // Send greeting
    appendBotMessage(WELCOME_MESSAGE);
    setChatTurnPending(false);
    input.focus();
  }, typingDelay);
}

document.querySelectorAll("[data-quick-message]").forEach((button) => {
  button.addEventListener("click", () =>
    sendQuick(button.dataset.quickMessage || ""),
  );
});
document.getElementById("send-message")?.addEventListener("click", sendMessage);

window.sendMessage = sendMessage;
window.sendQuick = sendQuick;
document.addEventListener(
  "DOMContentLoaded",
  () => {
    bindChatVisibleViewport();
    bindMobileKeyboardDismissal();
    document.addEventListener(
      "visibilitychange",
      checkInactivityAfterVisibilityChange,
    );
    initializeChat();
  },
  { once: true },
);
window.addEventListener("beforeunload", () => {
  clearTimeout(inactivityTimer);
});
