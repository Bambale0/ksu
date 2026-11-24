import { expect, test } from '@playwright/test';

const tools = ['photo','video','text','own-photo','reference'];
const trend = '11111111-1111-4111-8111-111111111111';

async function widget(page, options={}) {
  await page.route('**/api/v1/web-auth/me',route=>route.fulfill({json:{authenticated:false}}));
  await page.route('**/api/v1/web-auth/config',route=>route.fulfill({
    status:options.configStatus || 200,
    json:{bot_username:'RoxyTestBot',providers:{telegram:true,email:false,yandex:false}}
  }));
  await page.route('https://telegram.org/js/telegram-widget.js?22',route=>route.fulfill({
    status:200,contentType:'application/javascript',body:'window.__roxyWidgetLoaded=true;'
  }));
}

for (const width of [320,390,768,1440,1648]) {
  test(`each hero tile opens its own page and sign-in at ${width}px`,async({page})=>{
    await page.setViewportSize({width,height:900});
    await page.emulateMedia({reducedMotion:'reduce'});
    await widget(page);
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto('/?ref=QA',{waitUntil:'domcontentloaded'});
    const cards=page.locator('.hero-formats .format-card');
    await expect(cards).toHaveCount(5);
    for(let i=0;i<tools.length;i++){
      const id=tools[i];
      await expect(cards.nth(i)).toHaveAttribute('href','/features/'+id+'?ref=QA');
      await cards.nth(i).click();
      await expect(page.locator('body')).toHaveAttribute('data-page','feature-'+id);
      await expect(page.locator('h1')).toBeVisible();
      await expect(page.locator('.desktop-nav a[aria-current="page"]')).toHaveText('Возможности');
      expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);
      await expect(page.locator('.tool-actions .button-primary')).toHaveAttribute('href','/login?tool='+id+'&ref=QA');
      await page.locator('.tool-actions .button-primary').click();
      await expect(page.locator('body')).toHaveAttribute('data-page','login');
      await expect(page.locator('#login-status')).toContainText('Подтверди вход через Telegram');
      expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);
      await page.goBack();
      await expect(page.locator('body')).toHaveAttribute('data-page','feature-'+id);
      await page.goBack();
      await expect(page.locator('body')).toHaveAttribute('data-page','home');
    }
    expect(errors).toEqual([]);
  });
}

test('chosen trend opens standalone login and returns to exact trend only after signed exchange',async({page})=>{
  await widget(page);
  await page.route('**/api/v1/public-site/popular-trends?*',route=>route.fulfill({
    json:{items:[{id:trend,title:'Тестовый тренд',preview_kind:'image',preview_url:'/site-assets/atlas-1920.webp',usage_count:1}]}
  }));
  let writes=0;
  await page.route('**/api/v1/web-auth/telegram',route=>{
    writes++;
    expect(route.request().postDataJSON().telegram_auth.id).toBe(42);
    return route.fulfill({json:{ok:true,user_id:'11111111-1111-4111-8111-111111111111'},headers:{'set-cookie':'roxy_web_session=fixture-cookie; Path=/; HttpOnly; SameSite=Lax'}});
  });
  await page.route('**/api/v1/me',route=>route.fulfill({json:{id:'synthetic',telegram_id:42}}));
  await page.goto('/gallery?ref=QA&unknown=discard');
  await page.locator('#popular-trends').scrollIntoViewIfNeeded();
  const link=page.locator('.live-trend-link').first();
  await expect(link).toHaveAttribute('href','/login?trend='+trend+'&ref=QA');
  await link.click();
  await expect(page.locator('body')).toHaveAttribute('data-page','login');
  await expect(page.locator('#login-target')).toBeVisible();
  await expect(page.locator('#login-status')).toContainText('Подтверди вход');
  expect(writes).toBe(0);
  await page.evaluate(()=>{void window.onRoxyTelegramAuth({id:42,first_name:'Test',auth_date:1,hash:'fixture'});});
  await page.waitForURL(url=>url.pathname==='/mini-app/trend/');
  const url=new URL(page.url());
  expect(url.searchParams.get('id')).toBe(trend);
  expect(url.searchParams.get('ref')).toBe('QA');
  expect(url.searchParams.has('unknown')).toBe(false);
  expect(url.searchParams.has('init_data')).toBe(false);
  expect(writes).toBe(1);
  expect(await page.evaluate(()=>sessionStorage.getItem('__roxy_browser_init_data_v1'))).toBeNull();
  expect((await page.context().cookies()).some(c=>c.name==='roxy_web_session' && c.httpOnly)).toBe(true);
});

