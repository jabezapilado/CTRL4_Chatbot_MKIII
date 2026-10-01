/* dashboard.js — SOC Staff Dashboard logic */

if (window.requireAuth) {
  window.requireAuth();
}

const API_BASE = window.location.origin;

let staffInboxItems = [];
let inboxLoadState = "loading";
let flaggedConversations = [];
let flaggedConversationsLoaded = false;
let inboxSort = { key: "priority", direction: "desc" };
let chatbotFeedback = [];
let chatbotFeedbackLoadState = "loading";
let chatbotFeedbackInsights = null;
let feedbackSort = { key: "student", direction: "asc" };
let flaggedSort = { key: "priority", direction: "desc" };
let appointmentsLoaded = false;
let appointmentAnalytics = null;
let chatbotAnalytics = null;
let inboxStatistics = null;
let counselorWorkloadAnalytics = null;
let flaggedCaseAnalytics = null;
let reportsAnalytics = null;
let dashboardLoadPromise = null;
let reportsLoadPromise = null;
let activeCaseDetailsTab = "overview";
let activeCaseManagementTab = "confidentiality";
const DASHBOARD_TABLE_PAGE_SIZE = 10;
const DASHBOARD_TABLE_PAGE_SIZES = Object.freeze({
  "inbox-tbody": 7,
  "flagged-tbody": 7,
});
const dashboardTablePages = new Map();
let appointmentCalendarMonth = new Date(
  new Date().getFullYear(),
  new Date().getMonth(),
  1,
);

const views = document.querySelectorAll(".view");

let persistedSettings = null;
let appointmentBookingOptions = { state: "loading", bookingEnabled: false };
let persistedFaqs = [];
let settingsBaseline = "";
let counselorProfileBaseline = "";

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.message || data.error || "Request failed");
  }
  return data;
}

function mapInboxItem(row) {
  const createdAt = row.created_at ? new Date(row.created_at) : null;
  return {
    id: row.summary_id,
    studentName: row.student_name || "Authorized student",
    studentNumber: row.student_number || "—",
    program: row.program || "—",
    category: row.primary_concern || "General inquiry",
    emotion: row.emotion_results || "Unavailable",
    flagged: Boolean(row.flagged_status),
    priority: row.case_priority || "low",
    status: row.review_status || "routine",
    summary: row.summary_preview || "No AI summary preview is available.",
    hasReferral: Boolean(row.has_referral),
    hasIntervention: Boolean(row.has_intervention),
    createdAt,
  };
}

function mapFlaggedConversation(row) {
  return mapInboxItem(row);
}

function mapChatbotFeedback(row) {
  return {
    id: row.feedback_id,
    studentName: row.student_name || "Authorized student",
    studentNumber: row.student_number || "—",
    program: row.program || "—",
    category: row.category || "not_helpful",
    responseContext: row.response_context || "uncategorized",
    comment: row.comment || "—",
    createdAt: row.created_at ? new Date(row.created_at) : null,
  };
}

function mapAppointment(row) {
  return {
    id: row.id,
    student: row.student_name || row.full_name || "Unknown",
    studentNumber: row.student_number || "—",
    email: row.student_email || row.email || "",

    date: row.preferred_date
      ? new Date(row.preferred_date).toISOString().split("T")[0]
      : "",
    time: row.preferred_time_slot,

    category: row.appointment_category,
    mode: row.appointment_mode,
    source: row.appointment_source,

    contactNumber: row.contact_number,
    reason: row.reason,
    counselorNotes: row.counselor_notes,

    program: row.program || "—",
    assignedTo: row.assigned_to || "—",

    status: row.status || "pending",

    createdAt: row.created_at,
    updatedAt: row.updated_at,
  };
}

