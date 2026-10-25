/* Private same-account notification refresh for active Staff/Console sessions. */
(function () {
  "use strict";
  var config=document.querySelector("[data-staff-notification-client]");
  if(!config||!window.fetch)return;
  var statusUrl=config.dataset.statusUrl||"";
  var inboxUrl=config.dataset.inboxUrl||"";
  var seenKey="staff-notification-seen:"+(config.dataset.scopeKey||"default");
  if(!statusUrl)return;

  function updateBadge(count){
    document.querySelectorAll("[data-staff-notification-count]").forEach(function(badge){
      badge.textContent=String(count||0);
      badge.hidden=!count;
    });
  }

  function showBrowserAlert(alert){
    if(!alert||!("Notification" in window)||Notification.permission!=="granted")return;
    var previous="";
    try{previous=localStorage.getItem(seenKey)||"";}catch(error){}
    if(previous===alert.id)return;
    try{localStorage.setItem(seenKey,alert.id);}catch(error){}
    var notice=new Notification(alert.title||"Notification",{
      body:alert.body||"",
      tag:"staff-alert-"+alert.id
    });
    notice.onclick=function(){
      window.focus();
      window.location.href=alert.url||inboxUrl;
      notice.close();
    };
  }

  function poll(){
    fetch(statusUrl,{credentials:"same-origin",cache:"no-store"})
      .then(function(response){
        if(!response.ok)throw new Error("notification status");
        return response.json();
      })
      .then(function(data){
        updateBadge(data.unread_count);
        showBrowserAlert(data.latest);
      })
      .catch(function(){});
  }

  window.staffPollNotifications=poll;
  poll();
  window.setInterval(poll,15000);
}());
