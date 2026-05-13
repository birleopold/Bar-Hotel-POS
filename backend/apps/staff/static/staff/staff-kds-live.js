(function () {
  var root = document.getElementById("staff-kds-live-root");
  if (!root) return;

  var base = window.STAFF_KDS_WS_BASE || "/ws/kds/";
  if (base.charAt(base.length - 1) !== "/") {
    base += "/";
  }

  var enabled = root.getAttribute("data-kds-ws-enabled") === "true";
  var tenantId = (root.getAttribute("data-tenant-id") || "").trim();
  var outletId = (root.getAttribute("data-outlet-id") || "").trim();

  var labelEl = root.querySelector("[data-kds-live-label]");
  var initialDelayMs = 900;
  var maxDelayMs = 30000;
  var delayMs = initialDelayMs;

  function setStatus(status, label) {
    root.setAttribute("data-kds-live-status", status);
    if (labelEl && typeof label === "string") {
      labelEl.textContent = label;
    }
  }

  if (!enabled || !tenantId || !outletId) {
    setStatus("offline", "No live sync");
    return;
  }

  var ws = null;
  var reconnectTimer = null;
  var unloaded = false;

  var refreshDebounceTimer = null;
  var refreshInFlight = false;
  var refreshQueued = false;
  var debounceMs = 140;

  function wsUrl() {
    var proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return proto + "//" + window.location.host + base + tenantId + "/" + outletId + "/";
  }

  function clearReconnect() {
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  }

  function scheduleReconnect() {
    if (unloaded) return;
    clearReconnect();
    setStatus("reconnecting", "Reconnecting…");
    reconnectTimer = window.setTimeout(function () {
      reconnectTimer = null;
      connect();
    }, delayMs);
    delayMs = Math.min(maxDelayMs, Math.floor(delayMs * 1.65));
  }

  function replaceQueueFromHtml(html) {
    var doc = new DOMParser().parseFromString(html, "text/html");
    var next = doc.getElementById("staff-kds-queue-region");
    var cur = document.getElementById("staff-kds-queue-region");
    if (!next || !cur) {
      window.location.reload();
      return;
    }
    cur.replaceWith(document.importNode(next, true));
  }

  function applyQueueRefresh() {
    if (unloaded) return;
    if (refreshInFlight) {
      refreshQueued = true;
      return;
    }
    refreshInFlight = true;
    var url = window.location.href;
    fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "text/html" },
    })
      .then(function (r) {
        if (!r.ok) throw new Error("refresh failed");
        return r.text();
      })
      .then(function (html) {
        replaceQueueFromHtml(html);
      })
      .catch(function () {
        window.location.reload();
      })
      .then(function () {
        refreshInFlight = false;
        if (refreshQueued && !unloaded) {
          refreshQueued = false;
          applyQueueRefresh();
        }
      });
  }

  function onQueueChanged() {
    if (refreshDebounceTimer) {
      window.clearTimeout(refreshDebounceTimer);
    }
    refreshDebounceTimer = window.setTimeout(function () {
      refreshDebounceTimer = null;
      applyQueueRefresh();
    }, debounceMs);
  }

  function connect() {
    if (unloaded) return;
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    clearReconnect();
    try {
      ws = new WebSocket(wsUrl());
    } catch (_) {
      scheduleReconnect();
      return;
    }

    setStatus("connecting", "Connecting…");

    ws.onopen = function () {
      delayMs = initialDelayMs;
      setStatus("live", "Live");
    };

    ws.onmessage = function (ev) {
      try {
        var msg = JSON.parse(ev.data);
        if (msg && msg.type === "queue_changed") {
          onQueueChanged();
        }
      } catch (_) {}
    };

    ws.onerror = function () {};

    ws.onclose = function () {
      ws = null;
      if (!unloaded) {
        scheduleReconnect();
      }
    };
  }

  window.addEventListener("beforeunload", function () {
    unloaded = true;
    if (refreshDebounceTimer) {
      window.clearTimeout(refreshDebounceTimer);
    }
    clearReconnect();
    if (ws) {
      try {
        ws.close();
      } catch (_) {}
      ws = null;
    }
  });

  connect();
})();
