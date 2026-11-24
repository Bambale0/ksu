import { test, expect } from '@playwright/test';

const photo = {title:'QA Photo',media_type:'image',operation:'text_to_image',price_mode:'flat',retail_price_rox:'14.50',price_rox:'0.00',ui_schema:{fields:[]}};
const video = {title:'QA Video',media_type:'video',operation:'image_to_video',price_mode:'per_second',price_rox:'8.00',ui_schema:{fields:[{name:'image_url',group:'references',control:'file',accept:'image/*',required:true},{name:'duration',min:5,max:10}]}};
const music = {title:'QA Music',media_type:'audio',operation:'text_to_music',price_mode:'flat',price_rox:'25.00',ui_schema:{fields:[]}};
const packages = {configured:true,packages:{a:{credits:'300',bonus_credits:'30',total_credits:'330',prices:{RUB:'326.10'}}}};
const paths=['/','/features','/features/photo','/features/video','/features/text','/features/own-photo','/features/reference','/gallery','/process','/pricing','/faq','/login'];

async function setup(page){
 await page.route('**/api/v1/generations/models',route=>route.fulfill({json:{models:[photo,video,music]}}));
 await page.route('**/api/v1/payments/yookassa/packages',route=>route.fulfill({json:packages}));
 await page.route('**/api/v1/public-site/popular-trends?*',route=>route.fulfill({json:{items:[]}}));
 await page.route('**/api/v1/browser-auth/config',route=>route.fulfill({json:{bot_username:'RoxyTestBot'}}));
 await page.route('https://telegram.org/js/telegram-widget.js?22',route=>route.fulfill({contentType:'application/javascript',body:'window.__roxyWidgetLoaded=true;'}));
}

for(const width of [390,1440]){
 test(`all twelve public documents render without overflow at ${width}px`,async({page})=>{
  await setup(page);
  await page.setViewportSize({width,height:900});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  for(const path of paths){
   const response=await page.goto(path);
   expect(response.status()).toBe(200);
   await expect(page.locator('h1')).toHaveCount(1);
   for(const block of await page.locator('[data-catalog],[data-packages]').all())await expect(block).toHaveAttribute('aria-busy','false');
   expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);
  }
  expect(errors).toEqual([]);
 });
}
test('pricing uses retail data, true package total, shared request and filters',async({page})=>{
 await setup(page);
 let requests=0;
 await page.route('**/api/v1/generations/models',route=>{requests++;return route.fulfill({json:{models:[photo,video,music,{...photo,title:'Invalid',retail_price_rox:'NaN'}]}});});
 await page.goto('/pricing?ref=QA');
 const models=page.locator('[data-catalog="all"]');
 await expect(models.locator('.model-price-card')).toHaveCount(3);
 await expect(models).toContainText('14,5 ROX / запуск');
 await expect(models).toContainText('8 ROX / с');
 await expect(page.locator('[data-packages]')).toContainText('330 ROX');
 await expect(page.locator('[data-packages]')).toContainText('326,1 ₽');
 expect(requests).toBe(1);
 await models.getByRole('button',{name:'Видео',exact:true}).click();
 await expect(models.locator('.model-price-card:visible')).toHaveCount(1);
 await expect(models.locator('.model-price-card:visible')).toContainText('QA Video');
 await models.getByRole('button',{name:'Все',exact:true}).click();
 await expect(models.locator('.model-price-card:visible')).toHaveCount(3);
 await expect(page.locator('.price-actions .button-primary')).toHaveAttribute('href','/login?section=profile&ref=QA');
});
test('prices recover after API failure without inventing amounts',async({page})=>{
 await setup(page);
 let calls=0;
 await page.route('**/api/v1/generations/models',route=>++calls===1?route.fulfill({status:503,json:{}}):route.fulfill({json:{models:[photo]}}));
 await page.goto('/pricing');
 const overview=page.locator('[data-catalog="overview"]');
 await expect(overview).toContainText('Не удалось загрузить цены');
 await expect(page.locator('.model-price-card')).toHaveCount(0);
 await overview.getByRole('button',{name:'Повторить'}).click();
 await expect(page.locator('[data-catalog="all"] .model-price-card')).toHaveCount(1);
 expect(calls).toBe(2);
});
test('gallery labels first step price and gracefully handles unavailable image',async({page})=>{
 await setup(page);
 await page.route('**/api/v1/public-site/popular-trends?*',route=>route.fulfill({json:{items:[{id:'11111111-1111-4111-8111-111111111111',title:'QA workflow',preview_kind:'image',preview_url:'/site-assets/missing-original.webp',poster_url:'/site-assets/missing-thumbnail.webp',usage_count:1,catalog_cost_rox:'125.50',catalog_cost_kind:'first_step'}]}}));
 await page.goto('/gallery');
 await page.locator('#popular-trends').scrollIntoViewIfNeeded();
 await expect(page.locator('.live-trend-price')).toHaveText('1-й этап: 125,5 ROX');
 await expect(page.locator('.live-trend-placeholder')).toBeVisible();
 await expect(page.locator('.live-trend-link')).toHaveAttribute('href','/login?trend=11111111-1111-4111-8111-111111111111');
});

test('catalogue retains priced models with unfamiliar operation names',async({page})=>{
 await setup(page);
 const extra=[
  {...video,title:'Grok Video Upscale',operation:'video_upscale',price_rox:'5.00',ui_schema:{fields:[]}},
  {...video,title:'Grok Video Extend',operation:'video_extend',price_rox:'10.00',ui_schema:{fields:[]}},
  {...video,title:'Future Video Mode',operation:'future_video_operation',price_rox:'17.00',ui_schema:{fields:[]}}
 ];
 await page.route('**/api/v1/generations/models',route=>route.fulfill({json:{models:[photo,video,music,...extra]}}));
 await page.goto('/pricing');
 const models=page.locator('[data-catalog="all"]');
 await expect(models.locator('.model-price-card')).toHaveCount(6);
 await expect(models).toContainText('Grok Video Upscale');
 await expect(models).toContainText('Grok Video Extend');
 await expect(models).toContainText('Future Video Mode');
 await expect(models).toContainText('Параметры в студии');
 await expect(page.locator('[data-catalog="overview"]')).toContainText('4 режима в каталоге');
 await page.goto('/features/video');
 await expect(page.locator('.model-price-card')).toHaveCount(4);
 await page.goto('/features/text');
 await expect(page.locator('.model-price-card')).toHaveCount(1);
 await expect(page.locator('.model-price-card')).toContainText('QA Photo');
});

