(function () {
  "use strict";
  var root = document.querySelector(".staff-pos-order-layout");
  if (!root) return;
  var left = root.querySelector(".staff-pos-order-main");
  var right = root.querySelector(".staff-pos-order-side");
  if (!left || !right) return;
  var basket = left.querySelector(".staff-card");
  var catalog = right.querySelector(".staff-pos-menu-browser");
  var catalogCard = catalog && catalog.closest(".staff-card");
  var scanner = document.getElementById("retail-fast-checkout");
  if (catalogCard) left.insertBefore(catalogCard, left.firstChild);
  if (scanner) left.insertBefore(scanner, left.firstChild);
  if (basket) right.insertBefore(basket, right.firstChild);
  root.classList.add("grocery-register-ready");
  var heading = basket && basket.querySelector("h2");
  if (heading) heading.textContent = "Current basket";
  var name = catalogCard && catalogCard.querySelector("h2");
  if (name) name.textContent = "Products";
  var search = catalogCard && catalogCard.querySelector("[data-pos-menu-search]");
  document.addEventListener("keydown", function (event) {
    if (event.key === "F3" && search) {
      event.preventDefault();
      search.focus();
    }
  });
})();
