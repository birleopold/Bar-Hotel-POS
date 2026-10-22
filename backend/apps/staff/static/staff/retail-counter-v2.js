/* Checkout keyboard and pointer controls: non-destructive enhancements. */
(function(){
  "use strict";
  var root=document.querySelector(".fizo-checkout-catalogue");
  if(!root)return;
  var server=root.querySelector("#fizo-catalogue-server-query");
  var local=root.querySelector("[data-pos-menu-search]");
  var addForm=root.querySelector("[data-fizo-add-line-form]");
  var serverForm=server&&server.closest("form");
  var qty=addForm&&addForm.querySelector('input[name="quantity"]');
  var product=addForm&&addForm.querySelector('select[name="menu_item"]');
  var live=document.querySelector("[data-pos-menu-selection]");
  function focusSearch(barcode){
    var input=barcode?(server||local):(local||server);
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
    if(e.key==="F2"){e.preventDefault();focusSearch(false);}
    if(e.key==="F3"){e.preventDefault();focusSearch(true);}
    if(e.key==="Escape"&&(document.activeElement===server||document.activeElement===local)){
      document.activeElement.value="";
      document.activeElement.dispatchEvent(new Event("input",{bubbles:true}));
    }
  });
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
      if(submit){submit.setAttribute("aria-disabled","true");submit.textContent="Adding…";}
      window.addEventListener("pageshow",function(){
        addForm.dataset.submitting="";
        if(submit){submit.removeAttribute("aria-disabled");submit.textContent="Add to basket";}
      },{once:true});
    });
  }
  root.querySelectorAll("[data-pos-menu-tile]").forEach(function(tile){
    tile.addEventListener("click",function(){
      if(qty)qty.focus({preventScroll:true});
    });
  });
  document.querySelectorAll("[data-fizo-qty-form]").forEach(function(form){
    var input=form.querySelector('input[name="quantity"]');
    form.querySelectorAll("[data-fizo-step]").forEach(function(button){
      button.addEventListener("click",function(){
        if(!input)return;
        var value=Number(input.value),step=Number(input.step)||1;
        if(!Number.isFinite(value))value=1;
        var next=Math.max(Number(input.min)||0.001,Math.round((value+Number(button.dataset.fizoStep)*step)*1000)/1000);
        input.value=String(next);
      });
    });
  });
})();
