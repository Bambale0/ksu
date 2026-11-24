(() => {
  "use strict";
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  if (reduced.matches || !("IntersectionObserver" in window) || !Element.prototype.animate) return;
  const running = new Set();
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      const node = entry.target;
      observer.unobserve(node);
      if (reduced.matches) continue;
      // Price cards rise in short groups. Partner artwork and copy have a
      // directional entrance; nothing is permanently hidden on script failure.
      const kind = node.dataset.commercialMotion;
      const frames = kind === "partner" || kind === "creator"
        ? [{opacity:.65, transform:"translateX("+(kind==="partner"?12:-12)+"px)"},{opacity:1,transform:"translateX(0)"}]
        : [{opacity:.72,transform:"translateY(10px)"},{opacity:1,transform:"translateY(0)"}];
      const a = node.animate(frames,{duration:kind==="pricing"?380:460,easing:"cubic-bezier(.2,.8,.2,1)"});
      running.add(a);
      a.finished.catch(()=>{}).finally(()=>running.delete(a));
      node.dataset.motionPlayed="true";
    }
  },{threshold:.12});
  const seen = new WeakSet();
  const scan = () => {
    for(const node of document.querySelectorAll("[data-commercial-motion], .pricing-page .price-summary, .pricing-page .package-price-card, .pricing-page .model-price-card")){
      if(seen.has(node))continue;
      seen.add(node);
      observer.observe(node);
    }
  };
  scan();
  const pricing = document.querySelector(".pricing-section");
  if(pricing)new MutationObserver(scan).observe(pricing,{childList:true,subtree:true});
  reduced.addEventListener?.("change",()=>{if(reduced.matches){observer.disconnect();for(const a of running)a.cancel();}});
})();
