// Deterministically regenerate public subpages from the canonical index shell.
// Run: node scripts/build_public_site_pages.mjs [--check]
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const dir=fileURLToPath(new URL('../app/web/site/',import.meta.url));
function buildPages(home){
 const pageData={
  features:{label:"Возможности",title:"Создавай по-своему.",accent:"По-своему.",description:"Фото, видео, референсы и готовые тренды в ROXY AI STUDIO. Выбирай подходящий творческий инструмент.",heading:"features-title",next:["/process","Как это работает"],details:[
   ["Фото с нуля","Опиши композицию, освещение, фон и настроение. Начни с простого промпта и уточняй детали в следующих версиях.","/process","Как подготовить описание"],
   ["От снимка к видео","Выбери исходное изображение и опиши движение камеры или героя. Доступные режимы и длительность зависят от модели.","/gallery","Посмотреть идеи для видео"],
   ["Твои референсы","Используй собственные кадры, когда важно сохранить детали образа или композиции. Загружай изображения, на которые у тебя есть права.","/faq","Что можно загружать"],
   ["Повторы трендов","Открой понравившийся тренд и добавь исходники, которые просит выбранный сценарий. Настройки и стоимость видны в студии.","/gallery","Открыть тренды"]
  ]},
  gallery:{label:"Галерея",title:"Идеи в движении.",accent:"В движении.",description:"Популярные реальные тренды ROXY: фотографии и видео. Открой понравившийся шаблон и создай свой вариант.",heading:"gallery-title",next:["/features","Все инструменты"],details:[
   ["Выбери идею","Галерея показывает активные тренды с доступными превью. Порядок основан на количестве запусков в каталоге.","/process","Как повторить тренд"],
   ["Сделай свою версию","Нажми на плитку, чтобы открыть конкретный тренд в студии. Добавь нужные референсы и проверь настройки перед запуском.","/faq","Вопросы о референсах"]
  ]},
  process:{label:"Процесс",title:"От идеи до кадра.",accent:"До кадра.",description:"Как создать фотографию или видео в ROXY: выбор инструмента, описание, исходники, запуск и результат.",heading:"process-title",next:["/gallery","Выбрать тренд"],details:[
   ["Подготовь исходники","Для конкретного образа используй чёткий кадр и нужные референсы. Для генерации с нуля достаточно текстового описания.","/features","Выбрать инструмент"],
   ["Опиши результат","Укажи героя, действие, стиль и настроение. Для видео полезно описать движение и ракурс, не только внешний вид.","/features","Возможности студии"],
   ["Проверь условия запуска","Перед генерацией посмотри доступные настройки и стоимость в ROX. Они зависят от выбранной модели и режима.","/faq","Как работает стоимость"],
   ["Сохрани или повтори","Готовая работа остаётся в истории аккаунта. Можно использовать результат как исходник, если выбранный инструмент это поддерживает.","/gallery","Найти новую идею"]
  ]},
  faq:{label:"Вопросы",title:"Всё перед стартом.",accent:"Перед стартом.",description:"Ответы на вопросы о создании фото и видео, референсах, аккаунте и работе с ROXY.",heading:"faq-title",next:["/features","Возможности студии"],details:[
   ["Нужна помощь?","Открой приложение ROXY и перейди в раздел поддержки своего аккаунта, если возник вопрос о генерации, оплате или работе сервиса.","/mini-app/","Открыть ROXY"],
   ["Готов к первому кадру?","Начни с готового тренда или выбери фото либо видео. Не нужно заранее изучать все настройки.","/gallery","Выбрать идею"]
  ]}
 };
 const result={};
 const shell=home.match(/^(.*?)<main id="content">/s)?.[1],suffix=home.match(/<\/main>([\s\S]*)$/)?.[1];
 const final=home.match(/<section class="final-section"[\s\S]*?<\/section>/)?.[0];
 if(!shell||!suffix||!final)throw Error("invalid home shell");
 for(const [id,d] of Object.entries(pageData)){
   const match=home.match(new RegExp(`<section class="section [^"]+" id="${id}"[\\s\\S]*?<\\/section>`));
   if(!match)throw Error("missing section "+id);
   let section=match[0].replace(new RegExp(`<h2 id="${d.heading}">[^<]+<\\/h2>`),`<h1 class="page-intro" id="${d.heading}">${d.title.replace(d.accent,`<em>${d.accent}</em>`)}</h1>`);
   section=section.replace(/<a class="section-more"[^>]*>[\s\S]*?<\/a>/g,"");
   const breadcrumb=`<nav class="page-breadcrumb" aria-label="Путь страницы"><a href="/" data-site-link>Главная</a><span aria-hidden="true">/</span><span>${d.label}</span></nav>`;
   section=section.replace(/(<section[^>]*>)/,"$1\n      "+breadcrumb);
   if(id==="gallery")section=section.replace('id="popular-trends"','id="popular-trends" data-limit="12"');
   if(id==="faq"){
     const extra=[
      ["Как узнать стоимость генерации?","Стоимость и доступные параметры показываются в приложении перед запуском. Они зависят от модели и выбранного режима."],
      ["Можно ли использовать чужие фотографии?","Используй изображения, видео и другие материалы, на которые у тебя есть необходимые права или разрешение."],
      ["Где найти готовые работы?","Открой историю своего аккаунта в ROXY. Доступные действия с работой зависят от её типа и состояния."],
      ["Что делать, если генерация не пришла?","Проверь историю и статус работы. Если проблема сохраняется, обратись в поддержку через приложение."]
     ].map(([q,a])=>`        <details><summary>${q}<span aria-hidden="true">+</span></summary><p>${a}</p></details>`).join("\n");
     section=section.replace(/(\n      <\/div>\s*<\/section>)/,`\n${extra}$1`);
   }
   const details=`<div class="page-details">${d.details.map(([h,p,url,cta])=>`<article class="detail-panel"><h2>${h}</h2><p>${p}</p><a class="section-more" href="${url}" ${url==="/mini-app/"?"data-app-link":"data-site-link"}>${cta} <span aria-hidden="true">↗</span></a></article>`).join("\n")}</div>`;
   section=section.replace(/<\/section>$/,details+"\n    </section>");
   let pre=shell.replace('<body data-page="home">',`<body class="subpage" data-page="${id}">`)
     .replace(/<title>[\s\S]*?<\/title>/,`<title>ROXY AI STUDIO — ${d.label}</title>`)
     .replace(/(<meta name="description" content=")[^"]*"/,`$1${d.description}"`)
     .replace(/(<meta property="og:title" content=")[^"]*"/,`$1ROXY AI STUDIO — ${d.label}"`)
     .replace(/(<meta property="og:description" content=")[^"]*"/,`$1${d.description}"`)
     .replace(/(<link rel="canonical" href="[^"]*\/)"/,`$1${id}"`)
     .replace(/(<meta property="og:url" content="[^"]*\/)"/,`$1${id}"`)
     .replace(/\n  <link rel="preload" as="image"[^>]+>/,"")
     .replace(' data-site-link aria-current="page">Главная',' data-site-link>Главная')
     .replaceAll(`href="/${id}" data-site-link>`, `href="/${id}" data-site-link aria-current="page">`);
   const next=`<nav class="page-next" aria-label="Продолжить знакомство"><a class="section-more" href="/" data-site-link>← Главная</a><a class="section-more" href="${d.next[0]}" data-site-link>${d.next[1]} <span aria-hidden="true">↗</span></a></nav>`;
   const end=suffix.replace(/<script src="\/site-assets\/popular-trends\.js[^>]+><\/script>/,id==="gallery"?suffix.match(/<script src="\/site-assets\/popular-trends\.js[^>]+><\/script>/)[0]:"");
   result[id]=pre+`<main id="content">\n    ${section}\n    ${next}\n    ${final}\n  </main>`+end;
 }
 return result;
}
const pages=buildPages(readFileSync(dir+'index.html','utf8'));
for(const [name,html] of Object.entries(pages)){
 const path=dir+name+'.html';
 if(process.argv.includes('--check')){
  if(readFileSync(path,'utf8')!==html)throw new Error('Stale generated page: '+name);
 }else writeFileSync(path,html,'utf8');
}
