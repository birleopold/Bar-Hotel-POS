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
  var addForm = right.querySelector('form input[name="action"][value="add_line"]');
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
  if (action) action.textContent = "Complete payment";
  if (paymentCard) {
    var due = paymentCard.querySelector(".staff-pos-side-hint");
    if (due) due.classList.add("grocery-amount-due");
  }
})();