function formatAppointmentDate(dateValue) {
  if (!dateValue) return "No date";
  const parsed = new Date(`${dateValue}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return dateValue;
  return parsed.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatAppointmentTime(timeValue) {
  if (!timeValue) return "No time";

  // Already in 12-hour format (e.g. "10:00 AM")
  if (/^\d{1,2}:\d{2}\s?(AM|PM)$/i.test(timeValue.trim())) {
    return timeValue;
  }

  // 24-hour format (e.g. "14:30")
  if (/^\d{1,2}:\d{2}$/.test(timeValue.trim())) {
    const [hourStr, minuteStr] = timeValue.split(":");
    const date = new Date();
    date.setHours(Number(hourStr), Number(minuteStr), 0, 0);
    return date.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
    });
  }

  return timeValue;
}

function formatAppointmentSource(source) {
  const map = {
    chatbot: "Chatbot",
    walk_in: "Walk-in",
    hotline: "Hotline",
    messenger: "Messenger",
    email: "Email",
    staff_manual: "Staff Manual Entry",
  };
  return map[source] || source;
}

function formatAppointmentMode(mode) {
  const map = {
    onsite: "Onsite",
    online: "Online",
    hybrid: "Hybrid",
  };
  return map[mode] || mode || "—";
}

function formatAppointmentCategory(category) {
  if (!category) return "General";
  const map = {
    career_schooling: "Career / Schooling",
    home_family: "Home and Family",
    personality_development: "Personality Development",
    relationships: "Relationships",
    religion_spiritual: "Religion / Spiritual Development",
    health_recreation: "Health and Recreation",
    employment: "Employment",
    others: "Others",
  };
  return (
    map[category] ||
    category.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

function escapeHtml(value) {
  const escapeMap = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  };

  return String(value ?? "").replace(
    /[&<>"']/g,
    (character) => escapeMap[character],
  );
}

function escapeAppointmentText(value) {
  return escapeHtml(value);
}

function createFaqBlock(title, question, answer) {
  const container = document.createElement("div");
  container.className = "faq-block";
  container.innerHTML = `
    <div class="faq-block-header">
      <div class="faq-title">${escapeHtml(title)}</div>
      <div class="faq-q">${escapeHtml(question)}</div>
    </div>
    <div class="faq-block-body">
      <textarea>${escapeHtml(answer || "")}</textarea>
    </div>
  `;
  return container;
}

function getAppointmentCardText(appointment) {
  return {
    student: escapeAppointmentText(appointment.student),
    studentNumber: escapeAppointmentText(appointment.studentNumber),
    date: escapeAppointmentText(formatAppointmentDate(appointment.date)),
    time: escapeAppointmentText(formatAppointmentTime(appointment.time)),
    mode: escapeAppointmentText(formatAppointmentMode(appointment.mode)),
    source: escapeAppointmentText(formatAppointmentSource(appointment.source)),
    category: escapeAppointmentText(
      formatAppointmentCategory(appointment.category),
    ),
  };
}

const CALENDAR_STATUS_BADGES = {
  pending: ["pending", "Pending"],
  confirmed: ["neutral", "Confirmed"],
  cancelled: ["negative", "Cancelled"],
  rejected: ["negative", "Rejected"],
  completed: ["resolved", "Completed"],
};

function getAppointmentCalendarDate(value) {
  const date = String(value || "");
  return /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : "";
}

function getAppointmentCalendarTimeSortValue(value) {
  const time = String(value || "").trim();
  const twelveHourMatch = time.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/i);

  if (twelveHourMatch) {
    const hour = Number(twelveHourMatch[1]);
    const minute = Number(twelveHourMatch[2]);

    if (hour >= 1 && hour <= 12 && minute >= 0 && minute <= 59) {
      const normalizedHour =
        (hour % 12) + (twelveHourMatch[3].toUpperCase() === "PM" ? 12 : 0);
      return normalizedHour * 60 + minute;
    }
  }

  const twentyFourHourMatch = time.match(/^(\d{1,2}):(\d{2})$/);
  if (twentyFourHourMatch) {
    const hour = Number(twentyFourHourMatch[1]);
    const minute = Number(twentyFourHourMatch[2]);

    if (hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59) {
      return hour * 60 + minute;
    }
  }

  return Number.MAX_SAFE_INTEGER;
}

function createAppointmentCalendarStatusBadge(status) {
  const normalizedStatus = String(status || "").toLowerCase();
  const [className, label] =
    CALENDAR_STATUS_BADGES[normalizedStatus] || CALENDAR_STATUS_BADGES.pending;
  const badge = document.createElement("span");

  badge.className = `badge ${className}`;
  badge.textContent = label;

  return badge;
}

function createAppointmentCalendarEvent(appointment) {
  const event = document.createElement("button");
  const date = formatAppointmentDate(appointment.date);
  const time = formatAppointmentTime(appointment.time);
  const status = String(appointment.status || "pending").toLowerCase();

  event.type = "button";
  event.className = "appointment-calendar-event";
  event.setAttribute(
    "aria-label",
    [
      appointment.student || "Unknown student",
      appointment.studentNumber || "No student number",
      date,
      time,
      CALENDAR_STATUS_BADGES[status]?.[1] || "Pending",
    ].join(", "),
  );

  const student = document.createElement("strong");
  student.className = "appointment-calendar-event-student";
  student.textContent = appointment.student || "Unknown";

  const studentNumber = document.createElement("span");
  studentNumber.className = "appointment-calendar-event-student-number";
  studentNumber.textContent = appointment.studentNumber || "—";

  const appointmentDate = document.createElement("time");
  appointmentDate.className = "appointment-calendar-event-date";
  appointmentDate.dateTime = getAppointmentCalendarDate(appointment.date);
  appointmentDate.textContent = date;

  const appointmentTime = document.createElement("time");
  appointmentTime.className = "appointment-calendar-event-time";
  appointmentTime.textContent = time;

  const statusContainer = document.createElement("span");
  statusContainer.className = "appointment-calendar-event-status";
  statusContainer.appendChild(createAppointmentCalendarStatusBadge(status));

  event.append(
    student,
    studentNumber,
    appointmentDate,
    appointmentTime,
    statusContainer,
  );
  event.addEventListener("click", () => openAppointmentDetails(appointment));

  return event;
}

function renderAppointmentCalendar() {
  const grid = document.getElementById("appointment-calendar-grid");
  const monthLabel = document.getElementById("appointment-calendar-month");

  if (!grid || !monthLabel) {
    return;
  }

  const year = appointmentCalendarMonth.getFullYear();
  const month = appointmentCalendarMonth.getMonth();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const firstWeekday = new Date(year, month, 1).getDay();
  const totalCells = Math.ceil((firstWeekday + daysInMonth) / 7) * 7;
  const appointmentsByDate = new Map();

  (window.backendAppointments || []).forEach((appointment) => {
    const date = getAppointmentCalendarDate(appointment.date);
    if (!date) {
      return;
    }

    const items = appointmentsByDate.get(date) || [];
    items.push(appointment);
    appointmentsByDate.set(date, items);
  });

  monthLabel.textContent = new Date(year, month, 1).toLocaleDateString(
    "en-US",
    {
      month: "long",
      year: "numeric",
    },
  );
  grid.replaceChildren();

  for (let index = 0; index < totalCells; index += 1) {
    const dayNumber = index - firstWeekday + 1;
    const day = document.createElement("section");
    day.className = "appointment-calendar-day";

    if (dayNumber < 1 || dayNumber > daysInMonth) {
      day.classList.add("is-outside-month");
      grid.appendChild(day);
      continue;
    }

    const date = `${year}-${String(month + 1).padStart(2, "0")}-${String(
      dayNumber,
    ).padStart(2, "0")}`;
    const heading = document.createElement("time");
    heading.className = "appointment-calendar-day-number";
    heading.dateTime = date;
    heading.textContent = String(dayNumber);
    day.appendChild(heading);

    const events = document.createElement("div");
    events.className = "appointment-calendar-events";
    const appointments = appointmentsByDate.get(date) || [];

    appointments
      .sort(
        (left, right) =>
          getAppointmentCalendarTimeSortValue(left.time) -
          getAppointmentCalendarTimeSortValue(right.time),
      )
      .forEach((appointment) => {
        events.appendChild(createAppointmentCalendarEvent(appointment));
      });

    day.appendChild(events);
    grid.appendChild(day);
  }
}

function bindAppointmentCalendar() {
  document
    .getElementById("appointment-calendar-previous")
    ?.addEventListener("click", () => {
      appointmentCalendarMonth = new Date(
        appointmentCalendarMonth.getFullYear(),
        appointmentCalendarMonth.getMonth() - 1,
        1,
      );
      renderAppointmentCalendar();
    });

  document
    .getElementById("appointment-calendar-next")
    ?.addEventListener("click", () => {
      appointmentCalendarMonth = new Date(
        appointmentCalendarMonth.getFullYear(),
        appointmentCalendarMonth.getMonth() + 1,
        1,
      );
      renderAppointmentCalendar();
    });
}

function renderAppointmentDashboard() {
  renderAppointmentStatistics();
  renderAppointmentAnalytics();
  renderAppointmentCalendar();
  renderAppointmentRequests();
  renderTodaysAppointments();
  renderAppointmentHistory();
  renderFlaggedAppointmentCases();
  renderManualAppointmentEntry();
}

function renderAnalyticsRows(
  containerId,
  rows,
  labelKey,
  emptyMessage = "No appointment data for this period.",
) {
  const container = document.getElementById(containerId);
  if (!container) return;

  container.replaceChildren();

  if (!rows.length) {
    clearDashboardTablePagination(containerId);
    appendTableEmptyState(container, 2, emptyMessage);
    return;
  }

  const page = paginateDashboardRows(containerId, rows, () => {
    renderAnalyticsRows(containerId, rows, labelKey, emptyMessage);
  });

  page.items.forEach((item) => {
    const row = document.createElement("tr");
    const label = document.createElement("td");
    const count = document.createElement("td");
    label.textContent = item[labelKey];
    count.textContent = String(item.count);
    row.append(label, count);
    container.appendChild(row);
  });
}

function displayAggregateValue(value) {
  return value === null || value === undefined ? "—" : String(value);
}

function renderAppointmentAnalytics() {
  const analytics = appointmentAnalytics;
  if (!analytics) return;

  const total = document.getElementById("appointment-analytics-total");
  const range = document.getElementById("appointment-analytics-range");
  if (total)
    total.textContent = displayAggregateValue(analytics.total_appointments);

  if (range) {
    const { start_date: startDate, end_date: endDate } =
      analytics.filters || {};
    range.textContent =
      startDate || endDate
        ? `${startDate || "Beginning"} to ${endDate || "Present"}`
        : "All authorized appointment records";
  }

  renderAnalyticsRows(
    "appointment-analytics-statuses",
    analytics.status_distribution || [],
    "status",
  );
  renderAnalyticsRows(
    "appointment-analytics-daily",
    analytics.daily_trends || [],
    "date",
  );
  renderAnalyticsRows(
    "appointment-analytics-weekly",
    analytics.weekly_trends || [],
    "week",
  );
  renderAnalyticsRows(
    "appointment-analytics-monthly",
    analytics.monthly_trends || [],
    "month",
  );
  renderAnalyticsRows(
    "appointment-analytics-counselors",
    analytics.counselor_counts || [],
    "counselor_name",
  );
  renderAnalyticsRows(
    "appointment-analytics-programs",
    analytics.program_statistics || [],
    "program",
  );
}

function renderChatbotAnalytics() {
  const analytics = chatbotAnalytics;
  if (!analytics) return;

  const valueFor = (elementId, value) => {
    const element = document.getElementById(elementId);
    if (element) element.textContent = displayAggregateValue(value);
  };

  valueFor(
    "chatbot-analytics-total-messages",
    analytics.total_chatbot_messages,
  );
  valueFor(
    "chatbot-analytics-finalizations",
    analytics.conversation_finalization_count,
  );
  valueFor("chatbot-analytics-escalations", analytics.escalation_count);
  valueFor(
    "chatbot-analytics-average-length",
    analytics.average_finalized_conversation_length,
  );

  const volume = analytics.message_volume || {};
  renderAnalyticsRows(
    "chatbot-analytics-emotions",
    analytics.persisted_emotion_result_distribution || [],
    "emotion_result",
    "No persisted inquiry records for this period.",
  );
  renderAnalyticsRows(
    "chatbot-analytics-daily",
    volume.daily || [],
    "date",
    "No persisted inquiry records for this period.",
  );
  renderAnalyticsRows(
    "chatbot-analytics-weekly",
    volume.weekly || [],
    "week",
    "No persisted inquiry records for this period.",
  );
  renderAnalyticsRows(
    "chatbot-analytics-monthly",
    volume.monthly || [],
    "month",
    "No persisted inquiry records for this period.",
  );
  renderStudentReportGraph(
    "chatbot-analytics-emotion-graph",
    (analytics.persisted_emotion_result_distribution || []).map((item) => ({
      label: item.emotion_result || "Unknown",
      value: Number(item.count) || 0,
    })),
    "No persisted inquiry records for this period.",
  );
  renderStudentReportGraph(
    "chatbot-analytics-daily-graph",
    (volume.daily || []).slice(-7).map((item) => ({
      label: item.date,
      value: Number(item.count) || 0,
    })),
    "No daily message records for this period.",
  );
}

function todayAnalyticsQuery() {
  const today = new Date().toISOString().slice(0, 10);
  return `?${new URLSearchParams({ start_date: today, end_date: today })}`;
}

function renderInboxStatistics() {
  const setValue = (elementId, value) => {
    const element = document.getElementById(elementId);
    if (element) element.textContent = displayAggregateValue(value);
  };
  const status = document.getElementById("inbox-stat-status");
  const statusIndicator = document.getElementById("inbox-status-indicator");
  const setChatbotStatus = (value, state) => {
    if (status) status.textContent = value;
    if (!statusIndicator) return;
    statusIndicator.classList.toggle("is-online", state === "online");
    statusIndicator.classList.toggle("is-offline", state === "offline");
    statusIndicator.setAttribute("aria-label", `Chatbot status: ${value}`);
  };

  if (!inboxStatistics) {
    setValue("inbox-stat-inquiries", "—");
    setValue("inbox-stat-flagged", "—");
    setValue("inbox-stat-routine", "—");
    setChatbotStatus("Unavailable", "offline");
    return;
  }

  const finalizations =
    Number(inboxStatistics.conversation_finalization_count) || 0;
  const escalations = Number(inboxStatistics.escalation_count) || 0;
  setValue("inbox-stat-inquiries", inboxStatistics.total_chatbot_messages || 0);
  setValue("inbox-stat-flagged", escalations);
  setValue("inbox-stat-routine", Math.max(0, finalizations - escalations));
  setChatbotStatus("Online", "online");
}

async function loadInboxStatistics() {
  const result = await fetchJson(
    `${API_BASE}/api/dashboard/chatbot/analytics${todayAnalyticsQuery()}`,
  );
  inboxStatistics = result.data || null;
  renderInboxStatistics();
}

async function loadChatbotAnalytics() {
  const startDate = document.getElementById(
    "chatbot-analytics-start-date",
  )?.value;
  const endDate = document.getElementById("chatbot-analytics-end-date")?.value;
  const query = new URLSearchParams();
  if (startDate) query.set("start_date", startDate);
  if (endDate) query.set("end_date", endDate);

  const suffix = query.size ? `?${query.toString()}` : "";
  const result = await fetchJson(
    `${API_BASE}/api/dashboard/chatbot/analytics${suffix}`,
  );
  chatbotAnalytics = result.data || null;
  [
    "chatbot-analytics-emotions",
    "chatbot-analytics-daily",
    "chatbot-analytics-weekly",
    "chatbot-analytics-monthly",
  ].forEach(resetDashboardTablePage);
  renderChatbotAnalytics();
}

function bindChatbotAnalyticsFilters() {
  document
    .getElementById("chatbot-analytics-apply")
    ?.addEventListener("click", async () => {
      try {
        await loadChatbotAnalytics();
      } catch (error) {
        console.error(error);
        createToast("Unable to load chatbot analytics.", "info");
      }
    });

  document
    .getElementById("chatbot-analytics-reset")
    ?.addEventListener("click", async () => {
      const startDate = document.getElementById("chatbot-analytics-start-date");
      const endDate = document.getElementById("chatbot-analytics-end-date");
      if (startDate) startDate.value = "";
      if (endDate) endDate.value = "";

      try {
        await loadChatbotAnalytics();
      } catch (error) {
        console.error(error);
        createToast("Unable to load chatbot analytics.", "info");
      }
    });
}

function renderCounselorWorkloadAnalytics() {
  const analytics = counselorWorkloadAnalytics;
  if (!analytics) return;

  const values = [
    [
      "counselor-workload-authorized-appointments",
      analytics.authorized_appointment_count,
    ],
    [
      "counselor-workload-pending-appointments",
      analytics.pending_appointment_count,
    ],
    [
      "counselor-workload-confirmed-appointments",
      analytics.confirmed_appointment_count,
    ],
    [
      "counselor-workload-completed-appointments",
      analytics.completed_appointment_count,
    ],
    ["counselor-workload-active-referrals", analytics.active_referral_count],
    [
      "counselor-workload-active-interventions",
      analytics.active_intervention_count,
    ],
    [
      "counselor-workload-completed-interventions",
      analytics.completed_intervention_count,
    ],
  ];

  values.forEach(([elementId, value]) => {
    const element = document.getElementById(elementId);
    if (element) element.textContent = displayAggregateValue(value);
  });

  renderAnalyticsRows(
    "counselor-workload-programs",
    analytics.workload_by_program || [],
    "program",
    "No authorized appointment records for this period.",
  );
  renderStudentReportGraph(
    "counselor-workload-program-graph",
    (analytics.workload_by_program || []).map((item) => ({
      label: item.program || "Unknown",
      value: Number(item.count) || 0,
    })),
    "No authorized appointment records for this period.",
  );
}

async function loadCounselorWorkloadAnalytics() {
  const startDate = document.getElementById(
    "counselor-workload-start-date",
  )?.value;
  const endDate = document.getElementById("counselor-workload-end-date")?.value;
  const query = new URLSearchParams();
  if (startDate) query.set("start_date", startDate);
  if (endDate) query.set("end_date", endDate);

  const suffix = query.size ? `?${query.toString()}` : "";
  const result = await fetchJson(
    `${API_BASE}/api/dashboard/counselor-workload${suffix}`,
  );
  counselorWorkloadAnalytics = result.data || null;
  resetDashboardTablePage("counselor-workload-programs");
  renderCounselorWorkloadAnalytics();
}

function bindCounselorWorkloadAnalyticsFilters() {
  document
    .getElementById("counselor-workload-apply")
    ?.addEventListener("click", async () => {
      try {
        await loadCounselorWorkloadAnalytics();
      } catch (error) {
        console.error(error);
        createToast("Unable to load counselor workload analytics.", "info");
      }
    });

  document
    .getElementById("counselor-workload-reset")
    ?.addEventListener("click", async () => {
      const startDate = document.getElementById(
        "counselor-workload-start-date",
      );
      const endDate = document.getElementById("counselor-workload-end-date");
      if (startDate) startDate.value = "";
      if (endDate) endDate.value = "";

      try {
        await loadCounselorWorkloadAnalytics();
      } catch (error) {
        console.error(error);
        createToast("Unable to load counselor workload analytics.", "info");
      }
    });
}

function renderFlaggedCaseAnalytics() {
  const analytics = flaggedCaseAnalytics;
  if (!analytics) return;

  const values = [
    ["flagged-case-analytics-total", analytics.total_flagged_cases],
    ["flagged-case-analytics-pending", analytics.pending_flagged_case_reviews],
    ["flagged-case-analytics-reviewed", analytics.reviewed_flagged_cases],
    ["flagged-case-analytics-referrals", analytics.referral_count],
    ["flagged-case-analytics-interventions", analytics.intervention_count],
    [
      "flagged-case-analytics-confidential",
      analytics.current_confidential_case_count,
    ],
  ];

  values.forEach(([elementId, value]) => {
    const element = document.getElementById(elementId);
    if (element) element.textContent = displayAggregateValue(value);
  });

  const trends = analytics.escalation_trends || {};
  renderAnalyticsRows(
    "flagged-case-analytics-statuses",
    analytics.persisted_case_status_distribution || [],
    "status",
    "No flagged-case records for this period.",
  );
  renderAnalyticsRows(
    "flagged-case-analytics-daily",
    trends.daily || [],
    "date",
    "No escalation records for this period.",
  );
  renderAnalyticsRows(
    "flagged-case-analytics-weekly",
    trends.weekly || [],
    "week",
    "No escalation records for this period.",
  );
  renderAnalyticsRows(
    "flagged-case-analytics-monthly",
    trends.monthly || [],
    "month",
    "No escalation records for this period.",
  );
  renderStudentReportGraph(
    "flagged-case-status-graph",
    (analytics.persisted_case_status_distribution || []).map((item) => ({
      label: item.status || "Unknown",
      value: Number(item.count) || 0,
    })),
    "No flagged-case records for this period.",
  );
}

async function loadFlaggedCaseAnalytics() {
  const startDate = document.getElementById(
    "flagged-case-analytics-start-date",
  )?.value;
  const endDate = document.getElementById(
    "flagged-case-analytics-end-date",
  )?.value;
  const query = new URLSearchParams();
  if (startDate) query.set("start_date", startDate);
  if (endDate) query.set("end_date", endDate);

  const suffix = query.size ? `?${query.toString()}` : "";
  const result = await fetchJson(
    `${API_BASE}/api/dashboard/flagged-cases/analytics${suffix}`,
  );
  flaggedCaseAnalytics = result.data || null;
  [
    "flagged-case-analytics-statuses",
    "flagged-case-analytics-daily",
    "flagged-case-analytics-weekly",
    "flagged-case-analytics-monthly",
  ].forEach(resetDashboardTablePage);
  renderFlaggedCaseAnalytics();
}

function bindFlaggedCaseAnalyticsFilters() {
  document
    .getElementById("flagged-case-analytics-apply")
    ?.addEventListener("click", async () => {
      try {
        await loadFlaggedCaseAnalytics();
      } catch (error) {
        console.error(error);
        createToast("Unable to load flagged case analytics.", "info");
      }
    });

  document
    .getElementById("flagged-case-analytics-reset")
    ?.addEventListener("click", async () => {
      const startDate = document.getElementById(
        "flagged-case-analytics-start-date",
      );
      const endDate = document.getElementById(
        "flagged-case-analytics-end-date",
      );
      if (startDate) startDate.value = "";
      if (endDate) endDate.value = "";

      try {
        await loadFlaggedCaseAnalytics();
      } catch (error) {
        console.error(error);
        createToast("Unable to load flagged case analytics.", "info");
      }
    });
}

async function loadAppointmentAnalytics() {
  const startDate = document.getElementById(
    "appointment-analytics-start-date",
  )?.value;
  const endDate = document.getElementById(
    "appointment-analytics-end-date",
  )?.value;
  const query = new URLSearchParams();
  if (startDate) query.set("start_date", startDate);
  if (endDate) query.set("end_date", endDate);

  const suffix = query.size ? `?${query.toString()}` : "";
  const result = await fetchJson(
    `${API_BASE}/api/dashboard/appointments/analytics${suffix}`,
  );
  appointmentAnalytics = result.data || null;
  [
    "appointment-analytics-statuses",
    "appointment-analytics-daily",
    "appointment-analytics-weekly",
    "appointment-analytics-monthly",
    "appointment-analytics-counselors",
    "appointment-analytics-programs",
  ].forEach(resetDashboardTablePage);
  renderAppointmentAnalytics();
}

function bindAppointmentAnalyticsFilters() {
  document
    .getElementById("appointment-analytics-apply")
    ?.addEventListener("click", async () => {
      try {
        await loadAppointmentAnalytics();
      } catch (error) {
        console.error(error);
        createToast("Unable to load appointment analytics.", "info");
      }
    });

  document
    .getElementById("appointment-analytics-reset")
    ?.addEventListener("click", async () => {
      const startDate = document.getElementById(
        "appointment-analytics-start-date",
      );
      const endDate = document.getElementById("appointment-analytics-end-date");
      if (startDate) startDate.value = "";
      if (endDate) endDate.value = "";

      try {
        await loadAppointmentAnalytics();
      } catch (error) {
        console.error(error);
        createToast("Unable to load appointment analytics.", "info");
      }
    });
}

function getSearchedAppointments() {
  const appointments = window.backendAppointments || [];
  const query = document
    .getElementById("appointment-search-input")
    ?.value.trim()
    .toLowerCase();

  if (!query) {
    return appointments;
  }

  return appointments.filter((appointment) =>
    [appointment.student, appointment.studentNumber].some((value) =>
      String(value || "")
        .toLowerCase()
        .includes(query),
    ),
  );
}

function renderSearchedAppointmentSections() {
  renderAppointmentRequests();
  renderTodaysAppointments();
  renderAppointmentHistory();
}

function bindAppointmentSearch() {
  const input = document.getElementById("appointment-search-input");

  input?.addEventListener("input", renderSearchedAppointmentSections);
}

function renderAppointmentStatistics() {
  const appointments = window.backendAppointments || [];
  const statisticElements = [
    document.getElementById("appointments-today-count"),
    document.getElementById("pending-appointments-count"),
    document.getElementById("completed-appointments-count"),
  ];

  if (!appointmentsLoaded) {
    statisticElements.forEach((element) => {
      if (element) element.textContent = "—";
    });
    return;
  }

  const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
    .toISOString()
    .split("T")[0];

  const normalizeDate = (value) => {
    if (!value) return "";
    if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
      return value;
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "";
    return parsed.toISOString().split("T")[0];
  };

  const totalToday = appointments.filter(
    (appointment) => normalizeDate(appointment.date) === today,
  ).length;

  const pendingCount = appointments.filter(
    (appointment) =>
      appointment.status === "pending" && appointment.source !== "staff_manual",
  ).length;

  const completedToday = appointments.filter(
    (appointment) =>
      appointment.status === "completed" &&
      normalizeDate(appointment.date) === today,
  ).length;

  statisticElements[0].textContent = String(totalToday);
  statisticElements[1].textContent = String(pendingCount);
  statisticElements[2].textContent = String(completedToday);
}

function renderCompactEmptyState(container, message) {
  container.replaceChildren();
  const empty = document.createElement("p");
  empty.className = "compact-empty-state";
  empty.textContent = message;
  container.appendChild(empty);
}

function renderAppointmentRequests() {
  const appointments = getSearchedAppointments();

  const pendingAppointments = appointments.filter(
    (appointment) =>
      appointment.status === "pending" && appointment.source !== "staff_manual",
  );

  const container = document.getElementById("appointment-requests-container");

  if (!container) return;

  container.replaceChildren();

  if (!pendingAppointments.length) {
    renderCompactEmptyState(
      container,
      "No pending appointment requests. New student requests will appear here.",
    );
    return;
  }

  pendingAppointments.forEach((appointment) => {
    const card = createPendingAppointmentCard(appointment);

    container.appendChild(card);
  });
}

function renderTodaysAppointments() {
  const appointments = getSearchedAppointments();

  // (debug block moved below)

  const today = new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
    .toISOString()
    .split("T")[0];

  const normalizeDate = (value) => {
    if (!value) return "";
    if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
      return value;
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return String(value);
    return parsed.toISOString().split("T")[0];
  };

  // Manual appointments are created with a "confirmed" status,
  // so no special-case filtering is required here.
  const confirmedAppointments = appointments.filter(
    (appointment) => appointment.status === "confirmed",
  );

  const container = document.getElementById("todays-appointments-container");

  if (!container) return;

  container.replaceChildren();

  if (!confirmedAppointments.length) {
    renderCompactEmptyState(
      container,
      "No confirmed appointments. Confirmed appointments awaiting completion will appear here.",
    );
    return;
  }

  confirmedAppointments.forEach((appointment) => {
    const card = createTodaysAppointmentCard(appointment);
    container.appendChild(card);
  });
}

function renderAppointmentHistory() {
  const appointments = getSearchedAppointments();

  const historyAppointments = appointments.filter((appointment) =>
    ["completed", "cancelled", "rejected"].includes(appointment.status),
  );

  const container = document.getElementById("appointment-history-container");

  if (!container) return;

  container.replaceChildren();

  if (!historyAppointments.length) {
    renderCompactEmptyState(
      container,
      "No appointment history is available for the current selection.",
    );

    return;
  }

  historyAppointments.forEach((appointment) => {
    const card = createAppointmentHistoryCard(appointment);

    container.appendChild(card);
  });
}

function renderFlaggedAppointmentCases() {
  const flaggedCases = flaggedConversations;

  const container = document.getElementById(
    "flagged-appointment-cases-container",
  );

  if (!container) return;

  container.replaceChildren();

  if (!flaggedCases.length) {
    renderCompactEmptyState(
      container,
      "No flagged cases currently require an appointment recommendation.",
    );

    return;
  }

  flaggedCases.forEach((summary) => {
    const card = createFlaggedAppointmentCaseCard(summary);

    container.appendChild(card);
  });
}

function humanizeAppointmentChoice(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function addChoiceOptions(select, choices, placeholder) {
  if (!select) return;
  select.replaceChildren();
  const prompt = document.createElement("option");
  prompt.value = "";
  prompt.disabled = true;
  prompt.selected = true;
  prompt.textContent = placeholder;
  select.appendChild(prompt);
  choices.forEach((choice) => {
    const option = document.createElement("option");
    option.value = choice;
    option.textContent = humanizeAppointmentChoice(choice);
    select.appendChild(option);
  });
}

function bookingOptionsAreAvailable(options) {
  return options?.state === "available" && options.bookingEnabled === true;
}

function parseBookingTime(value) {
  const match = String(value || "")
    .trim()
    .match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/i);
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour < 1 || hour > 12 || minute > 59) return null;
  return (
    ((hour % 12) + (match[3].toUpperCase() === "PM" ? 12 : 0)) * 60 + minute
  );
}

function dateMatchesBookingWindow(dateValue, window) {
  const selectedDate = new Date(`${dateValue}T00:00:00`);
  if (Number.isNaN(selectedDate.getTime())) return false;
  const days = [
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
  ];
  const selectedDay = days[selectedDate.getDay()];
  const range = String(window.days || "").split(" to ");
  if (range.length === 1) return range[0] === selectedDay;
  const start = days.indexOf(range[0]);
  const end = days.indexOf(range[1]);
  const current = days.indexOf(selectedDay);
  return start >= 0 && end >= start && current >= start && current <= end;
}

function isManualBookingSelectionAvailable(dateValue, timeValue, options) {
  if (
    !bookingOptionsAreAvailable(options) ||
    options.unavailableDates?.includes(dateValue)
  ) {
    return false;
  }
  return Boolean(options.availableSlots?.includes(timeValue));
}

async function refreshAppointmentBookingOptions(
  preferredDate = "",
  studentNumber = "",
) {
  const query = new URLSearchParams();
  if (preferredDate) query.set("date", preferredDate);
  if (studentNumber) query.set("student_number", studentNumber);
  const response = await fetchJson(
    `${API_BASE}/api/appointments/booking-options${
      query.size ? `?${query}` : ""
    }`,
  );
  appointmentBookingOptions = response.data || {
    state: "unconfigured",
    bookingEnabled: false,
  };
  return appointmentBookingOptions;
}

function populateManualSlotSelect(
  select,
  slots,
  placeholder,
  disabled = false,
) {
  if (!select) return;
  const previousValue = select.value;
  select.replaceChildren();
  const prompt = document.createElement("option");
  prompt.value = "";
  prompt.disabled = true;
  prompt.selected = true;
  prompt.textContent = placeholder;
  select.appendChild(prompt);
  slots.forEach((slot) => {
    const option = document.createElement("option");
    option.value = slot;
    option.textContent = formatAppointmentTime(slot);
    if (slot === previousValue) option.selected = true;
    select.appendChild(option);
  });
  select.disabled = disabled;
}

function renderManualAppointmentOptions(container) {
  const available = bookingOptionsAreAvailable(appointmentBookingOptions);
  const date = container.querySelector("#manual-appointment-date");
  const time = container.querySelector("#manual-appointment-time");
  const mode = container.querySelector("#manual-appointment-mode");
  const category = container.querySelector("#manual-appointment-category");
  const status = container.querySelector("#manual-appointment-options-status");

  addChoiceOptions(
    mode,
    available ? appointmentBookingOptions.consultationModes || [] : [],
    available
      ? "Select a consultation mode"
      : "Appointment configuration unavailable",
  );
  addChoiceOptions(
    category,
    available ? appointmentBookingOptions.appointmentCategories || [] : [],
    available
      ? "Select an appointment category"
      : "Appointment configuration unavailable",
  );
  [date, time, mode, category].forEach((input) => {
    if (input) input.disabled = !available;
  });
  populateManualSlotSelect(
    time,
    [],
    available
      ? "Select a student and date first"
      : "Appointment configuration unavailable",
    true,
  );
  if (status) {
    status.textContent = available
      ? "Current appointment options loaded."
      : "Appointment configuration is unavailable. Manual appointment creation is disabled.";
    status.classList.toggle("error", !available);
  }
}

function renderManualAppointmentEntry() {
  const container = document.getElementById(
    "manual-appointment-entry-container",
  );

  if (!container) {
    return;
  }

  container.innerHTML = `
    <div class="manual-appointment-card">
      <div class="field-grid-2">
        <div class="field-group">
          <label for="manual-student-search">Student</label>
          <input
            id="manual-student-search"
            type="text"
            placeholder="Search by name, student number, or email"
            autocomplete="off"
            aria-autocomplete="list"
            aria-controls="manual-student-search-results"
            aria-expanded="false"
          />
          <div
            id="manual-student-search-results"
            class="search-results"
            hidden
          ></div>
        </div>

        <div class="field-group">
          <label for="manual-appointment-source">Appointment Source</label>
          <select id="manual-appointment-source">
            <option>Walk-in</option>
            <option>Hotline</option>
            <option>Messenger</option>
            <option>Email</option>
          </select>
        </div>
      </div>

      <div class="field-grid-2">
        <div class="field-group">
          <label for="manual-student-number">Student Number</label>
          <input id="manual-student-number" type="text" disabled />
        </div>

        <div class="field-group">
          <label for="manual-student-program">Program</label>
          <input id="manual-student-program" type="text" disabled />
        </div>

        <div class="field-group">
          <label for="manual-student-email">Email Address</label>
          <input id="manual-student-email" type="email" disabled />
        </div>
      </div>

      <div class="manual-entry-actions">
        <button
          id="create-manual-appointment-btn"
          class="btn btn-primary"
          type="button"
        >
          Continue
        </button>
      </div>

      <div id="manual-appointment-details" class="manual-appointment-details" hidden>
        <hr class="manual-entry-divider">

        <h3 class="manual-entry-title">Appointment Details</h3>

        <div class="field-group">
          <label for="manual-appointment-date">Preferred Date</label>
          <input id="manual-appointment-date" type="date" />
        </div>

        <div class="field-group manual-entry-spaced">
          <label for="manual-appointment-time">Preferred Time</label>
          <select id="manual-appointment-time" disabled>
            <option value="">Select an available time slot</option>
          </select>
        </div>

        <div class="field-grid-2 manual-entry-spaced">
          <div class="field-group">
            <label for="manual-appointment-mode">Mode</label>
            <select id="manual-appointment-mode"></select>
          </div>

          <div class="field-group">
            <label for="manual-appointment-category">Category</label>
            <select id="manual-appointment-category"></select>
          </div>
        </div>

        <p id="manual-appointment-options-status" class="settings-status" role="status"></p>

        <div class="field-group manual-entry-spaced">
          <label for="manual-appointment-reason">Reason</label>
          <textarea id="manual-appointment-reason" rows="4"></textarea>
        </div>

        <div class="manual-entry-actions">
          <button id="save-manual-appointment-btn" class="btn btn-primary" type="button">
            Create Appointment
          </button>
        </div>
      </div>
    </div>
  `;

  const studentSearchInput = container.querySelector("#manual-student-search");

  const studentNumberInput = container.querySelector("#manual-student-number");

  const studentProgramInput = container.querySelector(
    "#manual-student-program",
  );

  const studentEmailInput = container.querySelector("#manual-student-email");

  studentSearchInput.value = "";
  studentNumberInput.value = "";
  studentProgramInput.value = "";
  studentEmailInput.value = "";

  const studentSearchResults = container.querySelector(
    "#manual-student-search-results",
  );

  studentSearchResults.replaceChildren();
  studentSearchResults.hidden = true;
  let selectedStudent = null;
  let activeSuggestionIndex = -1;

  function clearSelectedStudent() {
    selectedStudent = null;
    studentNumberInput.value = "";
    studentProgramInput.value = "";
    studentEmailInput.value = "";
    container.querySelector("#manual-appointment-details").hidden = true;
    appointmentDateInput.disabled = true;
    populateManualSlotSelect(
      appointmentTimeInput,
      [],
      "Select a student and date first",
      true,
    );
  }

  function closeSuggestions() {
    studentSearchResults.replaceChildren();
    studentSearchResults.hidden = true;
    studentSearchInput.setAttribute("aria-expanded", "false");
    activeSuggestionIndex = -1;
  }

  function selectStudent(student) {
    selectedStudent = student;
    studentSearchInput.value = student.full_name || "";
    studentNumberInput.value = student.student_number || "";
    studentProgramInput.value = student.program || "";
    studentEmailInput.value = student.email || "";
    appointmentDateInput.disabled = false;
    closeSuggestions();
  }

  function renderSuggestions(students) {
    studentSearchResults.replaceChildren();
    activeSuggestionIndex = -1;
    if (!students.length) {
      const empty = document.createElement("p");
      empty.className = "manual-student-search-empty";
      empty.textContent =
        "No students in your assigned programs match this search.";
      studentSearchResults.appendChild(empty);
      studentSearchResults.hidden = false;
      studentSearchInput.setAttribute("aria-expanded", "true");
      return;
    }
    students.forEach((student, index) => {
      const option = document.createElement("button");
      option.type = "button";
      option.className = "manual-student-search-result";
      option.dataset.suggestionIndex = String(index);
      const name = document.createElement("strong");
      const detail = document.createElement("small");
      name.textContent = student.full_name || "Authorized student";
      detail.textContent = [
        student.student_number || "—",
        student.program || "—",
        student.email || "—",
      ].join(" · ");
      option.append(name, detail);
      option.addEventListener("click", () => selectStudent(student));
      studentSearchResults.appendChild(option);
    });
    studentSearchResults.hidden = false;
    studentSearchInput.setAttribute("aria-expanded", "true");
  }

  studentSearchInput.addEventListener("input", async () => {
    const query = studentSearchInput.value.trim();
    clearSelectedStudent();
    closeSuggestions();

    if (!query) {
      return;
    }

    try {
      const loading = document.createElement("p");
      loading.className = "manual-student-search-empty";
      loading.textContent = "Searching authorized students...";
      studentSearchResults.appendChild(loading);
      studentSearchResults.hidden = false;
      const response = await fetchJson(
        `${API_BASE}/api/accounts/search?q=${encodeURIComponent(query)}`,
      );

      renderSuggestions(response.data?.items || []);
    } catch (error) {
      console.error(error);
      studentSearchResults.replaceChildren();
      const unavailable = document.createElement("p");
      unavailable.className = "manual-student-search-empty";
      unavailable.textContent = "Student search is unavailable. Try again.";
      studentSearchResults.appendChild(unavailable);
      studentSearchResults.hidden = false;
    }
  });

  studentSearchInput.addEventListener("keydown", (event) => {
    const options = Array.from(
      studentSearchResults.querySelectorAll(".manual-student-search-result"),
    );
    if (!options.length) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      activeSuggestionIndex =
        event.key === "ArrowDown"
          ? Math.min(activeSuggestionIndex + 1, options.length - 1)
          : Math.max(activeSuggestionIndex - 1, 0);
      options.forEach((option, index) => {
        option.classList.toggle("is-active", index === activeSuggestionIndex);
      });
      options[activeSuggestionIndex]?.focus();
    } else if (event.key === "Enter" && activeSuggestionIndex >= 0) {
      event.preventDefault();
      options[activeSuggestionIndex]?.click();
    } else if (event.key === "Escape") {
      closeSuggestions();
    }
  });

  studentSearchResults.addEventListener("keydown", (event) => {
    const options = Array.from(
      studentSearchResults.querySelectorAll(".manual-student-search-result"),
    );
    const currentIndex = options.indexOf(document.activeElement);
    if (event.key === "ArrowDown" && currentIndex >= 0) {
      event.preventDefault();
      options[Math.min(currentIndex + 1, options.length - 1)]?.focus();
    } else if (event.key === "ArrowUp" && currentIndex >= 0) {
      event.preventDefault();
      if (currentIndex === 0) studentSearchInput.focus();
      else options[currentIndex - 1]?.focus();
    } else if (event.key === "Enter" && currentIndex >= 0) {
      event.preventDefault();
      options[currentIndex].click();
    } else if (event.key === "Escape") {
      closeSuggestions();
      studentSearchInput.focus();
    }
  });

  const appointmentSourceSelect = container.querySelector(
    "#manual-appointment-source",
  );

  appointmentSourceSelect.value = "Walk-in";

  const appointmentDateInput = container.querySelector(
    "#manual-appointment-date",
  );
  const appointmentTimeInput = container.querySelector(
    "#manual-appointment-time",
  );
  const appointmentModeSelect = container.querySelector(
    "#manual-appointment-mode",
  );
  const appointmentCategorySelect = container.querySelector(
    "#manual-appointment-category",
  );
  const appointmentReasonInput = container.querySelector(
    "#manual-appointment-reason",
  );
  renderManualAppointmentOptions(container);
  appointmentDateInput.disabled = true;

  appointmentDateInput.addEventListener("change", async () => {
    if (!selectedStudent || !appointmentDateInput.value) {
      populateManualSlotSelect(
        appointmentTimeInput,
        [],
        "Select a student and date first",
        true,
      );
      return;
    }
    populateManualSlotSelect(
      appointmentTimeInput,
      [],
      "Loading available time slots...",
      true,
    );
    try {
      const options = await refreshAppointmentBookingOptions(
        appointmentDateInput.value,
        selectedStudent.student_number,
      );
      const slots = options.availableSlots || [];
      populateManualSlotSelect(
        appointmentTimeInput,
        slots,
        slots.length
          ? "Select an available time slot"
          : "No available time slots for the selected date.",
        !slots.length,
      );
    } catch (error) {
      populateManualSlotSelect(
        appointmentTimeInput,
        [],
        "Unable to load available time slots",
        true,
      );
      createToast(
        error.message || "Unable to load available time slots.",
        "info",
      );
    }
  });

  container
    .querySelector("#create-manual-appointment-btn")
    ?.addEventListener("click", () => {
      if (!bookingOptionsAreAvailable(appointmentBookingOptions)) {
        createToast("Appointment configuration is unavailable.", "info");
        return;
      }
      if (!selectedStudent) {
        createToast(
          "Select an existing student account before continuing.",
          "info",
        );
        studentSearchInput.focus();
        return;
      }

      const detailsSection = container.querySelector(
        "#manual-appointment-details",
      );
      if (detailsSection) {
        detailsSection.hidden = false;
        studentSearchInput.disabled = true;
        appointmentSourceSelect.disabled = true;
        detailsSection.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });

  container
    .querySelector("#save-manual-appointment-btn")
    ?.addEventListener("click", async () => {
      let currentOptions;
      try {
        currentOptions = await refreshAppointmentBookingOptions(
          appointmentDateInput.value,
          selectedStudent.student_number,
        );
      } catch (error) {
        createToast("Unable to load current appointment options.", "info");
        return;
      }
      if (!bookingOptionsAreAvailable(currentOptions)) {
        renderManualAppointmentOptions(container);
        createToast("Appointment configuration is unavailable.", "info");
        return;
      }
      if (!appointmentDateInput.value) {
        createToast("Please select an appointment date.", "info");
        appointmentDateInput.focus();
        return;
      }

      if (!appointmentTimeInput.value) {
        createToast("Please select an appointment time.", "info");
        appointmentTimeInput.focus();
        return;
      }

      if (
        !isManualBookingSelectionAvailable(
          appointmentDateInput.value,
          appointmentTimeInput.value,
          currentOptions,
        )
      ) {
        createToast(
          "Select a date and time within the current appointment availability.",
          "info",
        );
        return;
      }

      if (
        !currentOptions.appointmentCategories.includes(
          appointmentCategorySelect.value,
        ) ||
        !currentOptions.consultationModes.includes(appointmentModeSelect.value)
      ) {
        renderManualAppointmentOptions(container);
        createToast(
          "Appointment options changed. Select the current options.",
          "info",
        );
        return;
      }

      if (!appointmentReasonInput.value.trim()) {
        createToast("Please enter the appointment reason.", "info");
        appointmentReasonInput.focus();
        return;
      }

      const payload = {
        student_number: selectedStudent.student_number,
        appointment_source: appointmentSourceSelect.value
          .toLowerCase()
          .replace("-", "_")
          .replace(/\s+/g, "_"),
        preferred_date: appointmentDateInput.value,
        preferred_time_slot: appointmentTimeInput.value,
        appointment_mode: appointmentModeSelect.value,
        appointment_category: appointmentCategorySelect.value,
        reason: appointmentReasonInput.value.trim(),
      };

      const saveButton = container.querySelector(
        "#save-manual-appointment-btn",
      );
      saveButton.disabled = true;
      try {
        await fetchJson(`${API_BASE}/api/appointments/manual`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        });

        createToast("Manual appointment created successfully.", "success");

        await loadBackendData();
      } catch (error) {
        console.error(error);
        createToast(
          error.message || "Unable to create manual appointment.",
          "info",
        );
      } finally {
        saveButton.disabled = false;
      }
    });
}

function createPendingAppointmentCard(appointment) {
  const card = document.createElement("div");
  card.className = "appointment-card";
  const text = getAppointmentCardText(appointment);
  card.innerHTML = `
    <div class="appointment-card-header">
      <div>
        <h4>${text.student}</h4>
        <p class="sub">${text.studentNumber}</p>
      </div>
      ${badgeHTML(appointment.status)}
    </div>
    <div class="appointment-card-body">
      <div class="appointment-meta-grid">
        <div><span>Date</span><strong>${text.date}</strong></div>
        <div><span>Time</span><strong>${text.time}</strong></div>
        <div><span>Mode</span><strong>${text.mode}</strong></div>
        <div><span>Source</span><strong>${text.source}</strong></div>
      </div>
      <p><strong>${text.category}</strong></p>
    </div>
    <div class="appointment-card-footer">
      <button class="btn btn-outline appointment-view-btn">
        View Details
      </button>
      <button
          class="btn btn-primary appointment-confirm-btn"
      >
          Confirm
      </button>
      <button
          class="btn btn-outline appointment-cancel-btn"
      >
          Cancel
      </button>
    </div>
  `;
  const confirmButton = card.querySelector(".appointment-confirm-btn");
  const cancelButton = card.querySelector(".appointment-cancel-btn");
  const viewButton = card.querySelector(".appointment-view-btn");
  viewButton?.addEventListener("click", () => {
    openAppointmentDetails(appointment);
  });
  confirmButton?.addEventListener("click", () => {
    openAppointmentDetails(appointment);
  });
  cancelButton?.addEventListener("click", () => {
    openAppointmentDetails(appointment);
  });
  return card;
}

function createTodaysAppointmentCard(appointment) {
  const card = document.createElement("div");
  card.className = "appointment-card";
  const text = getAppointmentCardText(appointment);
  card.innerHTML = `
    <div class="appointment-card-header">
      <div>
        <h4>${text.student}</h4>
        <p class="sub">${text.studentNumber}</p>
      </div>
      ${badgeHTML(appointment.status)}
    </div>
    <div class="appointment-card-body">
      <div class="appointment-meta-grid">
        <div><span>Date</span><strong>${text.date}</strong></div>
        <div><span>Time</span><strong>${text.time}</strong></div>
        <div><span>Mode</span><strong>${text.mode}</strong></div>
        <div><span>Source</span><strong>${text.source}</strong></div>
      </div>
      <p><strong>${text.category}</strong></p>
    </div>
    <div class="appointment-card-footer">
      <button class="btn btn-outline appointment-view-btn">
        View Details
      </button>
      <button
        class="btn btn-primary appointment-complete-btn"
      >
        Complete
      </button>
      <button
        class="btn btn-outline appointment-cancel-btn"
      >
        Cancel
      </button>
    </div>
  `;
  const completeButton = card.querySelector(".appointment-complete-btn");
  const cancelButton = card.querySelector(".appointment-cancel-btn");
  const viewButton = card.querySelector(".appointment-view-btn");
  viewButton?.addEventListener("click", () => {
    openAppointmentDetails(appointment);
  });
  completeButton?.addEventListener("click", () => {
    openAppointmentDetails(appointment);
  });
  cancelButton?.addEventListener("click", () => {
    openAppointmentDetails(appointment);
  });
  return card;
}

function createAppointmentHistoryCard(appointment) {
  const card = document.createElement("div");
  card.className = "appointment-card";
  const text = getAppointmentCardText(appointment);
  card.innerHTML = `
    <div class="appointment-card-header">
      <div>
        <h4>${text.student}</h4>
        <p class="sub">${text.studentNumber}</p>
      </div>
      ${badgeHTML(appointment.status)}
    </div>
    <div class="appointment-card-body">
      <div class="appointment-meta-grid">
        <div><span>Date</span><strong>${text.date}</strong></div>
        <div><span>Time</span><strong>${text.time}</strong></div>
        <div><span>Mode</span><strong>${text.mode}</strong></div>
        <div><span>Source</span><strong>${text.source}</strong></div>
      </div>
      <p><strong>${text.category}</strong></p>
    </div>
    <div class="appointment-card-footer">
      <button class="btn btn-outline appointment-view-btn">
        View Details
      </button>
    </div>
  `;
  const viewButton = card.querySelector(".appointment-view-btn");
  viewButton?.addEventListener("click", () => {
    openAppointmentDetails(appointment);
  });
  return card;
}

async function updateAppointment(appointment, updates) {
  await fetchJson(`${API_BASE}/api/appointments/${appointment.id}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(updates),
  });

  Object.assign(appointment, updates);

  await loadBackendData();
}

