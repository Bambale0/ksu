(() => {
  "use strict";
  const header = document.querySelector(".site-header");
  if (!header) return;
  const nav = header.querySelector(".desktop-nav");
  const links = Array.from(nav?.querySelectorAll('a[data-site-link]') || []);
  const action = header.querySelector(".top-action");
  const menu = header.querySelector(".mobile-nav");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)");
  const fine = matchMedia("(hover: hover) and (pointer: fine)");
  const mobile = matchMedia("(max-width: 660px)");
  const active = links.find(link => link.getAttribute("aria-current") === "page") || links[0];
  let hovered = null, focused = null, frame = 0, pointer = null;
  // Clamp Safari elastic scrolling so a bottom bounce cannot reveal the bar.
  const scrollPosition = () => Math.max(0, Math.min(scrollY, document.documentElement.scrollHeight - innerHeight));
  let scrollAnchor = scrollPosition(), scrollHidden = false;
  function draw() {
    frame = 0;
    const y = scrollPosition();
    header.classList.toggle("is-compact",y > 72);
    // Preserve a constant layout slot; hide only while reading down on mobile.
    // A small accumulated threshold prevents flicker on tiny scroll movements.
    if (!mobile.matches || y <= 72 || menu?.open || header.querySelector(":focus-visible")) {
      scrollHidden = false;
      scrollAnchor = y;
    } else if (y - scrollAnchor >= 12) {
      scrollHidden = true;
      scrollAnchor = y;
    } else if (scrollAnchor - y >= 12) {
      scrollHidden = false;
      scrollAnchor = y;
    }
    header.classList.toggle("is-scroll-hidden",scrollHidden);
    const shown=hovered || focused || active;
    if (nav && shown && nav.clientWidth) {
      nav.style.setProperty("--pill-x",shown.offsetLeft+"px");
      nav.style.setProperty("--pill-width",shown.offsetWidth+"px");
      nav.style.setProperty("--pill-opacity","1");
    }
    if (action && pointer && !reduce.matches && fine.matches) {
      const rect=action.getBoundingClientRect();
      const x=Math.max(-1,Math.min(1,(pointer.x-rect.left)/Math.max(1,rect.width)*2-1));
      const y=Math.max(-1,Math.min(1,(pointer.y-rect.top)/Math.max(1,rect.height)*2-1));
      action.style.setProperty("--magnet-x",x*5+"px");
      action.style.setProperty("--magnet-y",y*3+"px");
    } else {
      action?.style.removeProperty("--magnet-x");
      action?.style.removeProperty("--magnet-y");
    }
  }
  function schedule(){if(!frame)frame=requestAnimationFrame(draw);}
  for(const link of links){
    link.addEventListener("pointerenter",()=>{if(fine.matches&&!reduce.matches){hovered=link;schedule();}});
    link.addEventListener("focus",()=>{focused=link;schedule();});
    link.addEventListener("blur",()=>{focused=null;schedule();});
  }
  nav?.addEventListener("pointerleave",()=>{hovered=null;schedule();});
  action?.addEventListener("pointermove",event=>{if(event.pointerType==="mouse"){pointer={x:event.clientX,y:event.clientY};schedule();}},{passive:true});
  action?.addEventListener("pointerleave",()=>{pointer=null;schedule();});
  menu?.addEventListener("click",event=>{if(event.target instanceof Element && event.target.closest("nav a"))menu.open=false;});
  menu?.addEventListener("toggle",schedule);
  header.addEventListener("focusin",()=>{
    scrollHidden=false;
    scrollAnchor=scrollPosition();
    header.classList.remove("is-scroll-hidden");
    schedule();
  });
  mobile.addEventListener?.("change",()=>{
    scrollHidden=false;
    scrollAnchor=scrollPosition();
    schedule();
  });
  document.addEventListener("keydown",event=>{if(event.key==="Escape"&&menu?.open){menu.open=false;menu.querySelector("summary")?.focus();}});
  function reset(){hovered=null;pointer=null;schedule();}
  reduce.addEventListener?.("change",reset);
  fine.addEventListener?.("change",reset);
  window.addEventListener("scroll",schedule,{passive:true});
  window.addEventListener("resize",schedule,{passive:true});
  document.fonts?.ready.then(schedule);
  schedule();
})();
