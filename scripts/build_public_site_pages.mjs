// Regenerate independent public documents from the shared home shell.
// Run: node scripts/build_public_site_pages.mjs [--check]
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
const dir=fileURLToPath(new URL('../app/web/site/',import.meta.url));
const pageData={
  "features": {
    "label": "Возможности",
    "title": "Создавай по-своему.",
    "accent": "по-своему.",
    "description": "Фото, видео, референсы и готовые тренды в ROXY AI STUDIO. Выбирай подходящий творческий инструмент.",
    "heading": "features-title",
    "next": [
      "/process",
      "Как это работает"
    ],
    "details": [
      [
        "Фото с нуля",
        "Опиши композицию, освещение, фон и настроение. Начни с простого промпта и уточняй детали в следующих версиях.",
        "/features/photo",
        "Создавать фото"
      ],
      [
        "От снимка к видео",
        "Выбери исходное изображение и опиши движение камеры или героя. Доступные режимы и длительность зависят от модели.",
        "/features/video",
        "Создавать видео"
      ],
      [
        "По тексту",
        "Расскажи о герое, сюжете, свете и настроении.",
        "/features/text",
        "Создавать по тексту"
      ],
      [
        "По своему фото",
        "Возьми собственный снимок за основу, опиши необходимые изменения.",
        "/features/own-photo",
        "Работать со снимком"
      ],
      [
        "Твои референсы",
        "Используй собственные кадры, когда важно сохранить детали образа или композиции. Загружай изображения, на которые у тебя есть права.",
        "/features/reference",
        "Работать с референсами"
      ],
      [
        "Повторы трендов",
        "Открой понравившийся тренд и добавь исходники, которые просит выбранный сценарий. Настройки и стоимость видны в студии.",
        "/gallery",
        "Открыть тренды"
      ]
    ]
  },
  "gallery": {
    "label": "Галерея",
    "title": "Идеи в движении.",
    "accent": "в движении.",
    "description": "Популярные реальные тренды ROXY: фотографии и видео. Открой понравившийся шаблон и создай свой вариант.",
    "heading": "gallery-title",
    "next": [
      "/features",
      "Все инструменты"
    ],
    "details": [
      [
        "Выбери идею",
        "Галерея показывает активные тренды с доступными превью. Порядок основан на количестве запусков в каталоге.",
        "/process",
        "Как повторить тренд"
      ],
      [
        "Сделай свою версию",
        "Нажми на плитку, чтобы перейти к выбранному тренду после входа. Добавь нужные референсы и проверь настройки перед запуском.",
        "/faq",
        "Вопросы о референсах"
      ]
    ]
  },
  "process": {
    "label": "Процесс",
    "title": "От идеи до кадра.",
    "accent": "до кадра.",
    "description": "Как создать фотографию или видео в ROXY: выбор инструмента, описание, исходники, запуск и результат.",
    "heading": "process-title",
    "next": [
      "/gallery",
      "Выбрать тренд"
    ],
    "details": [
      [
        "Подготовь исходники",
        "Для конкретного образа используй чёткий кадр и нужные референсы. Для генерации с нуля достаточно текстового описания.",
        "/features",
        "Выбрать инструмент"
      ],
      [
        "Опиши результат",
        "Укажи героя, действие, стиль и настроение. Для видео полезно описать движение и ракурс, не только внешний вид.",
        "/features/text",
        "Работа с описанием"
      ],
      [
        "Проверь условия запуска",
        "Перед генерацией посмотри доступные настройки и стоимость в ROX. Они зависят от выбранной модели и режима.",
        "/faq",
        "Как работает стоимость"
      ],
      [
        "Сохрани или повтори",
        "Готовая работа остаётся в истории аккаунта. Можно использовать результат как исходник, если выбранный инструмент это поддерживает.",
        "/gallery",
        "Найти новую идею"
      ]
    ]
  },
  "faq": {
    "label": "Вопросы",
    "title": "Всё перед стартом.",
    "accent": "перед стартом.",
    "description": "Ответы на вопросы о создании фото и видео, референсах, аккаунте и работе с ROXY.",
    "heading": "faq-title",
    "next": [
      "/features",
      "Возможности студии"
    ],
    "details": [
      [
        "Нужна помощь?",
        "Войди в ROXY и перейди в раздел поддержки аккаунта, если возник вопрос о генерации, оплате или работе сервиса.",
        "/login",
        "Войти в ROXY"
      ],
      [
        "Готов к первому кадру?",
        "Начни с готового тренда или выбери фото либо видео. Не нужно заранее изучать все настройки.",
        "/gallery",
        "Выбрать идею"
      ]
    ]
  }
};
const toolsData=[
  {
    "id": "photo",
    "name": "Фото",
    "title": "Фотографии, которых ещё не было.",
    "accent": "ещё не было.",
    "description": "Создавай новые изображения по описанию, меняй стиль и композицию.",
    "intro": "От портрета до предметной съёмки. Задай настроение, свет и композицию — выбери подходящую модель в студии.",
    "example": "Крупный портрет в мягком боковом свете, тёплые оттенки, фактура плёнки, спокойный фон.",
    "blocks": [
      [
        "С нуля",
        "Опиши сцену и желаемый результат. Можно начать с нескольких точных деталей."
      ],
      [
        "Варианты",
        "Меняй описание, ракурс или стиль, чтобы получить новую версию."
      ],
      [
        "Твои кадры",
        "Если нужен исходный снимок, выбери режим работы со своим фото."
      ],
      [
        "Перед запуском",
        "Проверь модель, формат и стоимость в студии."
      ]
    ]
  },
  {
    "id": "video",
    "name": "Видео",
    "title": "Добавь кадру движение.",
    "accent": "движение.",
    "description": "Создавай видео по тексту или исходным кадрам в доступных видеомоделях ROXY.",
    "intro": "Из статичного изображения или описания — в движущуюся сцену. Направление движения, длительность и формат зависят от выбранной модели.",
    "example": "Медленное приближение камеры, ветер двигает волосы, мягкий свет меняется в кадре.",
    "blocks": [
      [
        "Движение",
        "Опиши действие героя, камеры или объектов в кадре."
      ],
      [
        "Первый кадр",
        "Для подходящих моделей загрузи фото, с которого начинается видео."
      ],
      [
        "Формат",
        "Длительность, пропорции и звук зависят от выбранного режима."
      ],
      [
        "Готовая работа",
        "Открой результат в истории студии и сохрани его."
      ]
    ]
  },
  {
    "id": "text",
    "name": "По тексту",
    "title": "Слова становятся кадрами.",
    "accent": "кадрами.",
    "description": "Создание визуала по текстовому описанию, без обязательного исходного фото.",
    "intro": "Начни с идеи. Расскажи, что должно быть в кадре, какой нужен свет, ракурс и настроение.",
    "example": "Ночной город после дождя, неоновый свет отражается в лужах, широкоугольная кинематографическая композиция.",
    "blocks": [
      [
        "Сюжет",
        "Назови главного героя, место и действие."
      ],
      [
        "Визуальный стиль",
        "Добавь цвет, освещение, композицию и детали."
      ],
      [
        "Уточнение",
        "Если результат не совпал с идеей, измени описание и повтори."
      ],
      [
        "Выбор режима",
        "В студии выбери фото или видео по тексту."
      ]
    ]
  },
  {
    "id": "own-photo",
    "name": "По своему фото",
    "title": "Твой снимок. Новый образ.",
    "accent": "Новый образ.",
    "description": "Редактируй собственные фотографии и создавай визуальные вариации.",
    "intro": "Загрузи свой кадр и опиши, что изменить. В поддерживаемых моделях можно сохранить важные детали исходника.",
    "example": "Сохрани черты лица, поменяй фон на вечерний город, добавь мягкое фиолетовое освещение.",
    "blocks": [
      [
        "Исходник",
        "Выбери чёткую фотографию, которой можешь распоряжаться."
      ],
      [
        "Что сохранить",
        "Укажи внешность, композицию или детали, важные для результата."
      ],
      [
        "Что изменить",
        "Опиши новый фон, одежду, стиль или освещение."
      ],
      [
        "Параметры",
        "Доступные форматы и количество входных изображений определяет модель."
      ]
    ]
  },
  {
    "id": "reference",
    "name": "По референсу",
    "title": "Собери свой визуальный язык.",
    "accent": "визуальный язык.",
    "description": "Используй изображения и поддерживаемые референсы для направления композиции и стиля.",
    "intro": "Покажи желаемое настроение, ракурс или образ на примере. Добавляй только те материалы, на которые у тебя есть права.",
    "example": "Сохрани свет и цвет первого референса, используй композицию второго, сделай собственный портрет.",
    "blocks": [
      [
        "Подбор",
        "Выбери референсы, которые объясняют идею."
      ],
      [
        "Роли",
        "В описании уточни, какие детали брать из каждого исходника."
      ],
      [
        "Сочетание",
        "Совмещай визуальное направление с текстовым описанием."
      ],
      [
        "Режим",
        "Поддерживаемые типы референсов и настройки зависят от выбранной модели."
      ]
    ]
  }
];
const loginVersion="e7dc50d3cb36";
function buildPages(home,pageData,toolsData,loginVersion){
 const result={};
 const shell=home.match(/^(.*?)<main id="content">/s)?.[1],suffix=home.match(/<\/main>([\s\S]*)$/)?.[1];
 const final=home.match(/<section class="final-section"[\s\S]*?<\/section>/)?.[0];
 if(!shell||!suffix||!final)throw Error("invalid home shell");
 const pre=(id,label,desc,path,active,extra="")=>shell.replace('<body data-page="home">',`<body class="subpage${extra}" data-page="${id}">`)
  .replace(/<title>[\s\S]*?<\/title>/,`<title>ROXY AI STUDIO — ${label}</title>`)
  .replace(/(<meta name="description" content=")[^"]*"/,`$1${desc}"`)
  .replace(/(<meta property="og:title" content=")[^"]*"/,`$1ROXY AI STUDIO — ${label}"`)
  .replace(/(<meta property="og:description" content=")[^"]*"/,`$1${desc}"`)
  .replace(/(<link rel="canonical" href="[^"]*\/)"/,`$1${path.slice(1)}"`)
  .replace(/(<meta property="og:url" content="[^"]*\/)"/,`$1${path.slice(1)}"`)
  .replace(/\n  <link rel="preload" as="image"[^>]+>/,"")
  .replaceAll(' data-site-link aria-current="page">Главная',' data-site-link>Главная')
  .replaceAll(`href="${active}" data-site-link>`,`href="${active}" data-site-link aria-current="page">`);
 const end=(gallery=false)=>gallery?suffix:suffix.replace(/<script src="\/site-assets\/popular-trends\.js[^>]+><\/script>/,"");
 const breadcrumb=(label,parent=false)=>`<nav class="page-breadcrumb" aria-label="Путь страницы"><a href="/" data-site-link>Главная</a><span aria-hidden="true">/</span>${parent?'<a href="/features" data-site-link>Возможности</a><span aria-hidden="true">/</span>':""}<span>${label}</span></nav>`;
 const more=(url,label)=>`<a class="section-more" href="${url}" ${url==="/login"?"data-app-link":"data-site-link"}>${label} <span aria-hidden="true">↗</span></a>`;
 const next=(url,label)=>`<nav class="page-next" aria-label="Продолжить знакомство"><a class="section-more" href="/" data-site-link>← Главная</a>${more(url,label)}</nav>`;
 const clean=s=>s.replace(/[ \t]+$/gm,"");
 for(const [id,d] of Object.entries(pageData)){
  const match=home.match(new RegExp(`<section class="section [^"]+" id="${id}"[\\s\\S]*?<\\/section>`));
  if(!match)throw Error("missing section "+id);
  let section=match[0].replace(new RegExp(`<h2 id="${d.heading}">[^<]+<\\/h2>`),`<h1 class="page-intro" id="${d.heading}">${d.title.replace(d.accent,`<em>${d.accent}</em>`)}</h1>`);
  section=section.replace(/<a class="section-more"[^>]*>[\s\S]*?<\/a>/g,"");
  section=section.replace(/(<section[^>]*>)/,"$1\n      "+breadcrumb(d.label));
  if(id==="gallery"){
    section=section.replace('id="popular-trends"','id="popular-trends" data-limit="12"')
      .replace('href="/gallery" data-site-link>Все тренды','href="/login" data-app-link>Открыть студию');
  }
  if(id==="features"){
    section=section.replace('href="/features" data-site-link>Перейти к инструментам','href="/login" data-app-link>Начать создавать');
  }
  if(id==="faq"){
    const extra=[
      ["Как узнать стоимость генерации?","Стоимость и доступные параметры показываются в приложении перед запуском. Они зависят от модели и выбранного режима."],
      ["Можно ли использовать чужие фотографии?","Используй изображения, видео и другие материалы, на которые у тебя есть необходимые права или разрешение."],
      ["Где найти готовые работы?","Открой историю своего аккаунта в ROXY. Доступные действия с работой зависят от её типа и состояния."],
      ["Что делать, если генерация не пришла?","Проверь историю и статус работы. Если проблема сохраняется, обратись в поддержку через приложение."]
    ].map(([q,a])=>`        <details><summary>${q}<span aria-hidden="true">+</span></summary><p>${a}</p></details>`).join("\n");
    section=section.replace(/(\n      <\/div>\s*<\/section>)/,`\n${extra}$1`);
  }
  const details=`<div class="page-details">${d.details.map(([h,p,url,cta])=>`<article class="detail-panel"><h2>${h}</h2><p>${p}</p>${more(url,cta)}</article>`).join("\n")}</div>`;
  section=section.replace(/<\/section>$/,details+"\n    </section>");
  result[id]=clean(pre(id,d.label,d.description,"/"+id,"/"+id)+`<main id="content">\n    ${section}\n    ${next(...d.next)}\n    ${final}\n  </main>`+end(id==="gallery"));
 }
 for(const d of toolsData){
  const id="feature-"+d.id;
  const heading=d.title.replace(d.accent,`<em>${d.accent}</em>`);
  const section=`<section class="section tool-section" aria-labelledby="tool-title">
    ${breadcrumb(d.name,true)}
    <div class="editorial-intro"><div><span class="eyebrow">${d.name} / ROXY STUDIO</span><h1 class="page-intro" id="tool-title">${heading}</h1></div><p>${d.intro}</p></div>
    <div class="tool-actions"><a class="button button-primary" href="/login?tool=${d.id}" data-app-link>Начать создавать <span aria-hidden="true">↗</span></a><a class="button button-outline" href="/gallery" data-site-link>Смотреть тренды</a></div>
    <div class="tool-example"><strong>Пример описания</strong>${d.example}</div>
    <div class="page-details">${d.blocks.map(([h,p])=>`<article class="detail-panel"><h2>${h}</h2><p>${p}</p></article>`).join("\n")}</div>
    <nav class="tool-picker" aria-label="Другие инструменты">${toolsData.filter(t=>t.id!==d.id).map(t=>`<a href="/features/${t.id}" data-site-link>${t.name}</a>`).join("")}</nav>
  </section>`;
  result[id]=clean(pre(id,d.name,d.description,"/features/"+d.id,"/features"," tool-page")+`<main id="content">\n    ${section}\n    ${next("/features","Все возможности")}\n    ${final}\n  </main>`+end());
 }
 const loginShell=pre("login","Вход","Вход в ROXY AI STUDIO через Telegram.","/login","/login"," login-page")
    .replace('name="robots" content="index,follow"','name="robots" content="noindex,nofollow"')
    .replace('href="/login" data-app-link>Начать <span aria-hidden="true">↗</span>','href="/" data-site-link>На главную <span aria-hidden="true">↗</span>');
 const login=`<section class="section login-layout" aria-labelledby="login-title">
   <div>
    ${breadcrumb("Вход")}
    <span class="eyebrow">ROXY / CREATIVE STUDIO</span>
    <h1 id="login-title" class="page-intro">Твой следующий кадр <em>начинается здесь.</em></h1>
    <p class="login-lead">Войди в свой аккаунт. История работ и баланс останутся с тобой.</p>
    <a class="login-return" href="/gallery" data-site-link>← Вернуться к галерее</a>
   </div>
   <div class="login-panel">
    <h2>Вход в ROXY</h2>
    <p>Подтверди вход через Telegram, чтобы продолжить с существующим профилем.</p>
    <p class="login-target" id="login-target" hidden>После входа откроется выбранный тренд.</p>
    <div class="login-widget" id="login-widget" aria-live="polite"></div>
    <p class="login-status" id="login-status" role="status" aria-live="polite">Подключаем безопасный вход…</p>
    <a class="button button-primary" id="login-continue" hidden>Продолжить в студии ↗</a>
    <button class="button button-outline" type="button" id="login-retry" hidden>Попробовать ещё раз</button>
    <noscript><p>Для входа необходимо включить JavaScript.</p></noscript>
   </div>
 </section>`;
 result.login=clean(loginShell+`<main id="content">\n    ${login}\n  </main>`+end().replace("</body>",`<script src="/site-assets/site-login.js?v=${loginVersion}" defer></script>\n</body>`));
 return result;
}
const pages=buildPages(readFileSync(dir+'index.html','utf8'),pageData,toolsData,loginVersion);
for(const [name,html] of Object.entries(pages)){
 const path=dir+name+'.html';
 if(process.argv.includes('--check')){if(readFileSync(path,'utf8')!==html)throw new Error('Stale generated page: '+name);}
 else writeFileSync(path,html,'utf8');
}
