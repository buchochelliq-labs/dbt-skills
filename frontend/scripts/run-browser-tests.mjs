import { runBrowserJourneys } from '../tests/browser/journeys.mjs';

const url = process.argv[2] || 'http://127.0.0.1:5173';
let browser;
try {
  const { chromium } = await import('playwright');
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await page.goto(url, { waitUntil: 'networkidle' });
  await runBrowserJourneys(page, result => console.log(JSON.stringify(result)));
} catch (error) {
  console.error(error.stack || String(error));
  process.exitCode = 1;
} finally {
  await browser?.close();
}