async function updateCounselorNotes(appointment, counselorNotes) {
  await fetchJson(`${API_BASE}/api/appointments/${appointment.id}/notes`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ counselor_notes: counselorNotes }),
  });

  appointment.counselorNotes = counselorNotes;
}

function createFlaggedAppointmentCaseCard(summary) {
  const card = document.createElement("div");

  card.className = "appointment-card";

  card.innerHTML = `
    <div class="appointment-card-header">
      <h4>${escapeHtml(summary.studentName || "Authorized student")}</h4>
      <p class="sub">${escapeHtml(summary.studentNumber || "—")}</p>
    </div>

    <div class="appointment-card-body">
      <p><strong>${escapeHtml(summary.category)}</strong></p>

      <p>
        Emotion:
        ${escapeHtml(capitalize(summary.emotion))}
      </p>

      <p>
        Recommendation:
        ${escapeHtml(summary.summary || "No AI summary preview available.")}
      </p>

      <p>
        Status:
        ${badgeHTML(summary.status)}
      </p>
    </div>

    <div class="appointment-card-footer">
      <button
        class="btn btn-primary view-case-btn"
      >
        View Case
      </button>
    </div>
  `;

  const viewButton = card.querySelector(".view-case-btn");

  viewButton?.addEventListener("click", () => {
    void openInboxItem(summary);
  });

  return card;
}

const AVAILABILITY_DAY_OPTIONS = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
  "Monday to Friday",
  "Monday to Saturday",
];

function setSettingsStatus(message, type = "") {
  const status = document.getElementById("settings-status");
  if (!status) return;
  status.textContent = message || "";
  status.hidden = !message;
  status.classList.remove("error", "success");
  if (type) status.classList.add(type);
}

function setCounselorProfileStatus(message, type = "") {
  const status = document.getElementById("counselor-profile-status");
  if (!status) return;
  status.textContent = message || "";
  status.hidden = !message;
  status.classList.remove("error", "success");
  if (type) status.classList.add(type);
}

function setFaqStatus(message, type = "") {
  const status = document.getElementById("faq-status");
  if (!status) return;
  status.textContent = message || "";
  status.hidden = !message;
  status.classList.remove("error", "success");
  if (type) status.classList.add(type);
}

function canonicalTimeToInputValue(value) {
  const match = String(value || "")
    .trim()
    .match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/i);
  if (!match) return "";

  const inputHour = Number(match[1]);
  const minute = Number(match[2]);
  if (inputHour < 1 || inputHour > 12 || minute > 59) return "";

  const hour = (inputHour % 12) + (match[3].toUpperCase() === "PM" ? 12 : 0);
  return `${String(hour).padStart(2, "0")}:${match[2]}`;
}

function inputTimeToCanonical(value) {
  const match = String(value || "")
    .trim()
    .match(/^(\d{2}):(\d{2})$/);
  if (!match) return "";

  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour > 23 || minute > 59) return "";

  const meridiem = hour >= 12 ? "PM" : "AM";
  const twelveHour = hour % 12 || 12;
  return `${String(twelveHour).padStart(2, "0")}:${match[2]} ${meridiem}`;
}

function availabilityWindowTimeValues(value) {
  const [start = "", end = ""] = String(value || "").split(" - ");
  return {
    startTime: canonicalTimeToInputValue(start),
    endTime: canonicalTimeToInputValue(end),
  };
}

function createAvailabilityField(labelText, control) {
  const field = document.createElement("div");
  const label = document.createElement("label");

  field.className = "availability-field";
  label.textContent = labelText;
  field.append(label, control);
  return field;
}

function createUnavailableDate(value = "") {
  const row = document.createElement("div");
  const input = document.createElement("input");
  const remove = document.createElement("button");

  row.className = "appointment-unavailable-date";
  input.type = "date";
  input.className = "form-control";
  input.value = value;
  input.setAttribute("aria-label", "Unavailable appointment date");
  remove.type = "button";
  remove.className = "btn btn-outline btn-sm";
  remove.dataset.removeUnavailableDate = "true";
  remove.textContent = "Remove";
  row.append(input, remove);
  return row;
}

function counselorRooms() {
  return String(document.getElementById("counselor-profile-rooms")?.value || "")
    .split(",")
    .map((room) => room.trim())
    .filter(Boolean);
}

function createCounselorScheduleRow(schedule = {}) {
  const row = document.createElement("div");
  const room = document.createElement("select");
  const day = document.createElement("select");
  const start = document.createElement("input");
  const end = document.createElement("input");
  const remove = document.createElement("button");
  const { startTime, endTime } = availabilityWindowTimeValues(schedule.time);

  row.className = "counselor-schedule-row";
  room.dataset.counselorScheduleRoom = "true";
  day.dataset.counselorScheduleDay = "true";
  start.dataset.counselorScheduleStart = "true";
  end.dataset.counselorScheduleEnd = "true";
  ["", ...counselorRooms()].forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value || "Select room";
    option.selected = value === (schedule.room || "");
    room.appendChild(option);
  });
  AVAILABILITY_DAY_OPTIONS.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    option.selected = value === (schedule.days || "Monday");
    day.appendChild(option);
  });
  start.type = "time";
  start.value = startTime;
  end.type = "time";
  end.value = endTime;
  remove.type = "button";
  remove.className = "btn btn-outline btn-sm";
  remove.textContent = "Remove";
  remove.addEventListener("click", () => {
    row.remove();
    updateCounselorProfileSaveButton();
  });

  row.append(
    createAvailabilityField("Room", room),
    createAvailabilityField("Days", day),
    createAvailabilityField("Start", start),
    createAvailabilityField("End", end),
    remove,
  );
  return row;
}

function renderCounselorProfile(profile) {
  const rooms = document.getElementById("counselor-profile-rooms");
  const office = document.getElementById("counselor-profile-office");
  const support = document.getElementById("counselor-profile-support");
  const schedules = document.getElementById("counselor-schedule-list");
  const appointmentSlots = document.getElementById(
    "counselor-profile-appointment-slots",
  );
  const consultationModes = document.getElementById(
    "counselor-profile-consultation-modes",
  );
  if (
    !rooms ||
    !office ||
    !support ||
    !schedules ||
    !appointmentSlots ||
    !consultationModes
  )
    return;
  rooms.value = (profile.consultation_rooms || []).join(", ");
  office.value = profile.office || "";
  support.value = profile.support_statement || "";
  appointmentSlots.value = (profile.appointment_slots || []).join("\n");
  consultationModes.value = (profile.consultation_modes || []).join("\n");
  schedules.replaceChildren();
  (profile.consultation_schedules || []).forEach((schedule) => {
    schedules.appendChild(createCounselorScheduleRow(schedule));
  });
  counselorProfileBaseline = getCounselorProfileState();
  updateCounselorProfileSaveButton();
}

function collectCounselorSchedules() {
  const schedules = [];
  for (const row of document.querySelectorAll(".counselor-schedule-row")) {
    const room =
      row.querySelector("[data-counselor-schedule-room]")?.value || "";
    const days =
      row.querySelector("[data-counselor-schedule-day]")?.value || "";
    const start =
      row.querySelector("[data-counselor-schedule-start]")?.value || "";
    const end = row.querySelector("[data-counselor-schedule-end]")?.value || "";
    if (!room || !days || !start || !end || start >= end) {
      throw new Error(
        "Each consultation schedule needs a room, day, and valid start/end time.",
      );
    }
    schedules.push({
      room,
      days,
      time: `${inputTimeToCanonical(start)} - ${inputTimeToCanonical(end)}`,
    });
  }
  return schedules;
}

function getCounselorProfileState() {
  const schedules = Array.from(
    document.querySelectorAll(".counselor-schedule-row"),
    (row) => ({
      room: row.querySelector("[data-counselor-schedule-room]")?.value || "",
      days: row.querySelector("[data-counselor-schedule-day]")?.value || "",
      start: row.querySelector("[data-counselor-schedule-start]")?.value || "",
      end: row.querySelector("[data-counselor-schedule-end]")?.value || "",
    }),
  );
  return JSON.stringify({
    office: document.getElementById("counselor-profile-office")?.value || "",
    rooms: document.getElementById("counselor-profile-rooms")?.value || "",
    support: document.getElementById("counselor-profile-support")?.value || "",
    appointmentSlots:
      document.getElementById("counselor-profile-appointment-slots")?.value ||
      "",
    consultationModes:
      document.getElementById("counselor-profile-consultation-modes")?.value ||
      "",
    schedules,
  });
}

function counselorProfileHasChanges() {
  return (
    Boolean(counselorProfileBaseline) &&
    getCounselorProfileState() !== counselorProfileBaseline
  );
}

function updateCounselorProfileSaveButton() {
  setSaveButtonState(
    document.getElementById("save-counselor-profile"),
    counselorProfileHasChanges(),
  );
}

async function loadCounselorProfile() {
  const response = await fetchJson(`${API_BASE}/api/accounts/staff/profile`);
  renderCounselorProfile(response.data || {});
}

function bindCounselorProfile() {
  const panel = document.querySelector(".counselor-profile-panel");
  panel?.addEventListener("input", updateCounselorProfileSaveButton);
  panel?.addEventListener("change", updateCounselorProfileSaveButton);
  document
    .getElementById("add-counselor-schedule")
    ?.addEventListener("click", () => {
      document
        .getElementById("counselor-schedule-list")
        ?.appendChild(createCounselorScheduleRow());
      updateCounselorProfileSaveButton();
    });
  document
    .getElementById("counselor-profile-rooms")
    ?.addEventListener("change", () => {
      const list = document.getElementById("counselor-schedule-list");
      const existing = Array.from(list?.children || [], (row) => ({
        room: row.querySelector("[data-counselor-schedule-room]")?.value || "",
        days: row.querySelector("[data-counselor-schedule-day]")?.value || "",
        time: `${inputTimeToCanonical(row.querySelector("[data-counselor-schedule-start]")?.value || "")} - ${inputTimeToCanonical(row.querySelector("[data-counselor-schedule-end]")?.value || "")}`,
      }));
      list?.replaceChildren(...existing.map(createCounselorScheduleRow));
      updateCounselorProfileSaveButton();
    });
  document
    .getElementById("save-counselor-profile")
    ?.addEventListener("click", async () => {
      try {
        if (!counselorProfileHasChanges()) return;
        const consultationSchedules = collectCounselorSchedules();
        if (!window.confirm("Save changes to your counselor profile?")) return;

        const saveButton = document.getElementById("save-counselor-profile");
        saveButton.disabled = true;
        setCounselorProfileStatus("Saving counselor profile...");
        const response = await fetchJson(
          `${API_BASE}/api/accounts/staff/profile`,
          {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              office:
                document.getElementById("counselor-profile-office")?.value ||
                "",
              support_statement:
                document.getElementById("counselor-profile-support")?.value ||
                "",
              consultation_rooms: counselorRooms(),
              consultation_schedules: consultationSchedules,
              appointment_slots: settingsChoices(
                "counselor-profile-appointment-slots",
              ),
              consultation_modes: settingsChoices(
                "counselor-profile-consultation-modes",
              ),
            }),
          },
        );
        renderCounselorProfile(response.data || {});
        setCounselorProfileStatus("Counselor profile saved.", "success");
      } catch (error) {
        setCounselorProfileStatus(
          error.message || "Unable to save counselor profile.",
          "error",
        );
        updateCounselorProfileSaveButton();
      }
    });
}

function renderGlobalBookingConfiguration(availability) {
  const unavailableDates = document.getElementById(
    "appointment-unavailable-dates",
  );
  if (!unavailableDates) return;

  unavailableDates.replaceChildren();
  const excludedDates = new Set([
    ...(availability?.holidays || []),
    ...(availability?.academicCalendarExclusions || []),
    ...(availability?.unavailableDates || []),
  ]);
  [...excludedDates].sort().forEach((value) => {
    unavailableDates.appendChild(createUnavailableDate(value));
  });
}

function settingsChoices(id) {
  return String(document.getElementById(id)?.value || "")
    .split("\n")
    .map((value) => value.trim())
    .filter(Boolean);
}

function controlState(control) {
  return {
    id: control.id,
    value: control.type === "checkbox" ? control.checked : control.value,
  };
}

function getSettingsFormState() {
  const controls = document.querySelectorAll(
    [
      "#settings-office-name",
      "#settings-office-hours",
      "#settings-office-email",
      "#settings-contact-number",
      "#settings-office-location",
      "#settings-booking-enabled",
      "#settings-appointment-categories",
      "#appointment-unavailable-dates input",
    ].join(", "),
  );
  return JSON.stringify(Array.from(controls, controlState));
}

function setSaveButtonState(button, hasChanges) {
  if (!button) return;
  button.disabled = !hasChanges;
  button.setAttribute("aria-disabled", String(!hasChanges));
}

function settingsHaveChanges() {
  return (
    Boolean(settingsBaseline) && getSettingsFormState() !== settingsBaseline
  );
}

function updateSettingsSaveButtons() {
  const hasChanges = settingsHaveChanges();
  setSaveButtonState(document.getElementById("save-settings-btn"), hasChanges);
}

function setPasswordStatus(message, type = "error") {
  const status = document.getElementById("password-status");
  if (!status) return;
  status.textContent = message || "";
  status.className = `settings-status ${type}`;
  status.hidden = !message;
}

function updatePasswordButton() {
  const currentPassword =
    document.getElementById("current-password")?.value || "";
  const newPassword = document.getElementById("new-password")?.value || "";
  const confirmPassword =
    document.getElementById("confirm-password")?.value || "";
  const button = document.getElementById("change-password-btn");
  const passwordsMatch = newPassword === confirmPassword;
  const hasValidInput = Boolean(
    currentPassword &&
    newPassword.length >= 8 &&
    confirmPassword &&
    passwordsMatch,
  );

  setSaveButtonState(button, hasValidInput);
  if (confirmPassword && !passwordsMatch) {
    setPasswordStatus("New passwords do not match.");
  } else if (newPassword && newPassword.length < 8) {
    setPasswordStatus("New password must be at least 8 characters long.");
  } else {
    setPasswordStatus("");
  }
}

