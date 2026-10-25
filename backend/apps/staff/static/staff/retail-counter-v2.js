/* Checkout keyboard and pointer controls: non-destructive enhancements. */
(function(){
  "use strict";
  var root=document.querySelector(".fizo-checkout-catalogue");
  if(!root)return;
  // Keep the basket dominant while items are being scanned. Settlement uses
  // the existing permission-gated form, but opens as an on-demand drawer only
  // after the cashier presses Pay.
  var basket=document.querySelector(".fizo-checkout-basket");
  var paymentForm=document.querySelector("[data-pos-payment-form]");
  var paymentCard=paymentForm&&paymentForm.closest(".staff-card--pos");
  var cashPanel=document.querySelector("[data-retail-cash-panel]");
  var idlePayment=document.querySelector(".reference-payment-idle");

  function syncCashPanelVisibility(){
    if(!cashPanel)return;
    var method=document.querySelector('[data-pos-payment-form] select[name="method"]');
    cashPanel.hidden=!!method&&method.value!=="cash";
  }
  function closePaymentDrawer(){
    if(!paymentCard)return;
    paymentCard.classList.remove("is-open");
    paymentCard.setAttribute("aria-hidden","true");
  }
  function openPaymentDrawer(){
    if(!paymentCard)return;
    paymentCard.classList.add("is-open");
    paymentCard.setAttribute("aria-hidden","false");
    syncCashPanelVisibility();
    var method=paymentCard.querySelector('select[name="method"]');
    if(method)method.focus({preventScroll:true});
  }
  function setupPaymentDrawer(card,panel){
    if(!basket||!card)return;
    paymentCard=card;
    paymentForm=card.querySelector("[data-pos-payment-form]");
    cashPanel=panel||card.querySelector("[data-retail-cash-panel]")||cashPanel;
    card.classList.add("reference-payment-card");
    if(!basket.contains(card))basket.appendChild(card);
    if(cashPanel&&!card.contains(cashPanel)){
      cashPanel.classList.add("reference-cash-panel");
      card.appendChild(cashPanel);
    }else if(cashPanel){
      cashPanel.classList.add("reference-cash-panel");
    }
    if(!card.querySelector("[data-retail-payment-close]")){
      var close=document.createElement("button");
      close.type="button";
      close.className="reference-payment-close";
      close.setAttribute("data-retail-payment-close","");
      close.setAttribute("aria-label","Close payment");
      close.innerHTML='<i class="bi bi-x-lg" aria-hidden="true"></i>';
      close.addEventListener("click",closePaymentDrawer);
      card.insertBefore(close,card.firstChild);
    }
    if(card.querySelector('[role="alert"],.errorlist,.staff-alert--danger')){
      openPaymentDrawer();
    }else if(!card.classList.contains("is-open")){
      card.setAttribute("aria-hidden","true");
    }
    syncCashPanelVisibility();
  }

  if(paymentCard)setupPaymentDrawer(paymentCard,cashPanel);
  if(basket&&idlePayment&&!basket.contains(idlePayment))basket.appendChild(idlePayment);
  // Keep Hold/Clear actions accessible without showing their bulky staff card
  // in the cashier workspace. Reuse the existing, authenticated forms.
  var holdAction=document.querySelector('input[name="action"][value="hold_order"]');
  var holdForm=holdAction&&holdAction.form;
  var holdCard=holdForm&&holdForm.closest(".staff-card");
  if(holdForm&&basket&&basket.dataset.orderId){
    holdForm.addEventListener("submit",function(){
      // Tender preview is not a payment and must not be revived when a
      // customer returns to a held, partially paid basket.
      try{localStorage.removeItem("pos:tender:"+basket.dataset.orderId);}catch(error){}
    });
  }
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
  // Keep refunds, wholesale, quick-create and other uncommon authenticated
  // workflows available without letting them dominate the selling surface.
  var side=document.querySelector(".staff-pos-order-side");
  if(side&&basket){
    var more=document.createElement("details");
    more.className="fizo-retail-more-tools";
    var moreSummary=document.createElement("summary");
    moreSummary.textContent="More checkout tools";
    more.appendChild(moreSummary);
    Array.prototype.slice.call(side.children).forEach(function(child){
      if(child===basket||child===paymentCard||child===idlePayment)return;
      if(child.classList&&child.classList.contains("staff-alert"))return;
      more.appendChild(child);
    });
    if(more.children.length>1)basket.appendChild(more);
  }
  function bindRetailPayShortcuts(){
    paymentForm=document.querySelector("[data-pos-payment-form]");
    paymentCard=paymentForm&&paymentForm.closest(".staff-card--pos");
    var payLink=document.querySelector(".fizo-cashier-pay-cta");
    if(!paymentForm)return;
    if(payLink){
      var dueLabel=document.querySelector('[data-retail-summary="total"] strong');
      if(dueLabel){
        var label=payLink.querySelector("span");
        if(!label){
          label=document.createElement("span");
          var arrow=payLink.querySelector(".bi-arrow-right");
          if(arrow)payLink.insertBefore(label,arrow);
          else payLink.appendChild(label);
        }
        label.textContent="Pay "+dueLabel.textContent.trim();
      }
    }
    setupPaymentDrawer(paymentCard,document.querySelector("[data-retail-cash-panel]"));
    if(payLink&&payLink.dataset.retailPayBound!=="1"){
      payLink.dataset.retailPayBound="1";
      payLink.addEventListener("click",function(event){
        event.preventDefault();
        openPaymentDrawer();
      });
    }
    var paymentMethod=paymentForm.querySelector('select[name="method"]');
    document.querySelectorAll("[data-fizo-payment-method]").forEach(function(button){
      if(button.dataset.retailMethodBound==="1")return;
      button.dataset.retailMethodBound="1";
      button.addEventListener("click",function(){
        var method=document.querySelector('[data-pos-payment-form] select[name="method"]');
        if(!method)return;
        method.value=button.dataset.fizoPaymentMethod;
        method.dispatchEvent(new Event("change",{bubbles:true}));
        syncCashPanelVisibility();
        document.querySelectorAll("[data-fizo-payment-method]").forEach(function(other){
          other.setAttribute("aria-pressed",String(other===button));
        });
      });
      button.setAttribute("aria-pressed",String(!!paymentMethod&&paymentMethod.value===button.dataset.fizoPaymentMethod));
    });
  }
  document.addEventListener("retail:payment-controls-added",bindRetailPayShortcuts);
  document.addEventListener("keydown",function(event){
    if(event.key==="Escape"&&paymentCard&&paymentCard.classList.contains("is-open")){
      event.preventDefault();
      closePaymentDrawer();
    }
  });
  bindRetailPayShortcuts();
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
    topSearch.addEventListener("input",function(){
      if(scanMode||!local)return;
      local.value=topSearch.value;
      local.dispatchEvent(new Event("input",{bubbles:true}));
    });
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
        if(live)live.textContent="Product matched.";
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
        if(live)live.textContent="Product matched.";
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
  function refreshCheckout(){
            return fetch(window.location.href,{credentials:"same-origin",cache:"no-store",
          headers:{"Accept":"text/html"}}).then(function(response){
        if(!response.ok||response.redirected)throw new Error("Cannot refresh basket display.");
        return response.text();
      }).then(function(html){
        var remote=new DOMParser().parseFromString(html,"text/html");
        var fresh=remote.querySelector("#fizo-current-basket .fizo-retail-basket-items");
        var current=document.querySelector("#fizo-current-basket .fizo-retail-basket-items");
        if(!fresh||!current)throw new Error("Checkout confirmation is unavailable.");
        var activePayment=document.querySelector("[data-pos-payment-form]");
        var remotePayment=remote.querySelector("[data-pos-payment-form]");
        // Never manufacture a payment form from fetched HTML: its CSRF,
        // request identity, tender and cash-change listeners are bound when
        // Django renders checkout. A mismatch needs a normal navigation.
        var activatingPayment=!activePayment&&!!remotePayment;
        // Check the server-rendered sale identity before reconciling any
        // lines. A redirected or otherwise mismatched sale must not replace
        // the current customer's basket.
        var remoteBasket=remote.querySelector(".fizo-checkout-basket");
        if(!basket||!remoteBasket||
           basket.dataset.orderId!==remoteBasket.dataset.orderId){
          throw new Error("Checkout sale identity changed; reload the original sale.");
        }
        var completingPayment=!!activePayment&&!remotePayment&&
          remoteBasket.classList.contains("is-complete");
        if(activePayment&&!remotePayment&&!completingPayment){
          throw new Error("Checkout payment controls changed; reopen this sale to continue.");
        }
        if(activatingPayment&&!basket){
          throw new Error("Checkout basket container is unavailable.");
        }
        // Confirm all required payment-state data before touching the live
        // basket. A partial HTML response must never leave mixed totals.
        var cash=document.querySelector("[data-retail-cash-panel]");
        var nextCash=remote.querySelector("[data-retail-cash-panel]");
        if(!!cash!==!!nextCash && !activatingPayment && !completingPayment){
          throw new Error("Checkout cash controls changed; reopen this sale to continue.");
        }
        if(activatingPayment&&!nextCash){
          throw new Error("Checkout cash calculator was not returned.");
        }
        if(nextCash){
          var serverDue=nextCash.getAttribute("data-balance-due");
          if(serverDue===null||serverDue.trim()===""||
             !Number.isFinite(Number(serverDue))||Number(serverDue)<0){
            throw new Error("Checkout returned an invalid payment balance.");
          }
        }
        // Do not apply a mixture of old and new amounts if a server-side
        // permission, settlement, or layout change omitted a required field.
        var amountSelectors=[
          '[data-retail-summary="subtotal"] strong',
          '[data-retail-summary="discount"] strong',
          '[data-retail-summary="tax"] strong',
          '[data-retail-summary="total"] strong',
          ".staff-pos-totals-row__total strong"
        ];
        if(amountSelectors.some(function(selector){
          var before=document.querySelector(selector);
          var after=remote.querySelector(selector);
          return !!before!==!!after || (before&&after&&!after.textContent.trim());
        })){
          throw new Error("Incomplete checkout totals; reopen this sale to continue.");
        }
        if(activatingPayment){
          var freshCard=remotePayment.closest(".staff-card--pos");
          if(!freshCard)throw new Error("Payment details missing from checkout.");
          if(idlePayment&&idlePayment.parentNode)idlePayment.remove();
          // The empty basket did not contain a Pay CTA. Import the
          // server-authorized shortcut before binding its click handler.
          var liveSummary=basket.querySelector(".fizo-cashier-payment-summary");
          var remoteCta=remoteBasket.querySelector(".fizo-cashier-pay-cta");
          if(liveSummary&&remoteCta&&!liveSummary.querySelector(".fizo-cashier-pay-cta")){
            liveSummary.appendChild(document.importNode(remoteCta,true));
          }
          var newCard=document.importNode(freshCard,true);
          var newCash=document.importNode(nextCash,true);
          newCard.appendChild(newCash);
          basket.appendChild(newCard);
          setupPaymentDrawer(newCard,newCash);
          paymentForm=newCard.querySelector("[data-pos-payment-form]");
          paymentCard=newCard;
          cashPanel=newCash;
          activePayment=paymentForm;
          cash=newCash;
        }
        current.replaceChildren.apply(current,Array.from(fresh.childNodes).map(function(n){return document.importNode(n,true);}));
        document.dispatchEvent(new Event("retail:basket-lines-replaced"));
        if(completingPayment){
          // The final tender closes the sale. Reconcile that state in place:
          // keep the same page, remove tender controls and expose receipt /
          // next-customer actions rendered by Django.
          basket.classList.add("is-complete");
          var oldTools=basket.querySelector(".fizo-retail-basket-tools");
          if(oldTools&&oldTools.parentNode)oldTools.parentNode.removeChild(oldTools);
          var oldCta=basket.querySelector(".fizo-cashier-pay-cta");
          if(oldCta&&oldCta.parentNode)oldCta.parentNode.removeChild(oldCta);
          var oldComplete=basket.querySelector(".fizo-sale-complete-actions");
          if(oldComplete&&oldComplete.parentNode)oldComplete.parentNode.removeChild(oldComplete);
          var nextComplete=remoteBasket.querySelector(".fizo-sale-complete-actions");
          if(nextComplete)basket.appendChild(document.importNode(nextComplete,true));
          if(paymentCard&&paymentCard.parentNode)paymentCard.parentNode.removeChild(paymentCard);
          paymentForm=null;
          paymentCard=null;
          cashPanel=null;
          activePayment=null;
          cash=null;
        }
        ['[data-retail-summary="subtotal"] strong',
         '[data-retail-summary="discount"] strong',
         '[data-retail-summary="tax"] strong',
         '[data-retail-summary="total"] strong',".fizo-cashier-payment-summary strong",
         ".staff-pos-totals-row__total strong",".staff-pos-totals-row__meta",
         ".fizo-cashier-pay-cta span"].forEach(function(selector){
          var a=document.querySelector(selector),b=remote.querySelector(selector);
          if(a&&b)a.textContent=b.textContent;
        });
        if(activePayment&&remotePayment&&!completingPayment){
          var currentCard=activePayment.closest(".staff-card--pos");
          var nextCard=remotePayment.closest(".staff-card--pos");
          if(currentCard&&nextCard){
            var currentHint=currentCard.querySelector(".staff-pos-side-hint");
            var nextHint=nextCard.querySelector(".staff-pos-side-hint");
            if(currentHint&&nextHint)currentHint.textContent=nextHint.textContent;
            var currentKey=activePayment.querySelector('input[name="payment_request_key"]');
            var nextKey=remotePayment.querySelector('input[name="payment_request_key"]');
            if(currentKey&&nextKey)currentKey.value=nextKey.value;
            var currentPartial=currentCard.querySelector(".reference-partial-payment");
            var nextPartial=nextCard.querySelector(".reference-partial-payment");
            if(nextPartial){
              var importedPartial=document.importNode(nextPartial,true);
              if(currentPartial&&currentPartial.parentNode){
                currentPartial.parentNode.replaceChild(importedPartial,currentPartial);
              }else{
                var intro=currentCard.querySelector(".fizo-cashier-pay-intro");
                currentCard.insertBefore(importedPartial,intro||activePayment);
              }
            }else if(currentPartial&&currentPartial.parentNode){
              currentPartial.parentNode.removeChild(currentPartial);
            }
          }
        }
        if(cash&&nextCash){
          var oldDue=activatingPayment ? null : cash.getAttribute("data-balance-due");
          var amount=activePayment&&activePayment.querySelector('input[name="amount"]');
          var tender=cash.querySelector("[data-retail-cash-received]");
          if(amount&&remotePayment&&Number.isFinite(Number(oldDue))&&
             Number(amount.value)===Number(oldDue)&&
             (!tender||!tender.value.trim())){
            var remoteAmount=remotePayment.querySelector('input[name="amount"]');
            if(remoteAmount)amount.value=remoteAmount.value;
          }
          cash.setAttribute("data-balance-due",nextCash.getAttribute("data-balance-due"));
          cash.dispatchEvent(new Event("retail:balance-updated"));
        }
        if(activatingPayment){
          document.dispatchEvent(new Event("retail:payment-controls-added"));
        }
        // Refund/return controls live outside the basket, but their limits,
        // request identities and histories are server-authoritative. Replace
        // only these stable zones after the checkout identity/totals above
        // have passed validation.
        ["[data-retail-refund-zone]","[data-retail-return-zone]"].forEach(function(selector){
          var liveZone=document.querySelector(selector);
          var remoteZone=remote.querySelector(selector);
          if(!liveZone||!remoteZone){
            throw new Error("Checkout refund controls are incomplete; reload this sale safely.");
          }
          liveZone.replaceChildren.apply(
            liveZone,
            Array.from(remoteZone.childNodes).map(function(node){
              return document.importNode(node,true);
            })
          );
        });
        document.dispatchEvent(new Event("retail:refund-zones-replaced"));
        // The existing delegated +/- handler will manage new basket rows.
      });
  }
  window.retailRefreshCheckout=refreshCheckout;
  // A successful POST followed by an incomplete GET is ambiguous. Offer a
  // safe read-only reload; never replay the sale mutation.
  function showCheckoutRecovery(node,error){
    if(!node)return;
    node.textContent=(error&&error.message?error.message:"Basket confirmation unavailable.")+
      " Your sale may already be updated. ";
    var retry=document.createElement("button");
    retry.type="button";
    retry.className="staff-btn staff-btn--secondary";
    retry.textContent="Reload sale safely";
    retry.addEventListener("click",function(){window.location.reload();});
    node.appendChild(retry);
  }

  window.retailShowCheckoutRecovery=showCheckoutRecovery;

  // Django confirms each add and supplies payment controls when an empty
  // basket first becomes payable. Native submission remains a fallback only
  // for browsers without the supported asynchronous checkout APIs.
  if(addForm){
    addForm.addEventListener("submit",function(e){
      if(addForm.dataset.submitting==="1"){e.preventDefault();return;}
      if(!product||!product.value){
        e.preventDefault();
        if(live)live.textContent="Choose a product before adding it.";
        if(product)product.focus();
        return;
      }
      if(!addForm.checkValidity())return;
      var submit=addForm.querySelector('button[type="submit"]');
      var previous=submit&&submit.textContent;
      var asyncReady=!!(window.fetch&&window.FormData&&
        document.querySelector("#fizo-current-basket .fizo-retail-basket-items"));
      addForm.dataset.submitting="1";
      if(submit){submit.disabled=true;submit.textContent="Adding…";}
      function unlock(){
        delete addForm.dataset.submitting;
        if(submit){submit.disabled=false;submit.textContent=previous||"Add to basket";}
      }
      if(!asyncReady){
        window.addEventListener("pageshow",unlock,{once:true});
        return;
      }
      e.preventDefault();
      if(live)live.textContent="Adding item…";
      var csrf=addForm.querySelector('input[name="csrfmiddlewaretoken"]');
      var url=addForm.getAttribute("action")||window.location.pathname+window.location.search;
      fetch(url,{method:"POST",body:new FormData(addForm),credentials:"same-origin",
        redirect:"follow",headers:{"X-Requested-With":"XMLHttpRequest",
          "X-CSRFToken":csrf?csrf.value:""}})
      .then(function(response){
        if(response.redirected)throw new Error("Checkout session changed or access was redirected.");
        var type=(response.headers.get("Content-Type")||"").toLowerCase();
        if(!type.includes("application/json"))throw new Error("Unexpected checkout response.");
        return response.json().then(function(data){
          if(!response.ok||!data.ok)throw new Error(data.message||"Product could not be added.");
          return data;
        });
      }).then(function(){
        return refreshCheckout();
      }).then(function(){
        if(live)live.textContent="Item added to basket.";
      }).catch(function(error){
        // Never replay a POST whose response was lost: it may have committed.
        showCheckoutRecovery(live,error);
      }).then(unlock);
    });
    window.addEventListener("pageshow",function(){delete addForm.dataset.submitting;});
  }
  function approvedRefundFormConfig(form){
    if(form.matches("[data-retail-refund-form]")){
      return {
        keyName:"refund_request_key",
        statusSelector:"[data-retail-refund-status]",
        busy:"Refunding…",
        pending:"Recording manager-approved refund…",
        fallback:"Refund",
        error:"Refund could not be recorded."
      };
    }
    if(form.matches("[data-retail-line-refund-form]")){
      return {
        keyName:"retail_refund_request_key",
        statusSelector:"[data-retail-line-refund-status]",
        busy:"Refunding item…",
        pending:"Recording manager-approved return and refund…",
        fallback:"Record return and refund",
        error:"Return and refund could not be recorded."
      };
    }
    return null;
  }

  document.addEventListener("submit",function(event){
    var form=event.target;
    if(!(form instanceof HTMLFormElement))return;
    var config=approvedRefundFormConfig(form);
    if(!config)return;
    var asyncReady=!!(window.fetch&&window.FormData&&window.retailRefreshCheckout);
    if(!asyncReady)return;
    event.preventDefault();
    if(form.dataset.submitting==="1")return;
    if(!form.checkValidity()){
      form.reportValidity();
      return;
    }
    form.dataset.submitting="1";
    var submit=form.querySelector('button[type="submit"]');
    var previous=submit&&submit.textContent;
    var status=form.querySelector(config.statusSelector);
    if(submit){submit.disabled=true;submit.textContent=config.busy;}
    if(status)status.textContent=config.pending;
    var csrf=form.querySelector('input[name="csrfmiddlewaretoken"]');
    fetch(form.getAttribute("action")||window.location.pathname+window.location.search,{
      method:"POST",body:new FormData(form),credentials:"same-origin",redirect:"follow",
      headers:{"X-Requested-With":"XMLHttpRequest","X-CSRFToken":csrf?csrf.value:""}
    }).then(function(response){
      if(response.redirected)throw new Error("Checkout session changed or access was redirected.");
      var type=(response.headers.get("Content-Type")||"").toLowerCase();
      if(!type.includes("application/json"))throw new Error("Unexpected refund response.");
      return response.json().then(function(data){
        if(!response.ok||!data.ok)throw new Error(data.message||config.error);
        var key=form.querySelector('input[name="'+config.keyName+'"]');
        if(key&&data.next_request_key)key.value=data.next_request_key;
        var pin=form.querySelector('input[name="approver_pin"]');
        if(pin)pin.value="";
        return data;
      });
    }).then(function(data){
      return window.retailRefreshCheckout().then(function(){return data;});
    }).then(function(data){
      var refreshed=document.querySelector("[data-retail-finance-status]")||
        document.querySelector(config.statusSelector);
      if(refreshed)refreshed.textContent=data.message||"Refund recorded.";
    }).catch(function(error){
      var liveStatus=document.querySelector("[data-retail-finance-status]")||
        document.querySelector(config.statusSelector)||status;
      if(liveStatus)showCheckoutRecovery(liveStatus,error);
    }).then(function(){
      delete form.dataset.submitting;
      if(submit){submit.disabled=false;submit.textContent=previous||config.fallback;}
    });
  });

  var discountForm=document.querySelector("[data-retail-discount-form]");
  if(discountForm){
    discountForm.addEventListener("submit",function(e){
      if(discountForm.dataset.submitting==="1"){e.preventDefault();return;}
      if(!discountForm.checkValidity())return;
      var status=discountForm.querySelector("[data-retail-discount-status]");
      var submit=discountForm.querySelector('button[type="submit"]');
      var previous=submit&&submit.textContent;
      var asyncReady=!!(window.fetch&&window.FormData&&window.retailRefreshCheckout);
      discountForm.dataset.submitting="1";
      if(submit){submit.disabled=true;submit.textContent="Applying…";}
      function unlock(){
        delete discountForm.dataset.submitting;
        if(submit){submit.disabled=false;submit.textContent=previous||"Apply";}
      }
      if(!asyncReady){
        window.addEventListener("pageshow",unlock,{once:true});
        return;
      }
      e.preventDefault();
      if(status)status.textContent="Requesting manager-approved discount…";
      var csrf=discountForm.querySelector('input[name="csrfmiddlewaretoken"]');
      fetch(discountForm.getAttribute("action")||window.location.pathname+window.location.search,{
        method:"POST",body:new FormData(discountForm),credentials:"same-origin",redirect:"follow",
        headers:{"X-Requested-With":"XMLHttpRequest","X-CSRFToken":csrf?csrf.value:""}
      }).then(function(response){
        if(response.redirected)throw new Error("Checkout session changed or access was redirected.");
        var type=(response.headers.get("Content-Type")||"").toLowerCase();
        if(!type.includes("application/json"))throw new Error("Unexpected discount response.");
        return response.json().then(function(data){
          if(!response.ok||!data.ok)throw new Error(data.message||"Discount could not be applied.");
          var key=discountForm.querySelector('input[name="discount_request_key"]');
          if(key&&data.next_request_key)key.value=data.next_request_key;
          var pin=discountForm.querySelector('input[name="approver_pin"]');
          if(pin)pin.value="";
          return data;
        });
      }).then(function(data){
        return window.retailRefreshCheckout().then(function(){return data;});
      }).then(function(data){
        var amount=discountForm.querySelector('input[name="discount_amount"]');
        var percent=discountForm.querySelector('input[name="discount_percent"]');
        if(amount)amount.value="";
        if(percent)percent.value="";
        if(status)status.textContent=data.message||"Manager-approved line discount saved.";
      }).catch(function(error){
        if(status)showCheckoutRecovery(status,error);
      }).then(unlock);
    });
    window.addEventListener("pageshow",function(){delete discountForm.dataset.submitting;});
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
      if(addForm)addForm.classList.toggle("is-required",!direct);
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
    if(addForm&&tile){
      var groups=modifierMap&&modifierMap[tile.dataset.itemId]||[];
      var direct=modifierMap!==null&&groups.length===0&&tile.dataset.fractionalQuantity!=="1";
      addForm.classList.toggle("is-required",!direct);
    }
  });
  /* Quantity stepper submission is owned by order_detail_supermarket.html. */
})();
