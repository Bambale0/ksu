(() => {
  "use strict";
  const header = document.querySelector(".site-header");
  if (!header) return;
  const nav = header.querySelector(".desktop-nav");
  const links = Array.from(nav?.querySelectorAll('a[href^="#"]') || []);
  const action = header.querySelector(".top-action");
  const menu = header.querySelector(".mobile-nav");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)");
  const fine = matchMedia("(hover: hover) and (pointer: fine)");
  const targets = links.map(link => ({link,section:document.getElementById(link.hash.slice(1))})).filter(entry=>entry.section);
  let active = links[0], hovered = null, focused = null, frame = 0, pointer = null;
  function draw() {
    frame = 0;
    header.classList.toggle("is-compact",scrollY > 72);
    let sectionLink = targets[0]?.link;
    let highest = -Infinity;
    for (const entry of targets) {
      const top = entry.section.getBoundingClientRect().top;
      if (top <= 145 && top > highest) { highest=top;sectionLink=entry.link; }
    }
    if (innerHeight + scrollY >= document.documentElement.scrollHeight - 4) sectionLink=targets[targets.length-1]?.link;
    if (sectionLink && sectionLink !== active) active=sectionLink;
    for (const link of links) {
      if (link===active) link.setAttribute("aria-current","location");
      else link.removeAttribute("aria-current");
    }
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
  document.addEventListener("keydown",event=>{if(event.key==="Escape"&&menu?.open){menu.open=false;menu.querySelector("summary")?.focus();}});
  function reset(){hovered=null;pointer=null;schedule();}
  reduce.addEventListener?.("change",reset);
  fine.addEventListener?.("change",reset);
  window.addEventListener("scroll",schedule,{passive:true});
  window.addEventListener("resize",schedule,{passive:true});
  document.fonts?.ready.then(schedule);
  schedule();
})();
