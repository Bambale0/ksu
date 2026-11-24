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
    expect(await art.evaluate(node => getComputedStyle(node).backgroundImage)).toContain('roxy-reference-hero.webp');
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