test('entry rejects arbitrary destinations, handles unavailable provider and never exposes unauthenticated continue',async({page})=>{
  await widget(page,{configStatus:503});
  await page.goto('/login?next=https%3A%2F%2Fexample.invalid&trend=invalid&ref=QA');
  await expect(page.locator('#login-status')).toHaveAttribute('role','alert');
  await expect(page.locator('#login-retry')).toBeVisible();
  await expect(page.locator('#login-continue')).toBeHidden();
  await expect(page.locator('#login-target')).toBeHidden();
  await widget(page);
  await page.locator('#login-retry').click();
  await expect(page.locator('#login-status')).toContainText('Подтверди вход');
  await page.route('**/api/v1/web-auth/telegram',route=>route.fulfill({status:401,json:{detail:'Invalid login'}}));
  await page.evaluate(()=>{void window.onRoxyTelegramAuth({id:42,first_name:'Test',auth_date:1,hash:'fixture'});});
  await expect(page.locator('#login-status')).toHaveAttribute('role','alert');
  expect(new URL(page.url()).pathname).toBe('/login');
  expect(await page.evaluate(()=>sessionStorage.getItem('__roxy_browser_init_data_v1'))).toBeNull();
});

test('existing signed browser session can continue but arbitrary next URL is ignored',async({page})=>{
  await page.route('**/api/v1/web-auth/me',route=>route.fulfill({json:{authenticated:false}}));
  await page.addInitScript(()=>sessionStorage.setItem('__roxy_browser_init_data_v1',JSON.stringify({initData:'query_id=existing&hash=fixture',expiresAt:Date.now()+60000})));
  await page.route('**/api/v1/me',route=>route.fulfill({json:{id:'synthetic',telegram_id:42}}));
  await page.goto('/login?next=https%3A%2F%2Fexample.invalid&trend=invalid&ref=QA');
  await expect(page.locator('#login-continue')).toBeVisible();
  await expect(page.locator('#login-continue')).toHaveAttribute('href','/mini-app/?ref=QA');
});


test('video tool entry continues to the real create screen with the video category selected',async({page})=>{
  await page.addInitScript(()=>{
    sessionStorage.setItem('__roxy_browser_init_data_v1',JSON.stringify({initData:'query_id=existing&hash=fixture',expiresAt:Date.now()+60000}));
    localStorage.setItem('ksu-selected-media','image');
  });
  const model=(id,media)=>({
    id,title:media==='video'?'Тест видео':'Тест фото',family:id,media_type:media,
    operation:media==='video'?'text_to_video':'text_to_image',
    known_fields:['prompt'],required_fields:['prompt'],price_rox:'10.00',
    ui_schema:{defaults:{},fields:[{name:'prompt',label:'Описание',control:'textarea',required:true}]},
  });
  let paidWrites=0;
  await page.route('**/api/v1/**',route=>{
    const req=route.request();
    const path=new URL(req.url()).pathname;
    if(path==='/api/v1/me')return route.fulfill({json:{id:'synthetic',telegram_id:42,first_name:'QA',balance_rox:'1000',is_admin:false}});
    if(path==='/api/v1/onboarding')return route.fulfill({json:{enabled:false,completed:true}});
    if(path==='/api/v1/generations/models')return route.fulfill({json:{models:[model('qa-photo','image'),model('qa-video','video')],families:[]}});
    if(req.method()==='POST' && path==='/api/v1/generations')paidWrites++;
    return route.fulfill({json:{items:[]}});
  });
  await page.goto('/features/video?ref=QA');
  await page.locator('.tool-actions .button-primary').click();
  await expect(page.locator('#login-continue')).toBeVisible();
  await expect(page.locator('#login-continue')).toHaveAttribute('href','/mini-app/?route=create&create_media=video&ref=QA');
  await page.locator('#login-continue').click();
  await expect(page.locator('.family-tabs .active')).toHaveText('Видео');
  expect(paidWrites).toBe(0);
});

test('cookie session takes precedence over old browser credential and permits provider linking',async({page})=>{
  await page.addInitScript(()=>sessionStorage.setItem('__roxy_browser_init_data_v1',JSON.stringify({initData:'stale-identity',expiresAt:Date.now()+60000})));
  await page.route('**/api/v1/web-auth/me',route=>route.fulfill({json:{authenticated:true,user_id:'11111111-1111-4111-8111-111111111111'}}));
  await page.route('**/api/v1/web-auth/config',route=>route.fulfill({json:{providers:{telegram:false,email:true,yandex:true}}}));
  await page.route('**/api/v1/web-auth/email/request',route=>route.fulfill({json:{ok:true}}));
  let linked=false;
  await page.route('**/api/v1/web-auth/email/verify',route=>{
    const payload=route.request().postDataJSON();
    expect(payload).toEqual({email:'qa@example.test',code:'123456',link:true});
    linked=true;
    return route.fulfill({json:{ok:true}});
  });
  await page.goto('/login');
  await expect(page.locator('#login-continue')).toBeVisible();
  expect(await page.evaluate(()=>sessionStorage.getItem('__roxy_browser_init_data_v1'))).toBeNull();
  await page.locator('#login-link').click();
  await expect(page.locator('#login-yandex')).toBeVisible();
  const yandex=new URL(await page.locator('#login-yandex').getAttribute('href'),page.url());
  expect(yandex.searchParams.get('link')).toBe('true');
  await page.locator('#login-email').fill('qa@example.test');
  await page.locator('#login-email-form button').click();
  await expect(page.locator('#login-code-form')).toBeVisible();
  await page.locator('#login-code').fill('123456');
  await page.locator('#login-code-form button').click();
  await expect(page).toHaveURL(/login\?linked=1$/);
  expect(linked).toBe(true);
});
