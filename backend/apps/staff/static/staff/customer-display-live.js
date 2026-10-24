/* Read-only customer screen; follows the cashier's active sale automatically. */
(function () {
  "use strict";
  var root = document.querySelector("[data-customer-display-root]");
  if (!root || !window.fetch || !window.DOMParser) return;
  var busy = false;
  function refresh() {
    if (busy || document.hidden) return;
    busy = true;
    fetch(window.location.href, {
      credentials: "same-origin", cache: "no-store",
      headers: {"X-Requested-With": "XMLHttpRequest"}
    }).then(function (response) {
      if (!response.ok) throw new Error("Display refresh failed");
      if (response.redirected && response.url !== window.location.href) {
        var next = new URL(response.url, window.location.href);
        if (next.origin === window.location.origin) {
          window.location.replace(next.href);
          return null;
        }
      }
      return response.text();
    }).then(function (html) {
      if (html === null) return;
      var doc = new DOMParser().parseFromString(html, "text/html");
      var nextRoot = doc.querySelector("[data-customer-display-root]");
      if (!nextRoot) return;
      if (root.innerHTML !== nextRoot.innerHTML) {
        root.innerHTML = nextRoot.innerHTML;
      }
    }).catch(function () {
      // Keep last known basket visible; next poll retries automatically.
    }).then(function () { busy = false; });
  }
  window.setInterval(refresh, 1500);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) refresh();
  });
}());
