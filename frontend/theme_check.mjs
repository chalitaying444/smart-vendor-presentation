/**
 * ตรวจธีมขาว–ดำ: ต้องไม่มีสีน้ำเงินหลงเหลือในหน้าจอจริง และตัวอักษรต้องยังอ่านออก
 *
 * ตรวจจาก computed style ของทุก element ที่แสดงผลจริง ไม่ใช่การ grep ไฟล์ CSS
 * เพราะสีอาจมาจาก inline style, ตัวแปร CSS หรือค่าที่ browser คำนวณเอง
 *
 * ข้อยกเว้นเดียว: โลโก้ Microsoft บนปุ่มเข้าสู่ระบบ — เป็นเครื่องหมายการค้าของเจ้าของ
 * แก้สีไม่ได้ตามข้อกำหนดการใช้โลโก้
 */
import { chromium } from 'playwright';
import { FE, API, CHROMIUM, token } from './_env.mjs';

const BASE = FE;
let pass = 0, fail = 0;
const check = (name, ok, detail = '') => {
  if (ok) { pass++; console.log('PASS ' + name); }
  else { fail++; console.log('FAIL ' + name + (detail ? '  → ' + detail : '')); }
};

const SNIFF = `
(() => {
  const parse = (c) => {
    const m = /rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)(?:,\\s*([\\d.]+))?\\)/.exec(c || '');
    if (!m) return null;
    const a = m[4] === undefined ? 1 : parseFloat(m[4]);
    return a === 0 ? null : { r: +m[1], g: +m[2], b: +m[3] };
  };
  const lum = ({ r, g, b }) => {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const blueish = (c) => c && (c.b - Math.max(c.r, c.g)) > 12;
  const label = (el) => (el.tagName + '.' + (el.className.baseVal ?? el.className ?? '')).slice(0, 60);

  const blues = [], low = [];
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('.ms-logo, [data-brand-logo]')) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;

    for (const prop of ['color', 'backgroundColor', 'borderTopColor', 'borderLeftColor', 'fill', 'stroke']) {
      const c = parse(cs[prop]);
      if (blueish(c)) blues.push(label(el) + ' ' + prop + '=' + cs[prop]);
    }

    // contrast เฉพาะ element ที่มีข้อความของตัวเอง
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!own) continue;
    const fg = parse(cs.color);
    if (!fg) continue;
    let bgEl = el, bg = null;
    while (bgEl && !bg) { const c = parse(getComputedStyle(bgEl).backgroundColor); if (c) bg = c; bgEl = bgEl.parentElement; }
    bg = bg || { r: 255, g: 255, b: 255 };
    const L1 = lum(fg), L2 = lum(bg);
    const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
    const size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight, 10) >= 700;
    const need = (size >= 24 || (size >= 18.66 && bold)) ? 3 : 4.5;
    if (ratio < need) low.push(label(el) + ' ' + ratio.toFixed(2) + ':1 (' + cs.color + ' บน rgb(' + bg.r + ',' + bg.g + ',' + bg.b + '))');
  }
  return { blues: [...new Set(blues)], low: [...new Set(low)] };
})()
`;

const browser = await chromium.launch({ executablePath: CHROMIUM });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const tok = token();
await ctx.addCookies([{ name: 'vendor_session', value: tok, domain: 'localhost', path: '/' }]);
const page = await ctx.newPage();

const bomId = (await (await fetch(`${API}/boms`, { headers: { Authorization: `Bearer ${tok}` } })).json()).items?.[0]?.id;

const PAGES = [
  ['หน้าเข้าสู่ระบบ', '/login'],
  ['แดชบอร์ด', '/dashboard'],
  ['ผู้ขาย', '/vendors'],
  ['สินค้า', '/products'],
  ['ใบขอราคา', '/rfqs'],
  ['การส่งของ', '/deliveries'],
  ['BOM', '/boms'],
];
// ถ้าไม่มีโครงการให้ตรวจ ต้องฟ้องออกมา ไม่ใช่ข้ามไปเงียบ ๆ แล้วรายงานว่า "ผ่านหมด"
// ด้วยจำนวนข้อที่น้อยลง — เทสต์ที่หดตัวเองได้คือเทสต์ที่เชื่อไม่ได้
check('มีโครงการให้ตรวจสีอย่างน้อยหนึ่งงาน', !!bomId, 'รัน bom_check.mjs ก่อนเพื่อสร้างข้อมูล');
if (bomId) {
  PAGES.push(['BOM รายโครงการ', `/boms/${bomId}`], ['เทียบราคา', `/boms/${bomId}/compare`], ['ออกใบขอราคา', `/boms/${bomId}/rfq`]);
}

// หน้าผู้ขาย (portal) ไม่มีเมนูและเป็นคนละ layout — ต้องตรวจแยก
const hdr = { Authorization: `Bearer ${tok}` };
const rfqId = (await (await fetch(`${API}/rfqs`, { headers: hdr })).json()).items?.[0]?.id;
if (rfqId) {
  const inv = await (await fetch(`${API}/rfqs/${rfqId}/invites`, { headers: hdr })).json();
  const t = (Array.isArray(inv) ? inv : inv.items)?.[0]?.token;
  check('มีลิงก์ผู้ขายให้ตรวจสี', !!t, 'ไม่พบ invite ในใบขอราคาแรก');
  if (t) PAGES.push(['หน้าผู้ขาย', `/portal/${t}`]);
}
check('มีใบขอราคาให้ตรวจสีหน้าผู้ขาย', !!rfqId, 'รัน bom_check.mjs ก่อนเพื่อสร้างใบขอราคา');

for (const [name, path] of PAGES) {
  await page.goto(BASE + path, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.card, .auth-screen, .portal-card, .gate-card', { timeout: 30000 });
  await page.waitForTimeout(900);
  check(`${name} — เข้าหน้าได้จริง ไม่ถูกเด้งไปหน้า login`, path === '/login' || !page.url().includes('/login'), page.url());
  const { blues, low } = await page.evaluate(SNIFF);
  check(`${name} — ไม่มีสีน้ำเงินเหลือ`, blues.length === 0, blues.slice(0, 4).join(' · '));
  check(`${name} — ตัวอักษรผ่าน contrast AA`, low.length === 0, low.slice(0, 4).join(' · '));
}

// เมนูซ้ายพื้นขาว แต่ต้องยังบอกได้ว่าอยู่หน้าไหน (แถบดำซ้าย ไม่ใช่แค่สี)
await page.goto(`${BASE}/vendors`, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('.nav-item', { timeout: 30000 });
const activeMark = await page.evaluate(() => {
  const el = document.querySelector('.nav-item.active');
  if (!el) return null;
  const cs = getComputedStyle(el);
  return { shadow: cs.boxShadow, weight: cs.fontWeight, bg: cs.backgroundColor };
});
check('เมนูที่เปิดอยู่ยังแยกออกโดยไม่พึ่งสี', !!activeMark && /inset/.test(activeMark.shadow) && parseInt(activeMark.weight, 10) >= 600, JSON.stringify(activeMark));

const errs = [];
page.on('pageerror', (e) => errs.push(e.message));
await page.goto(`${BASE}/dashboard`, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(2500);
check('ไม่มี JavaScript error', errs.length === 0, errs.join(' | '));

await browser.close();
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