function bindPasswordChange() {
  const button = document.getElementById("change-password-btn");
  const inputs = ["current-password", "new-password", "confirm-password"].map(
    (id) => document.getElementById(id),
  );
  inputs.forEach((input) =>
    input?.addEventListener("input", updatePasswordButton),
  );

  button?.addEventListener("click", async () => {
    const currentPassword =
      document.getElementById("current-password")?.value || "";
    const newPassword = document.getElementById("new-password")?.value || "";
    const confirmPassword =
      document.getElementById("confirm-password")?.value || "";
    if (button.disabled) return;

    button.disabled = true;
    let passwordUpdated = false;
    try {
      await fetchJson(`${API_BASE}/api/accounts/staff/password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
          confirm_password: confirmPassword,
        }),
      });
      inputs.forEach((input) => {
        if (input) input.value = "";
      });
      passwordUpdated = true;
    } catch (error) {
      setPasswordStatus(error.message || "Unable to update password.");
    } finally {
      updatePasswordButton();
      if (passwordUpdated) {
        setPasswordStatus("Password updated successfully.", "success");
      }
    }
  });

  updatePasswordButton();
}

function getSettingsSnapshot() {
  const unavailableDates = Array.from(
    document.querySelectorAll(".appointment-unavailable-date input"),
    (input) => input.value,
  ).filter(Boolean);

  return {
    officeName: document.getElementById("settings-office-name")?.value || "",
    officeHours: document.getElementById("settings-office-hours")?.value || "",
    officeEmail: document.getElementById("settings-office-email")?.value || "",
    contactNumber:
      document.getElementById("settings-contact-number")?.value || "",
    officeLocation:
      document.getElementById("settings-office-location")?.value || "",
    appointmentAvailability: {
      // Kept only for compatible historic records. Counselor consultation
      // schedules determine actual appointment availability.
      officeAvailability: Array.isArray(
        persistedSettings?.appointmentAvailability?.officeAvailability,
      )
        ? persistedSettings.appointmentAvailability.officeAvailability
        : [],
      appointmentSlots: Array.isArray(
        persistedSettings?.appointmentAvailability?.appointmentSlots,
      )
        ? persistedSettings.appointmentAvailability.appointmentSlots
        : [],
      consultationModes: Array.isArray(
        persistedSettings?.appointmentAvailability?.consultationModes,
      )
        ? persistedSettings.appointmentAvailability.consultationModes
        : [],
      bookingEnabled: Boolean(
        document.getElementById("settings-booking-enabled")?.checked,
      ),
      holidays: [],
      academicCalendarExclusions: [],
      unavailableDates,
      appointmentCategories: settingsChoices("settings-appointment-categories"),
    },
  };
}

function renderPersistedSettings(settings) {
  persistedSettings = settings || null;
  const availability = settings?.appointmentAvailability || null;
  const fields = {
    "settings-office-name": settings?.officeName || "",
    "settings-office-hours": settings?.officeHours || "",
    "settings-office-email": settings?.officeEmail || "",
    "settings-contact-number": settings?.contactNumber || "",
    "settings-office-location": settings?.officeLocation || "",
    "settings-appointment-categories": (
      availability?.appointmentCategories || []
    ).join("\n"),
  };
  Object.entries(fields).forEach(([id, value]) => {
    const input = document.getElementById(id);
    if (input) input.value = value;
  });
  const bookingEnabled = document.getElementById("settings-booking-enabled");
  if (bookingEnabled)
    bookingEnabled.checked = Boolean(availability?.bookingEnabled);
  renderGlobalBookingConfiguration(availability);
  const configurationState = settings?.appointmentConfigurationState;
  setSettingsStatus(
    configurationState === "configured"
      ? "Persisted settings loaded."
      : configurationState === "booking_disabled"
        ? "Appointment booking is disabled. Incomplete booking configuration is preserved but unavailable to students and manual entry."
        : "Appointment configuration is unconfigured. Booking is unavailable until it is saved with availability, categories, and modes.",
    configurationState === "configured" ||
      configurationState === "booking_disabled"
      ? "success"
      : "error",
  );
  settingsBaseline = getSettingsFormState();
  updateSettingsSaveButtons();
}

async function loadPersistedSettings() {
  const response = await fetchJson(`${API_BASE}/api/settings`);
  renderPersistedSettings(response.data);
}

function createFaqField(labelText, id, control) {
  const field = document.createElement("div");
  const label = document.createElement("label");
  field.className = "field-group";
  label.htmlFor = id;
  label.textContent = labelText;
  control.id = id;
  field.append(label, control);
  return field;
}

function createFaqEditorCard(faq) {
  const card = document.createElement("article");
  const header = document.createElement("div");
  const heading = document.createElement("h4");
  const activeLabel = document.createElement("label");
  const active = document.createElement("input");
  const title = document.createElement("input");
  const question = document.createElement("input");
  const answer = document.createElement("textarea");
  const actions = document.createElement("div");
  const save = document.createElement("button");
  const remove = document.createElement("button");

  card.className = "faq-editor-card";
  header.className = "faq-editor-card-header";
  heading.textContent = faq.title || "FAQ";
  active.type = "checkbox";
  active.checked = Boolean(faq.active);
  active.id = `faq-active-${faq.id}`;
  activeLabel.className = "faq-active-toggle";
  activeLabel.htmlFor = active.id;
  activeLabel.append(active, document.createTextNode("Active"));
  header.append(heading, activeLabel);

  title.type = "text";
  title.value = faq.title || "";
  question.type = "text";
  question.value = faq.question || "";
  answer.rows = 4;
  answer.value = faq.answer || "";

  const initialState = () =>
    JSON.stringify({
      title: title.value,
      question: question.value,
      answer: answer.value,
      active: active.checked,
    });
  const savedState = initialState();
  const updateSaveState = () => {
    setSaveButtonState(save, initialState() !== savedState);
  };

  actions.className = "faq-editor-card-actions";
  save.type = "button";
  save.className = "btn btn-primary btn-sm";
  save.textContent = "Save FAQ";
  remove.type = "button";
  remove.className = "btn btn-outline btn-sm";
  remove.textContent = "Remove";
  actions.append(save, remove);
  card.append(
    header,
    createFaqField("Title", `faq-title-${faq.id}`, title),
    createFaqField("Question", `faq-question-${faq.id}`, question),
    createFaqField("Answer", `faq-answer-${faq.id}`, answer),
    actions,
  );

  [title, question, answer, active].forEach((control) => {
    control.addEventListener("input", updateSaveState);
    control.addEventListener("change", updateSaveState);
  });
  updateSaveState();

  save.addEventListener("click", async () => {
    if (save.disabled) return;
    if (!window.confirm("Save changes to this FAQ?")) return;
    save.disabled = true;
    setFaqStatus("Saving FAQ...");
    try {
      await fetchJson(
        `${API_BASE}/api/settings/faqs/${encodeURIComponent(faq.id)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: title.value,
            question: question.value,
            answer: answer.value,
            active: active.checked,
          }),
        },
      );
      await loadFaqs();
      setFaqStatus("FAQ saved.", "success");
    } catch (error) {
      setFaqStatus(error.message || "Unable to save FAQ.", "error");
    } finally {
      save.disabled = false;
    }
  });

  remove.addEventListener("click", async () => {
    if (!window.confirm("Remove this FAQ?")) return;
    remove.disabled = true;
    setFaqStatus("Removing FAQ...");
    try {
      await fetchJson(
        `${API_BASE}/api/settings/faqs/${encodeURIComponent(faq.id)}`,
        {
          method: "DELETE",
        },
      );
      await loadFaqs();
      setFaqStatus("FAQ removed.", "success");
    } catch (error) {
      setFaqStatus(error.message || "Unable to remove FAQ.", "error");
      remove.disabled = false;
    }
  });
  return card;
}

function renderFaqs(items) {
  const list = document.getElementById("faq-list");
  if (!list) return;
  list.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "settings-status";
    empty.textContent = "No persisted FAQs are available.";
    list.appendChild(empty);
    return;
  }
  items.forEach((faq) => list.appendChild(createFaqEditorCard(faq)));
}

async function loadFaqs() {
  setFaqStatus("Loading FAQs...");
  const response = await fetchJson(`${API_BASE}/api/settings/faqs`);
  persistedFaqs = Array.isArray(response.data?.items)
    ? response.data.items
    : [];
  renderFaqs(persistedFaqs);
  setFaqStatus("");
}

function updateAddFaqButton() {
  const title = document.getElementById("new-faq-title")?.value.trim();
  const question = document.getElementById("new-faq-question")?.value.trim();
  const answer = document.getElementById("new-faq-answer")?.value.trim();
  setSaveButtonState(
    document.getElementById("add-faq-btn"),
    Boolean(title && question && answer),
  );
}

async function saveSettingsToApi() {
  setSettingsStatus("Saving settings...");
  try {
    const response = await fetchJson(`${API_BASE}/api/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(getSettingsSnapshot()),
    });
    await loadPersistedSettings();
    setSettingsStatus(response.message || "Settings saved.", "success");
    createToast("Settings saved", "success");
    return true;
  } catch (error) {
    setSettingsStatus(error.message || "Unable to save settings.", "error");
    return false;
  }
}

function bindSettingsInteractions() {
  const root = document.getElementById("view-settings");
  if (!root) return;

  root.addEventListener("click", (event) => {
    if (event.target.closest("#add-unavailable-date-btn")) {
      document
        .getElementById("appointment-unavailable-dates")
        ?.appendChild(createUnavailableDate());
    }
    event.target
      .closest("[data-remove-unavailable-date]")
      ?.parentElement?.remove();
    updateSettingsSaveButtons();
  });
  root.addEventListener("input", updateSettingsSaveButtons);
  root.addEventListener("change", updateSettingsSaveButtons);
}

function bindInboxControls() {
  document
    .getElementById("inbox-search-input")
    ?.addEventListener("input", () => {
      resetDashboardTablePage("inbox-tbody");
      renderInquiryTable();
    });
  document.getElementById("inbox-filter")?.addEventListener("change", () => {
    resetDashboardTablePage("inbox-tbody");
    renderInquiryTable();
  });
  bindTableSortControls(
    "inbox-table",
    inboxSort,
    renderInquiryTable,
    "inbox-tbody",
  );
  document.getElementById("inbox-retry")?.addEventListener("click", () => {
    void loadBackendData();
  });
}

function bindFeedbackControls() {
  document.getElementById("feedback-filter")?.addEventListener("change", () => {
    resetDashboardTablePage("feedback-tbody");
    renderChatbotFeedback();
  });
  document
    .getElementById("feedback-context-filter")
    ?.addEventListener("change", () => {
      resetDashboardTablePage("feedback-tbody");
      renderChatbotFeedback();
    });
  document
    .getElementById("feedback-search-input")
    ?.addEventListener("input", () => {
      resetDashboardTablePage("feedback-tbody");
      renderChatbotFeedback();
    });
  bindTableSortControls(
    "feedback-table",
    feedbackSort,
    renderChatbotFeedback,
    "feedback-tbody",
  );
  document.getElementById("feedback-retry")?.addEventListener("click", () => {
    void loadBackendData();
  });
}

function bindFlaggedControls() {
  document.getElementById("flagged-filter")?.addEventListener("change", () => {
    resetDashboardTablePage("flagged-tbody");
    renderFlaggedConversations();
  });
  document
    .getElementById("flagged-search-input")
    ?.addEventListener("input", () => {
      resetDashboardTablePage("flagged-tbody");
      renderFlaggedConversations();
    });
  bindTableSortControls(
    "flagged-table",
    flaggedSort,
    renderFlaggedConversations,
    "flagged-tbody",
  );
  document.getElementById("flagged-retry")?.addEventListener("click", () => {
    void loadBackendData();
  });
}

function bindTableSortControls(tableId, sortState, render, paginationId = "") {
  const table = document.getElementById(tableId);
  if (!table) return;
  table.querySelectorAll("[data-sort-key]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.sortKey;
      if (!key) return;
      if (sortState.key === key) {
        sortState.direction = sortState.direction === "asc" ? "desc" : "asc";
      } else {
        sortState.key = key;
        sortState.direction = "asc";
      }
      if (paginationId) resetDashboardTablePage(paginationId);
      render();
    });
  });
  syncTableSortHeaders(tableId, sortState);
}

function syncTableSortHeaders(tableId, sortState) {
  const table = document.getElementById(tableId);
  if (!table) return;
  table.querySelectorAll("[data-sort-key]").forEach((button) => {
    const isActive = button.dataset.sortKey === sortState.key;
    const direction = isActive ? sortState.direction : "none";
    button.classList.toggle("active", isActive);
    button
      .closest("th")
      ?.setAttribute(
        "aria-sort",
        direction === "none"
          ? "none"
          : direction === "asc"
            ? "ascending"
            : "descending",
      );
    const indicator = button.querySelector(".table-sort-indicator");
    if (indicator)
      indicator.textContent = isActive ? (direction === "asc" ? "↑" : "↓") : "";
  });
}

function bindFaqManagement() {
  const form = document.getElementById("add-faq-form");
  if (!form) return;
  form.addEventListener("input", updateAddFaqButton);
  form.addEventListener("change", updateAddFaqButton);
  updateAddFaqButton();
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const title = document.getElementById("new-faq-title");
    const question = document.getElementById("new-faq-question");
    const answer = document.getElementById("new-faq-answer");
    if (
      !title?.value.trim() ||
      !question?.value.trim() ||
      !answer?.value.trim()
    ) {
      updateAddFaqButton();
      return;
    }
    if (!window.confirm("Add this FAQ?")) return;
    setFaqStatus("Saving FAQ...");
    try {
      await fetchJson(`${API_BASE}/api/settings/faqs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: title?.value || "",
          question: question?.value || "",
          answer: answer?.value || "",
        }),
      });
      form.reset();
      updateAddFaqButton();
      await loadFaqs();
      setFaqStatus("FAQ added.", "success");
    } catch (error) {
      setFaqStatus(error.message || "Unable to add FAQ.", "error");
    }
  });
}

// lightweight toast for feedback
function createToast(message, type = "info", timeout = 3400) {
  let container = document.querySelector(".toast-container");
  if (!container) {
    container = document.createElement("div");
    container.className = "toast-container";
    document.body.appendChild(container);
  }
  const t = document.createElement("div");
  t.className = "toast " + (type || "");
  t.textContent = message;
  container.appendChild(t);
  // auto remove
  setTimeout(() => {
    t.style.animation = "toast-out 300ms forwards";
    setTimeout(() => t.remove(), 350);
  }, timeout);
  return t;
}

// small prompt modal (returns Promise<string|null>)
function showPrompt(title, placeholder = "", multiline = false) {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "prompt-overlay";
    const prompt = document.createElement("div");
    prompt.className = "prompt";
    const h = document.createElement("h4");
    h.textContent = title;
    prompt.appendChild(h);
    const input = document.createElement(multiline ? "textarea" : "input");
    input.placeholder = placeholder || "";
    prompt.appendChild(input);
    const actions = document.createElement("div");
    actions.className = "prompt-actions";
    const cancel = document.createElement("button");
    cancel.className = "btn btn-outline btn-sm";
    cancel.textContent = "Cancel";
    const ok = document.createElement("button");
    ok.className = "btn btn-primary btn-sm";
    ok.textContent = "OK";
    actions.appendChild(cancel);
    actions.appendChild(ok);
    prompt.appendChild(actions);
    overlay.appendChild(prompt);
    document.body.appendChild(overlay);
    input.focus();

    ok.onclick = () => {
      resolve(input.value.trim() || null);
      overlay.remove();
    };
    cancel.onclick = () => {
      resolve(null);
      overlay.remove();
    };
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) {
        resolve(null);
        overlay.remove();
      }
    });
  });
}

const navItems = document.querySelectorAll(".nav-item[data-view]");
const headerTitle = document.getElementById("header-title");
const headerSub = document.getElementById("header-sub");
const headerActions = document.getElementById("header-actions");
const sidebar = document.getElementById("sidebar");
const sidebarToggle = document.getElementById("sidebar-toggle");
const sidebarClose = document.getElementById("sidebar-close");
const sidebarOverlay = document.getElementById("sidebar-overlay");
const dashboardLogout = document.getElementById("dashboard-logout");
const dashboardHome = document.getElementById("dashboard-home");
const currentLocation = window.location.pathname || "";
const compactNavigation = window.matchMedia("(max-width: 900px)");

const viewMeta = {
  inbox: {
    title: "Case Inbox",
    sub: "Active and finalized student conversations awaiting counselor review.",
    actions: "",
  },

  flagged: {
    title: "Flagged Cases",
    sub: "Students with detected negative emotion requiring review",
    actions: "",
  },

  feedback: {
    title: "Chatbot Feedback",
    sub: "Review student ratings in your authorized programs to guide approved chatbot improvements.",
    actions: "",
  },

  appointments: {
    title: "Appointments",
    sub: "Monitor appointment requests, appointment history, and counselor interventions.",
    actions: "",
  },

  "conversation-summaries": {
    title: "Conversation Summaries",
    sub: "Review AI-generated summaries of completed student conversations.",
    actions: "",
  },

  "conversation-summary-details": {
    title: "Conversation Summary",
    sub: "Review AI-generated conversation summary and recommendation.",
    actions:
      '<button class="btn btn-outline" data-dashboard-action="back">Back</button>',
  },

  reports: {
    title: "Reports",
    sub: "Review authorized aggregate analytics and export staff reports.",
    actions: '<div class="report-period-badge">This Month</div>',
  },
  settings: {
    title: "Guidance Office Settings",
    sub: "Manage shared office settings and your individual counseling preferences.",
    actions: "",
  },
  "case-details": {
    title: "Case Details",
    sub: "Review student concern, chatbot classification, and counselor action.",
    actions:
      '<button class="btn btn-outline" data-dashboard-action="back">Back to Dashboard</button>',
  },
  "appointment-details": {
    title: "Appointment Details",
    sub: "Review appointment information, manage its status, and record counselor notes.",
    actions:
      '<button class="btn btn-outline" data-dashboard-action="back">Back to Appointments</button>',
  },
};

let currentView = "inbox";
let prevView = "inbox";
const dashboardSections = {
  appointments: "overview",
  reports: "overview",
  settings: "global",
};
const dashboardViewIds = new Set(
  Array.from(navItems, (item) => item.dataset.view),
);

function updateDashboardLocation(
  viewId,
  sectionId = dashboardSections[viewId],
) {
  const hash = sectionId ? `#${viewId}:${sectionId}` : `#${viewId}`;
  if (window.location.hash !== hash) {
    window.history.pushState(
      { viewId, sectionId: sectionId || null },
      "",
      hash,
    );
  }
}

function restoreDashboardLocation() {
  const [viewId, sectionId] = window.location.hash.slice(1).split(":");
  if (!dashboardViewIds.has(viewId)) {
    switchView("inbox", false);
    return;
  }

  const view = document.getElementById(`view-${viewId}`);
  const hasSection =
    sectionId && view?.querySelector(`[data-dashboard-section="${sectionId}"]`);
  if (hasSection) dashboardSections[viewId] = sectionId;
  switchView(viewId, false);
}

function initials(name) {
  return name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

function capitalize(value) {
  if (!value) return "Unknown";
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function badgeHTML(status) {
  const map = {
    negative: ["negative", "Negative"],
    neutral: ["neutral", "Routine"],
    resolved: ["resolved", "Resolved"],

    pending: ["pending", "Pending"],
    confirmed: ["neutral", "Confirmed"],
    completed: ["resolved", "Completed"],
    cancelled: ["negative", "Cancelled"],
    rejected: ["negative", "Rejected"],
  };
  const [cls, label] = map[status] || ["pending", "Pending"];
  return `<span class="badge ${cls}">${label}</span>`;
}

function updateHeader(viewId) {
  const meta = viewMeta[viewId] || {};
  headerTitle.textContent = meta.title || "";
  headerSub.textContent = meta.sub || "";
  headerActions.innerHTML = meta.actions || "";

  headerActions
    .querySelector('[data-dashboard-action="back"]')
    ?.addEventListener("click", goBack);
  if (viewId === "settings") updateSettingsSaveButtons();

  const backToSettingsBtn = document.getElementById("back-to-settings-btn");
  if (backToSettingsBtn) {
    backToSettingsBtn.addEventListener("click", () => {
      switchView("settings");
    });
  }
}

function switchView(viewId, updateLocation = true) {
  const isSameView = currentView === viewId;
  prevView = currentView;
  currentView = viewId;

  views.forEach((view) => view.classList.remove("active"));
  const activeView = document.getElementById(`view-${viewId}`);
  if (activeView) activeView.classList.add("active");

  navItems.forEach((item) => {
    item.classList.toggle("active", item.dataset.view === viewId);
  });

  updateHeader(viewId);
  if (dashboardSections[viewId]) {
    showDashboardSection(viewId, dashboardSections[viewId], false);
  }
  if (viewId === "reports") {
    void ensureReportsLoaded();
  }
  if (updateLocation && !isSameView) updateDashboardLocation(viewId);
  window.scrollTo(0, 0);
}

function goBack() {
  switchView(prevView === currentView ? "inbox" : prevView);
}

async function saveSettings() {
  if (!settingsHaveChanges()) {
    updateSettingsSaveButtons();
    return false;
  }
  if (!window.confirm("Save changes to Guidance Office settings?"))
    return false;
  return saveSettingsToApi();
}

function showDashboardSection(viewId, sectionId, updateLocation = true) {
  const view = document.getElementById(`view-${viewId}`);
  if (!view || !sectionId) return;

  dashboardSections[viewId] = sectionId;
  view.querySelectorAll("[data-dashboard-section]").forEach((section) => {
    section.hidden = section.dataset.dashboardSection !== sectionId;
  });

  const navigation = document.querySelector(
    `[data-dashboard-section-nav="${viewId}"]`,
  );
  navigation
    ?.querySelectorAll("[data-dashboard-section-target]")
    .forEach((button) => {
      const isActive = button.dataset.dashboardSectionTarget === sectionId;
      button.classList.toggle("active", isActive);
      button.setAttribute("aria-pressed", String(isActive));
    });

  if (updateLocation && currentView === viewId) {
    updateDashboardLocation(viewId, sectionId);
  }
}

function bindDashboardSectionNavigation() {
  document
    .querySelectorAll("[data-dashboard-section-nav]")
    .forEach((navigation) => {
      const viewId = navigation.dataset.dashboardSectionNav;
      navigation
        .querySelectorAll("[data-dashboard-section-target]")
        .forEach((button) => {
          button.addEventListener("click", () => {
            showDashboardSection(viewId, button.dataset.dashboardSectionTarget);
          });
        });
      showDashboardSection(viewId, dashboardSections[viewId]);
    });
}

function setSidebarOpen(open, restoreFocus = false) {
  sidebar.classList.toggle("open", open);
  sidebarOverlay.classList.toggle("open", open);
  sidebarToggle.setAttribute("aria-expanded", String(open));
  document.body.classList.toggle("sidebar-drawer-open", open);

  if (open) {
    sidebarClose?.focus();
  } else if (restoreFocus) {
    sidebarToggle.focus();
  }
}

navItems.forEach((item) => {
  item.addEventListener("click", () => {
    switchView(item.dataset.view);
    if (compactNavigation.matches) {
      setSidebarOpen(false);
    }
  });
});

sidebarToggle.addEventListener("click", () => {
  setSidebarOpen(!sidebar.classList.contains("open"));
});

sidebarOverlay.addEventListener("click", () => {
  setSidebarOpen(false, true);
});

sidebarClose?.addEventListener("click", () => setSidebarOpen(false, true));

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && sidebar.classList.contains("open")) {
    setSidebarOpen(false, true);
  }
});

