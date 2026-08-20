/**
 * Drive the LostIntoSpacE prototype through a real browser.
 *
 * Walks the product loop a user would: landing -> Rocket Lab -> Builder ->
 * Launch -> Mission Control, screenshotting each step and collecting every
 * console error along the way.
 */
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';

const SHOTS = '/tmp/claude-1000/-home-robot-LostIntoSpacE/f98cd1ca-3d43-4ee1-842f-7bb01c499a0d/scratchpad/shots';
mkdirSync(SHOTS, { recursive: true });

const errors = [];
const failedRequests = [];

const browser = await chromium.launch({ args: ['--no-sandbox'] });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

page.on('console', (msg) => {
  if (msg.type() === 'error') errors.push(`[${page.url()}] ${msg.text()}`);
});
page.on('pageerror', (err) => errors.push(`[pageerror] ${err.message}`));
page.on('requestfailed', (req) =>
  failedRequests.push(`${req.method()} ${req.url()} — ${req.failure()?.errorText}`),
);

async function shot(name) {
  await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: false });
  console.log(`  screenshot: ${name}.png`);
}

function step(text) {
  console.log(`\n\x1b[36m${text}\x1b[0m`);
}

// ---------------------------------------------------------------- landing
step('1. Landing page');
await page.goto('http://localhost:3000/', { waitUntil: 'domcontentloaded' });
await page.waitForSelector('text=You are not reading about space', { timeout: 30000 });
console.log('  title:', await page.title());
console.log('  hero:', (await page.locator('h1').first().innerText()).replace(/\n/g, ' / '));
await shot('01-landing');

// ------------------------------------------------------------- rocket lab
step('2. Rocket Lab — component catalogue');
await page.click('a:has-text("Build a rocket")');
await page.waitForSelector('h1:has-text("Rocket Lab")', { timeout: 30000 });
const catalogueBlurb = await page.locator('header p').first().innerText();
console.log('  ', catalogueBlurb.replace(/\s+/g, ' ').slice(0, 90));
const presetCount = await page.locator('h3:near(:text("Start from a design"))').count();
console.log('  preset cards visible:', await page.locator('button:has-text("Open in Builder")').count());
await shot('02-rocket-lab');

// component detail
await page.locator('button:has-text("Open in Builder")').first().waitFor();
const firstComponent = page.locator('ul li button:has-text("kg")').first();
if (await firstComponent.count()) {
  await firstComponent.click();
  await page.waitForSelector('text=Specifications', { timeout: 10000 });
  console.log('  component detail modal opened');
  await shot('03-component-detail');
  await page.keyboard.press('Escape');
}

// ---------------------------------------------------------------- builder
step('3. Builder — open the Orbital Launcher preset');
await page.locator('button:has-text("Open in Builder")').nth(1).click();
await page.waitForSelector('h1:has-text("Rocket Builder")', { timeout: 30000 });
await page.waitForTimeout(500);

const metric = async (label) => {
  const row = page.locator(`dt:text-is("${label}")`).first();
  if (!(await row.count())) return '(not found)';
  return (await row.locator('xpath=following-sibling::dd[1]').innerText()).trim();
};
console.log('  Launch mass  :', await metric('Launch mass'));
console.log('  Total Δv     :', await metric('Total Δv'));
console.log('  Liftoff TWR  :', await metric('Liftoff TWR'));
console.log('  Stability    :', await metric('Stability (wet)'));
console.log('  validation   :', (await page.locator('text=/No problems found|●/').first().innerText()).slice(0, 60));
await shot('04-builder');

// ----------------------------------------------------------------- launch
step('4. Launch — configure and fly');
await page.click('button:has-text("Configure launch")');
await page.waitForSelector('h1:has-text("Launch")', { timeout: 30000 });
await page.waitForTimeout(400);

const checks = await page.locator('li:has(p)').filter({ hasText: /Vehicle has|Liftoff thrust|budget|stable|payload/ }).allInnerTexts();
for (const c of checks.slice(0, 6)) console.log('  check:', c.replace(/\n/g, ' — '));
const readiness = await page.locator('text=/^(GO|\\d+ WARNING)$/').first().innerText().catch(() => '?');
console.log('  readiness:', readiness);
await shot('05-launch');

console.log('  pressing Launch…');
await page.click('button:has-text("Launch"):not(:has-text("Configure"))');

