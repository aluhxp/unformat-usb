// Ads on the web page (never in the program).
// To turn them on: get an AdSense account for your own domain, then set your
// publisher id below (looks like "ca-pub-1234567890123456") and, in AdSense,
// create one ad unit per place and put its number in SLOTS. Also add the
// ads.txt line AdSense gives you to docs/ads.txt.
var ADSENSE_CLIENT = "";
var SLOTS = { "after-how": "", "before-faq": "", "bottom": "" };

(function () {
  if (!ADSENSE_CLIENT) return;
  var places = document.querySelectorAll(".ad[data-ad-slot]");
  var used = 0;
  places.forEach(function (place) {
    var slot = SLOTS[place.getAttribute("data-ad-slot")];
    if (!slot) return;
    var ins = document.createElement("ins");
    ins.className = "adsbygoogle";
    ins.style.display = "block";
    ins.setAttribute("data-ad-client", ADSENSE_CLIENT);
    ins.setAttribute("data-ad-slot", slot);
    ins.setAttribute("data-ad-format", "auto");
    ins.setAttribute("data-full-width-responsive", "true");
    place.appendChild(ins);
    place.classList.add("on");
    used++;
  });
  if (!used) return;
  var s = document.createElement("script");
  s.async = true;
  s.crossOrigin = "anonymous";
  s.src = "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=" + ADSENSE_CLIENT;
  s.onload = function () {
    for (var i = 0; i < used; i++) (window.adsbygoogle = window.adsbygoogle || []).push({});
  };
  document.head.appendChild(s);
})();