compactNavigation.addEventListener("change", (event) => {
  if (!event.matches) {
    setSidebarOpen(false);
  }
});

dashboardLogout?.addEventListener("click", logout);
dashboardHome?.addEventListener("click", () => {
  switchView("inbox");
  if (window.location.hash !== "#inbox") {
    updateDashboardLocation("inbox");
  }
  if (compactNavigation.matches) {
    setSidebarOpen(false);
  }
});

function appendTableEmptyState(tbody, columnCount, message) {
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = columnCount;
  cell.className = "table-empty-state";
  cell.textContent = message;
  row.appendChild(cell);
  tbody.appendChild(row);
}

function clearDashboardTablePagination(tbodyId) {
  const tbody = document.getElementById(tbodyId);
  const host = tbody?.closest("table")?.parentElement;
  const pager = host?.querySelector(`[data-table-pagination="${tbodyId}"]`);
  pager?.remove();
  host?.classList.remove("is-paginated");
}

function resetDashboardTablePage(tbodyId) {
  dashboardTablePages.set(tbodyId, 1);
}

function getDashboardTablePageSize(tbodyId) {
  return DASHBOARD_TABLE_PAGE_SIZES[tbodyId] || DASHBOARD_TABLE_PAGE_SIZE;
}

function paginateDashboardRows(tbodyId, rows, render) {
  const tbody = document.getElementById(tbodyId);
  const table = tbody?.closest("table");
  const host = table?.parentElement;
  const total = rows.length;
  const pageSize = getDashboardTablePageSize(tbodyId);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const requestedPage = dashboardTablePages.get(tbodyId) || 1;
  const page = Math.min(Math.max(1, requestedPage), totalPages);
  dashboardTablePages.set(tbodyId, page);

  const existingPager = host?.querySelector(
    `[data-table-pagination="${tbodyId}"]`,
  );
  if (totalPages <= 1 || !host || !table) {
    existingPager?.remove();
    host?.classList.remove("is-paginated");
  } else {
    host.classList.add("is-paginated");
    const pager = existingPager || document.createElement("nav");
    pager.className = "table-pagination";
    pager.dataset.tablePagination = tbodyId;
    pager.setAttribute("aria-label", "Table pagination");
    pager.replaceChildren();

    const previous = document.createElement("button");
    previous.type = "button";
    previous.className = "btn btn-outline btn-sm";
    previous.textContent = "Previous";
    previous.disabled = page === 1;
    previous.addEventListener("click", () => {
      dashboardTablePages.set(tbodyId, page - 1);
      render();
    });

    const summary = document.createElement("span");
    summary.className = "table-pagination-summary";
    const start = (page - 1) * pageSize + 1;
    const end = Math.min(page * pageSize, total);
    summary.textContent = `Showing ${start}–${end} of ${total} · Page ${page} of ${totalPages}`;

    const next = document.createElement("button");
    next.type = "button";
    next.className = "btn btn-outline btn-sm";
    next.textContent = "Next";
    next.disabled = page === totalPages;
    next.addEventListener("click", () => {
      dashboardTablePages.set(tbodyId, page + 1);
      render();
    });

    pager.append(previous, summary, next);
    if (!existingPager) table.after(pager);
  }

  const start = (page - 1) * pageSize;
  return {
    items: rows.slice(start, start + pageSize),
    start: total ? start + 1 : 0,
    end: Math.min(start + pageSize, total),
    total,
  };
}

function formatInboxTimestamp(value) {
  if (!(value instanceof Date) || Number.isNaN(value.getTime())) {
    return "Unavailable";
  }
  return value.toLocaleString();
}

function setInboxState(message, type = "") {
  const state = document.getElementById("inbox-state");
  if (!state) return;
  state.textContent = message || "";
  state.classList.toggle("error", type === "error");
}

function inboxItemsForCurrentFilter() {
  const query = String(
    document.getElementById("inbox-search-input")?.value || "",
  )
    .trim()
    .toLowerCase();
  const filter = document.getElementById("inbox-filter")?.value || "all";

  const items = staffInboxItems.filter((item) => {
    const matchesFilter =
      filter === "all" ||
      (filter === "flagged" && item.flagged) ||
      (filter === "routine" && !item.flagged) ||
      (filter.startsWith("priority-") &&
        item.priority === filter.replace("priority-", "")) ||
      item.status === filter;
    if (!matchesFilter) return false;
    if (!query) return true;
    return [
      item.studentName,
      item.studentNumber,
      item.program,
      item.category,
      item.summary,
    ].some((value) =>
      String(value || "")
        .toLowerCase()
        .includes(query),
    );
  });
  return sortDashboardRecords(items, inboxSort, inboxSortValue);
}

function inboxSortValue(item, key) {
  const values = {
    student: `${item.studentNumber} ${item.studentName}`,
    program: item.program,
    priority: casePriorityRank(item.priority),
    category: item.category,
    summary: item.summary,
    status: item.status,
    createdAt: item.createdAt?.getTime() ?? Number.MAX_SAFE_INTEGER,
  };
  return values[key] ?? "";
}

function casePriorityRank(priority) {
  return (
    {
      critical: 4,
      high: 3,
      medium: 2,
      low: 1,
    }[String(priority || "low").toLowerCase()] || 0
  );
}

function createCasePriorityBadge(priority) {
  const normalized = String(priority || "low").toLowerCase();
  const presentation = {
    critical: { label: "Critical", badgeClass: "negative" },
    high: { label: "High", badgeClass: "pending" },
    medium: { label: "Medium", badgeClass: "pending" },
    low: { label: "Low", badgeClass: "neutral" },
  }[normalized] || { label: "Low", badgeClass: "neutral" };
  const badge = document.createElement("span");
  badge.className = `badge ${presentation.badgeClass}`;
  badge.textContent = presentation.label;
  return badge;
}

function applyCasePriority(detail) {
  const element = document.getElementById("case-priority");
  if (!element) return;
  const badge = createCasePriorityBadge(detail.case_priority);
  element.className = badge.className;
  element.textContent = badge.textContent;
}

function createInboxStatusBadge(item) {
  const badge = document.createElement("span");
  const status = String(item.status || "routine").toLowerCase();
  badge.className = "badge";
  if (status === "pending") {
    badge.classList.add("negative");
    badge.textContent = "Pending review";
  } else if (status === "active") {
    badge.classList.add("pending");
    badge.textContent = "Active";
  } else if (status === "reviewed") {
    badge.classList.add("resolved");
    badge.textContent = "Reviewed";
  } else if (item.flagged) {
    badge.classList.add("negative");
    badge.textContent = "Flagged";
  } else {
    badge.classList.add("neutral");
    badge.textContent = "Routine";
  }
  return badge;
}

function renderInquiryTable() {
  const tbody = document.getElementById("inbox-tbody");
  if (!tbody) return;

  tbody.replaceChildren();
  syncTableSortHeaders("inbox-table", inboxSort);
  if (inboxLoadState === "loading") {
    clearDashboardTablePagination("inbox-tbody");
    appendTableEmptyState(tbody, 8, "Loading current student summary items...");
    return;
  }
  if (inboxLoadState === "error") {
    clearDashboardTablePagination("inbox-tbody");
    appendTableEmptyState(
      tbody,
      8,
      "Inbox items are unavailable. Retry to load persisted summaries.",
    );
    return;
  }

  const items = inboxItemsForCurrentFilter();
  if (!items.length) {
    clearDashboardTablePagination("inbox-tbody");
    appendTableEmptyState(
      tbody,
      8,
      staffInboxItems.length
        ? "No current student summary items match this filter."
        : "No active or finalized student summary items are available yet.",
    );
    return;
  }

  const page = paginateDashboardRows("inbox-tbody", items, renderInquiryTable);
  page.items.forEach((item) => {
    const row = document.createElement("tr");
    row.className = "inbox-record";
    const student = document.createElement("td");
    const studentName = document.createElement("strong");
    const studentNumber = document.createElement("span");
    student.dataset.label = "Student";
    studentName.className = "inbox-student-name";
    studentName.textContent = item.studentName;
    studentNumber.className = "inbox-student-number";
    studentNumber.textContent = item.studentNumber;
    student.append(studentName, studentNumber);
    row.appendChild(student);
    appendTableCell(row, item.program, "Program");
    const priority = document.createElement("td");
    priority.dataset.label = "Priority";
    priority.appendChild(createCasePriorityBadge(item.priority));
    row.appendChild(priority);
    appendTableCell(row, item.category, "Concern");
    const preview = document.createElement("td");
    const previewText = document.createElement("div");
    preview.dataset.label = "Summary Preview";
    previewText.className = "inbox-summary-preview";
    previewText.textContent = item.summary;
    preview.appendChild(previewText);
    row.appendChild(preview);
    const status = document.createElement("td");
    status.dataset.label = "Status";
    status.appendChild(createInboxStatusBadge(item));
    row.appendChild(status);
    appendTableCell(row, formatInboxTimestamp(item.createdAt), "Updated");
    const action = document.createElement("td");
    const open = document.createElement("button");
    action.dataset.label = "Action";
    open.type = "button";
    open.className = "action-link";
    open.textContent = "Open";
    open.addEventListener("click", () => {
      void openInboxItem(item);
    });
    action.appendChild(open);
    row.appendChild(action);
    tbody.appendChild(row);
  });

  setInboxState(
    `Showing ${page.start}–${page.end} of ${page.total} current student summary ${page.total === 1 ? "item" : "items"}.`,
  );
}

function renderAllTables() {
  renderInquiryTable();
  renderFlaggedConversations();
  renderChatbotFeedback();
}

function setFeedbackState(message, state = "") {
  const element = document.getElementById("feedback-state");
  if (!element) return;
  element.textContent = message;
  element.classList.toggle("error", state === "error");
}

function feedbackCategoryLabel(category) {
  const labels = {
    helpful: "Helpful",
    clear_useful: "Clear and useful",
    not_helpful: "Not helpful",
    incorrect_information: "Incorrect information",
    did_not_understand: "Did not understand me",
    safety_concern: "Reply felt unsafe",
    other: "Other",
  };
  return labels[category] || "Feedback received";
}

function feedbackContextLabel(context) {
  const labels = {
    appointment: "Appointment",
    academics: "Academics",
    office_services: "Office services",
    counseling_support: "Counseling support",
    general_support: "General support",
    safety: "Safety response",
    uncategorized: "Uncategorized",
  };
  return labels[context] || "Uncategorized";
}

const dashboardTableCollator = new Intl.Collator(undefined, {
  numeric: true,
  sensitivity: "base",
});

function sortDashboardRecords(records, sortState, valueFor) {
  const direction = sortState.direction === "desc" ? -1 : 1;
  return [...records].sort((left, right) => {
    const leftValue = valueFor(left, sortState.key);
    const rightValue = valueFor(right, sortState.key);
    if (typeof leftValue === "number" && typeof rightValue === "number") {
      return (leftValue - rightValue) * direction;
    }
    return (
      dashboardTableCollator.compare(String(leftValue), String(rightValue)) *
      direction
    );
  });
}

function feedbackSortValue(feedback, key) {
  const values = {
    student: `${feedback.studentNumber} ${feedback.studentName}`,
    program: feedback.program,
    category: feedbackCategoryLabel(feedback.category),
    responseContext: feedbackContextLabel(feedback.responseContext),
    comment: feedback.comment,
    createdAt: feedback.createdAt?.getTime() ?? Number.MAX_SAFE_INTEGER,
  };
  return values[key] ?? "";
}

function renderFeedbackInsights() {
  const total = document.getElementById("feedback-total-count");
  const attention = document.getElementById("feedback-attention-count");
  const safety = document.getElementById("feedback-safety-count");
  const patternCount = document.getElementById("feedback-pattern-count");
  const patternDetail = document.getElementById("feedback-pattern-detail");
  if (!total || !attention || !safety || !patternCount || !patternDetail)
    return;

  if (!chatbotFeedbackInsights || chatbotFeedbackLoadState !== "ready") {
    total.textContent = "—";
    attention.textContent = "—";
    safety.textContent = "—";
    patternCount.textContent = "—";
    patternDetail.textContent = "Loading feedback signals";
    return;
  }

  total.textContent = String(chatbotFeedbackInsights.total || 0);
  attention.textContent = String(chatbotFeedbackInsights.needs_attention || 0);
  safety.textContent = String(chatbotFeedbackInsights.safety_concerns || 0);

  const pattern = chatbotFeedbackInsights.patterns?.[0];
  patternCount.textContent = String(pattern?.count || 0);
  patternDetail.textContent = pattern
    ? `${feedbackCategoryLabel(pattern.category)} · ${feedbackContextLabel(pattern.response_context)} replies`
    : "No needs-attention ratings yet";
}

function feedbackItemsForCurrentFilter() {
  const query = String(
    document.getElementById("feedback-search-input")?.value || "",
  )
    .trim()
    .toLowerCase();
  const filter = document.getElementById("feedback-filter")?.value || "all";
  const context =
    document.getElementById("feedback-context-filter")?.value || "all";
  const helpfulCategories = ["helpful", "clear_useful"];
  let items = chatbotFeedback.filter((feedback) => {
    const matchesCategory =
      filter === "all" ||
      (filter === "helpful" && helpfulCategories.includes(feedback.category)) ||
      (filter === "attention" &&
        !helpfulCategories.includes(feedback.category));
    const matchesContext =
      context === "all" || feedback.responseContext === context;
    const searchable = [
      feedback.studentName,
      feedback.studentNumber,
      feedback.program,
      feedbackCategoryLabel(feedback.category),
      feedbackContextLabel(feedback.responseContext),
      feedback.comment,
    ]
      .join(" ")
      .toLowerCase();
    return (
      matchesCategory &&
      matchesContext &&
      (!query || searchable.includes(query))
    );
  });
  items = sortDashboardRecords(items, feedbackSort, feedbackSortValue);
  return items;
}

function renderChatbotFeedback() {
  const tbody = document.getElementById("feedback-tbody");
  if (!tbody) return;
  tbody.replaceChildren();
  renderFeedbackInsights();
  syncTableSortHeaders("feedback-table", feedbackSort);

  if (chatbotFeedbackLoadState === "loading") {
    clearDashboardTablePagination("feedback-tbody");
    appendTableEmptyState(tbody, 6, "Loading student feedback...");
    return;
  }
  if (chatbotFeedbackLoadState === "error") {
    clearDashboardTablePagination("feedback-tbody");
    appendTableEmptyState(
      tbody,
      6,
      "Student feedback is unavailable right now.",
    );
    return;
  }
  const items = feedbackItemsForCurrentFilter();
  if (!items.length) {
    clearDashboardTablePagination("feedback-tbody");
    appendTableEmptyState(
      tbody,
      6,
      chatbotFeedback.length
        ? "No feedback items match this filter."
        : "No student feedback has been submitted in your authorized programs yet.",
    );
    setFeedbackState(
      chatbotFeedback.length
        ? "No feedback items match this filter."
        : "No student feedback has been submitted yet.",
    );
    return;
  }

  const page = paginateDashboardRows(
    "feedback-tbody",
    items,
    renderChatbotFeedback,
  );
  page.items.forEach((feedback) => {
    const row = document.createElement("tr");
    const student = document.createElement("td");
    const studentName = document.createElement("strong");
    const studentNumber = document.createElement("span");
    studentName.className = "inbox-student-name";
    studentName.textContent = feedback.studentName;
    studentNumber.className = "inbox-student-number";
    studentNumber.textContent = feedback.studentNumber;
    student.append(studentName, studentNumber);
    row.appendChild(student);
    appendTableCell(row, feedback.program, "Program");
    appendTableCell(row, feedbackCategoryLabel(feedback.category), "Rating");
    appendTableCell(
      row,
      feedbackContextLabel(feedback.responseContext),
      "Reply context",
    );
    appendTableCell(row, feedback.comment, "Optional note");
    appendTableCell(
      row,
      feedback.createdAt ? feedback.createdAt.toLocaleString() : "Unavailable",
      "Submitted",
    );
    tbody.appendChild(row);
  });
  setFeedbackState(
    `Showing ${page.start}–${page.end} of ${page.total} student feedback ${page.total === 1 ? "item" : "items"}.`,
  );
}

function appendTableCell(row, value, label = "") {
  const cell = document.createElement("td");
  cell.textContent = value;
  if (label) {
    cell.dataset.label = label;
  }
  row.appendChild(cell);
}

function flaggedSortValue(conversation, key) {
  const values = {
    student: `${conversation.studentNumber} ${conversation.studentName}`,
    priority: casePriorityRank(conversation.priority),
    summary: conversation.summary,
    category: conversation.category,
    status: conversation.status,
    createdAt: conversation.createdAt?.getTime() ?? Number.MAX_SAFE_INTEGER,
  };
  return values[key] ?? "";
}

function flaggedItemsForCurrentFilter() {
  const query = String(
    document.getElementById("flagged-search-input")?.value || "",
  )
    .trim()
    .toLowerCase();
  const filter = document.getElementById("flagged-filter")?.value || "all";
  const items = flaggedConversations.filter((conversation) => {
    const matchesFilter =
      filter === "all" ||
      conversation.status === filter ||
      (filter.startsWith("priority-") &&
        conversation.priority === filter.replace("priority-", ""));
    const searchable = [
      conversation.studentName,
      conversation.studentNumber,
      conversation.program,
      conversation.category,
      conversation.summary,
    ]
      .join(" ")
      .toLowerCase();
    return matchesFilter && (!query || searchable.includes(query));
  });
  return sortDashboardRecords(items, flaggedSort, flaggedSortValue);
}

function renderFlaggedInsights() {
  const cases = flaggedConversationsLoaded ? flaggedConversations : null;
  const pending = cases
    ? cases.filter((conversation) => conversation.status === "pending")
    : null;
  const reviewed = cases
    ? cases.filter((conversation) => conversation.status === "reviewed")
    : null;
  const values = [
    ["flagged-pending-count", pending?.length ?? "—"],
    ["flagged-reviewed-count", reviewed?.length ?? "—"],
  ];
  values.forEach(([elementId, value]) => {
    const element = document.getElementById(elementId);
    if (element) element.textContent = value;
  });
}

function setFlaggedState(message) {
  const state = document.getElementById("flagged-state");
  if (state) state.textContent = message;
}

function renderFlaggedConversations() {
  const tbody = document.getElementById("flagged-tbody");
  if (!tbody) return;

  renderFlaggedInsights();
  tbody.replaceChildren();
  syncTableSortHeaders("flagged-table", flaggedSort);

  if (!flaggedConversationsLoaded) {
    clearDashboardTablePagination("flagged-tbody");
    appendTableEmptyState(
      tbody,
      7,
      "Flagged cases are unavailable. Retry to load authorized cases.",
    );
    setFlaggedState(
      "Flagged cases are unavailable. Retry to load authorized cases.",
    );
    return;
  }

  const conversations = flaggedItemsForCurrentFilter();

  if (!conversations.length) {
    clearDashboardTablePagination("flagged-tbody");
    appendTableEmptyState(
      tbody,
      7,
      flaggedConversations.length
        ? "No flagged conversations match this filter."
        : "No flagged cases are available in your authorized programs.",
    );
    setFlaggedState(
      flaggedConversations.length
        ? "No flagged conversations match this filter."
        : "No flagged cases are available in your authorized programs.",
    );
    return;
  }

  const page = paginateDashboardRows(
    "flagged-tbody",
    conversations,
    renderFlaggedConversations,
  );
  page.items.forEach((conversation) => {
    const row = document.createElement("tr");
    const student = document.createElement("td");
    const studentName = document.createElement("strong");
    const studentNumber = document.createElement("span");
    studentName.className = "flagged-student-name";
    studentName.textContent = conversation.studentName || "Authorized student";
    studentNumber.className = "flagged-student-number";
    studentNumber.textContent = conversation.studentNumber || "—";
    student.append(studentName, studentNumber);
    row.appendChild(student);

    const priority = document.createElement("td");
    priority.dataset.label = "Priority";
    priority.appendChild(createCasePriorityBadge(conversation.priority));
    row.appendChild(priority);

    const summary = document.createElement("td");
    const summaryText = document.createElement("div");
    summaryText.className = "flagged-summary-preview";
    summaryText.textContent = conversation.summary;
    summary.appendChild(summaryText);
    row.appendChild(summary);

    appendTableCell(row, conversation.category);
    const status = document.createElement("td");
    status.dataset.label = "Status";
    status.appendChild(createInboxStatusBadge(conversation));
    row.appendChild(status);
    appendTableCell(
      row,
      conversation.createdAt
        ? conversation.createdAt.toLocaleString()
        : "Unavailable",
    );

    const actionCell = document.createElement("td");
    const viewButton = document.createElement("button");
    viewButton.type = "button";
    viewButton.className = "action-link";
    viewButton.textContent = "View";
    viewButton.addEventListener("click", () => {
      void openInboxItem(conversation);
    });
    actionCell.appendChild(viewButton);
    row.appendChild(actionCell);
    tbody.appendChild(row);
  });
  setFlaggedState(
    `Showing ${page.start}–${page.end} of ${page.total} flagged ${page.total === 1 ? "case" : "cases"}.`,
  );
}

function renderReports() {
  renderDashboardOverview();
}

function overviewValue(elementId, value) {
  const element = document.getElementById(elementId);
  if (element) element.textContent = displayAggregateValue(value);
}

function latestTrendRow(trends) {
  const rows = trends || [];
  return rows.length ? rows[rows.length - 1] : null;
}

function appendStudentReportCell(row, value) {
  const cell = document.createElement("td");
  cell.textContent = String(value ?? "—");
  row.appendChild(cell);
}

function renderStudentReportGraph(
  containerId,
  rows,
  emptyMessage = "No student records are available.",
) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.replaceChildren();

  if (!rows.length) {
    const empty = document.createElement("p");
    empty.className = "sub";
    empty.textContent = emptyMessage;
    container.appendChild(empty);
    return;
  }

  const maximum = Math.max(...rows.map((row) => row.value), 1);
  rows.forEach((item) => {
    const row = document.createElement("div");
    row.className = "reports-bar-row";
    const label = document.createElement("span");
    label.className = "reports-bar-label";
    label.textContent = item.label;
    const track = document.createElement("span");
    track.className = "reports-bar-track";
    const bar = document.createElement("span");
    bar.className = `reports-bar-fill ${item.tone || ""}`;
    bar.style.width = `${Math.round((item.value / maximum) * 100)}%`;
    bar.setAttribute("aria-hidden", "true");
    track.appendChild(bar);
    const value = document.createElement("strong");
    value.className = "reports-bar-value";
    value.textContent = String(item.value);
    row.append(label, track, value);
    container.appendChild(row);
  });
}

