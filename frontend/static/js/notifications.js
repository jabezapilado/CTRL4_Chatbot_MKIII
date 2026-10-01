/* Persistent in-app appointment notifications. */

(() => {
  "use strict";

  const API_BASE = window.location.origin;
  let notifications = [];
  let root;
  let panel;
  let list;
  let count;

  function positionHeaderPanel() {
    if (!root?.classList.contains("notifications-widget--header") || panel.hidden) {
      return;
    }

    const toggle = root.querySelector(".notifications-toggle");
    const bounds = toggle.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const panelWidth = Math.min(360, Math.max(0, viewportWidth - 24));
    const left = Math.max(
      12,
      Math.min(bounds.right - panelWidth, viewportWidth - panelWidth - 12),
    );
    const top = Math.min(bounds.bottom + 8, viewportHeight - 72);

    panel.style.width = `${panelWidth}px`;
    panel.style.left = `${left}px`;
    panel.style.top = `${top}px`;
    panel.style.maxHeight = `${Math.max(56, viewportHeight - top - 12)}px`;
  }

  function isRead(notification) {
    return (
      notification.is_read === true ||
      notification.is_read === 1 ||
      notification.is_read === "1"
    );
  }

  function formatCreatedAt(value) {
    const createdAt = new Date(value);
    if (Number.isNaN(createdAt.getTime())) {
      return String(value || "");
    }

    return createdAt.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  }

  function notificationDestination(notification) {
    const type = String(notification.type || "").trim().toLowerCase();
    const isStaffDashboard = Boolean(
      document.querySelector("[data-notifications-mount]"),
    );

    if (type === "high_risk_conversation") {
      return "/dashboard#flagged";
    }

    if (isStaffDashboard && type.startsWith("appointment_")) {
      return "/dashboard#appointments:requests";
    }

    if (!isStaffDashboard && type.startsWith("appointment_")) {
      return "/appointment";
    }

    return "";
  }

  async function openNotification(notification, button) {
    button.disabled = true;

    if (!isRead(notification)) {
      const markedRead = await markNotificationRead(notification.id);
      if (!markedRead) {
        button.disabled = false;
        return;
      }
    }

    const destination = notificationDestination(notification);
    if (destination) {
      window.location.assign(destination);
      return;
    }

    button.disabled = false;
  }

  function renderNotifications() {
    const unreadCount = notifications.filter(
      (notification) => !isRead(notification),
    ).length;

    count.textContent = unreadCount ? String(unreadCount) : "";
    count.hidden = unreadCount === 0;
    list.replaceChildren();

    if (!notifications.length) {
      const empty = document.createElement("p");
      empty.className = "notifications-empty";
      empty.textContent = "No notifications.";
      list.appendChild(empty);
      return;
    }

    notifications.forEach((notification) => {
      const notificationIsRead = isRead(notification);
      const item = document.createElement("button");
      item.type = "button";
      item.className = "notification-item";
      if (
        String(notification.type || "").trim().toLowerCase() ===
        "high_risk_conversation"
      ) {
        item.classList.add("notification-item--critical");
      }
      if (notificationIsRead) {
        item.classList.add("is-read");
      }
      item.setAttribute(
        "aria-label",
        `Open notification: ${String(notification.title || "Notification")}`,
      );
      item.addEventListener("click", () => {
        void openNotification(notification, item);
      });

      const heading = document.createElement("h3");
      heading.textContent = String(notification.title || "Notification");
      item.appendChild(heading);

      const message = document.createElement("p");
      message.textContent = String(notification.message || "");
      item.appendChild(message);

      const footer = document.createElement("div");
      footer.className = "notification-item-footer";

      const createdAt = document.createElement("time");
      createdAt.textContent = formatCreatedAt(notification.created_at);
      footer.appendChild(createdAt);

      item.appendChild(footer);
      list.appendChild(item);
    });
  }

  function showLoadError() {
    list.replaceChildren();
    const error = document.createElement("p");
    error.className = "notifications-empty";
    error.textContent = "Unable to load notifications.";
    list.appendChild(error);
  }

  async function loadNotifications() {
    try {
      const response = await fetch(`${API_BASE}/api/notifications`);
      const payload = await response.json();

      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          root.remove();
          panel.remove();
          return;
        }
        throw new Error(payload.message || "Unable to load notifications.");
      }

      notifications = Array.isArray(payload.data?.items)
        ? payload.data.items
        : [];
      renderNotifications();
    } catch (error) {
      console.error("Unable to load notifications:", error);
      showLoadError();
    }
  }

  async function markNotificationRead(notificationId) {
    try {
      const response = await fetch(
        `${API_BASE}/api/notifications/${encodeURIComponent(notificationId)}/read`,
        { method: "PATCH" },
      );
      const payload = await response.json();

      if (!response.ok) {
        throw new Error(
          payload.message || "Unable to mark notification as read.",
        );
      }

      const notification = notifications.find(
        (item) => item.id === notificationId,
      );
      if (notification) {
        notification.is_read = 1;
      }
      renderNotifications();
      return true;
    } catch (error) {
      console.error("Unable to mark notification as read:", error);
      return false;
    }
  }

  function initializeNotifications() {
    root = document.createElement("section");
    root.className = "notifications-widget";
    root.setAttribute("aria-label", "Notifications");

    const headerMount = document.querySelector("[data-notifications-mount]");
    if (headerMount) {
      root.classList.add("notifications-widget--header");
    }

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "notifications-toggle";
    toggle.setAttribute("aria-label", "Notifications");
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("title", "Notifications");

    const icon = document.createElement("img");
    icon.className = "notifications-icon";
    icon.src = "/static/img/Notification%20Bell2.svg";
    icon.alt = "";
    toggle.appendChild(icon);

    count = document.createElement("span");
    count.className = "notifications-count";
    count.hidden = true;
    toggle.appendChild(count);

    panel = document.createElement("div");
    panel.className = "notifications-panel";
    panel.hidden = true;

    function setPanelOpen(open, restoreFocus = false) {
      panel.hidden = !open;
      toggle.setAttribute("aria-expanded", String(open));
      if (open) positionHeaderPanel();
      if (!open && restoreFocus) toggle.focus();
    }

    const title = document.createElement("h2");
    title.textContent = "Notifications";
    panel.appendChild(title);

    list = document.createElement("div");
    list.className = "notifications-list";
    panel.appendChild(list);

    toggle.addEventListener("click", () => {
      const opening = panel.hidden;
      setPanelOpen(opening);
      if (opening) {
        loadNotifications();
      }
    });

    document.addEventListener("pointerdown", (event) => {
      if (!panel.hidden && !root.contains(event.target) && !panel.contains(event.target)) {
        setPanelOpen(false);
      }
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !panel.hidden) {
        setPanelOpen(false, true);
      }
    });

    root.append(toggle);
    (headerMount || document.body).appendChild(root);
    if (headerMount) {
      // A chat header clips decorative overflow. Keep the popover outside it
      // so notification content is never cut off on narrow viewports.
      panel.classList.add("notifications-panel--header");
      document.body.appendChild(panel);
      window.addEventListener("resize", positionHeaderPanel);
      window.visualViewport?.addEventListener("resize", positionHeaderPanel);
    } else {
      root.appendChild(panel);
    }
    loadNotifications();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeNotifications);
  } else {
    initializeNotifications();
  }
})();
