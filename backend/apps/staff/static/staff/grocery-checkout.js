(function () {
  "use strict";
  var root = document.querySelector(".staff-pos-order-layout");
  if (!root) return;
  var left = root.querySelector(".staff-pos-order-main");
  var right = root.querySelector(".staff-pos-order-side");
  if (!left || !right) return;
  var basket = left.querySelector(".staff-card");
  var catalog = right.querySelector("[data-pos-menu-browser]");
  var catalogCard = catalog && catalog.closest(".staff-card");
  var scan = document.getElementById("retail-fast-checkout");
  var payment = right.querySelector("[data-pos-payment-form]");
  var paymentCard = payment && payment.closest(".staff-card");
  var cash = right.querySelector("[data-retail-cash-panel]");
  if (catalogCard) left.insertBefore(catalogCard, left.firstChild);
  if (scan) left.insertBefore(scan, left.firstChild);
  if (basket) right.insertBefore(basket, right.firstChild);
  if (paymentCard && basket) right.insertBefore(paymentCard, basket.nextSibling);
  if (cash && paymentCard) right.insertBefore(cash, paymentCard.nextSibling);
  root.classList.add("grocery-register-ready");
  // Reference-inspired register header reuses real order, outlet and print links.
  var context = document.querySelector(".staff-context-bar--pos");
  var totalRow = document.querySelector(".staff-pos-totals-row");
  if (context) {
    context.classList.add("grocery-register-context");
    var header = document.createElement("div");
    header.className = "grocery-register-heading";
    var title = document.createElement("div");
    title.className = "grocery-register-heading__title";
    var mark = document.createElement("span");
    mark.className = "grocery-register-heading__mark";
    var cartIcon = document.createElement("i");
    cartIcon.className = "bi bi-cart3";
    mark.appendChild(cartIcon);
    mark.setAttribute("aria-hidden", "true");
    var titleCopy = document.createElement("span");
    var storeName = document.querySelector(".staff-sidebar__brand-copy strong, .owner-topbar__brand strong");
    var store = document.createElement("strong");
    store.textContent = storeName ? storeName.textContent.trim() : "Store checkout";
    var sub = document.createElement("small");
    sub.textContent = "Supermarket / Grocery Store";
    titleCopy.appendChild(store);
    titleCopy.appendChild(sub);
    title.appendChild(mark);
    title.appendChild(titleCopy);
    var station = document.createElement("div");
    station.className = "grocery-register-heading__status";
    var register = paymentCard && paymentCard.querySelector(".staff-muted.small");
    station.textContent = register ? register.textContent.trim().replace(/Choose till.*/, "").trim() : "Checkout register";
    header.appendChild(title);
    header.appendChild(station);
    context.parentNode.insertBefore(header, context);
  }
  if (totalRow) totalRow.classList.add("grocery-register-summary");
  if (basket) {
    var basketSummary = document.createElement("div");
    basketSummary.className = "grocery-basket-summary";
    var sourceTotal = totalRow && totalRow.querySelector(".staff-pos-totals-row__total");
    var sourceMeta = totalRow && totalRow.querySelector(".staff-pos-totals-row__meta");
    if (sourceMeta) {
      var subLine = document.createElement("span");
      subLine.textContent = sourceMeta.textContent.trim();
      basketSummary.appendChild(subLine);
    }
    if (sourceTotal) {
      var dueLabel = document.createElement("strong");
      dueLabel.textContent = "Sale total: " + sourceTotal.textContent.trim();
      basketSummary.appendChild(dueLabel);
    }
    if (basketSummary.children.length) basket.appendChild(basketSummary);
    var printLink = context && context.querySelector('a[href*="type=receipt"]');
    if (printLink) {
      var receipt = document.createElement("a");
      receipt.className = "grocery-receipt-shortcut staff-btn staff-btn--ghost";
      receipt.href = printLink.href;
      receipt.target = "_blank";
      receipt.rel = "noopener";
      receipt.textContent = "Print receipt";
      receipt.setAttribute("aria-label", "Print receipt using the configured format");
      basket.appendChild(receipt);
    }
  }

  // On compact screens, offer a clear jump to the live basket rather than
  // forcing a cashier to scroll past a long product catalogue.
  if (basket) {
    basket.id = "grocery-current-basket";
    var jump = document.createElement("a");
    jump.href = "#grocery-current-basket";
    jump.className = "grocery-basket-jump staff-btn staff-btn--primary";
    jump.textContent = "View basket and payment";
    jump.setAttribute("aria-label", "Jump to current basket and payment");
    left.insertBefore(jump, left.firstChild);
  }

  // Cashier basket controls use the existing server-backed quantity and void
  // forms; no client-side stock or payment state is invented.
  if (basket) {
    var lines = basket.querySelectorAll("tbody tr");
    lines.forEach(function (line) {
      var quantityForm = line.querySelector('form input[name="action"][value="adjust_line_qty"]');
      quantityForm = quantityForm && quantityForm.form;
      if (!quantityForm) return;
      var quantity = quantityForm.querySelector('input[name="quantity"]');
      if (!quantity) return;
      var buttons = document.createElement("div");
      buttons.className = "grocery-qty-shortcuts";
      [-1, 1].forEach(function (delta) {
        var button = document.createElement("button");
        button.type = "button";
        button.className = "grocery-qty-shortcut";
        button.textContent = delta > 0 ? "+" : "−";
        button.setAttribute("aria-label", delta > 0 ? "Increase item quantity" : "Decrease item quantity");
        button.addEventListener("click", function () {
          var current = Number(quantity.value);
          // One-unit shortcuts; measured goods remain editable in the quantity field.
          var updated = Math.round((current + delta) * 1000) / 1000;
          if (!(updated > 0)) return;
          quantity.value = String(updated);
          if (typeof quantityForm.requestSubmit === "function") quantityForm.requestSubmit();
        });
        buttons.appendChild(button);
      });
      quantityForm.classList.add("grocery-basket-quantity");
      quantityForm.insertBefore(buttons, quantityForm.querySelector('button[type="submit"]'));
    });
  }
  var basketHeading = basket && basket.querySelector("h2");
  if (basketHeading) basketHeading.textContent = "Current basket";
  var catalogHeading = catalogCard && catalogCard.querySelector("h2");
  if (catalogHeading) catalogHeading.textContent = "Products";
  var search = catalog && catalog.querySelector("[data-pos-menu-search]");
  if (search) search.placeholder = "Search grocery products";
  if (search) search.setAttribute("aria-label", "Search products");
  document.addEventListener("keydown", function (event) {
    if (event.key === "F3" && search) {
      event.preventDefault();
      search.focus();
    }
  });
  // Simple grocery products add on one tap through the existing Django form.
  // Products requiring options still use the visible item form so choices are not skipped.
  var addForm = catalogCard && catalogCard.querySelector('form input[name="action"][value="add_line"]');
  addForm = addForm && addForm.form;
  var productSelect = addForm && addForm.querySelector('select[name="menu_item"]');
  var quantityInput = addForm && addForm.querySelector('input[name="quantity"]');
  var modifierHost = addForm && addForm.querySelector("#staff-pos-add-line-modifiers");
  var busy = false;
  if (addForm && productSelect && catalog) {
    catalog.querySelectorAll("[data-pos-menu-tile]").forEach(function (tile) {
      tile.addEventListener("click", function () {
        if (busy) return;
        if (productSelect.value !== tile.dataset.itemId) return;
        // Existing modifier renderer has already processed the selection.
        if (modifierHost && modifierHost.querySelector("input,select,textarea")) return;
        if (quantityInput) quantityInput.value = "1";
        if (!addForm.checkValidity()) return;
        busy = true;
        if (typeof addForm.requestSubmit === "function") addForm.requestSubmit();
        else addForm.submit();
      });
    });
    addForm.addEventListener("submit", function (event) {
      if (!addForm.checkValidity()) { busy = false; return; }
      if (addForm.dataset.grocerySubmitting === "1") {
        event.preventDefault();
        return;
      }
      addForm.dataset.grocerySubmitting = "1";
      addForm.querySelectorAll('button[type="submit"]').forEach(function (button) { button.disabled = true; });
    });
    window.addEventListener("pageshow", function () {
      busy = false;
      delete addForm.dataset.grocerySubmitting;
      addForm.querySelectorAll('button[type="submit"]').forEach(function (button) { button.disabled = false; });
    });
  }
  // Keep product selection visible, but tuck away rare or manager-only
  // checkout controls without removing any existing server-backed actions.
  Array.prototype.slice.call(right.children).forEach(function (section) {
    if (!section.classList || !section.classList.contains("staff-card")) return;
    if (section === basket || section === paymentCard || section === cash) return;
    if (section.closest("details")) return;
    var title = section.querySelector("h2");
    if (!title) return;
    var detail = document.createElement("details");
    detail.className = "grocery-more-action";
    var summary = document.createElement("summary");
    summary.textContent = title.textContent.trim();
    detail.appendChild(summary);
    right.insertBefore(detail, section);
    detail.appendChild(section);
  });
  var action = payment && payment.querySelector('button[type="submit"]');
  if (action) action.textContent = "Take payment";
  // Quick payment-method choices mirror the existing form's available options.
  // They only select a method; the established server POST remains responsible
  // for validation, permissions and settlement.
  if (payment) {
    var methodSelect = payment.querySelector('select[name="method"]');
    if (methodSelect) {
      var methods = Array.prototype.slice.call(methodSelect.options).filter(function (option) {
        return option.value && option.value.trim();
      });
      if (methods.length) {
        var choices = document.createElement("div");
        choices.className = "grocery-payment-choices";
        choices.setAttribute("role", "group");
        choices.setAttribute("aria-label", "Choose payment method");
        methods.forEach(function (option) {
          var choice = document.createElement("button");
          choice.type = "button";
          choice.className = "grocery-payment-choice";
          choice.textContent = option.textContent.trim();
          choice.dataset.method = option.value;
          choice.setAttribute("aria-pressed", String(methodSelect.value === option.value));
          choice.addEventListener("click", function () {
            methodSelect.value = option.value;
            methodSelect.dispatchEvent(new Event("change", { bubbles: true }));
          });
          choices.appendChild(choice);
        });
        function reflectPaymentMethod() {
          Array.prototype.forEach.call(choices.children, function (choice) {
            choice.setAttribute("aria-pressed", String(methodSelect.value === choice.dataset.method));
          });
        }
        methodSelect.addEventListener("change", reflectPaymentMethod);
        payment.parentNode.insertBefore(choices, payment);
        reflectPaymentMethod();
      }
    }
  }
  if (paymentCard) {
    var due = paymentCard.querySelector(".staff-pos-side-hint");
    if (due) due.classList.add("grocery-amount-due");
  }
})();
