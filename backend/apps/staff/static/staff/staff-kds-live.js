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
  var fullscreenButton = document.getElementById("kds-fullscreen");
  var soundButton = document.getElementById("kds-sound");
  var soundKey = "staff-kds-sound:" + tenantId + ":" + outletId;
  var soundEnabled = false;
  var audioContext = null;
  var firstQueueSeen = true;
  try { soundEnabled = window.localStorage.getItem(soundKey) === "on"; } catch (_) {}
  function updateSoundLabel() {
    if (!soundButton) return;
    soundButton.setAttribute("aria-pressed", soundEnabled ? "true" : "false");
    soundButton.textContent = soundEnabled ? "Sound on" : "Sound off";
  }
  function playNotification() {
    if (!soundEnabled) return;
    try {
      var Context = window.AudioContext || window.webkitAudioContext;
      if (!Context) return;
      if (!audioContext) audioContext = new Context();
      if (audioContext.state === "suspended") audioContext.resume();
      var now = audioContext.currentTime;
      var oscillator = audioContext.createOscillator();
      var gain = audioContext.createGain();
      oscillator.type = "sine";
      oscillator.frequency.setValueAtTime(880, now);
      gain.gain.setValueAtTime(0.0001, now);
      gain.gain.exponentialRampToValueAtTime(0.12, now + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.23);
      oscillator.connect(gain);
      gain.connect(audioContext.destination);
      oscillator.start(now);
      oscillator.stop(now + 0.24);
    } catch (_) {}
  }
  if (soundButton) {
    updateSoundLabel();
    soundButton.addEventListener("click", function () {
      soundEnabled = !soundEnabled;
      try { window.localStorage.setItem(soundKey, soundEnabled ? "on" : "off"); } catch (_) {}
      if (soundEnabled) playNotification();
      updateSoundLabel();
    });
  }
  if (fullscreenButton) {
    fullscreenButton.addEventListener("click", function () {
      var element = document.getElementById("staff-main-content") || document.documentElement;
      if (document.fullscreenElement) {
        if (document.exitFullscreen) document.exitFullscreen();
      } else if (element.requestFullscreen) {
        var attempt = element.requestFullscreen();
        if (attempt && attempt.catch) attempt.catch(function () {});
      }
    });
    document.addEventListener("fullscreenchange", function () {
      fullscreenButton.textContent = document.fullscreenElement ? "Leave full screen" : "Full screen";
    });
  }
  function updateTicketTimers() {
    var elems = document.querySelectorAll("[data-kds-created-at]");
    var now = Date.now();
    elems.forEach(function (element) {
      var when = Date.parse(element.getAttribute("data-kds-created-at") || "");
      if (!Number.isFinite(when)) return;
      var minutes = Math.max(0, Math.floor((now - when) / 60000));
      var label = element.querySelector(".kds-line-timer");
      if (!label) return;
      var overdue = minutes >= 15 && !element.classList.contains("staff-pos-kds-line--ready");
      label.textContent = minutes + " min waiting" + (overdue ? " · Overdue" : "");
      element.classList.toggle("kds-line--overdue", overdue);
    });
  }
  window.setInterval(updateTicketTimers, 30000);
  updateTicketTimers();
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
  var refreshRetryTimer = null;
  var refreshInFlight = false;
  var refreshQueued = false;
  var debounceMs = 140;
  var refreshRetryDelayMs = 1000;
  var maxRefreshRetryDelayMs = 15000;

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

  function queueHasActiveEdit() {
    var queue = document.getElementById("staff-kds-queue-region");
    var active = document.activeElement;
    return !!(
      queue && active && queue.contains(active) &&
      active.matches("input, textarea, select")
    );
  }

  function clearRefreshRetry() {
    if (refreshRetryTimer !== null) {
      window.clearTimeout(refreshRetryTimer);
      refreshRetryTimer = null;
    }
  }

  function scheduleRefreshRetry() {
    if (unloaded || refreshRetryTimer !== null) return;
    setStatus("reconnecting", "Reconnecting…");
    refreshRetryTimer = window.setTimeout(function () {
      refreshRetryTimer = null;
      applyQueueRefresh();
    }, refreshRetryDelayMs);
    refreshRetryDelayMs = Math.min(
      maxRefreshRetryDelayMs,
      Math.floor(refreshRetryDelayMs * 1.65)
    );
  }

  function replaceQueueFromHtml(html) {
    var previousIds = {};
    document.querySelectorAll("[data-kds-ticket-id]").forEach(function (item) {
      previousIds[item.getAttribute("data-kds-ticket-id")] = true;
    });
    var doc = new DOMParser().parseFromString(html, "text/html");
    var newTicket = false;
    doc.querySelectorAll("[data-kds-ticket-id]").forEach(function (item) {
      if (!previousIds[item.getAttribute("data-kds-ticket-id")]) newTicket = true;
    });
    var next = doc.getElementById("staff-kds-queue-region");
    var cur = document.getElementById("staff-kds-queue-region");
    if (!next || !cur) {
      throw new Error("Kitchen queue response is incomplete.");
    }
    cur.replaceWith(document.importNode(next, true));
    var newSummary = doc.getElementById("staff-kds-summary");
    var oldSummary = document.getElementById("staff-kds-summary");
    if (newSummary && oldSummary) {
      oldSummary.replaceWith(document.importNode(newSummary, true));
    }
    updateTicketTimers();
    if (newTicket && !firstQueueSeen) playNotification();
    firstQueueSeen = false;
  }

  function applyQueueRefresh() {
    if (unloaded) return;
    if (queueHasActiveEdit()) {
      refreshQueued = true;
      setStatus("live", "Live · update waiting");
      return;
    }
    if (refreshInFlight) {
      refreshQueued = true;
      return;
    }
    clearRefreshRetry();
    refreshInFlight = true;
    var url = window.location.href;
    fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "text/html" },
      cache: "no-store",
      redirect: "follow",
    })
      .then(function (r) {
        if (r.redirected) {
          var changed = new Error("Kitchen display session changed.");
          changed.noRetry = true;
          throw changed;
        }
        var type = (r.headers.get("Content-Type") || "").toLowerCase();
        if (!r.ok || !type.includes("text/html")) {
          throw new Error("Kitchen queue refresh failed.");
        }
        return r.text();
      })
      .then(function (html) {
        replaceQueueFromHtml(html);
        refreshRetryDelayMs = 1000;
        setStatus("live", "Live");
      })
      .catch(function (error) {
        if (error && error.noRetry) {
          setStatus("offline", "Session changed · reopen KDS");
          return;
        }
        scheduleRefreshRetry();
      })
      .then(function () {
        refreshInFlight = false;
        if (refreshQueued && !unloaded && !queueHasActiveEdit()) {
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

  document.addEventListener("focusout", function () {
    if (!refreshQueued || refreshInFlight || unloaded) return;
    window.setTimeout(function () {
      if (!queueHasActiveEdit() && refreshQueued && !refreshInFlight && !unloaded) {
        refreshQueued = false;
        applyQueueRefresh();
      }
    }, 0);
  });

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
    clearRefreshRetry();
    if (ws) {
      try {
        ws.close();
      } catch (_) {}
      ws = null;
    }
  });

  connect();
})();
