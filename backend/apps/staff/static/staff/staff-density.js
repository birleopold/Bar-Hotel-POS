(function () {
  "use strict";
  var control = document.getElementById("staff-density-toggle");
  if (!control || !document.body) return;
  var key = "staff-layout:" + control.getAttribute("data-tenant-id")
          + ":" + control.getAttribute("data-user-id");
  var choices = ["standard", "touch", "compact"];
  var labels = {"standard": "Standard", "touch": "Floor touch", "compact": "Office compact"};
  var current = "standard";
  try {
    var saved = window.localStorage.getItem(key);
    if (choices.indexOf(saved) >= 0) current = saved;
  } catch (_) {}
  function apply(value) {
    current = value;
    document.body.setAttribute("data-staff-density", value);
    var label = control.querySelector("[data-staff-density-label]");
    if (label) label.textContent = "Layout: " + labels[value];
    var next = choices[(choices.indexOf(value) + 1) % choices.length];
    control.setAttribute("aria-label", "Current layout " + labels[value] +
      ". Activate to use " + labels[next] + ".");
    control.title = "Change to " + labels[next] + " layout";
  }
  apply(current);
  control.addEventListener("click", function () {
    var next = choices[(choices.indexOf(current) + 1) % choices.length];
    try { window.localStorage.setItem(key, next); } catch (_) {}
    apply(next);
  });
}());
