(function () {
  "use strict";
  var dialog = document.getElementById("staff-command-dialog");
  var trigger = document.querySelector("[data-staff-command-open]");
  if (!dialog || !trigger || !dialog.showModal) return;

  var input = document.getElementById("staff-command-input");
  var results = document.getElementById("staff-command-results");
  var feedback = document.getElementById("staff-command-feedback");
  var selected = -1, options = [], timer = null, controller = null, generation = 0;
  var endpoint = trigger.getAttribute("data-search-url") || "/staff/search/";

  function updateSelected(next) {
    selected = next;
    options.forEach(function (option, index) {
      option.setAttribute("aria-selected", String(index === selected));
    });
    if (selected >= 0 && options[selected]) {
      input.setAttribute("aria-activedescendant", options[selected].id);
      options[selected].scrollIntoView({block: "nearest"});
    } else {
      input.removeAttribute("aria-activedescendant");
    }
  }

  function reset() {
    selected = -1;
    options = [];
    results.replaceChildren();
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  }

  function open() {
    if (!dialog.open) dialog.showModal();
    input.value = "";
    reset();
    feedback.textContent = "Type two or more characters to search.";
    input.focus();
  }

  function close() {
    if (dialog.open) dialog.close();
  }

  trigger.addEventListener("click", open);
  document.addEventListener("keydown", function (event) {
    if ((event.ctrlKey || event.metaKey) && !event.altKey
      && !event.shiftKey && event.key.toLowerCase() === "k") {
      event.preventDefault();
      if (dialog.open) close();
      else open();
    }
  });
  dialog.addEventListener("click", function (event) {
    if (event.target === dialog) close();
  });
  dialog.addEventListener("close", function () {
    if (timer !== null) clearTimeout(timer);
    timer = null;
    generation += 1;
    if (controller) controller.abort();
    controller = null;
    reset();
    trigger.focus();
  });

  function addOption(group, record, index) {
    // Never use server-provided text as HTML or an untrusted absolute URL.
    if (!record || typeof record.url !== "string" ||
      !record.url.startsWith("/staff/") || record.url.startsWith("//")) return;
    var option = document.createElement("div");
    option.className = "staff-command-option";
    option.id = "staff-command-option-" + index;
    option.setAttribute("role", "option");
    option.setAttribute("aria-selected", "false");
    var link = document.createElement("a");
    link.href = record.url;
    var title = document.createElement("strong");
    title.textContent = String(record.title || "Record");
    var subtitle = document.createElement("small");
    subtitle.textContent = String(record.subtitle || "");
    link.append(title, subtitle);
    option.appendChild(link);
    option.addEventListener("mouseenter", function () {
      updateSelected(options.indexOf(option));
    });
    option.addEventListener("click", function (event) {
      if (event.target === option) link.click();
    });
    group.appendChild(option);
    options.push(option);
  }

  function render(groups) {
    reset();
    var count = 0;
    groups.forEach(function (group) {
      if (!group || !Array.isArray(group.items) || !group.items.length) return;
      var section = document.createElement("div");
      section.className = "staff-command-group";
      section.setAttribute("role", "group");
      section.setAttribute("aria-label", String(group.name || "Results"));
      var heading = document.createElement("div");
      heading.className = "staff-command-group-heading";
      heading.textContent = String(group.name || "Results");
      section.appendChild(heading);
      group.items.forEach(function (item) { addOption(section, item, count++); });
      results.appendChild(section);
    });
    input.setAttribute("aria-expanded", options.length ? "true" : "false");
    feedback.textContent = options.length
      ? options.length + " matching records. Use arrow keys to choose."
      : "No matches in your permitted workspace.";
  }

  function search() {
    var q = input.value.trim().slice(0, 80);
    generation += 1;
    var thisGeneration = generation;
    if (controller) controller.abort();
    if (q.length < 2) {
      reset();
      feedback.textContent = "Type two or more characters to search.";
      return;
    }
    controller = typeof AbortController === "function" ? new AbortController() : null;
    feedback.textContent = "Searching…";
    var url = endpoint + "?format=json&q=" + encodeURIComponent(q);
    fetch(url, {
      credentials: "same-origin",
      headers: {Accept: "application/json"},
      signal: controller ? controller.signal : undefined,
      cache: "no-store"
    }).then(function (response) {
      if (response.redirected) {
        throw new Error("Search session changed. Reload this workspace and try again.");
      }
      var type = (response.headers.get("Content-Type") || "").toLowerCase();
      if (!response.ok) {
        throw new Error(response.status === 429
          ? "Too many searches. Try again shortly."
          : "Search is unavailable.");
      }
      if (!type.includes("application/json")) {
        throw new Error("Search returned an unexpected response. Reload this workspace and try again.");
      }
      return response.json();
    }).then(function (data) {
      if (thisGeneration !== generation || !dialog.open) return;
      render(Array.isArray(data.groups) ? data.groups : []);
    }).catch(function (error) {
      if (thisGeneration !== generation || !dialog.open ||
          (error && error.name === "AbortError")) return;
      reset();
      feedback.textContent = error.message || "Search is unavailable.";
    });
  }

  input.addEventListener("input", function () {
    if (timer !== null) clearTimeout(timer);
    timer = setTimeout(function () { timer = null; search(); }, 280);
  });
  input.addEventListener("keydown", function (event) {
    if (event.key === "ArrowDown" && options.length) {
      event.preventDefault();
      updateSelected((selected + 1) % options.length);
    } else if (event.key === "ArrowUp" && options.length) {
      event.preventDefault();
      updateSelected((selected - 1 + options.length) % options.length);
    } else if (event.key === "Enter" && selected >= 0 && options[selected]) {
      event.preventDefault();
      var anchor = options[selected].querySelector("a");
      if (anchor) anchor.click();
    } else if (event.key === "Escape") {
      close();
    }
  });
}());
