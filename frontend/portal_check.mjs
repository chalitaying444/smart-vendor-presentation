/** ทดสอบหน้าเสนอราคาของผู้ขาย: ประตูเงื่อนไข → กรอกราคา → แนบไฟล์ */
import { chromium } from 'playwright';
import fs from 'node:fs';
import { FE, API, CHROMIUM, SHOTS, token as buyerToken } from './_env.mjs';

const TOK = buyerToken();
let pass = 0, fail = 0;
const check = (l, c, e = '') => { c ? (pass++, console.log('PASS', l)) : (fail++, console.log('FAIL', l, e)); };

const api = async (path, method = 'GET', body) => {
  const res = await fetch(API + path, {
    method, headers: { Authorization: `Bearer ${TOK}`, 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  return [res.status, await res.json().catch(() => null)];
};

// สร้าง RFQ ใหม่เพื่อให้ได้ลิงก์ที่ยังไม่รับทราบเงื่อนไข
const [, items] = await api('/catalog/items?limit=1');
const part = items.items[0].part_num;
const [, vend] = await api('/vendors?limit=2');
const [me, other] = vend.items;
const [, rfq] = await api('/rfqs', 'POST', {
  title: 'ทดสอบหน้าเสนอราคา', currency: 'THB',
  lines: [{ part_num: part, qty: 4 }],
  vendor_keys: [me.vendor_key, other.vendor_key],       // เชิญสองราย
});
await api(`/rfqs/${rfq.id}/send`, 'POST', { message: 'รบกวนเสนอราคาภายในสัปดาห์นี้' });
const [, invites] = await api(`/rfqs/${rfq.id}/invites`);
const mine = invites.find((i) => i.vendor_id === me.vendor_id);
const token = mine.token;

const browser = await chromium.launch({ executablePath: CHROMIUM });
const ctx = await browser.newContext({ viewport: { width: 1300, height: 1000 } });
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

await page.goto(`${FE}/portal/${token}`, { waitUntil: 'networkidle' });

// ---- ประตูเงื่อนไข: ยังไม่ติ๊ก = ยังไม่เห็นอะไรเลย
check('หน้าโหลดโดยไม่ต้องล็อกอิน', await page.locator('.portal-head').isVisible());
check('มีแถบขั้นตอนให้รู้ว่าต้องทำอะไรบ้าง',
  await page.locator('.portal-steps li').count() === 3);
check('เจอด่านรับทราบเงื่อนไขก่อนเป็นอย่างแรก',
  await page.locator('.gate-card').isVisible()
  && await page.locator('h1:text-is("เงื่อนไขการเสนอราคา")').isVisible());
check('แสดงเงื่อนไขครบทุกข้อ',
  await page.locator('.terms-list li').count() >= 5,
  await page.locator('.terms-list li').count());

const gateHtml = await page.content();
check('ยังไม่ติ๊ก = ไม่โชว์ชื่อสินค้า/รหัสสินค้าเลย',
  !gateHtml.includes(part) && !gateHtml.includes(items.items[0].description || '\u0000'),
  part);
check('ยังไม่ติ๊ก = ไม่โชว์ชื่อบริษัทผู้ขาย', !gateHtml.includes(me.name), me.name);
check('ยังไม่ติ๊ก = ยังไม่มีตารางกรอกราคาบนหน้า',
  await page.locator('input[type="number"]').count() === 0
  && await page.locator('#c-name').count() === 0
  && await page.locator('.dropzone').count() === 0);
check('แต่ยังบอกได้ว่าใบไหน กี่รายการ',
  /RFQ-\d{4}-\d+/.test(await page.locator('.gate-meta').innerText())
  && /1 รายการ/.test(await page.locator('.gate-meta').innerText()),
  await page.locator('.gate-meta').innerText());
check('ยังไม่ติ๊ก ปุ่มเปิดดูต้องกดไม่ได้', await page.locator('.gate-btn').isDisabled());
await page.screenshot({ path: `${SHOTS}/portal-terms.png`, fullPage: true });

await page.locator('.gate-check input[type="checkbox"]').check();
check('ติ๊กแล้วปุ่มกดได้', !(await page.locator('.gate-btn').isDisabled()));
await page.fill('#gate-by', 'คุณสมชาย ใจดี');
await page.locator('.gate-btn').click();
await page.waitForSelector('table', { timeout: 15000 });
check('รับทราบแล้วจึงเห็นรายการสินค้า', (await page.content()).includes(part));
check('รับทราบแล้วขึ้นสถานะและวันที่',
  await page.locator('.portal-terms.accepted .otd:has-text("รับทราบแล้ว")').isVisible());
check('เงื่อนไขยังกดกลับมาอ่านซ้ำได้',
  await page.locator('details.portal-terms > summary').isVisible());
check('ฟอร์มกรอกราคาใช้งานได้แล้ว',
  !(await page.locator('input[type="number"]').first().isDisabled())
  && !(await page.locator('#c-name').isDisabled()));

// ---- กรอกราคา
await page.fill('input[type="number"] >> nth=0', '12500');
await page.fill('input[type="number"] >> nth=1', '14');
await page.waitForTimeout(400);
const foot = await page.locator('tfoot').innerText();
check('คำนวณยอดรวมและ VAT ให้เห็นทันที',
  /รวมเป็นเงิน/.test(foot) && /ภาษีมูลค่าเพิ่ม/.test(foot) && /รวมทั้งสิ้น/.test(foot), foot.replace(/\n/g, ' | '));
check('ยอดรวมคำนวณถูก (12,500 x 4 = 50,000)', /50,000\.00/.test(foot), foot.replace(/\n/g, ' | '));
check('รวมทั้งสิ้นบวก VAT 7% แล้ว (53,500)', /53,500\.00/.test(foot), foot.replace(/\n/g, ' | '));

await page.fill('#c-name', 'คุณสมชาย ใจดี');
await page.fill('#c-email', 'sales@example.co.th');
await page.screenshot({ path: `${SHOTS}/portal-form.png`, fullPage: true });

// ---- แนบไฟล์
check('มีส่วนแนบใบเสนอราคา',
  await page.locator('h2:text-is("แนบใบเสนอราคาของบริษัทท่าน")').isVisible());
fs.writeFileSync('/tmp/vendor_quote.pdf', 'ใบเสนอราคาของผู้ขาย (ไฟล์ทดสอบ)');
await page.setInputFiles('.dropzone input[type="file"]', '/tmp/vendor_quote.pdf');
await page.waitForSelector('.file-list li', { timeout: 10000 });
check('แนบไฟล์แล้วขึ้นในรายการ',
  (await page.locator('.file-list li').innerText()).includes('vendor_quote.pdf'));
// ลิงก์ต้องผูกกับ token ของผู้ขายรายนี้ ไม่ใช่ /files/ ที่เปิดสาธารณะแบบเดิม
const attachHref = await page.locator('.file-list li a').first().getAttribute('href');
check('ลิงก์ไฟล์แนบผูกกับ token ของผู้ขายรายนี้ ไม่ได้เปิดสาธารณะ',
  attachHref?.startsWith(`/api/portal/${token}/attachments/`), attachHref);
// ไฟล์เก็บใน MongoDB แล้ว — ต้องพิสูจน์ว่าโหลดกลับมาได้เหมือนเดิมทุกไบต์
const back = await page.evaluate(async (href) => {
  const r = await fetch(href);
  return { status: r.status, text: await r.text() };
}, attachHref);
check('ดาวน์โหลดไฟล์ที่แนบกลับมาได้ เนื้อหาตรงกับไฟล์ต้นฉบับ',
  back.status === 200 && back.text === 'ใบเสนอราคาของผู้ขาย (ไฟล์ทดสอบ)', back);
check('แจ้งผลการแนบไฟล์ให้ผู้ใช้ทราบ',
  await page.locator('.alert-ok:has-text("แนบไฟล์")').isVisible());

// ---- ส่งราคา
await page.locator('button:has-text("ส่งราคา")').click();
await page.waitForSelector('.alert-ok:has-text("ส่งราคาเรียบร้อย")', { timeout: 12000 });
check('ส่งราคาสำเร็จและแจ้งผล', true);
await page.screenshot({ path: `${SHOTS}/portal-done.png`, fullPage: true });

const [, quotes] = await api(`/rfqs/${rfq.id}/quotes`);
check('ฝั่งผู้ซื้อได้รับราคาแล้ว', quotes.length === 1 && quotes[0].total > 0, quotes[0]?.total);
check('ใบเสนอราคาที่แนบมาถึงฝั่งผู้ซื้อด้วย',
  (quotes[0]?.attachments || []).some((f) => f.filename === 'vendor_quote.pdf'),
  quotes[0]?.attachments);

// ---- ฝั่งผู้ซื้อต้องเปิดไฟล์ที่ผู้ขายแนบมาได้จริงจากหน้าจอ (เดิมเห็นแค่จำนวน)
const buyerCtx = await browser.newContext({ viewport: { width: 1500, height: 1000 } });
await buyerCtx.addCookies([{ name: 'vendor_session', value: TOK, domain: 'localhost', path: '/' }]);
const buyer = await buyerCtx.newPage();
await buyer.goto(`${FE}/rfqs/${rfq.id}`, { waitUntil: 'domcontentloaded' });
await buyer.locator('.tab:has-text("เทียบราคา")').click();
await buyer.waitForSelector('.compare-table', { timeout: 20000 });
const linkCount = await buyer.locator('.attach-links a').count();
check('ผู้ซื้อเห็นลิงก์ใบเสนอราคาที่ผู้ขายแนบมาในตารางเทียบราคา', linkCount >= 1, linkCount);
const buyerHref = await buyer.locator('.attach-links a').first().getAttribute('href');
const buyerBack = await buyer.evaluate(async (href) => {
  const r = await fetch(href);
  return { status: r.status, text: await r.text() };
}, buyerHref);
check('ผู้ซื้อกดโหลดแล้วได้ไฟล์จริง',
  buyerBack.status === 200 && buyerBack.text === 'ใบเสนอราคาของผู้ขาย (ไฟล์ทดสอบ)', buyerBack);
await buyerCtx.close();

// ---- ลบไฟล์
await page.locator('.file-list button:has-text("ลบ")').first().click();
await page.waitForTimeout(1200);
check('ลบไฟล์ที่แนบผิดได้', await page.locator('.file-list li').count() === 0);

// ---- ไม่หลุดข้อมูลภายใน
const html = await page.content();
check('ไม่หลุดราคาที่บริษัทเคยซื้อให้ผู้ขายเห็น',
  !/ราคาเดิม|ราคาล่าสุดที่เคยซื้อ|last_price/.test(html));
check('ไม่หลุดชื่อผู้ขายรายอื่นที่ถูกเชิญด้วย',
  !html.includes(other.name) && !html.includes(other.vendor_id),
  other.name);
check('เห็นเฉพาะชื่อบริษัทตัวเอง', html.includes(me.name), me.name);

check('ไม่มี JavaScript error', errors.length === 0, errors.slice(0, 3));
await browser.close();
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
