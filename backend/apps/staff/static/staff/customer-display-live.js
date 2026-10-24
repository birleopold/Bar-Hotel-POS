/* Read-only customer screen; follows the cashier's active sale automatically. */
(function () {
  "use strict";
  var root = document.querySelector("[data-customer-display-root]");
  if (!root || !window.fetch || !window.DOMParser) return;
  var busy = false;
  var pendingIdle = 0;
  var authorizationFailures = 0;
  var lastOrderId = root.getAttribute("data-active-order") || "";
  function renderTender() {
    var order = root.getAttribute("data-active-order");
    var panel = root.querySelector("[data-display-tender]");
    if (!panel || !order) return;
    var record = null;
    try { record = JSON.parse(localStorage.getItem("pos:tender:" + order) || "null"); }
    catch (err) { record = null; }
    // Never show a previous customer's cash when a sale is switched.
    var liveDue = Number(root.getAttribute("data-current-due"));
    if (!record || Date.now() - record.updated > 10 * 60 * 1000 ||
        !Number.isFinite(record.received) || !Number.isFinite(record.due) ||
        !Number.isFinite(liveDue) || Math.abs(record.due - liveDue) > 0.005) {
      panel.hidden = true;
      return;
    }
    panel.hidden = false;
    panel.querySelector("[data-display-received]").textContent = record.received.toFixed(2);
    panel.querySelector("[data-display-change]").textContent =
      record.received >= record.due ? (record.received - record.due).toFixed(2) : "—";
  }
  window.addEventListener("storage", function (event) {
    if (event.key === "pos:tender:" + root.getAttribute("data-active-order")) renderTender();
  });

  function refresh() {
    if (busy || document.hidden) return;
    busy = true;
    fetch(window.location.href, {
      credentials: "same-origin", cache: "no-store",
      headers: {"X-Requested-With": "XMLHttpRequest"}
    }).then(function (response) {
      if (!response.ok) throw new Error("Display refresh failed");
      // An expired staff session must not navigate a public-facing monitor to
      // the staff PIN/password screen. Keep the last safe basket until restored.
      if (response.redirected) throw new Error("Display authorization changed");
      return response.text();
    }).then(function (html) {
      if (html === null) return;
      var doc = new DOMParser().parseFromString(html, "text/html");
      var nextRoot = doc.querySelector("[data-customer-display-root]");
      if (!nextRoot) throw new Error("Customer display state unavailable");
      authorizationFailures = 0;
      var nextOrderId = nextRoot.getAttribute("data-active-order") || "";
      if (!nextOrderId && lastOrderId) {
        // A single missing cache pointer during concurrent cashier requests
        // must not blank the screen between successive polls.
        pendingIdle += 1;
        if (pendingIdle < 3) return;
      } else {
        pendingIdle = 0;
      }
      lastOrderId = nextOrderId;
      if (root.innerHTML !== nextRoot.innerHTML) {
        root.innerHTML = nextRoot.innerHTML;
        root.setAttribute("data-active-order", nextOrderId);
        root.setAttribute("data-current-due", nextRoot.getAttribute("data-current-due") || "");
        renderTender();
      }
    }).catch(function () {
      // A register must never leave another customer's items on an abandoned
      // second screen indefinitely after logout, PIN expiry or a backend error.
      // Brief connection glitches tolerate two missed polls before blanking.
      authorizationFailures += 1;
      if (authorizationFailures >= 3 && lastOrderId) {
        root.replaceChildren();
        var heading = document.createElement("h1");
        heading.textContent = "Checkout paused";
        var detail = document.createElement("p");
        detail.textContent = "Waiting for the cashier to reconnect.";
        root.appendChild(heading);
        root.appendChild(detail);
        root.removeAttribute("data-current-due");
        root.setAttribute("data-active-order", "");
        lastOrderId = "";
      }
    }).then(function () { busy = false; });
  }
  renderTender();
  window.setInterval(refresh, 1500);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) refresh();
  });
}());
