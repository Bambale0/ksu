import { expect, test } from '@playwright/test';

const tools = ['photo','video','text','own-photo','reference'];
const trend = '11111111-1111-4111-8111-111111111111';

async function widget(page, options={}) {
  await page.route('**/api/v1/browser-auth/config',route=>route.fulfill({
    status:options.configStatus || 200,
    json:{bot_username:'RoxyTestBot'}
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
      await expect(page.locator('.tool-actions .button-primary')).toHaveAttribute('href','/login?ref=QA');
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
  await page.route('**/api/v1/browser-auth',route=>{
    writes++;
    expect(route.request().postDataJSON().telegram_auth.id).toBe(42);
    return route.fulfill({json:{ok:true,init_data:'query_id=browser-test&hash=synthetic',expires_in:3600}});
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
  expect(await page.evaluate(()=>JSON.parse(sessionStorage.getItem('__roxy_browser_init_data_v1')).initData)).toBe('query_id=browser-test&hash=synthetic');
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
  await page.route('**/api/v1/browser-auth',route=>route.fulfill({status:401,json:{detail:'Invalid login'}}));
  await page.evaluate(()=>{void window.onRoxyTelegramAuth({id:42,first_name:'Test',auth_date:1,hash:'fixture'});});
  await expect(page.locator('#login-status')).toHaveAttribute('role','alert');
  expect(new URL(page.url()).pathname).toBe('/login');
  expect(await page.evaluate(()=>sessionStorage.getItem('__roxy_browser_init_data_v1'))).toBeNull();
});

test('existing signed browser session can continue but arbitrary next URL is ignored',async({page})=>{
  await page.addInitScript(()=>sessionStorage.setItem('__roxy_browser_init_data_v1',JSON.stringify({initData:'query_id=existing&hash=fixture',expiresAt:Date.now()+60000})));
  await page.route('**/api/v1/me',route=>route.fulfill({json:{id:'synthetic',telegram_id:42}}));
  await page.goto('/login?next=https%3A%2F%2Fexample.invalid&trend=invalid&ref=QA');
  await expect(page.locator('#login-continue')).toBeVisible();
  await expect(page.locator('#login-continue')).toHaveAttribute('href','/mini-app/?ref=QA');
});
