import { expect, test } from '@playwright/test';

async function openSite(page) {
  await page.route('**/api/v1/public-site/popular-trends?*', route => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({items:[]}),
  }));
  await page.goto('/', {waitUntil:'domcontentloaded'});
  await expect(page.locator('.hero-art-photo')).toBeVisible();
}

for (const [width,height] of [[320,740],[390,844],[768,1024],[1440,900],[1648,928],[1850,830]]) {
  test(`approved campaign composition fits ${width}×${height}`, async ({page}) => {
    await page.setViewportSize({width,height});
    await openSite(page);
    const art = page.locator('.hero-art-photo');
    expect(await art.evaluate(node => getComputedStyle(node).backgroundSize)).toBe('contain');
    expect(await art.evaluate(node => getComputedStyle(node).backgroundImage)).toContain('roxy-hero-cutout.webp');
    const lines = page.locator('.hero-line');
    await expect(lines).toHaveCount(3);
    await expect(page.locator('.hero-formats .format-card')).toHaveCount(5);
    const metrics = await page.evaluate(() => {
      const title = document.querySelector('.hero h1').getBoundingClientRect();
      const cards = document.querySelector('.hero-formats').getBoundingClientRect();
      const copy = document.querySelector('.hero-copy').getBoundingClientRect();
      return {overflow:document.documentElement.scrollWidth-innerWidth,titleRight:title.right,copyBottom:copy.bottom,cardsTop:cards.top,cardsBottom:cards.bottom};
    });
    expect(metrics.overflow).toBeLessThanOrEqual(1);
    expect(metrics.copyBottom).toBeLessThanOrEqual(metrics.cardsTop + 1);
    if (width >= 1280) {
      expect(metrics.cardsBottom).toBeLessThanOrEqual(height+2);
      for (const line of await lines.all()) {
        expect(await line.evaluate(node => node.scrollWidth <= node.clientWidth + 2)).toBeTruthy();
      }
    }
    await expect(page.locator('.hero-actions .button-primary')).toBeVisible();
  });
}

test('public campaign pointer motion and scroll progress remain functional', async ({page},info) => {
  await page.setViewportSize({width:1440,height:900});
  await openSite(page);
  await page.evaluate(() => window.scrollTo(0,600));
  await expect.poll(async()=>Number(await page.locator('#reading-progress').getAttribute('aria-valuenow'))).toBeGreaterThan(0);
  await page.evaluate(() => window.scrollTo(0,0));
  if (info.project.name === 'chromium') {
    const tile = page.locator('.format-card').first();
    await tile.hover({position:{x:12,y:12}});
    await expect.poll(()=>tile.evaluate(node=>node.style.getPropertyValue('--spot-x'))).not.toBe('');
    await page.mouse.move(3,3);
    await expect.poll(()=>tile.evaluate(node=>node.style.getPropertyValue('--spot-x'))).toBe('');
  }
  await page.emulateMedia({reducedMotion:'reduce'});
  expect(await page.locator('.hero-art-photo').evaluate(node=>getComputedStyle(node).transform)).toBe('none');
});


test('floating navigation stays usable and RX shines only with motion enabled', async ({page},info) => {
  await page.setViewportSize({width:1440,height:900});
  await openSite(page);
  const header=page.locator('.site-header');
  const mark=header.locator('.brand-monogram');
  await expect(mark.locator('img')).toHaveAttribute('src',/roxy-rx-transparent\.png/);
  expect(await mark.evaluate(n=>getComputedStyle(n,'::after').animationName)).toContain('rx-contour-shine');
  const box=await header.boundingBox();
  expect(box.x).toBeGreaterThan(0);
  expect(box.width).toBeLessThan(1440);
  expect(await header.evaluate(n=>getComputedStyle(n,'::before').borderRadius)).toBe('999px');
  await page.evaluate(()=>window.scrollTo(0,500));
  await expect(header).toHaveClass(/is-compact/);
  await expect.poll(async()=>Number(await header.locator('#reading-progress').getAttribute('aria-valuenow'))).toBeGreaterThan(0);
  if(info.project.name==='chromium') {
    const link=header.getByRole('link',{name:'Галерея',exact:true});
    await link.hover();
    await expect.poll(()=>header.locator('.desktop-nav').evaluate(n=>n.style.getPropertyValue('--pill-x'))).toBe(await link.evaluate(n=>n.offsetLeft+'px'));
    const action=header.locator('.top-action');
    await action.hover({position:{x:5,y:5}});
    await expect.poll(()=>action.evaluate(n=>n.style.getPropertyValue('--magnet-x'))).not.toBe('');
  }
  await page.emulateMedia({reducedMotion:'reduce'});
  expect(await mark.evaluate(n=>getComputedStyle(n,'::after').animationName)).toBe('none');
  await page.setViewportSize({width:320,height:740});
  await expect(header.locator('.top-action')).toBeVisible();
  await header.locator('.mobile-nav summary').click();
  await expect(header.locator('.mobile-nav nav')).toBeVisible();
  await header.locator('.mobile-nav nav').getByRole('link',{name:'Возможности'}).click();
  await expect(header.locator('.mobile-nav')).not.toHaveAttribute('open','');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth)).toBeLessThanOrEqual(1);
});


