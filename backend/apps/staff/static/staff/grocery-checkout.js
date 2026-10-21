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
  var basketHeading = basket && basket.querySelector("h2");
  if (basketHeading) basketHeading.textContent = "Current basket";
  var catalogHeading = catalogCard && catalogCard.querySelector("h2");
  if (catalogHeading) catalogHeading.textContent = "Products";
  var search = catalog && catalog.querySelector("[data-pos-menu-search]");
  if (search) search.setAttribute("aria-label", "Search products");
  document.addEventListener("keydown", function (event) {
    if (event.key === "F3" && search) {
      event.preventDefault();
      search.focus();
    }
  });
  var action = payment && payment.querySelector('button[type="submit"]');
  if (action) action.textContent = "Complete payment";
  if (paymentCard) {
    var due = paymentCard.querySelector(".staff-pos-side-hint");
    if (due) due.classList.add("grocery-amount-due");
  }
})();
