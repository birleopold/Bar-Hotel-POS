(function(){
  "use strict";

  function refreshHospitalityCheck(){
    return fetch(window.location.pathname+window.location.search,{
      method:"GET",
      credentials:"same-origin",
      redirect:"follow",
      headers:{"X-Requested-With":"XMLHttpRequest"}
    }).then(function(response){
      if(!response.ok||response.redirected)throw new Error("Could not refresh this check.");
      return response.text();
    }).then(function(html){
      var remote=new DOMParser().parseFromString(html,"text/html");
      var currentLines=document.querySelector("[data-hospitality-lines-zone]");
      var nextLines=remote.querySelector("[data-hospitality-lines-zone]");
      if(currentLines&&nextLines){
        currentLines.replaceChildren.apply(
          currentLines,
          Array.prototype.map.call(nextLines.childNodes,function(node){
            return document.importNode(node,true);
          })
        );
      }
      var currentTotal=document.querySelector("[data-hospitality-order-total]");
      var nextTotal=remote.querySelector("[data-hospitality-order-total]");
      if(currentTotal&&nextTotal)currentTotal.textContent=nextTotal.textContent;
      var currentMeta=document.querySelector("[data-hospitality-order-meta]");
      var nextMeta=remote.querySelector("[data-hospitality-order-meta]");
      if(currentMeta&&nextMeta)currentMeta.textContent=nextMeta.textContent;
      return true;
    });
  }

  function statusFor(form){
    return form.querySelector("[data-hospitality-seat-status]");
  }

  document.addEventListener("submit",function(event){
    var form=event.target;
    if(!(form instanceof HTMLFormElement)||
       !form.matches("[data-fizo-add-line-form]"))return;
    if(!(window.fetch&&window.FormData&&window.DOMParser))return;
    event.preventDefault();
    if(form.dataset.submitting==="1")return;
    if(!form.checkValidity()){
      form.reportValidity();
      return;
    }

    form.dataset.submitting="1";
    var button=form.querySelector('button[type="submit"]');
    var previous=button&&button.textContent;
    var status=form.querySelector("[data-hospitality-add-status]");
    if(button){button.disabled=true;button.textContent="Adding…";}
    if(status)status.textContent="Adding item…";
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
      if(response.redirected)throw new Error("The check changed or access was redirected.");
      var type=(response.headers.get("Content-Type")||"").toLowerCase();
      if(!type.includes("application/json"))throw new Error("Unexpected add-item response.");
      return response.json().then(function(data){
        if(!response.ok||!data.ok){
          var rejected=new Error(data.message||"Item could not be added.");
          rejected.serverRejected=true;
          throw rejected;
        }
        return data;
      });
    }).then(function(data){
      return refreshHospitalityCheck().then(function(){return data;});
    }).then(function(data){
      var qty=form.querySelector('input[name="quantity"]');
      if(qty)qty.value="1";
      var seat=form.querySelector('input[name="seat_number"]');
      if(seat)seat.value="";
      form.querySelectorAll('input[name="modifier_option"]').forEach(function(input){
        input.checked=false;
      });
      if(status)status.textContent=data.message||"Line added.";
    }).catch(function(error){
      if(error&&error.serverRejected){
        if(status)status.textContent=error.message;
        return;
      }
      // The POST may have committed even when its response was lost. Reconcile
      // from the authoritative check; never repeat the mutation automatically.
      refreshHospitalityCheck().then(function(){
        if(status)status.textContent="Check refreshed. Verify the item before trying again.";
      }).catch(function(){
        if(status)status.textContent="Could not verify whether the item was added. Reload this check before trying again.";
      });
    }).then(function(){
      delete form.dataset.submitting;
      if(button){button.disabled=false;button.textContent=previous||"Add to order";}
    });
  });

  document.addEventListener("submit",function(event){
    var form=event.target;
    if(!(form instanceof HTMLFormElement)||
       !form.matches("[data-hospitality-seat-form]"))return;
    if(!(window.fetch&&window.FormData))return;
    event.preventDefault();
    if(form.dataset.submitting==="1")return;
    if(!form.checkValidity()){
      form.reportValidity();
      return;
    }

    form.dataset.submitting="1";
    var button=form.querySelector('button[type="submit"]');
    var previous=button&&button.textContent;
    var status=statusFor(form);
    if(button){button.disabled=true;button.textContent="Saving…";}
    if(status)status.textContent="Updating seat…";
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
      if(response.redirected)throw new Error("The check changed or access was redirected.");
      var type=(response.headers.get("Content-Type")||"").toLowerCase();
      if(!type.includes("application/json"))throw new Error("Unexpected seat response.");
      return response.json().then(function(data){
        if(!response.ok||!data.ok){
          var rejected=new Error(data.message||"Seat could not be updated.");
          rejected.serverRejected=true;
          throw rejected;
        }
        return data;
      });
    }).then(function(data){
      var label=document.querySelector(
        '[data-hospitality-seat-label="'+data.line_id+'"]'
      );
      if(label)label.textContent=data.seat_label;
      if(status)status.textContent=data.message||"Seat updated.";
    }).catch(function(error){
      if(status){
        status.textContent=(error&&error.serverRejected)
          ? error.message
          : "Could not verify the seat update. Reload this check before trying again.";
      }
    }).then(function(){
      delete form.dataset.submitting;
      if(button){button.disabled=false;button.textContent=previous||"Seat";}
    });
  });

  document.addEventListener("submit",function(event){
    var form=event.target;
    if(!(form instanceof HTMLFormElement)||
       !form.matches("[data-hospitality-qty-form]"))return;
    if(!(window.fetch&&window.FormData))return;
    event.preventDefault();
    if(form.dataset.submitting==="1")return;
    if(!form.checkValidity()){
      form.reportValidity();
      return;
    }

    form.dataset.submitting="1";
    var button=form.querySelector('button[type="submit"]');
    var previous=button&&button.textContent;
    var status=form.querySelector("[data-hospitality-qty-status]");
    var input=form.querySelector('input[name="quantity"]');
    var confirmed=input&&input.value;
    if(button){button.disabled=true;button.textContent="Saving…";}
    if(status)status.textContent="Updating quantity…";
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
      if(response.redirected)throw new Error("The check changed or access was redirected.");
      var type=(response.headers.get("Content-Type")||"").toLowerCase();
      if(!type.includes("application/json"))throw new Error("Unexpected quantity response.");
      return response.json().then(function(data){
        if(!response.ok||!data.ok){
          var rejected=new Error(data.message||"Quantity could not be updated.");
          rejected.serverRejected=true;
          throw rejected;
        }
        return data;
      });
    }).then(function(data){
      if(input)input.value=data.quantity;
      var qty=document.querySelector(
        '[data-hospitality-line-quantity="'+data.line_id+'"]'
      );
      if(qty)qty.textContent=data.quantity;
      var amount=document.querySelector(
        '[data-hospitality-line-total="'+data.line_id+'"]'
      );
      if(amount)amount.textContent=data.line_total;
      var total=document.querySelector("[data-hospitality-order-total]");
      if(total)total.textContent=data.total;
      var meta=document.querySelector("[data-hospitality-order-meta]");
      if(meta)meta.textContent="Sub "+data.subtotal+" · Tax "+data.tax;
      if(status)status.textContent="Quantity updated.";
    }).catch(function(error){
      if(input&&confirmed!=null)input.value=confirmed;
      if(status){
        status.textContent=(error&&error.serverRejected)
          ? error.message
          : "Could not verify the quantity update. Reload this check before trying again.";
      }
    }).then(function(){
      delete form.dataset.submitting;
      if(button){button.disabled=false;button.textContent=previous||"Set";}
    });
  });

  document.addEventListener("submit",function(event){
    var form=event.target;
    if(!(form instanceof HTMLFormElement)||
       !form.matches("[data-hospitality-void-form]"))return;
    if(!(window.fetch&&window.FormData&&window.DOMParser))return;
    event.preventDefault();
    if(form.dataset.submitting==="1")return;
    if(!form.checkValidity()){form.reportValidity();return;}
    form.dataset.submitting="1";
    var button=form.querySelector('button[type="submit"]');
    var previous=button&&button.textContent;
    var status=form.querySelector("[data-hospitality-void-status]");
    if(button){button.disabled=true;button.textContent="Voiding…";}
    if(status)status.textContent="Removing item…";
    var csrf=form.querySelector('input[name="csrfmiddlewaretoken"]');
    fetch(form.getAttribute("action")||window.location.pathname+window.location.search,{
      method:"POST",body:new FormData(form),credentials:"same-origin",redirect:"follow",
      headers:{"X-Requested-With":"XMLHttpRequest","X-CSRFToken":csrf?csrf.value:""}
    }).then(function(response){
      if(response.redirected)throw new Error("The check changed or access was redirected.");
      var type=(response.headers.get("Content-Type")||"").toLowerCase();
      if(!type.includes("application/json"))throw new Error("Unexpected void response.");
      return response.json().then(function(data){
        if(!response.ok||!data.ok){
          var rejected=new Error(data.message||"Item could not be voided.");
          rejected.serverRejected=true;throw rejected;
        }
        return data;
      });
    }).then(function(data){
      return refreshHospitalityCheck().then(function(){return data;});
    }).then(function(data){
      if(status)status.textContent=data.message||"Item voided.";
    }).catch(function(error){
      if(error&&error.serverRejected){if(status)status.textContent=error.message;return;}
      // A lost response must never cause a second void. Refresh from the
      // authoritative check and let the operator verify the current state.
      refreshHospitalityCheck().then(function(){
        if(status)status.textContent="Check refreshed. Verify the item before trying again.";
      }).catch(function(){
        if(status)status.textContent="Could not verify whether the item was voided. Reload this check before trying again.";
      });
    }).then(function(){
      delete form.dataset.submitting;
      if(button){button.disabled=false;button.textContent=previous||"Void";}
    });
  });

  window.addEventListener("pageshow",function(){
    document.querySelectorAll("[data-fizo-add-line-form],[data-hospitality-seat-form],[data-hospitality-qty-form],[data-hospitality-void-form]").forEach(function(form){
      delete form.dataset.submitting;
      var button=form.querySelector('button[type="submit"]');
      if(button)button.disabled=false;
    });
  });
}());
