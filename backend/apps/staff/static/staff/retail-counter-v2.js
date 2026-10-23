/* Checkout keyboard and pointer controls: non-destructive enhancements. */
(function(){
  "use strict";
  var root=document.querySelector(".fizo-checkout-catalogue");
  if(!root)return;
  // Keep settlement immediately below the basket pay action, as in the owner's
  // references. Move only the existing permission-gated payment card; do not
  // clone forms or generate new POST endpoints.
  var basket=document.querySelector(".fizo-checkout-basket");
  var paymentForm=document.querySelector("[data-pos-payment-form]");
  var paymentCard=paymentForm&&paymentForm.closest(".staff-card--pos");
  if(basket&&paymentCard&&!basket.contains(paymentCard)){
    paymentCard.classList.add("reference-payment-card");
    basket.appendChild(paymentCard);
  }
  // Empty baskets have no eligible payment form. Still present the methods
  // in their intended fixed position, disabled until there is an amount due.
  var idlePayment=document.querySelector(".reference-payment-idle");
  if(basket&&idlePayment&&!basket.contains(idlePayment))basket.appendChild(idlePayment);
  // Keep Hold/Clear actions accessible without showing their bulky staff card
  // in the cashier workspace. Reuse the existing, authenticated forms.
  var holdForm=document.querySelector('input[name="action"][value="hold_order"]');
  var holdCard=holdForm&&holdForm.closest(".staff-card");
  var tools=basket&&basket.querySelector(".fizo-retail-basket-tools");
  if(basket&&tools&&holdCard&&!basket.contains(holdCard)){
    var details=document.createElement("details");
    details.className="reference-basket-more";
    var summary=document.createElement("summary");
    summary.textContent="Hold or clear sale";
    details.appendChild(summary);
    details.appendChild(holdCard);
    basket.appendChild(details);
    tools.querySelectorAll('a[href="#hold_label"],a[href="#void_reason"]').forEach(function(link){
      link.addEventListener("click",function(event){
        event.preventDefault();
        details.open=true;
        var target=document.querySelector(link.getAttribute("href"));
        if(target){target.focus();target.scrollIntoView({block:"nearest"});}
      });
    });
  }
  var payLink=document.querySelector(".fizo-cashier-pay-cta");
  if(payLink&&paymentForm){
    payLink.addEventListener("click",function(event){
      event.preventDefault();
      paymentCard.scrollIntoView({behavior:"smooth",block:"nearest"});
      var method=paymentForm.querySelector('select[name="method"]');
      var amount=paymentForm.querySelector('input[name="amount"]');
      if(method)method.focus({preventScroll:true});
      else if(amount)amount.focus({preventScroll:true});
    });
  }
  var server=root.querySelector("#fizo-catalogue-server-query");
  var local=root.querySelector("[data-pos-menu-search]");
  var addForm=root.querySelector("[data-fizo-add-line-form]");
  var serverForm=server&&server.closest("form");
  var qty=addForm&&addForm.querySelector('input[name="quantity"]');
  var product=addForm&&addForm.querySelector('select[name="menu_item"]');
  var live=document.querySelector("[data-pos-menu-selection]");
  var topSearch=document.getElementById("reference-top-catalogue-search");
  var scannerForm=document.querySelector("[data-retail-scan-form]");
  var scannerInput=scannerForm&&scannerForm.querySelector('input[name="code"]');
  var scanMode=false;
  function setHeaderScanMode(enabled){
    scanMode=enabled;
    if(!topSearch)return;
    topSearch.placeholder=enabled?"Scan barcode and press Enter to add item":"Scan barcode or search products...";
    topSearch.focus();topSearch.select();
  }
  document.querySelectorAll("[data-reference-scan-focus]").forEach(function(button){
    button.addEventListener("click",function(){setHeaderScanMode(true);});
  });
  if(topSearch){
    topSearch.addEventListener("keydown",function(event){
      if(event.key==="Escape"){setHeaderScanMode(false);topSearch.value="";return;}
      if(event.key!=="Enter"||!scanMode||event.isComposing)return;
      event.preventDefault();
      var code=topSearch.value.trim();
      if(!code||!scannerForm||!scannerInput)return;
      scannerInput.value=code;
      var quantity=scannerForm.querySelector('input[name="quantity"]');
      if(quantity)quantity.value="1";
      if(scannerForm.requestSubmit)scannerForm.requestSubmit();
    });
  }
  var icons=[
    [/^all/i,"bi-grid"],[/grain|food|flour|rice/i,"bi-flower1"],
    [/drink|beverage|water/i,"bi-cup-straw"],[/dairy|milk/i,"bi-cup-hot"],
    [/snack|biscuit|cookie/i,"bi-cookie"],[/fruit|veg|produce/i,"bi-apple"],
    [/house|home|clean/i,"bi-house"],[/personal|beauty|care/i,"bi-droplet"],
    [/other|misc/i,"bi-three-dots"]
  ];
  root.querySelectorAll("[data-pos-menu-filter]").forEach(function(button){
    if(button.querySelector(".reference-category-icon"))return;
    var label=(button.textContent||"").trim();
    var found=icons.find(function(entry){return entry[0].test(label);});
    var icon=document.createElement("i");
    icon.className="bi "+(found?found[1]:"bi-grid-3x3-gap")+" reference-category-icon";
    icon.setAttribute("aria-hidden","true");
    button.insertBefore(icon,button.firstChild);
  });
  function focusSearch(barcode){
    if(barcode){setHeaderScanMode(true);return;}
    var input=topSearch||local||server;
    if(input){input.focus();input.select();input.scrollIntoView({block:"nearest"});}
  }
  document.querySelectorAll("[data-fizo-focus-search]").forEach(function(a){
    a.addEventListener("click",function(e){e.preventDefault();focusSearch(false);});
  });
  document.querySelectorAll("[data-fizo-focus-scan]").forEach(function(a){
    a.addEventListener("click",function(e){e.preventDefault();focusSearch(true);});
  });
  document.addEventListener("keydown",function(e){
    if(e.altKey||e.ctrlKey||e.metaKey||e.repeat)return;
    if(e.key==="F2"){e.preventDefault();setHeaderScanMode(false);focusSearch(false);}
    if(e.key==="F3"){e.preventDefault();focusSearch(true);}
    if(e.key==="Escape"&&(document.activeElement===server||document.activeElement===local)){
      document.activeElement.value="";
      document.activeElement.dispatchEvent(new Event("input",{bubbles:true}));
    }
  });
  if(local){
    local.addEventListener("keydown",function(event){
      if(event.key!=="Enter"||event.isComposing)return;
      var term=local.value.trim().toLowerCase();
      if(!term)return;
      var tiles=Array.prototype.slice.call(root.querySelectorAll("[data-pos-menu-tile]"));
      var exact=tiles.filter(function(tile){
        return (tile.dataset.itemBarcode||"").toLowerCase()===term ||
          (tile.dataset.itemSku||"").toLowerCase()===term;
      });
      if(exact.length===1){
        event.preventDefault();
        exact[0].click();
        if(live)live.textContent="Product matched. Confirm quantity and add to basket.";
      } else if(server&&term.length>0&&tiles.every(function(tile){return tile.hidden;})){
        /* The local filter does not cover unloaded products. Search the whole
           outlet rather than silently pretending that no SKU exists. */
        event.preventDefault();
        server.value=local.value.trim();
        if(serverForm&&serverForm.requestSubmit)serverForm.requestSubmit();
        else if(serverForm)serverForm.submit();
      }
    });
  }
  /* Barcode scanners normally type a code followed by Enter. Resolve only
     unambiguous visible SKU/barcode matches; never silently sell an item. */
  if(server){
    server.addEventListener("keydown",function(event){
      if(event.key!=="Enter"||event.isComposing)return;
      var code=server.value.trim().toLowerCase();
      if(!code)return;
      var matched=Array.prototype.slice.call(root.querySelectorAll("[data-pos-menu-tile]")).filter(function(tile){
        return (tile.dataset.itemBarcode||"").toLowerCase()===code ||
          (tile.dataset.itemSku||"").toLowerCase()===code;
      });
      if(matched.length===1){
        event.preventDefault();
        /* Clicking the existing tile executes the same selection and
           modifier rendering path as selecting with a mouse. */
        matched[0].click();
        if(qty)qty.focus();
        if(live)live.textContent="Product found. Confirm quantity and choose Add to basket.";
      }
      /* An unknown barcode submits the full-catalogue GET search. */
    });
  }
  if(local&&server){
    /* The server endpoint searches the full catalogue; the local filter only
       covers products already loaded. Keep both explicitly distinguishable. */
    local.setAttribute("aria-label","Filter products displayed on this page");
    server.setAttribute("aria-label","Search all outlet products by name SKU or barcode");
  }
  if(serverForm){
    serverForm.addEventListener("submit",function(){
      var button=serverForm.querySelector('button[type="submit"]');
      if(button)button.setAttribute("aria-disabled","true");
    });
  }
  if(addForm){
    addForm.addEventListener("submit",function(e){
      if(addForm.dataset.submitting==="1"){e.preventDefault();return;}
      if(!product||!product.value){
        e.preventDefault();
        if(live)live.textContent="Choose a product before adding it.";
        if(product)product.focus();
        return;
      }
      addForm.dataset.submitting="1";
      var submit=addForm.querySelector('button[type="submit"]');
      if(submit){submit.dataset.originalLabel=submit.textContent;submit.setAttribute("aria-disabled","true");submit.textContent="Adding…";}
      window.addEventListener("pageshow",function(){
        addForm.dataset.submitting="";
        if(submit){submit.removeAttribute("aria-disabled");submit.textContent=submit.dataset.originalLabel||"Add to basket";}
      },{once:true});
    });
  }
  function adjustUnitStep(tile){
    if(!qty||!tile)return;
    var fractional=tile.dataset.fractionalQuantity==="1";
    qty.step=fractional?"0.001":"1";
    qty.min=fractional?"0.001":"1";
    if(!fractional&&Number(qty.value)%1!==0)qty.value="1";
  }
  // Enhance ordinary retail tiles into direct Add actions. Measured goods and
  // products with options keep the existing quantity/modifier confirmation.
  var modifierData=document.getElementById("staff-pos-menu-modifiers");
  var modifierMap=null;
  try{modifierMap=JSON.parse(modifierData.textContent);}catch(error){}
  root.querySelectorAll("[data-pos-menu-tile]").forEach(function(tile){
    var groups=modifierMap&&modifierMap[tile.dataset.itemId]||[];
    var direct=modifierMap!==null&&groups.length===0&&tile.dataset.fractionalQuantity!=="1";
    var label=tile.querySelector(".fizo-tile-add");
    if(direct&&addForm&&addForm.requestSubmit&&label)label.textContent="Add";
    tile.addEventListener("click",function(){
      adjustUnitStep(tile);
      if(direct&&addForm&&addForm.requestSubmit&&product&&product.value===tile.dataset.itemId){
        if(addForm.dataset.submitting==="1")return;
        qty.value="1";
        addForm.requestSubmit();
        return;
      }
      if(qty)qty.focus({preventScroll:true});
    });
  });
  if(product)product.addEventListener("change",function(){
    var tile=root.querySelector('[data-pos-menu-tile][data-item-id="'+product.value+'"]');
    adjustUnitStep(tile);
  });
  /* Quantity stepper submission is owned by order_detail_supermarket.html. */
})();