function renderStudentReports() {
  const caseTable = document.getElementById("reports-student-cases");
  const appointmentTable = document.getElementById(
    "reports-student-appointments",
  );
  const cases = flaggedConversations
    .filter((item) => item.flagged && item.status !== "reviewed")
    .sort((left, right) => {
      const priorityOrder = { critical: 4, high: 3, medium: 2, low: 1 };
      return (
        (priorityOrder[right.priority] || 0) -
        (priorityOrder[left.priority] || 0)
      );
    });

  const appointments = (window.backendAppointments || [])
    .filter((item) => ["pending", "confirmed"].includes(item.status))
    .sort((left, right) =>
      `${left.date} ${left.time}`.localeCompare(`${right.date} ${right.time}`),
    );

  if (caseTable && appointmentTable) {
    caseTable.replaceChildren();
    appointmentTable.replaceChildren();

    if (!cases.length) {
      appendTableEmptyState(
        caseTable,
        6,
        "No student cases currently require counselor action.",
      );
    } else {
      cases.forEach((item) => {
        const row = document.createElement("tr");
        appendStudentReportCell(
          row,
          `${item.studentName} (${item.studentNumber})`,
        );
        appendStudentReportCell(row, item.program);
        appendStudentReportCell(row, item.category);
        appendStudentReportCell(row, item.priority);
        appendStudentReportCell(row, item.status);
        const actionCell = document.createElement("td");
        const action = document.createElement("button");
        action.type = "button";
        action.className = "action-link";
        action.textContent = "Open case";
        action.addEventListener("click", () => openInboxItem(item));
        actionCell.appendChild(action);
        row.appendChild(actionCell);
        caseTable.appendChild(row);
      });
    }

    if (!appointments.length) {
      appendTableEmptyState(
        appointmentTable,
        6,
        "No pending or confirmed student appointments are available.",
      );
    } else {
      appointments.forEach((item) => {
        const row = document.createElement("tr");
        appendStudentReportCell(row, `${item.student} (${item.studentNumber})`);
        appendStudentReportCell(row, formatAppointmentDate(item.date));
        appendStudentReportCell(row, formatAppointmentTime(item.time));
        appendStudentReportCell(row, item.category || "General support");
        appendStudentReportCell(row, item.status);
        const actionCell = document.createElement("td");
        const action = document.createElement("button");
        action.type = "button";
        action.className = "action-link";
        action.textContent = "Open appointment";
        action.addEventListener("click", () => openAppointmentDetails(item));
        actionCell.appendChild(action);
        row.appendChild(actionCell);
        appointmentTable.appendChild(row);
      });
    }
  }

  const priorityCounts = new Map([
    ["Critical", 0],
    ["High", 0],
    ["Medium", 0],
    ["Low", 0],
  ]);
  cases.forEach((item) => {
    const label = `${item.priority || "low"}`.replace(/^./, (character) =>
      character.toUpperCase(),
    );
    priorityCounts.set(label, (priorityCounts.get(label) || 0) + 1);
  });
  renderStudentReportGraph(
    "reports-case-priority-graph",
    Array.from(priorityCounts, ([label, value]) => ({
      label,
      value,
      tone: label.toLowerCase(),
    })),
  );

  const appointmentStatusCounts = new Map();
  appointments.forEach((item) => {
    const label = `${item.status || "pending"}`.replace(/^./, (character) =>
      character.toUpperCase(),
    );
    appointmentStatusCounts.set(
      label,
      (appointmentStatusCounts.get(label) || 0) + 1,
    );
  });
  renderStudentReportGraph(
    "reports-appointment-status-graph",
    Array.from(appointmentStatusCounts, ([label, value]) => ({ label, value })),
  );
}

function renderDashboardOverview() {
  renderStudentReports();
  const studentAppointments = window.backendAppointments || [];
  const reviewableCases = flaggedConversations.filter(
    (item) => item.flagged && item.status !== "reviewed",
  );
  const referralCases = flaggedConversations.filter(
    (item) => item.hasReferral && item.status !== "reviewed",
  );

  overviewValue("reports-overview-appointments", studentAppointments.length);
  overviewValue("reports-overview-pending-cases", reviewableCases.length);
  overviewValue(
    "reports-overview-chatbot-messages",
    flaggedConversations.length,
  );
  overviewValue("reports-overview-active-referrals", referralCases.length);
}

function navigateOverview(target) {
  const destinations = {
    appointment: { view: "appointments", section: "overview" },
    chatbot: { view: "reports", section: "chatbot" },
    workload: { view: "reports", section: "workload" },
    "flagged-cases": { view: "reports", section: "flagged-cases" },
  };
  const destination = destinations[target];
  if (!destination) return;

  switchView(destination.view);
  showDashboardSection(destination.view, destination.section);
}

function bindDashboardOverviewNavigation() {
  document.querySelectorAll("[data-overview-target]").forEach((button) => {
    button.addEventListener("click", () => {
      navigateOverview(button.dataset.overviewTarget);
    });
  });
}

function appendReportRows(containerId, rows) {
  const container = document.getElementById(containerId);
  if (!container) return;

  container.replaceChildren();

  if (!rows.length) {
    clearDashboardTablePagination(containerId);
    appendTableEmptyState(
      container,
      2,
      "No aggregate data is available for the selected period.",
    );
    return;
  }

  const page = paginateDashboardRows(containerId, rows, () => {
    appendReportRows(containerId, rows);
  });
  page.items.forEach(([labelText, value]) => {
    const row = document.createElement("tr");
    const label = document.createElement("td");
    const count = document.createElement("td");
    label.textContent = labelText;
    count.textContent = String(value);
    row.append(label, count);
    container.appendChild(row);
  });
}

function trendReportRows(label, trends) {
  return (trends || []).map((item) => [
    `${label}: ${item.date || item.week || item.month}`,
    item.count,
  ]);
}

function renderCombinedReports() {
  const reports = reportsAnalytics;
  if (!reports) return;

  const appointment = reports.appointment || {};
  const chatbot = reports.chatbot || {};
  const workload = reports.workload || {};
  const flaggedCases = reports.flaggedCases || {};

  appendReportRows("reports-appointment-rows", [
    [
      "Total appointments",
      displayAggregateValue(appointment.total_appointments),
    ],
    ...(appointment.status_distribution || []).map((item) => [
      `Status: ${item.status}`,
      item.count,
    ]),
    ...trendReportRows("Daily trend", appointment.daily_trends),
    ...trendReportRows("Weekly trend", appointment.weekly_trends),
    ...trendReportRows("Monthly trend", appointment.monthly_trends),
    ...(appointment.program_statistics || []).map((item) => [
      `Program: ${item.program}`,
      item.count,
    ]),
  ]);

  const chatbotVolume = chatbot.message_volume || {};
  appendReportRows("reports-chatbot-rows", [
    [
      "Total chatbot messages",
      displayAggregateValue(chatbot.total_chatbot_messages),
    ],
    [
      "Conversation finalizations",
      displayAggregateValue(chatbot.conversation_finalization_count),
    ],
    ["Escalations", displayAggregateValue(chatbot.escalation_count)],
    [
      "Average finalized conversation length",
      displayAggregateValue(chatbot.average_finalized_conversation_length),
    ],
    ...(chatbot.persisted_emotion_result_distribution || []).map((item) => [
      `Persisted emotion result: ${item.emotion_result}`,
      item.count,
    ]),
    ...trendReportRows("Daily message volume", chatbotVolume.daily),
    ...trendReportRows("Weekly message volume", chatbotVolume.weekly),
    ...trendReportRows("Monthly message volume", chatbotVolume.monthly),
  ]);

  appendReportRows("reports-workload-rows", [
    [
      "Authorized appointments",
      displayAggregateValue(workload.authorized_appointment_count),
    ],
    [
      "Pending appointments",
      displayAggregateValue(workload.pending_appointment_count),
    ],
    [
      "Confirmed appointments",
      displayAggregateValue(workload.confirmed_appointment_count),
    ],
    [
      "Completed appointments",
      displayAggregateValue(workload.completed_appointment_count),
    ],
    ["Active referrals", displayAggregateValue(workload.active_referral_count)],
    [
      "Active interventions",
      displayAggregateValue(workload.active_intervention_count),
    ],
    [
      "Completed interventions",
      displayAggregateValue(workload.completed_intervention_count),
    ],
    ...(workload.workload_by_program || []).map((item) => [
      `Authorized program: ${item.program}`,
      item.count,
    ]),
  ]);

  const escalationTrends = flaggedCases.escalation_trends || {};
  appendReportRows("reports-flagged-case-rows", [
    [
      "Total flagged cases",
      displayAggregateValue(flaggedCases.total_flagged_cases),
    ],
    [
      "Pending flagged-case reviews",
      displayAggregateValue(flaggedCases.pending_flagged_case_reviews),
    ],
    [
      "Reviewed flagged cases",
      displayAggregateValue(flaggedCases.reviewed_flagged_cases),
    ],
    ["Referrals", displayAggregateValue(flaggedCases.referral_count)],
    ["Interventions", displayAggregateValue(flaggedCases.intervention_count)],
    [
      "Current confidential cases",
      displayAggregateValue(flaggedCases.current_confidential_case_count),
    ],
    ...(flaggedCases.persisted_case_status_distribution || []).map((item) => [
      `Persisted case status: ${item.status}`,
      item.count,
    ]),
    ...trendReportRows("Daily escalation trend", escalationTrends.daily),
    ...trendReportRows("Weekly escalation trend", escalationTrends.weekly),
    ...trendReportRows("Monthly escalation trend", escalationTrends.monthly),
  ]);
}

function selectedReportDateRange() {
  return {
    startDate: document.getElementById("reports-start-date")?.value || "",
    endDate: document.getElementById("reports-end-date")?.value || "",
  };
}

function analyticsQuery(startDate, endDate) {
  const query = new URLSearchParams();
  if (startDate) query.set("start_date", startDate);
  if (endDate) query.set("end_date", endDate);
  return query.size ? `?${query.toString()}` : "";
}

async function loadCombinedReports() {
  const { startDate, endDate } = selectedReportDateRange();
  const suffix = analyticsQuery(startDate, endDate);
  const [appointment, chatbot, workload, flaggedCases] = await Promise.all([
    fetchJson(`${API_BASE}/api/dashboard/appointments/analytics${suffix}`),
    fetchJson(`${API_BASE}/api/dashboard/chatbot/analytics${suffix}`),
    fetchJson(`${API_BASE}/api/dashboard/counselor-workload${suffix}`),
    fetchJson(`${API_BASE}/api/dashboard/flagged-cases/analytics${suffix}`),
  ]);

  reportsAnalytics = {
    appointment: appointment.data || {},
    chatbot: chatbot.data || {},
    workload: workload.data || {},
    flaggedCases: flaggedCases.data || {},
  };
  [
    "reports-overview-appointment-summary",
    "reports-overview-chatbot-summary",
    "reports-overview-workload-summary",
    "reports-overview-flagged-case-summary",
    "reports-overview-recent-activity",
    "reports-appointment-rows",
    "reports-chatbot-rows",
    "reports-workload-rows",
    "reports-flagged-case-rows",
  ].forEach(resetDashboardTablePage);
  renderCombinedReports();
  renderDashboardOverview();
}

async function ensureReportsLoaded() {
  if (reportsAnalytics) return;
  if (reportsLoadPromise) return reportsLoadPromise;

  reportsLoadPromise = loadCombinedReports().catch((error) => {
    console.error(error);
    reportsAnalytics = null;
    createToast("Unable to load reports.", "info");
  });
  try {
    await reportsLoadPromise;
  } finally {
    reportsLoadPromise = null;
  }
}

function csvCell(value) {
  const text = String(value ?? "");
  const safeText = /^[=+\-@]/.test(text) ? `'${text}` : text;
  return `"${safeText.replaceAll('"', '""')}"`;
}

function reportCsvRows() {
  const rows = [
    ["Overview summary", "Generated at", new Date().toISOString()],
    ["Section", "Metric", "Value"],
  ];
  const add = (metric, value) => rows.push(["Student Overview", metric, value]);
  const cases = flaggedConversations.filter(
    (item) => item.flagged && item.status !== "reviewed",
  );
  const appointments = (window.backendAppointments || []).filter((item) =>
    ["pending", "confirmed"].includes(item.status),
  );
  const referrals = cases.filter((item) => item.hasReferral).length;
  add("Student appointments", appointments.length);
  add("Students needing review", cases.length);
  add("Student case records", flaggedConversations.length);
  add("Students with referrals", referrals);

  const priorityCounts = new Map();
  cases.forEach((item) => {
    const priority = item.priority || "low";
    priorityCounts.set(priority, (priorityCounts.get(priority) || 0) + 1);
  });
  priorityCounts.forEach((value, priority) =>
    rows.push(["Student case priority", priority, value]),
  );

  const appointmentStatusCounts = new Map();
  appointments.forEach((item) => {
    const status = item.status || "pending";
    appointmentStatusCounts.set(
      status,
      (appointmentStatusCounts.get(status) || 0) + 1,
    );
  });
  appointmentStatusCounts.forEach((value, status) =>
    rows.push(["Student appointment status", status, value]),
  );

  return rows;
}

