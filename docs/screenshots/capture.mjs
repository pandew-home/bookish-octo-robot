import { chromium } from 'playwright';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const BASE = 'http://localhost:30080';
const KUBECONFIG_PATH = 'docs/screenshots/kubeconfig-incluster.yaml';
const OUT = resolve('docs/screenshots');

// --- Step 1: Authenticate via API and get session ID ---
const kubeconfigContent = readFileSync(KUBECONFIG_PATH, 'utf8');
const authRes = await fetch(`${BASE}/api/credentials/kubeconfig/auth`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ content: kubeconfigContent, context: 'docker-desktop' }),
});
const { session_id } = await authRes.json();
console.log('Session ID:', session_id);

// --- Step 2: Open browser, inject session, navigate ---
const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();

// Capture console errors
page.on('console', msg => { if (msg.type() === 'error') console.error('PAGE ERROR:', msg.text()); });
page.on('pageerror', err => console.error('PAGE CRASH:', err.message));

// Load page to establish origin, then inject session
await page.goto(BASE, { waitUntil: 'networkidle' });
await page.evaluate((sid) => localStorage.setItem('sessionId', sid), session_id);
console.log('Session injected into localStorage');

// Reload and wait for React to render
await page.reload({ waitUntil: 'networkidle' });
await page.waitForTimeout(6000);

await page.screenshot({ path: `${OUT}/01-after-auth.png`, fullPage: true });
console.log('01-after-auth captured');

// Check page title/content
const title = await page.title();
const bodyText = await page.locator('body').innerText().catch(() => '');
console.log('Page title:', title);
console.log('Body text (first 300):', bodyText.slice(0, 300));

// Wait for cluster selector to appear
await page.waitForSelector('text=Select a Cluster', { timeout: 15000 }).catch(() => console.log('cluster selector not visible'));
await page.waitForTimeout(2000);
await page.screenshot({ path: `${OUT}/02-cluster-select.png` });
console.log('02-cluster-select captured');

// Try to select cluster via API directly, then let the page react
const selectRes = await fetch(`${BASE}/api/clusters/select`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', 'x-session-id': session_id },
  body: JSON.stringify({ cluster_name: 'docker-desktop' }),
});
console.log('Cluster select API:', await selectRes.text());

// Also try clicking the dropdown
const dropdown = page.locator('[role="combobox"]').first();
if (await dropdown.isVisible().catch(() => false)) {
  await dropdown.click();
  await page.waitForTimeout(1000);
  await page.screenshot({ path: `${OUT}/02b-dropdown-open.png` });
  const option = page.getByRole('option', { name: /docker-desktop/i });
  if (await option.isVisible().catch(() => false)) {
    await option.click();
    console.log('Selected docker-desktop from dropdown');
  } else {
    console.log('docker-desktop option not visible in dropdown');
    await page.keyboard.press('Escape');
  }
}

await page.waitForTimeout(6000);
await page.screenshot({ path: `${OUT}/02c-after-cluster-select.png` });

await page.screenshot({ path: `${OUT}/03-main-interface.png`, fullPage: true });
console.log('03-main-interface captured');

// Clip top bar for weather widget
await page.screenshot({ path: `${OUT}/04-weather-widget.png`, clip: { x: 0, y: 0, width: 1440, height: 160 } });

await browser.close();
console.log('Done — screenshots saved to docs/screenshots/');