// The first screen is the reference for the rest of the same public campaign.
// Check rendered geometry and actual controls rather than snapshotting prose.
for (const width of [320,390,768,1440,1648]) {
  test(`hero visual language continues through the public site at ${width}px`, async ({page}) => {
    await page.setViewportSize({width,height:900});
    await openSite(page);
    await page.emulateMedia({reducedMotion:'reduce'});
    const sections=page.locator('main > .section, main > .final-section');
    await expect(sections).toHaveCount(7);
    const metrics=await page.evaluate(() => {
      const hero=document.querySelector('.hero h1');
      const card=document.querySelector('.format-card');
      const feature=document.querySelector('.capability');
      const heading=document.querySelector('#features-title');
      const bounds=[...document.querySelectorAll('main > .section, main > .final-section, .site-footer')].map(n=>{
        const r=n.getBoundingClientRect();
        return {left:r.left,right:r.right,width:r.width,scroll:n.scrollWidth,client:n.clientWidth};
      });
      return {
        overflow:document.documentElement.scrollWidth-innerWidth,
        headingFont:getComputedStyle(heading).fontFamily,
        heroFont:getComputedStyle(hero).fontFamily,
        featureBackground:getComputedStyle(feature).backgroundImage,
        heroCardBackground:getComputedStyle(card).backgroundImage,
        featureRadius:getComputedStyle(feature).borderTopLeftRadius,
        featureTransform:getComputedStyle(feature).transform,
        bounds,
        columns:getComputedStyle(document.querySelector('.capabilities-list')).gridTemplateColumns.split(' ').length,
        finalArtwork:getComputedStyle(document.querySelector('.final-section'),'::after').backgroundImage,
      };
    });
    expect(metrics.overflow).toBeLessThanOrEqual(1);
    expect(metrics.headingFont).toBe(metrics.heroFont);
    expect(metrics.featureBackground).toContain('linear-gradient');
    expect(metrics.heroCardBackground).toContain('linear-gradient');
    expect(parseFloat(metrics.featureRadius)).toBeGreaterThan(0);
    expect(metrics.featureTransform).toBe('none');
    expect(metrics.columns).toBe(width<=700?1:2);
    expect(metrics.finalArtwork).toBe('none');
    await expect(page.locator('#creators .promo-art img')).toHaveAttribute('src',/roxy-promo-2\.webp\?v=/);
    await expect(page.locator('.final-section .promo-art img')).toHaveAttribute('src',/roxy-promo-1\.webp\?v=/);
    for(const rect of metrics.bounds){
      expect(rect.left).toBeGreaterThanOrEqual(-1);
      expect(rect.right).toBeLessThanOrEqual(width+1);
      expect(rect.scroll-rect.client).toBeLessThanOrEqual(1);
    }
    const faq=page.locator('#faq details').first();
    await faq.locator('summary').click();
    await expect(faq).toHaveAttribute('open','');
    await expect(faq.locator('p')).toBeVisible();
    await faq.locator('summary').press('Enter');
    await expect(faq).not.toHaveAttribute('open','');
    await expect(page.locator('.final-section .button-primary')).toHaveAttribute('href','/login?section=partners');
    await expect(page.locator('.capability-link')).toHaveAttribute('href','/features');
  });
}


test('original Mini App promos retain their whole image and partner destination',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.addInitScript(()=>sessionStorage.setItem('__roxy_browser_init_data_v1',JSON.stringify({initData:'query_id=fixture&hash=fixture',expiresAt:Date.now()+60000})));
  await page.route('**/api/v1/me',route=>route.fulfill({json:{id:'fixture',telegram_id:42}}));
  await page.goto('/?ref=QA&unknown=discard');
  for(const selector of ['#creators .promo-art','.final-section .promo-art']){
    const link=page.locator(selector);
    await link.scrollIntoViewIfNeeded();
    const picture=link.locator('img');
    await expect.poll(()=>picture.evaluate(el=>el.complete && el.naturalWidth>0)).toBe(true);
    const box=await picture.boundingBox();
    expect(Math.abs(box.width/box.height-16/9)).toBeLessThan(.04);
    expect(await picture.evaluate(el=>getComputedStyle(el).objectFit)).toBe('contain');
    await expect(link).toHaveAttribute('href','/login?section=partners&ref=QA');
    await link.click();
    await expect(page.locator('body')).toHaveAttribute('data-page','login');
    await expect(page.locator('#login-continue')).toHaveAttribute('href','/mini-app/?route=partners&ref=QA');
    await page.goBack();
    await expect(page.locator('body')).toHaveAttribute('data-page','home');
  }
});
