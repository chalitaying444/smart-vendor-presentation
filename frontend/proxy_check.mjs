/**
 * เปิดระบบผ่าน ngrok — ตรวจสองอย่างที่พังเงียบที่สุดเวลาใช้งานจริง
 *
 * 1. ทุกคำขอ API ต้องติดหัวข้อมูล ngrok-skip-browser-warning
 *    ถ้าไม่ติด ngrok รุ่นฟรีจะคืนหน้าเตือนเป็น HTML แทน JSON แล้วหน้าจอจะขึ้น
 *    error ที่ไล่ต้นเหตุไม่ถูกเลย (ดูเหมือนแอปพัง ทั้งที่แอปไม่ได้ทำอะไรผิด)
 * 2. next.config ต้องอนุญาตโดเมน ngrok ตอน dev ไม่งั้น Next บล็อกทิ้งตั้งแต่แรก
 */
import { chromium } from 'playwright';
import fs from 'node:fs';
import { FE, API, CHROMIUM, token } from './_env.mjs';

const TOK = token();
let pass = 0, fail = 0;
const check = (l, c, e = '') => { c ? (pass++, console.log('PASS', l))
                                   : (fail++, console.log('FAIL', l, String(e).slice(0, 200))); };

// ---- next.config: โดเมน ngrok ต้องผ่าน dev server ได้
const cfg = (await import('./next.config.mjs')).default;
const origins = cfg.allowedDevOrigins || [];
check('next.config อนุญาตโดเมนของ ngrok ตอน dev',
  ['*.ngrok-free.app', '*.ngrok-free.dev', '*.ngrok.app'].every((o) => origins.includes(o)),
  origins);

process.env.DEV_ORIGINS = 'https://my-static.ngrok-free.app/';
const cfg2 = (await import(`./next.config.mjs?v=${Date.now()}`)).default;
check('เติมโดเมนเองผ่าน DEV_ORIGINS ได้ และตัด https:// กับ / ท้ายให้เอง',
  (cfg2.allowedDevOrigins || []).includes('my-static.ngrok-free.app'),
  cfg2.allowedDevOrigins);

// ---- ทุกคำขอ API ต้องมีหัวข้อมูลข้ามหน้าเตือนของ ngrok
const browser = await chromium.launch({ executablePath: CHROMIUM });
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
await ctx.addCookies([{ name: 'vendor_session', value: TOK, domain: 'localhost', path: '/' }]);
const page = await ctx.newPage();

const apiCalls = [];
page.on('request', (r) => {
  if (r.url().includes('/api/')) {
    apiCalls.push({ url: r.url(), skip: r.headers()['ngrok-skip-browser-warning'] });
  }
});

await page.goto(`${FE}/products`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.card', { timeout: 30000 });
await page.waitForTimeout(2000);
check('หน้าเว็บยิง API จริงระหว่างทดสอบ', apiCalls.length > 0, apiCalls.length);
const missing = apiCalls.filter((c) => c.skip !== 'true');
check('ทุกคำขอ API ติดหัวข้อมูลข้ามหน้าเตือนของ ngrok',
  missing.length === 0, missing.map((m) => m.url).slice(0, 3).join(' · '));

// อัปโหลดไฟล์ (multipart) ก็ต้องติดด้วย — เป็นคนละเส้นทางกับ request() ปกติ
await page.goto(`${FE}/boms`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.card', { timeout: 30000 });
await page.waitForTimeout(1500);
await page.locator('button:has-text("นำ BOM เข้ามาประมาณราคา")').click();
await page.waitForSelector('.modal-wide', { timeout: 20000 });
await page.locator('button:has-text("อัปโหลดไฟล์")').click();
await page.waitForSelector('input[type="file"]', { timeout: 15000 });
apiCalls.length = 0;
fs.writeFileSync('/tmp/ngrok_bom.csv', 'รายการ,จำนวน,หน่วย\nสายไฟ THW 1x2.5,100,M\n');
await page.setInputFiles('input[type="file"]', '/tmp/ngrok_bom.csv');
await page.waitForTimeout(2500);
const upload = apiCalls.find((c) => c.url.includes('parse-file'));
check('การอัปโหลดไฟล์ก็ติดหัวข้อมูลเดียวกัน', upload && upload.skip === 'true', upload);

await browser.close();
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
