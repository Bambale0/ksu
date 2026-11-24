import { expect, test } from '@playwright/test';

const pages = [
  ['/', 'Главная', 'hero-title'],
  ['/features', 'Возможности', 'features-title'],
  ['/gallery', 'Галерея', 'gallery-title'],
  ['/process', 'Процесс', 'process-title'],
  ['/faq', 'Вопросы', 'faq-title'],
];

async function fixtureGallery(page) {
  const requests=[];
  await page.route('**/api/v1/public-site/popular-trends?*', route => {
    const limit=Number(new URL(route.request().url()).searchParams.get('limit'));
    requests.push(limit);
    const items=Array.from({length:limit},(_,i)=>({
      id:'11111111-1111-4111-8111-'+String(i+1).padStart(12,'0'),
      title:'Тренд '+(i+1),preview_kind:'image',
      preview_url:'/site-assets/atlas-1920.webp',usage_count:100-i,
    }));
    return route.fulfill({json:{items}});
  });
  return requests;
}

for(const width of [320,390,768,1440,1648]){
  test(`all five public pages have real navigation and fit ${width}px`,async({page})=>{
    await page.setViewportSize({width,height:900});
    await page.emulateMedia({reducedMotion:'reduce'});
    const requests=await fixtureGallery(page);
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto('/?ref=QA&unknown=discard',{waitUntil:'domcontentloaded'});
    const titles=new Set();
    for(const [path,label,id] of pages){
      if(path!=='/'){
        if(width<=1000){
          await page.locator('.mobile-nav summary').click();
          await page.locator('.mobile-nav nav').getByRole('link',{name:label,exact:true}).click();
        }else{
          await page.locator('.desktop-nav').getByRole('link',{name:label,exact:true}).click();
        }
      }
      await expect(page).toHaveURL(new RegExp(path==='/'?'\\/\\?ref=QA':'\\'+path+'\\?ref=QA$'));
      await expect(page.locator('h1')).toHaveCount(1);
      await expect(page.locator('#'+id)).toBeVisible();
      await expect(page.locator('.desktop-nav a[aria-current="page"]')).toHaveText(label);
      expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);
      const title=await page.title(); expect(titles.has(title)).toBe(false); titles.add(title);
      await expect(page.locator('.top-action')).toHaveAttribute('href','/login?ref=QA');
      if(path==='/gallery'){
        await page.locator('#popular-trends').scrollIntoViewIfNeeded();
        await expect(page.locator('.live-trend-tile')).toHaveCount(12);
        expect(requests).toContain(12);
        await expect(page.locator('.live-trend-link').first()).toHaveAttribute('href',/\/login\?trend=.*&ref=QA$/);
      }
      if(path==='/faq'){
        const faq=page.locator('.faq-list details').first();
        await faq.locator('summary').click();
        await expect(faq).toHaveAttribute('open','');
        await faq.locator('summary').press('Enter');
        await expect(faq).not.toHaveAttribute('open','');
      }
    }
    expect(errors).toEqual([]);
    await page.goBack();
    await expect(page.locator('#process-title')).toBeVisible();
    await page.reload();
    await expect(page.locator('#process-title')).toBeVisible();
  });
}
