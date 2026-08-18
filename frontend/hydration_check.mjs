/**
 * ส่วนขยายของเบราว์เซอร์ต้องไม่ทำให้ hydration พัง
 *
 * QuillBot / Grammarly / ตัวแปลภาษา เขียน attribute ลงบน <html> หรือ <body>
 * ก่อน React จะ hydrate ฝั่งเซิร์ฟเวอร์ไม่มี attribute นั้น React จึงฟ้อง mismatch
 * ทั้งที่แอปไม่ได้ทำอะไรผิด · dev overlay ที่ขึ้นทับทุกครั้งจะบัง error จริงที่ควรเห็น
 *
 * ต้องทดสอบบน dev server เท่านั้น — production build ไม่ขึ้นคำเตือนแบบนี้
 * สคริปต์นี้จึงเปิด next dev ของตัวเองที่พอร์ต 3200 แล้วปิดให้เมื่อจบ
 */
import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import { CHROMIUM } from './_env.mjs';

const PORT = 3200;
let pass = 0, fail = 0;
const check = (l, c, e = '') => { c ? (pass++, console.log('PASS', l))
                                   : (fail++, console.log('FAIL', l, String(e).slice(0, 300))); };

const dev = spawn('npx', ['next', 'dev', '-p', String(PORT)], {
  stdio: ['ignore', 'pipe', 'pipe'],
  env: { ...process.env, BACKEND_URL: 'http://localhost:8000' },
});
const stop = () => { try { process.kill(-dev.pid); } catch { dev.kill('SIGKILL'); } };

async function waitReady(ms = 90000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    try {
      const r = await fetch(`http://localhost:${PORT}/login`);
      if (r.status < 500) return true;
    } catch { /* ยังไม่ขึ้น */ }
    await new Promise((r) => setTimeout(r, 1000));
  }
  return false;
}

if (!(await waitReady())) {
  console.log('FAIL เปิด next dev ไม่ขึ้น');
  stop();
  process.exit(1);
}

const browser = await chromium.launch({ executablePath: CHROMIUM });
const ctx = await browser.newContext();
const page = await ctx.newPage();

const errors = [];
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', (e) => errors.push(String(e)));

// เลียนแบบส่วนขยาย: เขียน attribute ลงไปก่อนสคริปต์ของหน้าจะทำงาน
await page.addInitScript(() => {
  // สคริปต์นี้ทำงานก่อน <html> จะถูกสร้างด้วยซ้ำ จึงต้องรอให้มีก่อนแล้วค่อยเขียน
  const apply = () => {
    const html = document.documentElement;
    if (html) {
      html.setAttribute('data-qb-installed', 'true');
      html.setAttribute('data-lt-installed', 'true');
    }
    if (document.body) document.body.setAttribute('data-gr-ext-installed', '');
    return Boolean(html && document.body);
  };
  if (!apply()) {
    const obs = new MutationObserver(() => { if (apply()) obs.disconnect(); });
    obs.observe(document, { childList: true, subtree: true });
  }
});

await page.goto(`http://localhost:${PORT}/login`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.auth-screen, .center-screen, form', { timeout: 60000 });
await page.waitForTimeout(3000);

check('ส่วนขยายเขียน attribute ลงหน้าจริง (เลียนแบบสำเร็จ)',
  await page.evaluate(() => document.documentElement.hasAttribute('data-qb-installed')));

const hydrationErrors = errors.filter((e) => /hydrat/i.test(e));
check('มีส่วนขยายอยู่ก็ไม่ขึ้น hydration error', hydrationErrors.length === 0,
  hydrationErrors.slice(0, 2).join(' | '));

// 401 ของ /api/auth/me บนหน้า login เป็นเรื่องปกติ (ยังไม่ได้ล็อกอิน) เบราว์เซอร์
// ขึ้นเป็น console error ให้เองทุกครั้ง — กรองออกไม่งั้นเทสต์จะฟ้องเรื่องที่ไม่ใช่ปัญหา
const realErrors = errors.filter((e) => !/Failed to load resource/i.test(e));
check('ไม่มี JavaScript error อื่นค้างบนหน้า', realErrors.length === 0,
  realErrors.slice(0, 2).join(' | '));

await browser.close();
stop();
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
