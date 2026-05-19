const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.on('console', msg => console.log('[CONSOLE]', msg.type(), msg.text()));
  page.on('pageerror', err => console.log('[PAGE_ERR]', err.message));

  // Screenshot each page
  for (const url of ['http://127.0.0.1:9700/', 'http://127.0.0.1:9700/agents', 'http://127.0.0.1:9700/tasks/25']) {
    console.log('\n=== NAV TO ' + url + ' ===');
    await page.goto(url, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1000);
    const html = await page.content();
    console.log('HTML length:', html.length);
    console.log('Body innerText:', (await page.locator('body').innerText()).substring(0, 1000));
    const btns = await page.locator('button').allTextContents();
    console.log('Buttons:', btns);
    await page.screenshot({ path: 'C:\\temp\\' + url.replace(/[:\/]/g, '_') + '.png' });
    console.log('Screenshot saved');
  }

  await browser.close();
})();