// --------------------------------------------------------- mission control
step('5. Mission Control — the flight');
await page.waitForSelector('text=Telemetry', { timeout: 60000 });
await page.waitForTimeout(2500); // let the 3D chunk load and playback start

const outcome = await page.locator('header span').filter({ hasText: /^(SUCCESS|PARTIAL|FAILURE)$/ }).first().innerText().catch(() => '?');
console.log('  outcome:', outcome);
console.log('  subtitle:', (await page.locator('header p').first().innerText()).replace(/\s+/g, ' '));

const gauge = async (label) => {
  const dt = page.locator(`dt:text-is("${label}")`).first();
  if (!(await dt.count())) return '(n/a)';
  return (await dt.locator('xpath=following-sibling::dd[1]').innerText()).replace(/\n/g, ' ').trim();
};
console.log('  Altitude :', await gauge('Altitude'));
console.log('  Speed    :', await gauge('Speed'));
console.log('  Mass     :', await gauge('Mass'));
console.log('  Thrust   :', await gauge('Thrust'));

const canvas = await page.locator('canvas').count();
console.log('  canvases rendered (3D viewport):', canvas);

const events = await page.locator('ol li button span:nth-child(2)').allInnerTexts().catch(() => []);
console.log('  events:', events.length, '→', events.slice(0, 6).join(' | '));
await shot('06-mission-control');

// summary panel
const summaryRows = await page.locator('dl >> dt:text-is("Max altitude")').first().count();
if (summaryRows) {
  const maxAlt = await page.locator('dt:text-is("Max altitude")').first().locator('xpath=following-sibling::dd[1]').innerText();
  const maxSpeed = await page.locator('dt:text-is("Max speed")').first().locator('xpath=following-sibling::dd[1]').innerText();
  const gLoss = await page.locator('dt:text-is("Gravity loss")').first().locator('xpath=following-sibling::dd[1]').innerText();
  console.log('  summary: max altitude', maxAlt, '| max speed', maxSpeed, '| gravity loss', gLoss);
}

// playback controls
step('6. Playback controls');
await page.click('button:has-text("Pause")').catch(() => {});
await page.waitForTimeout(200);
const afterPause = await page.locator('span:has-text("T+")').first().innerText();
await page.waitForTimeout(800);
const stillPaused = await page.locator('span:has-text("T+")').first().innerText();
console.log(`  paused at ${afterPause}; 800ms later ${stillPaused} → ${afterPause === stillPaused ? 'held' : 'STILL RUNNING'}`);

await page.click('button:has-text("10×")').catch(() => {});
await page.click('button:has-text("Play")').catch(() => {});
await page.waitForTimeout(1000);
const after10x = await page.locator('span:has-text("T+")').first().innerText();
console.log(`  after 1s at 10×: ${after10x}`);
await shot('07-playback');

// --------------------------------------------------------------- other pages
step('7. Search, Assistant, Help');
for (const [path, selector, label] of [
  ['/search?q=why+do+rockets+have+stages', 'text=/result/', 'Search'],
  ['/assistant', 'h1:has-text("AI Assistant")', 'Assistant'],
  ['/learn', 'h1:has-text("Learn")', 'Learn'],
  ['/missions', 'h1:has-text("Missions")', 'Missions'],
  ['/help', 'h1:has-text("Help")', 'Help'],
  ['/explore', 'h1:has-text("Explore Space")', 'Explore'],
]) {
  await page.goto(`http://localhost:3000${path}`, { waitUntil: 'domcontentloaded' });
  try {
    await page.waitForSelector(selector, { timeout: 20000 });
    console.log(`  ✓ ${label}`);
  } catch {
    console.log(`  ✗ ${label} — selector not found`);
  }
  await page.waitForTimeout(600);
  await shot(`08-${label.toLowerCase()}`);
}

// ------------------------------------------------------------------- report
step('Console errors and failed requests');
const realErrors = errors.filter((e) => !/favicon|Download the React DevTools/i.test(e));
if (realErrors.length === 0) console.log('  none');
else for (const e of realErrors.slice(0, 12)) console.log('  ✗', e.slice(0, 200));

const realFailures = failedRequests.filter((r) => !/favicon/i.test(r));
if (realFailures.length) {
  console.log('\n  failed requests:');
  for (const r of realFailures.slice(0, 8)) console.log('  ✗', r.slice(0, 160));
}

await browser.close();
console.log(`\nScreenshots in ${SHOTS}`);
