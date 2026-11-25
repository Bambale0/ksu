(() => {
  "use strict";
  const blocks = [...document.querySelectorAll("[data-catalog], [data-packages]")];
  if (!blocks.length) return;
  const fmt = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 });
  const number = value => typeof value === "number" || (typeof value === "string" && /^\d+(?:\.\d+)?$/.test(value)) ? Number(value) : NaN;
  const operations = {
    text_to_image:"Фото по тексту", generate_or_edit:"Создание и редактирование фото",
    image_edit:"Редактирование фото", image_to_image:"Фото по исходнику",
    layer_decomposition:"Разделение на слои", text_to_video:"Видео по тексту",
    image_to_video:"Видео по фото", text_or_image_to_video:"Видео по тексту или фото",
    multimodal_video:"Видео с референсами", motion_control:"Перенос движения",
    audio_driven_avatar:"Аватар по фото и аудио", text_to_music:"Музыка по описанию",
    video_upscale:"Повышение разрешения видео", video_extend:"Продление видео"
  };
  const media = { image:"Фото", video:"Видео", audio:"Музыка" };
  function element(tag, value, klass) {
    const node = document.createElement(tag);
    if (klass) node.className = klass;
    if (value != null) node.textContent = value;
    return node;
  }
  function price(m) {
    const amounts = m.tiers.map(t=>t.amount).concat(m.amount);
    const suffix = m.mode === "per_second" ? " / с" : " / запуск";
    return (m.tiers.length && Math.min(...amounts) !== Math.max(...amounts) ? "от " : "") + fmt.format(Math.min(...amounts)) + " ROX" + suffix;
  }
  function imageFields(m) {
    return m.fields.some(f=>["file","files"].includes(f.control) && typeof f.accept==="string" && f.accept.includes("image/"));
  }
  function filter(m, group) {
    if (group === "all" || group === "overview") return true;
    if (group === "photo") return m.media === "image";
    if (group === "video") return m.media === "video";
    if (group === "text") return !m.fields.some(f=>["file","files"].includes(f.control) && f.required) && (m.media === "image" || m.media === "video") && ["text_to_image","generate_or_edit","text_to_video","text_or_image_to_video","multimodal_video"].includes(m.operation);
    if (group === "own-photo") return imageFields(m) && ["image","video"].includes(m.media);
    if (group === "reference") return m.fields.some(f=>["file","files"].includes(f.control) && f.group === "references") && ["image","video"].includes(m.media);
    return false;
  }
  async function request(path) {
    const controller = new AbortController();
    const timer = setTimeout(()=>controller.abort(), 10000);
    try {
      const r = await fetch(path, {credentials:"omit",cache:"no-store",signal:controller.signal,headers:{Accept:"application/json"}});
      if (!r.ok) throw new Error("catalog unavailable");
      return await r.json();
    } finally { clearTimeout(timer); }
  }
  function normalize(data) {
    if (!Array.isArray(data?.models)) throw new Error("invalid catalog");
    return data.models.flatMap(m=>{
      const amount = number(m?.retail_price_rox ?? m?.price_rox);
      if (!m || !Object.hasOwn(media,m.media_type) || !["flat","per_second"].includes(m.price_mode) || !Number.isFinite(amount) || amount<=0 || typeof m.title!=="string" || !m.title.trim()) return [];
      const tiers=[];
      for(const [key,field] of [["by_mode","mode"],["by_quality","quality"],["by_resolution","resolution"]]){
        const prices=m.retail_price_tiers?.[key];
        if(!prices || typeof prices!=="object" || Array.isArray(prices))continue;
        const options=m.ui_schema?.fields?.find(f=>f?.name===field)?.suggestions;
        for(const [label,raw] of Object.entries(prices)){
          const value=number(raw);
          if(Number.isFinite(value)&&value>0&&label.length<=32&&(!Array.isArray(options)||options.includes(label)))tiers.push({label:field==="quality"?label.toUpperCase():label,amount:value});
        }
      }
      return [{title:m.title.slice(0,160),media:m.media_type,operation:m.operation,mode:m.price_mode,amount,tiers,fields:Array.isArray(m.ui_schema?.fields)?m.ui_schema.fields.filter(f=>f && typeof f==="object"):[]}];
    });
  }
  function details(m) {
    const fields=m.fields;
    const out=[];
    const duration=fields.find(f=>f.name==="duration");
    if (m.mode==="per_second" && duration && Number.isFinite(duration.min) && Number.isFinite(duration.max)) out.push("Длительность: "+duration.min+"–"+duration.max+" с");
    else if(m.mode==="per_second" && ["motion_control","audio_driven_avatar"].includes(m.operation)) out.push("Расчёт по длительности исходника");
    const resolution=fields.find(f=>f.name==="resolution" || f.name==="image_resolution");
    if (Array.isArray(resolution?.suggestions)) {
      const values=resolution.suggestions.filter(v=>typeof v==="string" && /^(?:\d{3,4}p|[1248]K|[1248]k)$/.test(v)).slice(0,5);
      if(values.length) out.push(values.join(" / "));
    }
    const input=[];
    for(const f of fields){
      if(!["file","files"].includes(f.control) || typeof f.accept!=="string")continue;
      for(const [prefix,label] of [["image/","Фото"],["video/","Видео"],["audio/","Аудио"]]){
        if(f.accept.includes(prefix)&&!input.includes(label))input.push(label);
      }
    }
    if(input.length)out.push("Исходники: "+input.join(", "));
    return out.join(" · ");
  }
  function renderModels(block, data) {
    const group=block.dataset.catalog;
    const models=data.filter(m=>filter(m,group));
    if (!models.length) {block.append(element("p","Сейчас в этом разделе нет доступных моделей.","price-empty"));return;}
    const grid=element("div",null,group==="overview"?"price-summary-grid":"model-price-grid");
    if(group==="overview"){
      for(const [key,label] of Object.entries(media)){
        const list=models.filter(m=>m.media===key);
        if(!list.length)continue;
        const card=element("article",null,"price-summary");
        card.append(element("span",label,"price-kicker"));
        for(const mode of ["flat","per_second"]){
          const prices=list.filter(m=>m.mode===mode).flatMap(m=>[m.amount,...m.tiers.map(t=>t.amount)]);
          if(prices.length)card.append(element("strong","от "+fmt.format(Math.min(...prices))+" ROX"+(mode==="per_second"?" / с":" / запуск")));
        }
        const plural = new Intl.PluralRules("ru-RU").select(list.length);
        const noun = plural === "one" ? "режим" : plural === "few" ? "режима" : "режимов";
        card.append(element("p",list.length+" "+noun+" в каталоге"));
        grid.append(card);
      }
    }else{
      for(const m of models){
        const card=element("article",null,"model-price-card");
        card.dataset.media=m.media;
        card.append(element("span",media[m.media],"price-kicker"),element("h3",m.title),element("p",Object.hasOwn(operations,m.operation)?operations[m.operation]:"Параметры в студии"),element("strong",price(m)));
        if(m.tiers.length)card.append(element("small",m.tiers.map(t=>t.label+" — "+fmt.format(t.amount)+" ROX"+(m.mode==="per_second"?" / с":"")).join(" · "),"model-price-tiers"));
        const spec=details(m);
        if(spec)card.append(element("small",spec));
        grid.append(card);
      }
    }
    if(group==="all"){
      const filters=element("div",null,"price-filters");
      filters.setAttribute("role","group");
      filters.setAttribute("aria-label","Тип модели");
      for(const [value,label] of [["all","Все"],...Object.entries(media).filter(([key])=>models.some(m=>m.media===key))]){
        const button=element("button",label,"price-filter");
        button.type="button";button.dataset.media=value;button.setAttribute("aria-pressed",String(value==="all"));
        button.addEventListener("click",()=>{
          for(const b of filters.querySelectorAll("button"))b.setAttribute("aria-pressed",String(b===button));
          for(const c of grid.children)c.hidden=value!=="all"&&c.dataset.media!==value;
        });
        filters.append(button);
      }
      block.append(filters);
    }
    block.append(grid);
  }
  function renderPackages(block,data){
    if(!data?.configured || !data.packages || typeof data.packages!=="object"){
      block.append(element("p","Рублёвый способ пополнения сейчас недоступен. Проверь доступные способы в профиле.","price-empty"));return;
    }
    const rows=Object.values(data.packages).flatMap(p=>{
      const amount=number(p?.prices?.RUB),base=number(p?.credits),bonus=number(p?.bonus_credits),total=number(p?.total_credits);
      return [amount,base,bonus,total].every(Number.isFinite)&&amount>0&&base>0&&bonus>=0&&total===base+bonus?[{amount,base,bonus,total}]:[];
    }).sort((a,b)=>a.amount-b.amount);
    if(!rows.length){block.append(element("p","Нет доступных рублёвых пакетов.","price-empty"));return;}
    const grid=element("div",null,"package-price-grid");
    for(const p of rows){
      const card=element("article",null,"package-price-card");
      card.append(element("span","Пакет ROX","price-kicker"),element("h3",fmt.format(p.total)+" ROX"),element("p",fmt.format(p.base)+" основных"+(p.bonus?" + "+fmt.format(p.bonus)+" бонусных":"")),element("strong",fmt.format(p.amount)+" ₽"));
      grid.append(card);
    }
    block.append(grid);
  }
  const channels = [
    {selector:"[data-catalog]",url:"/api/v1/generations/models",parse:normalize,render:renderModels},
    {selector:"[data-packages]",url:"/api/v1/payments/yookassa/packages",parse:x=>x,render:renderPackages}
  ];
  for(const channel of channels){
    const targets=[...document.querySelectorAll(channel.selector)];
    if(!targets.length)continue;
    let loading=false;
    async function load(){
      if(loading)return;
      loading=true;
      for(const t of targets){t.replaceChildren(element("p","Загружаем актуальные цены…","price-status"));t.setAttribute("aria-busy","true");}
      try{
        const data=channel.parse(await request(channel.url));
        for(const t of targets){t.replaceChildren();channel.render(t,data);}
      }catch{
        for(const t of targets){
          const status=element("p","Не удалось загрузить цены. Попробуй ещё раз.","price-status");
          status.setAttribute("role","status");
          const retry=element("button","Повторить","button button-outline price-retry");
          retry.type="button";retry.addEventListener("click",load,{once:true});
          t.replaceChildren(status,retry);
        }
      }finally{loading=false;for(const t of targets)t.setAttribute("aria-busy","false");}
    }
    void load();
  }
})();