function downloadReportsCsv() {
  const rows = reportCsvRows();
  if (!rows.length) {
    createToast("No Overview data is available to export.", "info");
    return;
  }

  const csv = rows.map((row) => row.map(csvCell).join(",")).join("\r\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  const url = URL.createObjectURL(blob);
  link.href = url;
  link.download = "guidance-overview-summary.csv";
  link.click();
  URL.revokeObjectURL(url);
}

function reportVisualRows(rows, maximum) {
  return rows
    .map((item) => {
      const width = Math.round((item.value / Math.max(maximum, 1)) * 100);
      return `<div class="bar-row"><span>${escapeHtml(item.label)}</span><div class="bar-track"><i style="width:${width}%"></i></div><strong>${item.value}</strong></div>`;
    })
    .join("");
}

function downloadVisualOverview() {
  const cases = flaggedConversations.filter(
    (item) => item.flagged && item.status !== "reviewed",
  );
  const appointments = (window.backendAppointments || []).filter((item) =>
    ["pending", "confirmed"].includes(item.status),
  );
  const priorityRows = ["critical", "high", "medium", "low"].map(
    (priority) => ({
      label: priority.replace(/^./, (character) => character.toUpperCase()),
      value: cases.filter((item) => item.priority === priority).length,
    }),
  );
  const statusRows = ["pending", "confirmed"].map((status) => ({
    label: status.replace(/^./, (character) => character.toUpperCase()),
    value: appointments.filter((item) => item.status === status).length,
  }));
  const referrals = cases.filter((item) => item.hasReferral).length;
  const metrics = [
    ["Student appointments", appointments.length],
    ["Students needing review", cases.length],
    ["Student case records", flaggedConversations.length],
    ["Students with referrals", referrals],
  ];
  const metricMarkup = metrics
    .map(
      ([label, value]) =>
        `<div class="metric"><span>${escapeHtml(label)}</span><strong>${value}</strong></div>`,
    )
    .join("");
  const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Guidance Overview Summary</title>
<style>
body{margin:0;padding:32px;background:#f5f3ef;color:#2f2f2f;font:14px system-ui,sans-serif}main{max-width:1000px;margin:auto;background:#fff;padding:28px;border:1px solid #ddd}h1{margin:0 0 6px;color:#d35400}h2{font-size:16px;margin:28px 0 12px}.meta{color:#777;font-size:12px}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.metric{padding:14px;border:1px solid #e3ded7;background:#fbfaf8}.metric span{display:block;font-size:11px;text-transform:uppercase;color:#777}.metric strong{display:block;margin-top:6px;font-size:28px}.graphs{display:grid;grid-template-columns:1fr 1fr;gap:20px}.graph{padding:16px;border:1px solid #e3ded7}.bar-row{display:grid;grid-template-columns:80px 1fr 28px;gap:8px;align-items:center;margin:12px 0}.bar-track{height:10px;background:#e5e0d8;border-radius:8px;overflow:hidden}.bar-track i{display:block;height:100%;background:#d35400;border-radius:8px}@media(max-width:700px){body{padding:12px}.metrics,.graphs{grid-template-columns:1fr 1fr}.metric strong{font-size:22px}}
</style></head><body><main><h1>SOC Guidance Office</h1><div class="meta">Counselor Overview Summary · Generated ${escapeHtml(new Date().toLocaleString())}</div><section class="metrics">${metricMarkup}</section><section class="graphs"><div class="graph"><h2>Student cases by priority</h2>${reportVisualRows(priorityRows, Math.max(...priorityRows.map((row) => row.value)))}</div><div class="graph"><h2>Student appointments by status</h2>${reportVisualRows(statusRows, Math.max(...statusRows.map((row) => row.value)))}</div></section></main></body></html>`;
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "guidance-overview-visual.html";
  link.click();
  URL.revokeObjectURL(link.href);
}

function bindReportsControls() {
  document
    .getElementById("reports-apply")
    ?.addEventListener("click", async () => {
      try {
        await loadCombinedReports();
      } catch (error) {
        console.error(error);
        createToast("Unable to load reports.", "info");
      }
    });

  document
    .getElementById("reports-reset")
    ?.addEventListener("click", async () => {
      const startDate = document.getElementById("reports-start-date");
      const endDate = document.getElementById("reports-end-date");
      if (startDate) startDate.value = "";
      if (endDate) endDate.value = "";

      try {
        await loadCombinedReports();
      } catch (error) {
        console.error(error);
        createToast("Unable to load reports.", "info");
      }
    });

  document
    .getElementById("reports-export-csv")
    ?.addEventListener("click", downloadReportsCsv);
  document
    .getElementById("reports-export-visual")
    ?.addEventListener("click", downloadVisualOverview);
}

function updateFlaggedCount() {
  const count = flaggedConversationsLoaded
    ? flaggedConversations.filter(
        (conversation) => conversation.status === "pending",
      ).length
    : "—";
  const flaggedCount = document.getElementById("flagged-count");
  if (flaggedCount) {
    flaggedCount.textContent = count;
    flaggedCount.setAttribute("aria-label", "Pending flagged-case count");
  }
}

function formatCaseNoteTimestamp(timestamp) {
  if (!timestamp) return "Timestamp unavailable";
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime())
    ? "Timestamp unavailable"
    : date.toLocaleString();
}

function renderCaseNotes(notes, onEdit) {
  const list = document.getElementById("case-notes-list");
  if (!list) return;

  list.replaceChildren();
  if (!notes.length) {
    const empty = document.createElement("p");
    empty.className = "sub";
    empty.textContent = "No counselor notes have been added.";
    list.appendChild(empty);
    return;
  }

  notes.forEach((note) => {
    const entry = document.createElement("article");
    entry.className = "case-note-entry";

    const text = document.createElement("p");
    text.className = "case-note-text";
    text.textContent = note.note_text;

    const footer = document.createElement("div");
    footer.className = "case-note-footer";
    const timestamp = document.createElement("span");
    const createdAt = formatCaseNoteTimestamp(note.created_at);
    const updatedAt = formatCaseNoteTimestamp(note.updated_at);
    timestamp.textContent =
      note.created_at === note.updated_at
        ? `Created ${createdAt}`
        : `Created ${createdAt} · Updated ${updatedAt}`;
    const editButton = document.createElement("button");
    editButton.type = "button";
    editButton.className = "action-link";
    editButton.textContent = "Edit";
    editButton.addEventListener("click", () => onEdit(note));
    footer.append(timestamp, editButton);

    entry.append(text, footer);
    list.appendChild(entry);
  });
}

function formatReferralStatus(status) {
  return String(status || "pending")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function getReferralStatusBadgeClass(status) {
  const classes = {
    pending: "pending",
    in_progress: "neutral",
    completed: "resolved",
    cancelled: "negative",
  };
  return classes[status] || "pending";
}

function renderReferralHistory(history) {
  const list = document.createElement("ul");
  list.className = "referral-history";
  history.forEach((item) => {
    const entry = document.createElement("li");
    entry.textContent = `${formatReferralStatus(item.status)}: ${formatCaseNoteTimestamp(item.created_at)}`;
    list.appendChild(entry);
  });
  return list;
}

function renderReferralNotes(notes) {
  const list = document.createElement("ul");
  list.className = "referral-notes-history";
  notes.forEach((note) => {
    const entry = document.createElement("li");
    entry.textContent = `${formatCaseNoteTimestamp(note.created_at)}: ${note.note_text}`;
    list.appendChild(entry);
  });
  return list;
}

function renderReferrals(referrals, onStatusChange, onAddNote) {
  const list = document.getElementById("case-referrals-list");
  if (!list) return;

  list.replaceChildren();
  if (!referrals.length) {
    const empty = document.createElement("p");
    empty.className = "sub";
    empty.textContent = "No internal referrals have been created.";
    list.appendChild(empty);
    return;
  }

  referrals.forEach((referral) => {
    const entry = document.createElement("article");
    entry.className = "referral-entry";

    const header = document.createElement("div");
    header.className = "referral-entry-header";
    const destination = document.createElement("h5");
    destination.textContent = referral.destination;
    const status = document.createElement("span");
    status.className = `badge ${getReferralStatusBadgeClass(referral.status)}`;
    status.textContent = formatReferralStatus(referral.status);
    header.append(destination, status);

    const reason = document.createElement("p");
    reason.textContent = referral.referral_reason;

    const footer = document.createElement("div");
    footer.className = "referral-entry-footer";
    const timestamps = document.createElement("span");
    timestamps.textContent =
      referral.created_at === referral.updated_at
        ? `Created ${formatCaseNoteTimestamp(referral.created_at)}`
        : `Created ${formatCaseNoteTimestamp(referral.created_at)} · Updated ${formatCaseNoteTimestamp(referral.updated_at)}`;
    footer.appendChild(timestamps);

    const statusControl = document.createElement("div");
    statusControl.className = "referral-status-control";
    const statusLabel = document.createElement("label");
    statusLabel.textContent = "Referral Status";
    const statusSelect = document.createElement("select");
    ["pending", "in_progress", "completed", "cancelled"].forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = formatReferralStatus(value);
      option.selected = value === referral.status;
      statusSelect.appendChild(option);
    });
    statusSelect.addEventListener("change", () => {
      onStatusChange(referral, statusSelect.value);
    });
    statusControl.append(statusLabel, statusSelect);

    const historyHeading = document.createElement("strong");
    historyHeading.textContent = "Status History";
    const notesHeading = document.createElement("strong");
    notesHeading.textContent = "Referral Notes";

    const noteEditor = document.createElement("div");
    noteEditor.className = "referral-note-editor";
    const noteInput = document.createElement("textarea");
    noteInput.placeholder = "Add a confidential referral note.";
    const addNoteButton = document.createElement("button");
    addNoteButton.type = "button";
    addNoteButton.className = "btn btn-outline btn-sm";
    addNoteButton.textContent = "Add Referral Note";
    addNoteButton.disabled = true;
    addNoteButton.classList.add("disabled");
    noteInput.addEventListener("input", () => {
      const empty = !noteInput.value.trim();
      addNoteButton.disabled = empty;
      addNoteButton.classList.toggle("disabled", empty);
    });
    addNoteButton.addEventListener("click", () => {
      const noteText = noteInput.value.trim();
      if (noteText) onAddNote(referral, noteText);
    });
    noteEditor.append(noteInput, addNoteButton);

    entry.append(
      header,
      reason,
      footer,
      statusControl,
      historyHeading,
      renderReferralHistory(referral.status_history || []),
      notesHeading,
      renderReferralNotes(referral.notes || []),
      noteEditor,
    );
    list.appendChild(entry);
  });
}

function formatInterventionProgress(progressStatus) {
  return String(progressStatus || "planned")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function getInterventionProgressBadgeClass(progressStatus) {
  const classes = {
    planned: "pending",
    ongoing: "neutral",
    completed: "resolved",
    discontinued: "negative",
  };
  return classes[progressStatus] || "pending";
}

function renderInterventionHistory(history) {
  const list = document.createElement("ul");
  list.className = "intervention-history";
  history.forEach((item) => {
    const entry = document.createElement("li");
    const progress = formatInterventionProgress(item.progress_status);
    const timestamp = formatCaseNoteTimestamp(item.created_at);
    entry.textContent = item.outcome
      ? `${progress}: ${timestamp}. Outcome: ${item.outcome}`
      : `${progress}: ${timestamp}`;
    list.appendChild(entry);
  });
  return list;
}

function renderInterventions(interventions, onProgressChange, onOutcome) {
  const list = document.getElementById("case-interventions-list");
  if (!list) return;

  list.replaceChildren();
  if (!interventions.length) {
    const empty = document.createElement("p");
    empty.className = "sub";
    empty.textContent = "No confidential interventions have been created.";
    list.appendChild(empty);
    return;
  }

  interventions.forEach((intervention) => {
    const entry = document.createElement("article");
    entry.className = "intervention-entry";
    const isTerminal = ["completed", "discontinued"].includes(
      intervention.progress_status,
    );
    const hasOutcome = Boolean(intervention.outcome);

    const header = document.createElement("div");
    header.className = "intervention-entry-header";
    const type = document.createElement("h5");
    type.textContent = intervention.intervention_type;
    const status = document.createElement("span");
    status.className = `badge ${getInterventionProgressBadgeClass(intervention.progress_status)}`;
    status.textContent = formatInterventionProgress(
      intervention.progress_status,
    );
    header.append(type, status);

    const objective = document.createElement("p");
    objective.textContent = intervention.objective;
    const footer = document.createElement("div");
    footer.className = "intervention-entry-footer";
    const timestamps = document.createElement("span");
    timestamps.textContent =
      intervention.created_at === intervention.updated_at
        ? `Created ${formatCaseNoteTimestamp(intervention.created_at)}`
        : `Created ${formatCaseNoteTimestamp(intervention.created_at)} · Updated ${formatCaseNoteTimestamp(intervention.updated_at)}`;
    footer.appendChild(timestamps);

    const progressControl = document.createElement("div");
    progressControl.className = "intervention-progress-control";
    const progressLabel = document.createElement("label");
    progressLabel.textContent = "Progress";
    const progressSelect = document.createElement("select");
    ["planned", "ongoing", "completed", "discontinued"].forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = formatInterventionProgress(value);
      option.selected = value === intervention.progress_status;
      progressSelect.appendChild(option);
    });
    progressSelect.disabled = hasOutcome;
    progressSelect.addEventListener("change", () => {
      onProgressChange(intervention, progressSelect.value);
    });
    progressControl.append(progressLabel, progressSelect);

    const completeButton = document.createElement("button");
    completeButton.type = "button";
    completeButton.className = "btn btn-outline btn-sm";
    completeButton.textContent = "Mark Completed";
    completeButton.hidden = isTerminal || hasOutcome;
    completeButton.addEventListener("click", () => {
      onProgressChange(intervention, "completed");
    });

    const historyHeading = document.createElement("strong");
    historyHeading.textContent = "Intervention History";

    entry.append(
      header,
      objective,
      footer,
      progressControl,
      completeButton,
      historyHeading,
      renderInterventionHistory(intervention.history || []),
    );

    if (hasOutcome) {
      const outcomeHeading = document.createElement("strong");
      outcomeHeading.textContent = "Outcome";
      const outcome = document.createElement("p");
      outcome.textContent = intervention.outcome;
      entry.append(outcomeHeading, outcome);
    } else if (isTerminal) {
      const outcomeEditor = document.createElement("div");
      outcomeEditor.className = "intervention-outcome-editor";
      const outcomeInput = document.createElement("textarea");
      outcomeInput.placeholder =
        "Record the confidential intervention outcome.";
      const outcomeButton = document.createElement("button");
      outcomeButton.type = "button";
      outcomeButton.className = "btn btn-primary btn-sm";
      outcomeButton.textContent = "Record Outcome";
      outcomeButton.disabled = true;
      outcomeButton.classList.add("disabled");
      outcomeInput.addEventListener("input", () => {
        const empty = !outcomeInput.value.trim();
        outcomeButton.disabled = empty;
        outcomeButton.classList.toggle("disabled", empty);
      });
      outcomeButton.addEventListener("click", () => {
        const outcome = outcomeInput.value.trim();
        if (outcome) onOutcome(intervention, outcome);
      });
      outcomeEditor.append(outcomeInput, outcomeButton);
      entry.appendChild(outcomeEditor);
    }

    list.appendChild(entry);
  });
}

function formatConfidentialityStatus(confidentialityStatus) {
  return confidentialityStatus === "confidential"
    ? "Confidential"
    : "Not Confidential";
}

function renderCaseConfidentiality(confidentiality) {
  const current = document.getElementById("case-confidentiality-current");
  if (!current) return;

  current.replaceChildren();
  const status = document.createElement("span");
  status.className = `badge ${
    confidentiality.confidentiality_status === "confidential"
      ? "negative"
      : "resolved"
  }`;
  status.textContent = formatConfidentialityStatus(
    confidentiality.confidentiality_status,
  );
  current.appendChild(status);

  if (confidentiality.confidentiality_reason) {
    const reason = document.createElement("p");
    reason.textContent = confidentiality.confidentiality_reason;
    current.appendChild(reason);
  }

  if (confidentiality.history?.length) {
    const historyHeading = document.createElement("strong");
    historyHeading.textContent = "Confidentiality History";
    const history = document.createElement("ul");
    history.className = "case-confidentiality-history";
    confidentiality.history.forEach((item) => {
      const entry = document.createElement("li");
      const timestamp = formatCaseNoteTimestamp(item.created_at);
      const reason = item.confidentiality_reason
        ? ` Reason: ${item.confidentiality_reason}`
        : "";
      entry.textContent = `${formatConfidentialityStatus(item.confidentiality_status)}: ${timestamp}.${reason}`;
      history.appendChild(entry);
    });
    current.append(historyHeading, history);
  }
}

function formatReviewedCaseTimestamp(value) {
  if (!value) return "Reviewed date unavailable";
  const timestamp = new Date(value);
  return Number.isNaN(timestamp.getTime())
    ? "Reviewed date unavailable"
    : timestamp.toLocaleString();
}

async function renderReviewedCaseHistory(summaryId, existingItems = null) {
  const card = document.getElementById("case-history-card");
  const list = document.getElementById("case-history-list");
  if (!card || !list) return;

  card.hidden = true;
  card.dataset.caseHistoryAvailable = "false";
  list.replaceChildren();
  try {
    const items =
      existingItems ||
      (
        await fetchJson(
          `${API_BASE}/api/staff/inbox/${encodeURIComponent(summaryId)}/history`,
          { cache: "no-store" },
        )
      ).data?.items ||
      [];
    if (!items.length) return;
    card.dataset.caseHistoryAvailable = "true";

    items.forEach((item) => {
      const isCurrentCase = String(item.summary_id) === String(summaryId);
      const row = document.createElement("div");
      row.className = "case-history-row";
      row.classList.toggle("case-history-row--current", isCurrentCase);
      const content = document.createElement("div");
      content.className = "case-history-content";
      const title = document.createElement("strong");
      title.textContent = item.primary_concern || "Guidance Office case";
      const meta = document.createElement("span");
      meta.textContent = `Reviewed ${formatReviewedCaseTimestamp(item.reviewed_at)}`;
      const preview = document.createElement("p");
      preview.textContent =
        item.summary_preview || "No AI summary preview is available.";
      content.append(title, meta, preview);

      const actions = document.createElement("div");
      actions.className = "case-history-actions";
      const status = document.createElement("span");
      status.className = "badge resolved";
      status.textContent = "Reviewed";
      const open = document.createElement("button");
      open.type = "button";
      open.className = "action-link";
      open.disabled = isCurrentCase;
      open.classList.toggle("is-current", isCurrentCase);
      open.textContent = isCurrentCase ? "Current" : "Open";
      if (isCurrentCase) {
        open.setAttribute("aria-label", "Current case is open");
      } else {
        open.addEventListener("click", () => {
          void openInboxItem({ id: item.summary_id });
        });
      }
      actions.append(status, open);
      row.append(content, actions);
      list.appendChild(row);
    });
    card.hidden = activeCaseDetailsTab !== "overview";
  } catch (error) {
    console.error(error);
  }
}

async function openInboxItem(item) {
  try {
    const response = await fetchJson(
      `${API_BASE}/api/staff/inbox/${encodeURIComponent(item.id)}`,
    );
    const detail = response.data;
    const conversation = {
      ...item,
      id: detail.summary_id,
      studentName: detail.student_name,
      studentNumber: detail.student_number,
      program: detail.program,
      category: detail.primary_concern,
      emotion: detail.emotion_results,
      flagged: Boolean(detail.flagged_status),
      status: detail.review_status,
      summary: detail.summary_preview,
    };

    if (detail.flagged_status) {
      await openFlaggedConversationDetails(conversation, detail);
      return;
    }
    await openRoutineInboxDetails(conversation, detail);
  } catch (error) {
    console.error(error);
    createToast("Unable to open the authorized summary item.", "info");
  }
}

async function openRoutineInboxDetails(conversation, detail) {
  const reviewButton = document.getElementById("case-resolve-btn");
  const pendingButton = document.getElementById("case-pending-btn");
  const notesCard = document.querySelector(".staff-notes-card");
  const referralsCard = document.getElementById("case-referrals-card");
  const interventionsCard = document.getElementById("case-interventions-card");
  const confidentialityCard = document.getElementById(
    "case-confidentiality-card",
  );
  const badge = document.getElementById("case-badge");
  const staffActionsNote = document.getElementById("case-staff-actions-note");
  const transcriptCard = document.getElementById("case-transcript-card");
  transcriptCard.hidden = true;
  document.getElementById("case-transcript-list").replaceChildren();

  document.getElementById("case-avatar").textContent = initials(
    detail.student_name || "Student",
  );
  document.getElementById("case-name").textContent =
    detail.student_name || "Authorized student";
  document.getElementById("case-meta").textContent = [
    detail.student_number || "Student number unavailable",
    detail.program || "Program unavailable",
  ].join(" · ");
  document.getElementById("case-message").textContent = detail.summary;
  document.getElementById("case-category").textContent =
    detail.primary_concern || "General inquiry";
  document.getElementById("case-emotion").textContent = capitalize(
    detail.emotion_results || "Unavailable",
  );
  applySafetyRisk(detail);
  applyCasePriority(detail);
  document.getElementById("case-time").textContent = detail.created_at
    ? new Date(detail.created_at).toLocaleString()
    : "Unavailable";
  document.getElementById("case-recommendation").textContent =
    detail.recommendations || "No AI recommendation available.";
  document.getElementById("case-total-messages").textContent = Number.isFinite(
    Number(detail.total_messages),
  )
    ? String(detail.total_messages)
    : "—";
  document.getElementById("case-student-messages").textContent = "Not retained";
  document.getElementById("case-ai-messages").textContent = "Not retained";
  document.getElementById("case-escalation-status").textContent =
    "No escalation record";
  document.getElementById("case-escalation-reason").textContent =
    "Routine summary item";
  const activeConversation = detail.review_status === "active";
  document.getElementById("case-status-label").textContent = activeConversation
    ? "Active"
    : "Routine";
  badge.className = `badge ${activeConversation ? "pending" : "neutral"}`;
  badge.textContent = activeConversation ? "Active" : "Routine";
  staffActionsNote.textContent = activeConversation
    ? "This conversation is still active. The AI summary will be available after the conversation is finalized."
    : "No immediate intervention is required. Continue with the requested appointment and monitor the student's progress.";

  reviewButton.hidden = true;
  pendingButton.hidden = true;
  notesCard.hidden = true;
  referralsCard.hidden = true;
  interventionsCard.hidden = true;
  confidentialityCard.hidden = true;
  [confidentialityCard, referralsCard, interventionsCard].forEach((card) => {
    card.dataset.caseRecordAvailable = "false";
  });
  configureCaseDetailsTabs(false);
  await renderReviewedCaseHistory(detail.summary_id);
  switchView("case-details");
}

function displayCaseEmotion(detail) {
  return capitalize(detail.emotion_results || "Unavailable");
}

function safetyRiskPresentation(detail) {
  if (!detail.flagged_status) {
    return { label: "No immediate safety concern", badgeClass: "neutral" };
  }

  const safetyMetadata = [detail.escalation_reason, detail.primary_concern]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  const isImmediateRisk =
    /safety escalation|crisis|self[ -]?harm|suicid|high-risk/.test(
      safetyMetadata,
    );

  return isImmediateRisk
    ? { label: "Immediate safety concern", badgeClass: "negative" }
    : { label: "Elevated concern", badgeClass: "pending" };
}

function applySafetyRisk(detail) {
  const risk = safetyRiskPresentation(detail);
  const element = document.getElementById("case-safety-risk");
  element.className = `badge ${risk.badgeClass}`;
  element.textContent = risk.label;
}

function renderFlaggedConversationTranscript(items) {
  const card = document.getElementById("case-transcript-card");
  const list = document.getElementById("case-transcript-list");
  list.replaceChildren();
  card.hidden = false;

  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "sub";
    empty.textContent =
      "No retained transcript is available for this flagged case.";
    list.appendChild(empty);
    return;
  }

  items.forEach((item) => {
    const entry = document.createElement("article");
    entry.className = "case-transcript-entry";
    const speaker = document.createElement("strong");
    speaker.textContent =
      item.role === "student" ? "Student" : "CTRL4 Assistant";
    const content = document.createElement("p");
    content.textContent = item.content || "";
    entry.append(speaker, content);
    list.appendChild(entry);
  });
}

async function openFlaggedConversationDetails(
  conversation,
  inboxDetail = null,
) {
  try {
    const detail =
      inboxDetail ||
      (
        await fetchJson(
          `${API_BASE}/api/staff/inbox/${encodeURIComponent(conversation.id)}`,
        )
      ).data;
    const reviewButton = document.getElementById("case-resolve-btn");
    const pendingButton = document.getElementById("case-pending-btn");
    const notesCard = document.querySelector(".staff-notes-card");
    const notesInput = document.getElementById("case-notes-input");
    const saveNotesButton = document.getElementById("save-notes-btn");
    const referralsCard = document.getElementById("case-referrals-card");
    const referralDestination = document.getElementById("referral-destination");
    const referralReason = document.getElementById("referral-reason");
    const referralNote = document.getElementById("referral-note");
    const createReferralButton = document.getElementById("create-referral-btn");
    const interventionsCard = document.getElementById(
      "case-interventions-card",
    );
    const interventionType = document.getElementById("intervention-type");
    const interventionObjective = document.getElementById(
      "intervention-objective",
    );
    const createInterventionButton = document.getElementById(
      "create-intervention-btn",
    );
    const confidentialityCard = document.getElementById(
      "case-confidentiality-card",
    );
    const confidentialityReason = document.getElementById(
      "case-confidentiality-reason",
    );
    const markConfidentialButton = document.getElementById(
      "mark-case-confidential-btn",
    );
    const removeConfidentialityButton = document.getElementById(
      "remove-case-confidential-btn",
    );
    const [
      notesResponse,
      referralsResponse,
      interventionsResponse,
      confidentialityResponse,
      historyResponse,
      transcriptResponse,
    ] = await Promise.all([
      fetchJson(
        `${API_BASE}/api/flagged-conversations/${conversation.id}/notes`,
      ),
      fetchJson(
        `${API_BASE}/api/flagged-conversations/${conversation.id}/referrals`,
      ),
      fetchJson(
        `${API_BASE}/api/flagged-conversations/${conversation.id}/interventions`,
      ),
      fetchJson(
        `${API_BASE}/api/flagged-conversations/${conversation.id}/confidentiality`,
      ),
      fetchJson(
        `${API_BASE}/api/staff/inbox/${encodeURIComponent(conversation.id)}/history`,
        { cache: "no-store" },
      ),
      fetchJson(
        `${API_BASE}/api/flagged-conversations/${conversation.id}/transcript`,
        { cache: "no-store" },
      ),
    ]);
    const notes = notesResponse.data?.items || [];
    const referrals = referralsResponse.data?.items || [];
    const interventions = interventionsResponse.data?.items || [];
    const transcript = transcriptResponse.data?.items || [];
    let confidentiality = confidentialityResponse.data;
    let editingNoteId = null;

    document.getElementById("case-avatar").textContent = initials(
      detail.student_name || conversation.studentName || "Student",
    );
    document.getElementById("case-name").textContent =
      detail.student_name || conversation.studentName || "Authorized student";
    document.getElementById("case-meta").textContent = [
      detail.student_number ||
        conversation.studentNumber ||
        "Student number unavailable",
      detail.program || conversation.program || "Program unavailable",
    ].join(" · ");
    document.getElementById("case-message").textContent = detail.summary;
    document.getElementById("case-category").textContent =
      detail.primary_concern || "General inquiry";
    document.getElementById("case-emotion").textContent =
      displayCaseEmotion(detail);
    const safetyRisk = safetyRiskPresentation(detail);
    applySafetyRisk(detail);
    applyCasePriority(detail);
    document.getElementById("case-time").textContent = detail.created_at
      ? new Date(detail.created_at).toLocaleString()
      : "Unavailable";
    document.getElementById("case-recommendation").textContent =
      detail.recommendations || "No recommendation available.";
    const totalMessages = Number(detail.total_messages);
    document.getElementById("case-total-messages").textContent =
      Number.isFinite(totalMessages) ? String(totalMessages) : "—";
    document.getElementById("case-student-messages").textContent =
      "Not retained";
    document.getElementById("case-ai-messages").textContent = "Not retained";
    document.getElementById("case-escalation-status").textContent =
      detail.escalation_status === "reviewed" ? "Reviewed" : "Pending review";
    document.getElementById("case-escalation-reason").textContent =
      detail.escalation_reason || "AI safety escalation.";
    document.getElementById("case-status-label").textContent =
      detail.escalation_status === "reviewed" ? "Reviewed" : "Pending review";
    renderFlaggedConversationTranscript(transcript);

    const badge = document.getElementById("case-badge");
    const staffActionsNote = document.getElementById("case-staff-actions-note");
    badge.className =
      detail.escalation_status === "reviewed"
        ? "badge resolved"
        : "badge negative";
    badge.textContent =
      detail.escalation_status === "reviewed" ? "Reviewed" : "Pending review";
    staffActionsNote.textContent =
      safetyRisk.label === "Immediate safety concern"
        ? "Immediate Guidance Office review is recommended. Assess the student's immediate safety, follow the approved Guidance Office protocol, and document the action taken."
        : "Guidance Office review is recommended. Review the reported warning sign, follow the approved Guidance Office procedure, and document the action taken.";

    reviewButton.hidden = false;
    pendingButton.hidden = true;
    notesCard.hidden = false;
    referralsCard.hidden = false;
    interventionsCard.hidden = false;
    confidentialityCard.hidden = false;
    [confidentialityCard, referralsCard, interventionsCard].forEach((card) => {
      card.dataset.caseRecordAvailable = "true";
    });
    configureCaseDetailsTabs(true);
    reviewButton.textContent = "Mark Reviewed";
    reviewButton.disabled = detail.escalation_status === "reviewed";
    reviewButton.classList.toggle("disabled", reviewButton.disabled);
    reviewButton.onclick = async () => {
      if (reviewButton.disabled) return;
      reviewButton.disabled = true;
      reviewButton.classList.add("disabled");
      try {
        const reviewed = await fetchJson(
          `${API_BASE}/api/flagged-conversations/${conversation.id}/review`,
          { method: "PATCH" },
        );
        conversation.status = reviewed.data.escalation_status;
        const updatedDetail = {
          ...detail,
          ...reviewed.data,
          summary_id: detail.summary_id || conversation.id,
          student_name: detail.student_name,
          student_number: detail.student_number,
          program: detail.program,
          flagged_status: true,
          review_status: "reviewed",
        };
        await Promise.all([
          refreshReviewableCaseLists(),
          openFlaggedConversationDetails(conversation, updatedDetail),
        ]);
        createToast("Flagged conversation marked as reviewed.", "success");
      } catch (error) {
        console.error(error);
        reviewButton.disabled = false;
        reviewButton.classList.remove("disabled");
        createToast("Unable to mark flagged conversation as reviewed.", "info");
      }
    };

    function resetNoteEditor() {
      editingNoteId = null;
      notesInput.value = "";
      saveNotesButton.textContent = "Add Note";
      saveNotesButton.disabled = true;
      saveNotesButton.classList.add("disabled");
    }

    function startEditingNote(note) {
      editingNoteId = note.id;
      notesInput.value = note.note_text;
      saveNotesButton.textContent = "Update Note";
      saveNotesButton.disabled = false;
      saveNotesButton.classList.remove("disabled");
      notesInput.focus();
    }

    notesInput.oninput = () => {
      const empty = !notesInput.value.trim();
      saveNotesButton.disabled = empty;
      saveNotesButton.classList.toggle("disabled", empty);
    };
    saveNotesButton.onclick = async () => {
      const noteText = notesInput.value.trim();
      if (!noteText) return;

      try {
        const isEditing = editingNoteId !== null;
        const endpoint = isEditing
          ? `${API_BASE}/api/flagged-conversations/${conversation.id}/notes/${editingNoteId}`
          : `${API_BASE}/api/flagged-conversations/${conversation.id}/notes`;
        const response = await fetchJson(endpoint, {
          method: isEditing ? "PATCH" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ note_text: noteText }),
        });
        const savedNote = response.data;
        const index = notes.findIndex((note) => note.id === savedNote.id);
        if (index >= 0) {
          notes[index] = savedNote;
        } else {
          notes.push(savedNote);
        }
        renderCaseNotes(notes, startEditingNote);
        resetNoteEditor();
        createToast(
          isEditing ? "Counselor note updated." : "Counselor note added.",
          "success",
        );
      } catch (error) {
        console.error(error);
        createToast("Unable to save counselor note.", "info");
      }
    };

    renderCaseNotes(notes, startEditingNote);
    resetNoteEditor();

    function resetReferralEditor() {
      referralDestination.value = "";
      referralReason.value = "";
      referralNote.value = "";
      createReferralButton.disabled = true;
      createReferralButton.classList.add("disabled");
    }

    function updateReferralButton() {
      const incomplete =
        !referralDestination.value || !referralReason.value.trim();
      createReferralButton.disabled = incomplete;
      createReferralButton.classList.toggle("disabled", incomplete);
    }

    async function replaceReferral(savedReferral) {
      const index = referrals.findIndex(
        (referral) => referral.id === savedReferral.id,
      );
      if (index >= 0) {
        referrals[index] = savedReferral;
      } else {
        referrals.push(savedReferral);
      }
      renderReferrals(referrals, updateReferralStatus, addReferralNote);
    }

    async function updateReferralStatus(referral, status) {
      try {
        const response = await fetchJson(
          `${API_BASE}/api/flagged-conversations/${conversation.id}/referrals/${referral.id}/status`,
          {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status }),
          },
        );
        await replaceReferral(response.data);
        createToast("Referral status updated.", "success");
      } catch (error) {
        console.error(error);
        createToast("Unable to update referral status.", "info");
      }
    }

    async function addReferralNote(referral, noteText) {
      try {
        const response = await fetchJson(
          `${API_BASE}/api/flagged-conversations/${conversation.id}/referrals/${referral.id}/notes`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ note_text: noteText }),
          },
        );
        await replaceReferral(response.data);
        createToast("Referral note added.", "success");
      } catch (error) {
        console.error(error);
        createToast("Unable to add referral note.", "info");
      }
    }

    referralDestination.onchange = updateReferralButton;
    referralReason.oninput = updateReferralButton;
    createReferralButton.onclick = async () => {
      if (createReferralButton.disabled) return;
      try {
        const response = await fetchJson(
          `${API_BASE}/api/flagged-conversations/${conversation.id}/referrals`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              destination: referralDestination.value,
              referral_reason: referralReason.value.trim(),
              note_text: referralNote.value.trim(),
            }),
          },
        );
        await replaceReferral(response.data);
        resetReferralEditor();
        createToast("Referral created.", "success");
      } catch (error) {
        console.error(error);
        createToast("Unable to create referral.", "info");
      }
    };

    renderReferrals(referrals, updateReferralStatus, addReferralNote);
    resetReferralEditor();

    function resetInterventionEditor() {
      interventionType.value = "";
      interventionObjective.value = "";
      createInterventionButton.disabled = true;
      createInterventionButton.classList.add("disabled");
    }

    function updateInterventionButton() {
      const incomplete =
        !interventionType.value || !interventionObjective.value.trim();
      createInterventionButton.disabled = incomplete;
      createInterventionButton.classList.toggle("disabled", incomplete);
    }

    async function replaceIntervention(savedIntervention) {
      const index = interventions.findIndex(
        (intervention) => intervention.id === savedIntervention.id,
      );
      if (index >= 0) {
        interventions[index] = savedIntervention;
      } else {
        interventions.push(savedIntervention);
      }
      renderInterventions(
        interventions,
        updateInterventionProgress,
        recordInterventionOutcome,
      );
    }

    async function updateInterventionProgress(intervention, progressStatus) {
      try {
        const response = await fetchJson(
          `${API_BASE}/api/flagged-conversations/${conversation.id}/interventions/${intervention.id}/progress`,
          {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ progress_status: progressStatus }),
          },
        );
        await replaceIntervention(response.data);
        createToast("Intervention progress updated.", "success");
      } catch (error) {
        console.error(error);
        createToast("Unable to update intervention progress.", "info");
      }
    }

    async function recordInterventionOutcome(intervention, outcome) {
      try {
        const response = await fetchJson(
          `${API_BASE}/api/flagged-conversations/${conversation.id}/interventions/${intervention.id}/outcome`,
          {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ outcome }),
          },
        );
        await replaceIntervention(response.data);
        createToast("Intervention outcome recorded.", "success");
      } catch (error) {
        console.error(error);
        createToast("Unable to record intervention outcome.", "info");
      }
    }

    interventionType.onchange = updateInterventionButton;
    interventionObjective.oninput = updateInterventionButton;
    createInterventionButton.onclick = async () => {
      if (createInterventionButton.disabled) return;
      try {
        const response = await fetchJson(
          `${API_BASE}/api/flagged-conversations/${conversation.id}/interventions`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              intervention_type: interventionType.value,
              objective: interventionObjective.value.trim(),
            }),
          },
        );
        await replaceIntervention(response.data);
        resetInterventionEditor();
        createToast("Intervention created.", "success");
      } catch (error) {
        console.error(error);
        createToast("Unable to create intervention.", "info");
      }
    };

    renderInterventions(
      interventions,
      updateInterventionProgress,
      recordInterventionOutcome,
    );
    resetInterventionEditor();

    function updateConfidentialityControls() {
      const isConfidential =
        confidentiality.confidentiality_status === "confidential";
      confidentialityReason.value = "";
      confidentialityReason.hidden = isConfidential;
      document.querySelector(
        'label[for="case-confidentiality-reason"]',
      ).hidden = isConfidential;
      markConfidentialButton.hidden = isConfidential;
      markConfidentialButton.disabled = true;
      markConfidentialButton.classList.add("disabled");
      removeConfidentialityButton.hidden = !isConfidential;
      renderCaseConfidentiality(confidentiality);
    }

    async function updateConfidentiality(status, reason) {
      try {
        const response = await fetchJson(
          `${API_BASE}/api/flagged-conversations/${conversation.id}/confidentiality`,
          {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              confidentiality_status: status,
              confidentiality_reason: reason,
            }),
          },
        );
        confidentiality = response.data;
        updateConfidentialityControls();
        createToast(
          status === "confidential"
            ? "Case marked confidential."
            : "Case confidentiality removed.",
          "success",
        );
      } catch (error) {
        console.error(error);
        createToast("Unable to update case confidentiality.", "info");
      }
    }

    confidentialityReason.oninput = () => {
      const empty = !confidentialityReason.value.trim();
      markConfidentialButton.disabled = empty;
      markConfidentialButton.classList.toggle("disabled", empty);
    };
    markConfidentialButton.onclick = () => {
      const reason = confidentialityReason.value.trim();
      if (reason) updateConfidentiality("confidential", reason);
    };
    removeConfidentialityButton.onclick = () => {
      updateConfidentiality("not_confidential");
    };
    updateConfidentialityControls();

    await renderReviewedCaseHistory(
      detail.summary_id,
      historyResponse.data?.items || [],
    );
    switchView("case-details");
  } catch (error) {
    console.error(error);
    createToast("Unable to open flagged conversation.", "info");
  }
}

function openAppointmentDetails(appointment) {
  document.getElementById("appointment-avatar").textContent = initials(
    appointment.student,
  );

  document.getElementById("appointment-student-name").textContent =
    appointment.student;

  document.getElementById("appointment-student-number").textContent =
    appointment.studentNumber || "—";

  document.getElementById("appointment-email").textContent =
    appointment.email || "—";

  document.getElementById("appointment-contact-number").textContent =
    appointment.contactNumber || "—";

  document.getElementById("appointment-reason").textContent =
    appointment.reason || "No reason provided.";

  document.getElementById("appointment-category").textContent =
    formatAppointmentCategory(appointment.category);

  document.getElementById("appointment-mode").textContent =
    formatAppointmentMode(appointment.mode);

  document.getElementById("appointment-preferred-date").textContent =
    formatAppointmentDate(appointment.date);

  document.getElementById("appointment-preferred-time").textContent =
    formatAppointmentTime(appointment.time);

  document.getElementById("appointment-status").textContent = capitalize(
    appointment.status.replaceAll("_", " "),
  );

  document.getElementById("appointment-source").textContent =
    formatAppointmentSource(appointment.source);

  document.getElementById("appointment-program").textContent =
    appointment.program || "—";

  document.getElementById("appointment-assigned-to").textContent =
    appointment.assignedTo || "—";

  document.getElementById("appointment-created-at").textContent =
    appointment.createdAt
      ? new Date(appointment.createdAt).toLocaleString()
      : "—";
  const badge = document.getElementById("appointment-status-badge");

  badge.className = "badge";

  switch (appointment.status) {
    case "pending":
      badge.classList.add("pending");
      badge.textContent = "Pending";
      break;

    case "confirmed":
      badge.classList.add("neutral");
      badge.textContent = "Confirmed";
      break;

    case "completed":
      badge.classList.add("resolved");
      badge.textContent = "Completed";
      break;

    case "cancelled":
      badge.classList.add("negative");
      badge.textContent = "Cancelled";
      break;

    case "rejected":
      badge.classList.add("negative");
      badge.textContent = "Rejected";
      break;

    default:
      badge.classList.add("pending");
      badge.textContent = appointment.status;
  }

  const notesInput = document.getElementById("appointment-notes-input");
  const saveBtn = document.getElementById("save-appointment-notes-btn");

  const confirmBtn = document.getElementById("appointment-confirm-btn");
  const completeBtn = document.getElementById("appointment-complete-btn");
  const rejectBtn = document.getElementById("appointment-reject-btn");
  const cancelBtn = document.getElementById("appointment-cancel-btn");

  // Action button visibility logic
  const isPending = appointment.status === "pending";
  const isConfirmed = appointment.status === "confirmed";

  confirmBtn.hidden = !isPending;
  rejectBtn.hidden = !isPending;
  completeBtn.hidden = !isConfirmed;
  cancelBtn.hidden = !["pending", "confirmed"].includes(appointment.status);

  notesInput.value = appointment.counselorNotes || "";

  // Disable notes editing and hide save button if appointment is closed
  const appointmentClosed = ["completed", "cancelled", "rejected"].includes(
    appointment.status,
  );

  notesInput.readOnly = appointmentClosed;
  saveBtn.hidden = appointmentClosed;
  saveBtn.disabled = appointmentClosed;
  saveBtn.classList.toggle("disabled", appointmentClosed);

  let originalNotes = notesInput.value.trim();

  saveBtn.disabled = appointmentClosed || true;
  saveBtn.classList.toggle("disabled", true);

  notesInput.oninput = () => {
    if (appointmentClosed) {
      return;
    }
    const unchanged = notesInput.value.trim() === originalNotes;

    saveBtn.disabled = unchanged;
    saveBtn.classList.toggle("disabled", unchanged);
  };

  saveBtn.onclick = async () => {
    const notes = notesInput.value.trim();

    if (notes === originalNotes) {
      return;
    }

    if (!notes) {
      createToast("Please enter a note first.", "info");
      return;
    }

    saveBtn.disabled = true;
    try {
      await updateCounselorNotes(appointment, notes);
      originalNotes = notes;
      openAppointmentDetails(appointment);
      createToast("Counselor notes saved.", "success");
    } catch (error) {
      console.error(error);
      saveBtn.disabled = false;
      createToast("Unable to save counselor notes.", "info");
    }
  };
  confirmBtn.onclick = async () => {
    confirmBtn.disabled = true;
    try {
      await updateAppointment(appointment, {
        status: "confirmed",
      });

      createToast("Appointment confirmed.", "success");

      openAppointmentDetails(appointment);
    } catch (error) {
      console.error(error);
      confirmBtn.disabled = false;
      createToast("Unable to confirm appointment.", "info");
    }
  };

  cancelBtn.onclick = async () => {
    cancelBtn.disabled = true;
    try {
      await updateAppointment(appointment, {
        status: "cancelled",
      });

      createToast("Appointment cancelled.", "success");

      openAppointmentDetails(appointment);
    } catch (error) {
      console.error(error);
      cancelBtn.disabled = false;
      createToast("Unable to cancel appointment.", "info");
    }
  };

  rejectBtn.onclick = async () => {
    rejectBtn.disabled = true;
    try {
      await updateAppointment(appointment, {
        status: "rejected",
      });

      createToast("Appointment rejected.", "success");

      openAppointmentDetails(appointment);
    } catch (error) {
      console.error(error);
      rejectBtn.disabled = false;
      createToast("Unable to update appointment status.", "info");
    }
  };

  completeBtn.onclick = async () => {
    completeBtn.disabled = true;
    const notes = notesInput.value.trim();

    if (!notes) {
      createToast(
        "Please save counselor notes before completing the appointment.",
        "info",
      );
      notesInput.focus();
      completeBtn.disabled = false;
      return;
    }
    try {
      if (notes !== originalNotes) {
        await updateCounselorNotes(appointment, notes);
        originalNotes = notes;
      }

      await updateAppointment(appointment, {
        status: "completed",
      });

      createToast("Appointment marked as completed.", "success");

      openAppointmentDetails(appointment);
    } catch (error) {
      console.error(error);
      completeBtn.disabled = false;
      createToast("Unable to update appointment status.", "info");
    }
  };

  switchView("appointment-details");
}

async function refreshReviewableCaseLists() {
  inboxLoadState = "loading";
  renderInquiryTable();

  const [inboxResult, flaggedResult] = await Promise.allSettled([
    fetchJson(`${API_BASE}/api/staff/inbox`, { cache: "no-store" }),
    fetchJson(`${API_BASE}/api/flagged-conversations`, { cache: "no-store" }),
  ]);

  if (inboxResult.status === "fulfilled") {
    const inbox = inboxResult.value;
    staffInboxItems = (inbox.data?.items || []).map(mapInboxItem);
    inboxLoadState = "ready";
  } else {
    console.error(inboxResult.reason);
    staffInboxItems = [];
    inboxLoadState = "error";
    setInboxState(
      "Inbox items are unavailable. Retry to load persisted summaries.",
      "error",
    );
  }

  if (flaggedResult.status === "fulfilled") {
    const flagged = flaggedResult.value;
    flaggedConversations = (flagged.data?.items || []).map(
      mapFlaggedConversation,
    );
    flaggedConversationsLoaded = true;
  } else {
    console.error(flaggedResult.reason);
    flaggedConversations = [];
    flaggedConversationsLoaded = false;
  }

  renderInquiryTable();
  renderFlaggedConversations();
  updateFlaggedCount();
}

async function loadDashboardData() {
  inboxLoadState = "loading";
  chatbotFeedbackLoadState = "loading";
  renderInquiryTable();

  const inboxTask = (async () => {
    try {
      const inbox = await fetchJson(`${API_BASE}/api/staff/inbox`, {
        cache: "no-store",
      });
      staffInboxItems = (inbox.data?.items || []).map(mapInboxItem);
      inboxLoadState = "ready";
    } catch (error) {
      console.error(error);
      staffInboxItems = [];
      inboxLoadState = "error";
      setInboxState(
        "Inbox items are unavailable. Retry to load persisted summaries.",
        "error",
      );
    }
  })();

  const flaggedTask = (async () => {
    try {
      const flagged = await fetchJson(`${API_BASE}/api/flagged-conversations`, {
        cache: "no-store",
      });
      flaggedConversations = (flagged.data?.items || []).map(
        mapFlaggedConversation,
      );
      flaggedConversationsLoaded = true;
    } catch (error) {
      console.error(error);
      flaggedConversations = [];
      flaggedConversationsLoaded = false;
    }
  })();

  const feedbackTask = (async () => {
    try {
      const feedback = await fetchJson(
        `${API_BASE}/api/staff/chatbot-feedback`,
        {
          cache: "no-store",
        },
      );
      chatbotFeedback = (feedback.data?.items || []).map(mapChatbotFeedback);
      chatbotFeedbackInsights = feedback.data?.insights || null;
      chatbotFeedbackLoadState = "ready";
    } catch (error) {
      console.error(error);
      chatbotFeedback = [];
      chatbotFeedbackInsights = null;
      chatbotFeedbackLoadState = "error";
      setFeedbackState("Student feedback is unavailable right now.", "error");
    }
  })();

  const inboxStatisticsTask = loadInboxStatistics().catch((error) => {
    console.error(error);
    inboxStatistics = null;
    renderInboxStatistics();
  });

  const appointmentsTask = (async () => {
    try {
      const appointments = await fetchJson(`${API_BASE}/api/appointments`);
      window.backendAppointments = (appointments.data?.items || []).map(
        mapAppointment,
      );
      appointmentsLoaded = true;
    } catch (error) {
      console.error(error);
      window.backendAppointments = [];
      appointmentsLoaded = false;
    }
  })();

  const appointmentAnalyticsTask = loadAppointmentAnalytics().catch((error) => {
    console.error(error);
    appointmentAnalytics = null;
  });

  const chatbotAnalyticsTask = loadChatbotAnalytics().catch((error) => {
    console.error(error);
    chatbotAnalytics = null;
  });

  const counselorWorkloadTask = loadCounselorWorkloadAnalytics().catch(
    (error) => {
      console.error(error);
      counselorWorkloadAnalytics = null;
    },
  );

  const flaggedAnalyticsTask = loadFlaggedCaseAnalytics().catch((error) => {
    console.error(error);
    flaggedCaseAnalytics = null;
  });

  const settingsTask = loadPersistedSettings().catch((error) => {
    console.error(error);
    renderPersistedSettings(null);
    setSettingsStatus("Unable to load persisted settings.", "error");
  });

  const counselorProfileTask = loadCounselorProfile().catch((error) => {
    console.error(error);
    setCounselorProfileStatus("Unable to load counselor profile.", "error");
  });

  const faqsTask = loadFaqs().catch((error) => {
    console.error(error);
    persistedFaqs = [];
    renderFaqs(persistedFaqs);
    setFaqStatus("Unable to load persisted FAQs.", "error");
  });

  const bookingOptionsTask = (async () => {
    try {
      const bookingOptions = await fetchJson(
        `${API_BASE}/api/appointments/booking-options`,
      );
      appointmentBookingOptions = bookingOptions.data || {
        state: "unconfigured",
        bookingEnabled: false,
      };
    } catch (error) {
      console.error(error);
      appointmentBookingOptions = {
        state: "unconfigured",
        bookingEnabled: false,
      };
    }
  })();

  await Promise.all([
    inboxTask,
    flaggedTask,
    feedbackTask,
    inboxStatisticsTask,
    appointmentsTask,
    appointmentAnalyticsTask,
    chatbotAnalyticsTask,
    counselorWorkloadTask,
    flaggedAnalyticsTask,
    settingsTask,
    counselorProfileTask,
    faqsTask,
    bookingOptionsTask,
  ]);

  renderAllTables();
  updateFlaggedCount();
  renderReports();
  renderAppointmentDashboard();
}

async function loadBackendData() {
  if (dashboardLoadPromise) return dashboardLoadPromise;

  dashboardLoadPromise = loadDashboardData();
  try {
    await dashboardLoadPromise;
  } finally {
    dashboardLoadPromise = null;
  }
}

function setCaseDetailsTab(tabName) {
  activeCaseDetailsTab = tabName;
  document.querySelectorAll("[data-case-tab]").forEach((tab) => {
    const selected = tab.dataset.caseTab === tabName;
    tab.classList.toggle("active", selected);
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
  });
  document.querySelectorAll("[data-case-tab-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.caseTabPanel !== tabName;
  });
  const historyCard = document.getElementById("case-history-card");
  if (historyCard) {
    historyCard.hidden =
      tabName !== "overview" ||
      historyCard.dataset.caseHistoryAvailable !== "true";
  }
  setCaseManagementTab(activeCaseManagementTab);
}

function configureCaseDetailsTabs(isFlagged) {
  document.querySelectorAll("[data-case-tab]").forEach((tab) => {
    const requiresFlaggedCase = tab.dataset.caseTab !== "overview";
    tab.hidden = requiresFlaggedCase && !isFlagged;
  });
  const managementTabs = document.querySelector(".case-management-tabs");
  if (managementTabs) managementTabs.hidden = !isFlagged;
  activeCaseManagementTab = "confidentiality";
  setCaseDetailsTab("overview");
}

function bindCaseDetailsTabs() {
  document.querySelectorAll("[data-case-tab]").forEach((tab) => {
    tab.addEventListener("click", () => setCaseDetailsTab(tab.dataset.caseTab));
  });
}

function setCaseManagementTab(tabName) {
  activeCaseManagementTab = tabName;
  document.querySelectorAll("[data-case-management-tab]").forEach((tab) => {
    const selected = tab.dataset.caseManagementTab === tabName;
    tab.classList.toggle("active", selected);
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
  });
  document.querySelectorAll("[data-case-management-panel]").forEach((panel) => {
    const panelName = panel.dataset.caseManagementPanel;
    const available =
      panelName === "actions" || panel.dataset.caseRecordAvailable === "true";
    const shouldShow =
      panelName === "actions" || (available && panelName === tabName);
    panel.hidden = !shouldShow;
    if (panelName !== "actions") {
      panel.setAttribute("aria-hidden", String(!shouldShow));
    }
  });
}

function bindCaseManagementTabs() {
  document.querySelectorAll("[data-case-management-tab]").forEach((tab) => {
    tab.addEventListener("click", () => {
      setCaseManagementTab(tab.dataset.caseManagementTab);
    });
  });
}

function logout() {
  let redirected = false;
  const redirectToLogin = () => {
    if (redirected) return;
    redirected = true;
    sessionStorage.removeItem("hau_user");
    window.location.replace("/login?reason=logged-out");
  };
  const fallbackTimer = setTimeout(redirectToLogin, 1500);

  fetch(`${API_BASE}/auth/logout`, { method: "POST" })
    .catch(() => {})
    .finally(() => {
      clearTimeout(fallbackTimer);
      createToast("Logged out.", "info");
      setTimeout(redirectToLogin, 300);
    });
}

window.addEventListener("error", (event) => {
  console.error("Unexpected error:", event.error);
});

bindSettingsInteractions();
bindPasswordChange();
bindCounselorProfile();
bindInboxControls();
bindFeedbackControls();
bindFlaggedControls();
bindCaseDetailsTabs();
bindCaseManagementTabs();
bindFaqManagement();
bindAppointmentSearch();
bindAppointmentCalendar();
bindAppointmentAnalyticsFilters();
bindChatbotAnalyticsFilters();
bindCounselorWorkloadAnalyticsFilters();
bindFlaggedCaseAnalyticsFilters();
bindReportsControls();
bindDashboardOverviewNavigation();
bindDashboardSectionNavigation();
restoreDashboardLocation();
window.addEventListener("hashchange", restoreDashboardLocation);
loadBackendData();

// Save settings button in the UI
document
  .getElementById("save-settings-btn")
  ?.addEventListener("click", () => saveSettings());

window.saveSettings = saveSettings;
window.goBack = goBack;
window.logout = window.logout || logout;
