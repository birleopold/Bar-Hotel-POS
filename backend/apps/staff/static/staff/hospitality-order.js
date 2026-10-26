(function(){
  "use strict";

  function statusFor(form){
    return form.querySelector("[data-hospitality-seat-status]");
  }

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

  window.addEventListener("pageshow",function(){
    document.querySelectorAll("[data-hospitality-seat-form]").forEach(function(form){
      delete form.dataset.submitting;
      var button=form.querySelector('button[type="submit"]');
      if(button)button.disabled=false;
    });
  });
}());
