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

  function refreshRetailZone(selector){
    return fetch(window.location.href,{
      credentials:"same-origin",
      cache:"no-store",
      headers:{"Accept":"text/html"}
    }).then(function(response){
      if(!response.ok||response.redirected){
        throw new Error("Cannot refresh sale details.");
      }
      return response.text();
    }).then(function(html){
      var remote=new DOMParser().parseFromString(html,"text/html");
      var live=document.querySelector(selector);
      var fresh=remote.querySelector(selector);
      var liveBasket=document.querySelector(".fizo-checkout-basket");
      var remoteBasket=remote.querySelector(".fizo-checkout-basket");
      if(!live||!fresh||!liveBasket||!remoteBasket||
         liveBasket.dataset.orderId!==remoteBasket.dataset.orderId){
        throw new Error("Sale details changed; reload this sale safely.");
      }
      live.replaceWith(document.importNode(fresh,true));
    });
  }
  window.retailRefreshZone=refreshRetailZone;


  document.addEventListener("submit",function(event){
    var form=event.target;
    if(!(form instanceof HTMLFormElement)||
       !form.matches("[data-retail-pickup-form]"))return;
    if(!(window.fetch&&window.FormData&&window.retailRefreshZone))return;
    event.preventDefault();
    if(form.dataset.submitting==="1")return;
    if(!form.checkValidity()){
      form.reportValidity();
      return;
    }
    form.dataset.submitting="1";
    var button=form.querySelector('button[type="submit"]');
    var previous=button&&button.textContent;
    var status=form.querySelector("[data-retail-pickup-status]");
    if(button){button.disabled=true;button.textContent="Saving…";}
    if(status)status.textContent="Saving pickup status…";
    var csrf=form.querySelector('input[name="csrfmiddlewaretoken"]');
    fetch(form.getAttribute("action")||window.location.pathname+window.location.search,{
      method:"POST",
      body:new FormData(form),
      credentials:"same-origin",
      redirect:"follow",
      headers:{
        "X-Requested-With":"XMLHttpRequest",
        "X-CSRFToken":csrf?csrf.value:""
      }
    }).then(function(response){
      if(response.redirected)throw new Error("Sale session changed or access was redirected.");
      var type=(response.headers.get("Content-Type")||"").toLowerCase();
      if(!type.includes("application/json"))throw new Error("Unexpected pickup response.");
      return response.json().then(function(data){
        if(!response.ok||!data.ok){
          var rejected=new Error(data.message||"Pickup could not be updated.");
          rejected.serverRejected=true;
          throw rejected;
        }
        return data;
      });
    }).then(function(data){
      return window.retailRefreshZone("[data-retail-pickup-zone]").then(function(){
        return data;
      });
    }).then(function(data){
      var live=document.querySelector("[data-retail-pickup-status]");
      if(live)live.textContent=data.message||"Pickup updated.";
    }).catch(function(error){
      var live=document.querySelector("[data-retail-pickup-status]")||status;
      if(error&&error.serverRejected){
        if(live)live.textContent=error.message;
      }else if(live){
        // A lost response may follow a committed handover. Never replay it.
        showCheckoutRecovery(live,error);
      }
    }).then(function(){
      delete form.dataset.submitting;
      if(button){button.disabled=false;button.textContent=previous||"Save";}
    });
  });

  document.addEventListener("submit",function(event){
    var form=event.target;
    if(!(form instanceof HTMLFormElement)||
       !form.matches("[data-retail-customer-form]"))return;
    if(!(window.fetch&&window.FormData&&window.retailRefreshZone))return;
    event.preventDefault();
    if(form.dataset.submitting==="1")return;
    if(!form.checkValidity()){
      form.reportValidity();
      return;
    }
    form.dataset.submitting="1";
    var button=form.querySelector('button[type="submit"]');
    var previous=button&&button.textContent;
    var status=document.querySelector("[data-retail-customer-status]");
    if(button){button.disabled=true;button.textContent="Saving…";}
    if(status)status.textContent="Saving customer link…";
    var csrf=form.querySelector('input[name="csrfmiddlewaretoken"]');
    fetch(form.getAttribute("action")||window.location.pathname+window.location.search,{
      method:"POST",
      body:new FormData(form),
      credentials:"same-origin",
      redirect:"follow",
      headers:{
        "X-Requested-With":"XMLHttpRequest",
        "X-CSRFToken":csrf?csrf.value:""
      }
    }).then(function(response){
      if(response.redirected)throw new Error("Sale session changed or access was redirected.");
      var type=(response.headers.get("Content-Type")||"").toLowerCase();
      if(!type.includes("application/json"))throw new Error("Unexpected customer-link response.");
      return response.json().then(function(data){
        if(!response.ok||!data.ok){
          var rejected=new Error(data.message||"Customer link could not be saved.");
          rejected.serverRejected=true;
          throw rejected;
        }
        return data;
      });
    }).then(function(data){
      var summary=document.querySelector("[data-retail-customer-summary]");
      if(summary&&data.customer_name){
        summary.textContent="Customer: "+data.customer_name;
      }else if(summary&&!data.customer_name&&summary.parentNode){
        summary.parentNode.removeChild(summary);
      }
      return window.retailRefreshZone("[data-retail-customer-zone]").then(function(){
        return data;
      });
    }).then(function(data){
      var live=document.querySelector("[data-retail-customer-status]");
      if(live)live.textContent=data.message||"Customer link saved.";
    }).catch(function(error){
      var live=document.querySelector("[data-retail-customer-status]")||status;
      if(error&&error.serverRejected){
        if(live)live.textContent=error.message;
      }else if(live){
        // The customer link may already be committed; never repeat the POST.
        showCheckoutRecovery(live,error);
      }
    }).then(function(){
      delete form.dataset.submitting;
      if(button){button.disabled=false;button.textContent=previous||"Save customer link";}
    });
  });

  // Quick-register a genuinely missing product without refreshing the till.
  // The server-side request key remains the idempotency boundary; an ambiguous
  // response is never automatically replayed.
  var quickForm=document.querySelector("[data-fizo-quick-product-form]");
  if(quickForm){
    quickForm.addEventListener("submit",function(event){
      if(quickForm.dataset.submitting==="1"){event.preventDefault();return;}
      if(!quickForm.checkValidity())return;
      var asyncReady=!!(window.fetch&&window.FormData&&window.retailRefreshCheckout);
      quickForm.dataset.submitting="1";
      var submit=quickForm.querySelector('button[type="submit"]');
      var previous=submit&&submit.textContent;
      var status=quickForm.querySelector("[data-fizo-quick-product-status]");
      if(submit){submit.disabled=true;submit.textContent="Saving product…";}
      function unlock(){
        delete quickForm.dataset.submitting;
        if(submit){submit.disabled=false;submit.textContent=previous||"Save product & add to basket";}
      }
      if(!asyncReady){
        window.addEventListener("pageshow",unlock,{once:true});
        return;
      }
      event.preventDefault();
      if(status)status.textContent="Saving product and adding it to this basket…";
      var csrf=quickForm.querySelector('input[name="csrfmiddlewaretoken"]');
      fetch(quickForm.getAttribute("action")||window.location.pathname+window.location.search,{
        method:"POST",body:new FormData(quickForm),credentials:"same-origin",redirect:"follow",
        headers:{"X-Requested-With":"XMLHttpRequest","X-CSRFToken":csrf?csrf.value:""}
      }).then(function(response){
        if(response.redirected)throw new Error("Checkout session changed or access was redirected.");
        var type=(response.headers.get("Content-Type")||"").toLowerCase();
        if(!type.includes("application/json"))throw new Error("Unexpected quick-product response.");
        return response.json().then(function(data){
          if(!response.ok||!data.ok){
            var rejected=new Error(data.message||"Product could not be saved.");
            rejected.serverRejected=true;
            throw rejected;
          }
          var key=quickForm.querySelector('input[name="quick_product_request_key"]');
          if(key&&data.next_request_key)key.value=data.next_request_key;
          return data;
        });
      }).then(function(data){
        return window.retailRefreshCheckout().then(function(){return data;});
      }).then(function(data){
        ["name","unit_price","barcode"].forEach(function(name){
          var input=quickForm.querySelector('[name="'+name+'"]');
          if(input)input.value="";
        });
        var quantity=quickForm.querySelector('input[name="quantity"]');
        if(quantity)quantity.value="1";
        var live=document.querySelector("[data-fizo-quick-product-status]")||status;
        if(live)live.textContent=data.message||"Product saved and added to basket.";
      }).catch(function(error){
        var live=document.querySelector("[data-fizo-quick-product-status]")||status;
        if(error&&error.serverRejected){
          if(live)live.textContent=error.message;
        }else if(live){
          showCheckoutRecovery(live,error);
        }
      }).then(unlock);
    });
    window.addEventListener("pageshow",function(){delete quickForm.dataset.submitting;});
  }

  // Cashiers and barcode scanners can generate mutations much faster than a
  // network round-trip. Preserve every accepted scan/tap in FIFO order instead
  // of dropping events behind a single-flight "submitting" flag. POSTs remain
  // serialized because the server locks the order row, while expensive basket
  // HTML reconciliation is coalesced until the queue drains.
  var retailAddQueue=[];
  var retailAddRunning=false;
  var retailAddRefreshRunning=false;
  var retailAddDirty=false;

  function retailAddQueueStatus(node,message){
    if(!node)return;
    var waiting=retailAddQueue.length+(retailAddRunning?1:0);
    node.textContent=message+(waiting>1?" · "+waiting+" items queued":"");
  }

  function drainRetailAddQueue(){
    if(retailAddRunning||retailAddRefreshRunning)return;
    if(!retailAddQueue.length){
      if(!retailAddDirty)return;
      retailAddRefreshRunning=true;
      refreshCheckout().then(function(){
        retailAddDirty=false;
        if(live)live.textContent="Basket caught up with all queued items.";
      }).catch(function(error){
        showCheckoutRecovery(live,error);
      }).then(function(){
        retailAddRefreshRunning=false;
        if(retailAddQueue.length)drainRetailAddQueue();
      });
      return;
    }
    var job=retailAddQueue.shift();
    retailAddRunning=true;
    retailAddQueueStatus(job.status,"Adding item…");
    fetch(job.url,{
      method:"POST",
      body:job.body,
      credentials:"same-origin",
      redirect:"follow",
      headers:{
        "X-Requested-With":"XMLHttpRequest",
        "X-CSRFToken":job.csrf||""
      }
    }).then(function(response){
      if(response.redirected)throw new Error("Checkout session changed or access was redirected.");
      var type=(response.headers.get("Content-Type")||"").toLowerCase();
      if(!type.includes("application/json"))throw new Error("Unexpected checkout response.");
      return response.json().then(function(data){
        if(!response.ok||!data.ok){
          var rejected=new Error(data.message||"Product could not be added.");
          rejected.serverRejected=true;
          throw rejected;
        }
        return data;
      });
    }).then(function(data){
      retailAddDirty=true;
      if(job.accepted)job.accepted(data);
      retailAddRunning=false;
      drainRetailAddQueue();
    }).catch(function(error){
      retailAddRunning=false;
      // A lost response may follow a committed POST. Stop later queued writes
      // rather than replaying or reordering them behind an ambiguous mutation.
      retailAddQueue.length=0;
      if(error&&error.serverRejected){
        if(job.status)job.status.textContent=error.message;
      }else{
        showCheckoutRecovery(job.status||live,error);
      }
    });
  }

  function enqueueRetailAdd(form,status,accepted,overrides){
    var csrf=form.querySelector('input[name="csrfmiddlewaretoken"]');
    var body=new FormData(form); // snapshot now; later scans may change inputs
    if(overrides){
      Object.keys(overrides).forEach(function(name){
        body.set(name,String(overrides[name]));
      });
    }
    retailAddQueue.push({
      url:form.getAttribute("action")||window.location.pathname+window.location.search,
      body:body,
      csrf:csrf?csrf.value:"",
      status:status||live,
      accepted:accepted||null
    });
    retailAddQueueStatus(status||live,"Queued for basket");
    drainRetailAddQueue();
  }

  window.retailEnqueueAddMutation=enqueueRetailAdd;

  // Django confirms each add and supplies payment controls when an empty
  // basket first becomes payable. Native submission remains a fallback only
  // for browsers without the supported asynchronous checkout APIs.
  if(addForm){
    addForm.addEventListener("submit",function(e){
      if(!product||!product.value){
        e.preventDefault();
        if(live)live.textContent="Choose a product before adding it.";
        if(product)product.focus();
        return;
      }
      if(!addForm.checkValidity())return;
      var asyncReady=!!(window.fetch&&window.FormData&&
        document.querySelector("#fizo-current-basket .fizo-retail-basket-items"));
      if(!asyncReady)return;
      e.preventDefault();
      enqueueRetailAdd(addForm,live,function(){
        if(live)retailAddQueueStatus(live,"Item accepted");
      });
    });
  }
  document.addEventListener("submit",function(event){
    var form=event.target;
    if(!(form instanceof HTMLFormElement)||!form.matches("[data-retail-group-form]"))return;
    if(!form.checkValidity())return;
    var asyncReady=!!(window.fetch&&window.FormData&&window.retailEnqueueAddMutation);
    if(!asyncReady)return;
    event.preventDefault();
    var status=form.querySelector("[data-retail-group-status]");
    window.retailEnqueueAddMutation(form,status,function(data){
      if(status)status.textContent=data.message||"Group accepted.";
    });
  });

  document.addEventListener("submit",function(event){
    var form=event.target;
    if(!(form instanceof HTMLFormElement)||
       !form.matches("[data-retail-void-line-form]"))return;
    var asyncReady=!!(window.fetch&&window.FormData&&window.retailRefreshCheckout);
    if(!asyncReady)return;
    event.preventDefault();
    if(form.dataset.submitting==="1")return;
    form.dataset.submitting="1";
    var button=form.querySelector('button[type="submit"]');
    var status=document.querySelector("[data-retail-basket-mutation-status]");
    if(button)button.disabled=true;
    if(status)status.textContent="Removing item…";
    var csrf=form.querySelector('input[name="csrfmiddlewaretoken"]');
    fetch(form.getAttribute("action")||window.location.pathname+window.location.search,{
      method:"POST",body:new FormData(form),credentials:"same-origin",redirect:"follow",
      headers:{"X-Requested-With":"XMLHttpRequest","X-CSRFToken":csrf?csrf.value:""}
    }).then(function(response){
      if(response.redirected)throw new Error("Checkout session changed or access was redirected.");
      var type=(response.headers.get("Content-Type")||"").toLowerCase();
      if(!type.includes("application/json"))throw new Error("Unexpected item-removal response.");
      return response.json().then(function(data){
        if(!response.ok||!data.ok){
          var rejected=new Error(data.message||"Item could not be removed.");
          rejected.serverRejected=true;
          rejected.refundRequired=!!data.refund_required;
          throw rejected;
        }
        return data;
      });
    }).then(function(data){
      return window.retailRefreshCheckout().then(function(){return data;});
    }).then(function(data){
      var live=document.querySelector("[data-retail-basket-mutation-status]");
      if(live)live.textContent=data.message||"Item removed from basket.";
    }).catch(function(error){
      var live=document.querySelector("[data-retail-basket-mutation-status]")||status;
      if(error&&error.serverRejected){
        if(live){
          live.textContent=error.message;
          if(error.refundRequired){
            var refund=document.querySelector("[data-retail-refund-form]");
            if(refund){
              var open=document.createElement("button");
              open.type="button";
              open.className="staff-btn staff-btn--secondary ms-2";
              open.textContent="Open refund controls";
              open.addEventListener("click",function(){
                refund.scrollIntoView({behavior:"smooth",block:"center"});
                var amount=refund.querySelector('input[name="amount"]');
                if(amount)amount.focus({preventScroll:true});
              });
              live.appendChild(document.createTextNode(" "));
              live.appendChild(open);
            }
          }
        }
      }else if(live){
        showCheckoutRecovery(live,error);
      }
    }).then(function(){
      delete form.dataset.submitting;
      if(button)button.disabled=false;
    });
  });

  document.addEventListener("submit",function(event){
    var form=event.target;
    if(!(form instanceof HTMLFormElement)||
       !form.matches("[data-retail-line-return-form]"))return;
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
    var status=form.querySelector("[data-retail-line-return-status]");
    if(submit){submit.disabled=true;submit.textContent="Recording…";}
    if(status)status.textContent="Recording physical return…";
    var csrf=form.querySelector('input[name="csrfmiddlewaretoken"]');
    fetch(form.getAttribute("action")||window.location.pathname+window.location.search,{
      method:"POST",body:new FormData(form),credentials:"same-origin",redirect:"follow",
      headers:{"X-Requested-With":"XMLHttpRequest","X-CSRFToken":csrf?csrf.value:""}
    }).then(function(response){
      if(response.redirected)throw new Error("Checkout session changed or access was redirected.");
      var type=(response.headers.get("Content-Type")||"").toLowerCase();
      if(!type.includes("application/json"))throw new Error("Unexpected return response.");
      return response.json().then(function(data){
        if(!response.ok||!data.ok){
          var rejected=new Error(data.message||"Physical return could not be recorded.");
          rejected.serverRejected=true;
          throw rejected;
        }
        var key=form.querySelector('input[name="line_return_request_key"]');
        if(key&&data.next_request_key)key.value=data.next_request_key;
        return data;
      });
    }).then(function(data){
      return window.retailRefreshCheckout().then(function(){return data;});
    }).then(function(data){
      var live=document.querySelector("[data-retail-finance-status]")||
        document.querySelector("[data-retail-line-return-status]");
      if(live)live.textContent=data.message||"Physical return recorded.";
    }).catch(function(error){
      var live=document.querySelector("[data-retail-finance-status]")||
        document.querySelector("[data-retail-line-return-status]")||status;
      if(error&&error.serverRejected){
        if(live)live.textContent=error.message;
      }else if(live){
        showCheckoutRecovery(live,error);
      }
    }).then(function(){
      delete form.dataset.submitting;
      if(submit){submit.disabled=false;submit.textContent=previous||"Return";}
    });
  });

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

  document.addEventListener("submit",function(event){
    var form=event.target;
    if(!(form instanceof HTMLFormElement)||
       !form.matches("[data-retail-promotion-form]"))return;
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
    var status=form.querySelector("[data-retail-promotion-status]")||
      form.querySelector("[data-hospitality-promotion-status]");
    var actionInput=form.querySelector('input[name="action"]');
    var removing=!!(actionInput&&actionInput.value==="remove_promotion");
    if(submit){submit.disabled=true;submit.textContent=removing?"Removing…":"Applying…";}
    if(status)status.textContent=removing?"Removing offer…":"Applying offer…";
    var csrf=form.querySelector('input[name="csrfmiddlewaretoken"]');
    fetch(form.getAttribute("action")||window.location.pathname+window.location.search,{
      method:"POST",body:new FormData(form),credentials:"same-origin",redirect:"follow",
      headers:{"X-Requested-With":"XMLHttpRequest","X-CSRFToken":csrf?csrf.value:""}
    }).then(function(response){
      if(response.redirected)throw new Error("Checkout session changed or access was redirected.");
      var type=(response.headers.get("Content-Type")||"").toLowerCase();
      if(!type.includes("application/json"))throw new Error("Unexpected offer response.");
      return response.json().then(function(data){
        if(!response.ok||!data.ok){
          var rejected=new Error(data.message||(removing?"Offer could not be removed.":"Offer could not be applied."));
          rejected.serverRejected=true;
          throw rejected;
        }
        return data;
      });
    }).then(function(data){
      return window.retailRefreshCheckout().then(function(){return data;});
    }).then(function(data){
      var live=document.querySelector("[data-retail-promotion-status]")||
        document.querySelector("[data-hospitality-promotion-status]")||status;
      if(live)live.textContent=data.message||(removing?"Offer removed.":"Offer applied.");
    }).catch(function(error){
      var live=document.querySelector("[data-retail-promotion-status]")||
        document.querySelector("[data-hospitality-promotion-status]")||status;
      if(error&&error.serverRejected){
        if(live)live.textContent=error.message;
      }else if(live){
        showCheckoutRecovery(live,error);
      }
    }).then(function(){
      delete form.dataset.submitting;
      if(submit){submit.disabled=false;submit.textContent=previous||(removing?"Remove offer":"Apply");}
    });
  });

  document.addEventListener("submit",function(event){
    var form=event.target;
    if(!(form instanceof HTMLFormElement)||
       !form.matches("[data-retail-wholesale-form]"))return;
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
    var status=form.querySelector("[data-retail-wholesale-status]");
    if(submit){submit.disabled=true;submit.textContent="Applying…";}
    if(status)status.textContent="Applying approved wholesale price…";
    var csrf=form.querySelector('input[name="csrfmiddlewaretoken"]');
    fetch(form.getAttribute("action")||window.location.pathname+window.location.search,{
      method:"POST",body:new FormData(form),credentials:"same-origin",redirect:"follow",
      headers:{"X-Requested-With":"XMLHttpRequest","X-CSRFToken":csrf?csrf.value:""}
    }).then(function(response){
      if(response.redirected)throw new Error("Checkout session changed or access was redirected.");
      var type=(response.headers.get("Content-Type")||"").toLowerCase();
      if(!type.includes("application/json"))throw new Error("Unexpected wholesale response.");
      return response.json().then(function(data){
        if(!response.ok||!data.ok){
          var rejected=new Error(data.message||"Wholesale price could not be applied.");
          rejected.serverRejected=true;
          throw rejected;
        }
        return data;
      });
    }).then(function(data){
      return window.retailRefreshCheckout().then(function(){return data;});
    }).then(function(data){
      var live=document.querySelector("[data-retail-wholesale-status]")||status;
      if(live)live.textContent=data.message||"Wholesale unit price approved and recalculated.";
    }).catch(function(error){
      var live=document.querySelector("[data-retail-wholesale-status]")||status;
      if(error&&error.serverRejected){
        if(live)live.textContent=error.message;
      }else if(live){
        // Never repeat a price mutation after an ambiguous response.
        showCheckoutRecovery(live,error);
      }
    }).then(function(){
      delete form.dataset.submitting;
      if(submit){submit.disabled=false;submit.textContent=previous||"Manager: apply wholesale price";}
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
  // Enhance ordinary retail tiles into direct Add actions. The generic
  // catalogue owns click/selection; retail reacts only after selection is
  // published, so mutation no longer depends on listener registration order.
  var modifierData=document.getElementById("staff-pos-menu-modifiers");
  var modifierMap=null;
  try{modifierMap=JSON.parse(modifierData.textContent);}catch(error){}
  root.querySelectorAll("[data-pos-menu-tile]").forEach(function(tile){
    var groups=modifierMap&&modifierMap[tile.dataset.itemId]||[];
    var direct=modifierMap!==null&&groups.length===0&&tile.dataset.fractionalQuantity!=="1";
    tile.dataset.retailDirectAdd=direct?"1":"0";
    var label=tile.querySelector(".fizo-tile-add");
    if(direct&&addForm&&addForm.requestSubmit&&label)label.textContent="Add";
  });
  root.addEventListener("pos:menu-item-selected",function(event){
    var tile=event.target&&event.target.closest&&event.target.closest("[data-pos-menu-tile]");
    if(!tile||!root.contains(tile))return;
    var direct=tile.dataset.retailDirectAdd==="1";
    adjustUnitStep(tile);
    if(addForm)addForm.classList.toggle("is-required",!direct);
    if(direct&&addForm&&window.retailEnqueueAddMutation){
      // Never depend on the shared select's current value for rapid alternating
      // taps. Snapshot the tile identity directly into this queued mutation.
      window.retailEnqueueAddMutation(addForm,live,function(){
        if(live)retailAddQueueStatus(live,"Item accepted");
      },{
        menu_item:tile.dataset.itemId,
        quantity:"1",
        action:"add_line"
      });
      return;
    }
    if(qty)qty.focus({preventScroll:true});
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
  // Basket quantity mutation belongs to this controller with the other
  // modern retail checkout mutations; the template now only renders controls.
  // Keep every visible checkout amount synchronized with the authoritative
  // response. This is one renderer for POST success and GET reconciliation.
  function updateBasketAmounts(values) {
    var currency = values.currency;
    // Follow the changed balance only if the form still contains the old
    // automatic due amount. Never overwrite a manually entered partial tender.
    var cashPanel = document.querySelector("[data-retail-cash-panel]");
    var oldDue = cashPanel && cashPanel.getAttribute("data-balance-due");
    var payment = document.querySelector('[data-pos-payment-form] input[name="amount"]');
    var enteredCash = cashPanel && cashPanel.querySelector("[data-retail-cash-received]");
    if (payment && oldDue != null && values.due != null &&
        Number.isFinite(Number(oldDue)) && Number(payment.value) === Number(oldDue) &&
        (!enteredCash || !enteredCash.value.trim())) {
      payment.value = values.due;
    }
    var show = function (selector, amount) {
      var node = document.querySelector(selector);
      if (node && amount != null) node.textContent = currency + " " + amount;
    };
    show('[data-retail-summary="subtotal"] strong', values.subtotal);
    show('[data-retail-summary="discount"] strong', values.discount);
    show('[data-retail-summary="tax"] strong', values.tax);
    show('[data-retail-summary="total"] strong', values.due);
    show(".fizo-cashier-payment-summary strong", values.due);
    var header = document.querySelector(".staff-pos-totals-row__total strong");
    if (header && values.total != null) header.textContent = values.total;
    var meta = document.querySelector(".staff-pos-totals-row__meta");
    if (meta && values.subtotal != null && values.discount != null && values.tax != null) {
      meta.textContent = "Sub " + values.subtotal + " · Disc " + values.discount + " · Tax " + values.tax;
    }
    var payLabel = document.querySelector(".fizo-cashier-pay-cta span");
    if (payLabel && values.due != null) payLabel.textContent = "Pay " + currency + " " + values.due;
    var cash = document.querySelector("[data-retail-cash-panel]");
    if (cash && values.due != null) {
      cash.setAttribute("data-balance-due", values.due);
      cash.dispatchEvent(new Event("retail:balance-updated"));
    }
  }

  /* Each basket quantity update is single-flight, whether submitted using
     +/- buttons, the keyboard, or the Save button. */
  function reconcileFromServer() {
    return fetch(window.location.href, {
      credentials: "same-origin", cache: "no-store",
      headers: {"Accept": "text/html"}
    }).then(function (response) {
      if (!response.ok || response.redirected) throw new Error("Checkout cannot be read.");
      return response.text();
    }).then(function (html) {
      var page = new DOMParser().parseFromString(html, "text/html");
      var remoteBasket = page.querySelector("#fizo-current-basket");
      if (!remoteBasket) throw new Error("Basket missing in checkout response.");
      document.querySelectorAll("[data-fizo-qty-form]").forEach(function (form) {
        var id = form.querySelector('input[name="line_id"]');
        if (!id) return;
        var remoteForm = Array.prototype.find.call(
          remoteBasket.querySelectorAll("[data-fizo-qty-form]"),
          function (candidate) {
            var candidateId = candidate.querySelector('input[name="line_id"]');
            return candidateId && candidateId.value === id.value;
          }
        );
        if (!remoteForm) return;
        var input = form.querySelector('input[name="quantity"]');
        var remoteInput = remoteForm.querySelector('input[name="quantity"]');
        if (input && remoteInput) {
          input.value = remoteInput.value;
          input.dataset.confirmedQuantity = remoteInput.value;
        }
        var row = form.closest(".fizo-retail-basket-row");
        var remoteRow = remoteForm.closest(".fizo-retail-basket-row");
        var amount = row && row.querySelector(".fizo-retail-basket-row__amount");
        var remoteAmount = remoteRow && remoteRow.querySelector(".fizo-retail-basket-row__amount");
        if (amount && remoteAmount) amount.textContent = remoteAmount.textContent;
      });
      // Copy rendered amounts from the fresh server page, including totals
      // changed by discounts or previously recorded partial payments.
      [".staff-pos-totals-row__total strong", ".staff-pos-totals-row__meta",
       ".fizo-cashier-payment-summary strong", '[data-retail-summary="subtotal"] strong',
       '[data-retail-summary="discount"] strong', '[data-retail-summary="tax"] strong',
       '[data-retail-summary="total"] strong'].forEach(function (selector) {
        var local = document.querySelector(selector);
        var remote = page.querySelector(selector);
        if (local && remote) local.textContent = remote.textContent;
      });
      var currentDue = document.querySelector('[data-retail-summary="total"] strong');
      var payLabel = document.querySelector(".fizo-cashier-pay-cta span");
      if (currentDue && payLabel) payLabel.textContent = "Pay " + currentDue.textContent.trim();
      var cash = document.querySelector("[data-retail-cash-panel]");
      var remoteCash = page.querySelector("[data-retail-cash-panel]");
      if (cash && remoteCash) {
        var localPayment = document.querySelector('[data-pos-payment-form] input[name="amount"]');
        var remotePayment = page.querySelector('[data-pos-payment-form] input[name="amount"]');
        var cashTender = cash.querySelector("[data-retail-cash-received]");
        var previousDue = cash.getAttribute("data-balance-due");
        if (localPayment && remotePayment && previousDue != null &&
            Number.isFinite(Number(previousDue)) &&
            Number(localPayment.value) === Number(previousDue) &&
            (!cashTender || !cashTender.value.trim())) {
          localPayment.value = remotePayment.value;
        }
        cash.setAttribute("data-balance-due", remoteCash.getAttribute("data-balance-due"));
        cash.dispatchEvent(new Event("retail:balance-updated"));
      }
    });
  }
  function bindQuantityForms() {
    document.querySelectorAll("[data-fizo-qty-form]").forEach(function (form) {
      if (form.dataset.quantityBound === "1") return;
      form.dataset.quantityBound = "1";
      var input = form.querySelector('input[name="quantity"]');
      if (!input) return;
      input.dataset.confirmedQuantity = input.value;
      form.dataset.projectedQuantity = input.value;
      form._retailQtyQueue = [];
      form._retailQtyRunning = false;

      function errorBoxForForm() {
        var box = form.parentNode.querySelector("[data-inline-qty-status]");
        if (!box) {
          box = document.createElement("p");
          box.setAttribute("data-inline-qty-status", "");
          box.setAttribute("role", "status");
          box.setAttribute("aria-live", "polite");
          form.parentNode.appendChild(box);
        }
        return box;
      }

      function runQuantityQueue() {
        if (form._retailQtyRunning || !form._retailQtyQueue.length) return;
        var job = form._retailQtyQueue.shift();
        form._retailQtyRunning = true;
        var errorBox = errorBoxForForm();
        errorBox.textContent = form._retailQtyQueue.length
          ? "Updating basket · " + (form._retailQtyQueue.length + 1) + " quantity changes queued"
          : "Updating basket…";
        var csrf = form.querySelector('input[name="csrfmiddlewaretoken"]');
        fetch(form.getAttribute("action") || window.location.pathname + window.location.search, {
          method: "POST",
          body: job.body,
          credentials: "same-origin",
          redirect: "follow",
          headers: {
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRFToken": csrf ? csrf.value : ""
          }
        }).then(function (response) {
          var type = response.headers.get("Content-Type") || "";
          if (response.redirected || !type.toLowerCase().includes("application/json")) {
            throw new Error("Checkout rejected the update (HTTP " + response.status +
              "). The session may have expired or the action was redirected.");
          }
          if (!response.ok && response.status !== 422 && response.status !== 403 &&
              response.status !== 404 && response.status !== 409) {
            throw new Error("Checkout returned HTTP " + response.status + ".");
          }
          return response.json();
        }).then(function (data) {
          if (!data.ok) {
            form._retailQtyQueue.length = 0;
            input.value = input.dataset.confirmedQuantity || input.defaultValue;
            form.dataset.projectedQuantity = input.value;
            errorBox.textContent = data.message || "The quantity was not changed.";
            if (data.refund_required) {
              var refundForm = document.querySelector("[data-retail-refund-form]");
              if (refundForm) {
                var openRefund = document.createElement("button");
                openRefund.type = "button";
                openRefund.className = "staff-btn staff-btn--secondary ms-2";
                openRefund.textContent = "Open refund controls";
                openRefund.addEventListener("click", function () {
                  refundForm.scrollIntoView({behavior: "smooth", block: "center"});
                  var refundAmount = refundForm.querySelector('input[name="amount"]');
                  if (refundAmount) refundAmount.focus({preventScroll: true});
                });
                errorBox.appendChild(document.createTextNode(" "));
                errorBox.appendChild(openRefund);
              }
            }
            return;
          }
          input.dataset.confirmedQuantity = data.quantity;
          if (!form._retailQtyQueue.length) {
            input.value = form.dataset.projectedQuantity || data.quantity;
          }
          var row = form.closest(".fizo-retail-basket-row");
          var amount = row && row.querySelector(".fizo-retail-basket-row__amount");
          if (amount) amount.textContent = data.currency + " " + data.line_total;
          updateBasketAmounts(data);
          errorBox.textContent = form._retailQtyQueue.length
            ? "Basket updating · " + form._retailQtyQueue.length + " changes queued"
            : "Basket updated.";
        }).catch(function (error) {
          form._retailQtyQueue.length = 0;
          var why = error && error.message ? error.message : "Unknown network error";
          return reconcileFromServer().then(function () {
            input.dataset.confirmedQuantity = input.value;
            form.dataset.projectedQuantity = input.value;
            errorBox.textContent = "Basket verified after connection delay.";
          }).catch(function () {
            input.value = input.dataset.confirmedQuantity || input.defaultValue;
            form.dataset.projectedQuantity = input.value;
            errorBox.textContent = "Could not verify quantity. " + why;
          });
        }).then(function () {
          form._retailQtyRunning = false;
          runQuantityQueue();
        });
      }

      function enqueueQuantityTarget(target) {
        var body = new FormData(form);
        body.set("quantity", String(target));
        form._retailQtyQueue.push({body: body, target: String(target)});
        runQuantityQueue();
      }

      form._retailEnqueueQuantityTarget = enqueueQuantityTarget;

      form.addEventListener("submit", function (event) {
        if (!form.checkValidity()) return;
        if (!window.fetch || !window.FormData) return;
        event.preventDefault();
        form.dataset.projectedQuantity = input.value;
        enqueueQuantityTarget(input.value);
      });
    });
  }
  document.addEventListener("retail:basket-lines-replaced", bindQuantityForms);
  bindQuantityForms();

  /* Ordinary products move in whole units; measured goods retain 0.001 steps.
     Fast +/- clicks update the projected quantity immediately and queue every
     resulting target; no click is dropped while an earlier POST is in flight. */
  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-fizo-step]");
    if (!button) return;
    var form = button.closest("[data-fizo-qty-form]");
    if (!form) return;
    var input = form.querySelector('input[name="quantity"]');
    if (!input || !form._retailEnqueueQuantityTarget) return;
    var current = Number(form.dataset.projectedQuantity || input.value);
    var delta = Number(button.dataset.fizoStep);
    if (!Number.isFinite(current) || !Number.isFinite(delta)) return;
    var step = Number(input.step || "1");
    if (!Number.isFinite(step) || step <= 0) step = 1;
    var next = step < 1
      ? Math.round((current + delta * step) * 1000) / 1000
      : Math.round(current + delta);
    if (next < Number(input.min || step)) return;
    form.dataset.projectedQuantity = String(next);
    input.value = String(next);
    form._retailEnqueueQuantityTarget(String(next));
  });


  // Scan, settlement and cash-tender behavior belong to the same modern
  // checkout controller as add/quantity/refund mutations. This nested scope
  // prevents variable collisions while keeping one file as the behavior owner.
  (function () {
    "use strict";
  
    /* The visible header owns search/scan focus and payment-method selection.
       This wrapper only protects the real authenticated POST forms. */
    var scanForm = document.querySelector("[data-retail-scan-form]");
    if (scanForm) {
      var scanInput = scanForm.querySelector('input[name="code"]');
      var scanQuantity = scanForm.querySelector('input[name="quantity"]');
      var scanButton = scanForm.querySelector("[data-retail-scan-submit]");
      var scanStatus = document.querySelector("[data-retail-scan-status]");
      if (scanInput) {
        scanInput.setAttribute("aria-label", "Barcode or product lookup code");
        scanInput.setAttribute("enterkeyhint", "done");
        // Resume scanner focus after the existing server POST redirects to this basket.
        // Use only session-scoped state for this exact sale, never a shared register flag.
        var focusKey = "retail-scan-focus:" + window.location.pathname;
        try {
          if (window.sessionStorage.getItem(focusKey) === "1") {
            window.sessionStorage.removeItem(focusKey);
            if (!window.matchMedia || window.matchMedia("(pointer: fine)").matches) scanInput.focus();
          }
        } catch (ignored) { /* Private browsing may disable storage. */ }
      }
      scanForm.addEventListener("submit", function (event) {
        if (!scanInput || !scanInput.value.trim()) {
          event.preventDefault();
          if (scanInput) scanInput.focus();
          if (scanStatus) scanStatus.textContent = "Scan a barcode or type a PLU first.";
          return;
        }
        var qty = scanQuantity ? Number(scanQuantity.value) : 1;
        if (!Number.isFinite(qty) || qty <= 0 || Math.abs(Math.round(qty * 1000) - qty * 1000) > 0.000001) {
          event.preventDefault();
          if (scanQuantity) scanQuantity.focus();
          if (scanStatus) scanStatus.textContent = "Enter a positive quantity with at most three decimal places.";
          return;
        }
        // Do not lock the scanner when native form constraints prevent submission.
        if (!scanForm.checkValidity()) return;
        var inline = !!(window.fetch && window.FormData &&
          document.querySelector("#fizo-current-basket .fizo-retail-basket-items") &&
          window.retailRefreshCheckout);
        if (inline) event.preventDefault();
        if (!inline) {
          try {
            if (scanInput) window.sessionStorage.setItem("retail-scan-focus:" + window.location.pathname, "1");
          } catch (ignored) { /* Scanning still works without storage. */ }
          return;
        }
        if (!window.retailEnqueueAddMutation) return;
        // Snapshot the scan before clearing the field so the scanner can accept
        // the next barcode immediately, even while prior writes are in flight.
        window.retailEnqueueAddMutation(scanForm, scanStatus, function() {
          if (scanStatus) scanStatus.textContent = "Scan accepted.";
        });
        if (scanInput) {
          scanInput.value = "";
          scanInput.focus();
        }
        if (scanQuantity) scanQuantity.value = "1";
      });
    }
  
    function bindRetailPaymentControls() {
    var paymentForm = document.querySelector("[data-pos-payment-form]");
    if (paymentForm && paymentForm.dataset.retailPaymentBound !== "1") {
      paymentForm.dataset.retailPaymentBound = "1";
      var paymentPending = false;
      var paymentSubmitButton = paymentForm.querySelector('button[type="submit"]');
      var paymentSubmitLabel = paymentSubmitButton ? paymentSubmitButton.textContent : "";
      var paymentStatus = paymentForm.parentNode.querySelector("[data-retail-payment-status]");
  
      function unlockPayment() {
        paymentPending = false;
        if (paymentSubmitButton) {
          paymentSubmitButton.disabled = false;
          paymentSubmitButton.textContent = paymentSubmitLabel;
        }
      }
  
      paymentForm.addEventListener("submit", function (event) {
        if (paymentPending) { event.preventDefault(); return; }
        if (!paymentForm.checkValidity()) return;
        var inline = !!(window.fetch && window.FormData && window.retailRefreshCheckout);
        paymentPending = true;
        if (paymentSubmitButton) {
          paymentSubmitButton.disabled = true;
          paymentSubmitButton.textContent = "Recording payment…";
        }
        if (!inline) return;
  
        event.preventDefault();
        if (paymentStatus) paymentStatus.textContent = "Recording payment…";
        var csrf = paymentForm.querySelector('input[name="csrfmiddlewaretoken"]');
        fetch(paymentForm.getAttribute("action") || window.location.pathname + window.location.search, {
          method: "POST",
          body: new FormData(paymentForm),
          credentials: "same-origin",
          redirect: "follow",
          headers: {
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRFToken": csrf ? csrf.value : ""
          }
        }).then(function (response) {
          var type = (response.headers.get("Content-Type") || "").toLowerCase();
          if (response.redirected || !type.includes("application/json")) {
            throw new Error("Checkout session changed or returned an unexpected payment response.");
          }
          return response.json().then(function (data) {
            if (!response.ok || !data.ok) {
              var confirmed = new Error(data.message || "Payment was not recorded.");
              confirmed.confirmedFailure = true;
              throw confirmed;
            }
            return data;
          });
        }).then(function (data) {
          // Reset tender-only UI before the authoritative GET reconciliation.
          // Never replay this POST if that reconciliation fails.
          var panel = document.querySelector("[data-retail-cash-panel]");
          var oldDue = panel && panel.getAttribute("data-balance-due");
          var amount = paymentForm.querySelector('input[name="amount"]');
          if (amount && oldDue != null && Number.isFinite(Number(oldDue))) {
            amount.value = oldDue;
          }
          var tender = panel && panel.querySelector("[data-retail-cash-received]");
          if (tender) tender.value = "";
          try {
            var basket = document.querySelector("#fizo-current-basket");
            if (basket && basket.dataset.orderId) {
              localStorage.removeItem("pos:tender:" + basket.dataset.orderId);
            }
          } catch (ignored) { /* Payment remains valid without local storage. */ }
          return window.retailRefreshCheckout().then(function () { return data; });
        }).then(function (data) {
          if (paymentStatus && document.documentElement.contains(paymentStatus)) {
            paymentStatus.textContent = data.message || "Payment recorded.";
          }
        }).catch(function (error) {
          if (error && error.confirmedFailure) {
            if (paymentStatus) paymentStatus.textContent = error.message;
            return;
          }
          if (window.retailShowCheckoutRecovery) {
            window.retailShowCheckoutRecovery(paymentStatus, error);
          } else if (paymentStatus) {
            paymentStatus.textContent = (error.message || "Payment confirmation unavailable.") +
              " Reload this sale to verify before trying again.";
          }
        }).then(unlockPayment);
      });
      window.addEventListener("pageshow", unlockPayment);
    }
  
    var cashPanel = document.querySelector("[data-retail-cash-panel]");
    if (cashPanel && cashPanel.dataset.retailCashBound !== "1") {
      cashPanel.dataset.retailCashBound = "1";
      var received = cashPanel.querySelector("[data-retail-cash-received]");
      var change = cashPanel.querySelector("[data-retail-change]");
      var tenderStatus = cashPanel.querySelector("[data-retail-tender-status]");
      var paymentAction = document.querySelector('form input[name="action"][value="record_payment"]');
      var realPaymentForm = paymentAction && paymentAction.form;
      var paymentAmount = realPaymentForm && realPaymentForm.querySelector('input[name="amount"]');
      var paymentMethod = realPaymentForm && realPaymentForm.querySelector('select[name="method"]');
      var dueRaw = Number(cashPanel.getAttribute("data-balance-due"));
      var dueCents = Math.round(dueRaw * 100);
      function calculateChange() {
        if (!received || !change || !tenderStatus) return;
        var raw = received.value.trim();
        var tender = raw === "" ? NaN : Number(raw);
        var cents = Math.round(tender * 100);
        change.textContent = "—";
        if (!Number.isFinite(dueRaw) || !Number.isFinite(tender) || tender < 0 ||
            !Number.isSafeInteger(cents) || Math.abs(tender * 100 - cents) > 0.000001) {
          tenderStatus.textContent = "Enter a valid cash amount.";
          return;
        }
        if (cents < dueCents) {
          // Partial cash tender is a partial payment, never the full amount due.
          // Keep the actual payment field consistent with the cashier's tender.
          if (paymentAmount && paymentMethod && paymentMethod.value === "cash") {
            paymentAmount.value = (cents / 100).toFixed(2);
          }
          tenderStatus.textContent = "Partial cash. Save this amount, then collect or hold the balance.";
          return;
        }
        change.textContent = ((cents - dueCents) / 100).toFixed(2);
        tenderStatus.textContent = "Change ready.";
        if (paymentAmount && paymentMethod && paymentMethod.value === "cash") {
          paymentAmount.value = (dueCents / 100).toFixed(2);
        }
      }
      function publishCustomerTender() {
        if (!received) return;
        var amount = received.value.trim() === "" ? NaN : Number(received.value);
        try {
          var basket = document.querySelector("#fizo-current-basket");
          if (!basket || !basket.dataset.orderId) return;
          var key = "pos:tender:" + basket.dataset.orderId;
          if (!Number.isFinite(amount) || amount < 0) {
            localStorage.removeItem(key);
          } else {
            localStorage.setItem(key, JSON.stringify({
              received: amount, due: dueRaw, updated: Date.now()
            }));
          }
        } catch (error) {
          // Local storage can be unavailable in restricted browsers.
        }
      }
      if (received) received.addEventListener("input", function () {
        calculateChange();
        publishCustomerTender();
      });
      if (paymentMethod) paymentMethod.addEventListener("change", calculateChange);
      cashPanel.addEventListener("retail:balance-updated", function () {
        dueRaw = Number(cashPanel.getAttribute("data-balance-due"));
        dueCents = Math.round(dueRaw * 100);
        calculateChange();
        publishCustomerTender();
      });
    }
  
    }
    document.addEventListener("retail:payment-controls-added", bindRetailPaymentControls);
    bindRetailPaymentControls();
  
  }());

})();
