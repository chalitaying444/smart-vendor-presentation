/**
 * ทดสอบหน้าเว็บจริงตั้งแต่ค้นหาสินค้า → เปิดสินค้า → ดูราคาล่าสุด → ดู transaction
 * → ขอใบเสนอราคา → ผู้ขายเสนอราคา → เทียบราคากับราคาเดิม
 */
import { chromium } from 'playwright';
import { FE, API, CHROMIUM, SHOTS, token } from './_env.mjs';

const TOK = token();

let pass = 0, fail = 0;
const check = (label, cond, extra = '') => {
  if (cond) { pass++; console.log('PASS', label); }
  else { fail++; console.log('FAIL', label, extra); }
};

const api = async (path, method = 'GET', body) => {
  const res = await fetch(API + path, {
    method,
    headers: { Authorization: `Bearer ${TOK}`, 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  return [res.status, await res.json().catch(() => null)];
};

const browser = await chromium.launch({ executablePath: CHROMIUM });
const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } });
await ctx.addCookies([{ name: 'vendor_session', value: TOK, domain: 'localhost', path: '/' }]);
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

const shot = (name) => page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });

// ------------------------------------------------------------- ภาพรวม
await page.goto(`${FE}/dashboard`, { waitUntil: 'networkidle' });
await page.waitForSelector('.sk', { state: 'detached' }).catch(() => {});
check('หน้าภาพรวมโหลดได้', await page.locator('text=สินค้าที่ซื้อมากที่สุด').isVisible());
check('เมนูซ้ายมีเฉพาะเมนูที่ใช้จริง',
  await page.locator('.nav-item:has-text("ค้นหาสินค้า")').isVisible()
  && await page.locator('.nav-item:has-text("จับคู่ผู้ขาย")').count() === 0);
await shot('ep-dashboard');

// ------------------------------------------------------------- ค้นหาสินค้า
await page.goto(`${FE}/products`, { waitUntil: 'networkidle' });
await page.waitForSelector('table.vendor-table tbody tr');
const rowCount = await page.locator('table.vendor-table tbody tr').count();
check('เปิดหน้าค้นหาสินค้าแล้วเห็นรายการทันที (ไม่ต้องพิมพ์)', rowCount > 10, rowCount);

const headers = await page.locator('table.vendor-table thead th').allInnerTexts();
check('ตารางมีคอลัมน์ราคาล่าสุด', headers.some((h) => h.includes('ราคาล่าสุด')), headers);
check('ตารางมีคอลัมน์ผู้ขายและยอดซื้อ',
  headers.some((h) => h.includes('ผู้ขาย')) && headers.some((h) => h.includes('ยอดซื้อ')), headers);

const firstRowText = await page.locator('table.vendor-table tbody tr').first().innerText();
check('แถวแรกแสดงชื่อสินค้าและรหัสจริง',
  /[A-Z]{3,}/.test(firstRowText) && /\d{2}-\d{3}-/.test(firstRowText), firstRowText.slice(0, 120));
check('แถวแรกมีตัวเลขราคา', /[\d,]+\.\d\d/.test(firstRowText), firstRowText.slice(0, 120));
await shot('ep-products');

// ค้นหาแบบไม่ตรงเป๊ะ
const [, sample] = await api('/catalog/items?limit=1');
const partNum = sample.items[0].part_num;
await page.fill('input[type="search"]', partNum.replaceAll('-', ''));
await page.waitForTimeout(900);
await page.waitForSelector('table.vendor-table tbody tr');
check('พิมพ์รหัสไม่มีขีดแล้วยังเจอ',
  (await page.locator('table.vendor-table tbody tr').first().innerText()).includes(partNum));

await page.fill('input[type="search"]', 'ethernett swich');
await page.waitForTimeout(900);
const fuzzyHint = await page.locator('text=แสดงผลของคำที่ใกล้เคียงแทน').count();
const fuzzyRows = await page.locator('table.vendor-table tbody tr').count();
check('สะกดผิดแล้วระบบเดาคำให้ พร้อมบอกผู้ใช้', fuzzyHint > 0 && fuzzyRows > 0, { fuzzyHint, fuzzyRows });
await shot('ep-fuzzy');

await page.fill('input[type="search"]', 'switch');
await page.waitForTimeout(900);
await page.waitForSelector('table.vendor-table tbody tr');

// ------------------------------------------------------------- หน้าสินค้า
await page.locator('table.vendor-table tbody tr').first().click();
await page.waitForURL('**/products/**');
await page.waitForSelector('.stat-card');
await page.waitForSelector('.sk', { state: 'detached' });   // รอโครงหน้าหายก่อน
const openedPart = new URL(page.url()).pathname.split('/products/')[1];

check('การ์ดราคาล่าสุดแสดงอยู่', await page.locator('text=ราคาล่าสุดที่ซื้อ').isVisible());
check('มีราคาถูกสุด/แพงสุดให้เทียบ',
  await page.locator('text=ถูกที่สุดที่เคยซื้อได้').isVisible()
  && await page.locator('text=แพงที่สุดที่เคยซื้อ').isVisible());

const priceText = await page.locator('.stat-card').first().innerText();
check('การ์ดราคามีตัวเลข วันที่ และชื่อผู้ขาย',
  /[\d,]+\.\d\d/.test(priceText) && /25\d\d/.test(priceText), priceText.replace(/\n/g, ' | '));

check('มีตารางผู้ขายที่เคยขายสินค้านี้',
  await page.locator('text=ผู้ขายที่เคยขายสินค้านี้ให้เรา').isVisible());
const vendorRows = await page.locator('.card:has-text("ผู้ขายที่เคยขายสินค้านี้") table tbody tr').count();
check('ตารางผู้ขายมีข้อมูล', vendorRows > 0, vendorRows);

const vendorLink = page.locator('.card:has-text("ผู้ขายที่เคยขายสินค้านี้") table tbody tr a').first();
check('ชื่อผู้ขายกดไปหน้าผู้ขายได้',
  (await vendorLink.getAttribute('href'))?.startsWith('/vendors/'));

check('มีตารางรายการเคลื่อนไหว', await page.locator('text=รายการเคลื่อนไหวทั้งหมด').isVisible());
const txRows = await page.locator('.card:has-text("รายการเคลื่อนไหวทั้งหมด") table tbody tr').count();
check('รายการเคลื่อนไหวมีข้อมูลจริง', txRows > 1, txRows);
await shot('ep-item-detail');

// สลับแท็บ transaction
await page.locator('.card:has-text("รายการเคลื่อนไหวทั้งหมด") .tab:has-text("ใบสั่งซื้อ")').click();
await page.waitForTimeout(700);
const poOnly = await page.locator('.card:has-text("รายการเคลื่อนไหวทั้งหมด") table tbody tr .tag').allInnerTexts();
check('กรองเฉพาะใบสั่งซื้อได้', poOnly.length > 0 && poOnly.every((t) => t === 'ใบสั่งซื้อ'), poOnly.slice(0, 5));

await page.locator('.card:has-text("รายการเคลื่อนไหวทั้งหมด") .tab:has-text("ใบแจ้งหนี้")').click();
await page.waitForTimeout(700);
const invOnly = await page.locator('.card:has-text("รายการเคลื่อนไหวทั้งหมด") table tbody tr .tag').allInnerTexts();
check('กรองเฉพาะใบแจ้งหนี้ได้', invOnly.every((t) => t === 'ใบแจ้งหนี้'), invOnly.slice(0, 5));
await shot('ep-item-tx');

// ------------------------------------------------------------- ขอใบเสนอราคา
await page.locator('button:has-text("ขอใบเสนอราคาจากทุกราย")').click();
await page.waitForSelector('.modal');
check('เปิดกล่องขอใบเสนอราคาได้', await page.locator('.modal:has-text("ขอใบเสนอราคา")').isVisible());
check('กล่องขอราคาโชว์ราคาล่าสุดเป็นฐานเทียบ',
  await page.locator('.modal .alert:has-text("ราคาล่าสุดที่เคยซื้อ")').count() > 0);
const pickRows = await page.locator('.modal .pick-row').count();
check('มีรายชื่อผู้ขายให้ติ๊กเลือก', pickRows > 0, pickRows);
await page.fill('.modal #rq-qty', '25');
await shot('ep-quote-modal');

await page.locator('.modal button:has-text("สร้างใบขอราคา")').click();
await page.waitForURL('**/rfqs/**', { timeout: 15000 });
check('สร้าง RFQ แล้วเด้งไปหน้าใบขอราคา', /\/rfqs\/[a-f0-9]{24}/.test(page.url()), page.url());
const rfqId = page.url().split('/rfqs/')[1];

await page.waitForSelector('table');
const lineText = await page.locator('.tab-panel table tbody tr').first().innerText();
check('บรรทัดใน RFQ แสดงรหัสสินค้าและราคาเดิม',
  lineText.includes(decodeURIComponent(openedPart)) && /[\d,]+\.\d\d/.test(lineText),
  lineText.replace(/\n/g, ' | '));
await shot('ep-rfq-created');

// ส่ง RFQ
await page.locator('button:has-text("ส่งใบขอราคา")').first().click();
await page.waitForSelector('.modal');
await page.locator('.modal button:has-text("ออกใบขอราคา")').click();
await page.waitForTimeout(2500);

const [, invites] = await api(`/rfqs/${rfqId}/invites`);
check('ส่งแล้วได้ลิงก์ portal ครบทุกราย',
  invites.length > 0 && invites.every((i) => i.portal_url), invites.length);

// ------------------------------------------------------------- portal ของผู้ขาย
const portal = await ctx.newPage();
await portal.goto(`${FE}/portal/${invites[0].token}`, { waitUntil: 'networkidle' });
await portal.waitForSelector('.gate-card');
const gateHtml = await portal.content();
check('เปิดลิงก์ครั้งแรก เจอด่านรับทราบเงื่อนไขก่อน',
  gateHtml.includes('เงื่อนไขการเสนอราคา') && (await portal.locator('.gate-check input').count()) === 1);
check('ยังไม่ติ๊ก = ไม่เห็นรหัส/ชื่อสินค้าในหน้าเลย',
  !gateHtml.includes(decodeURIComponent(openedPart)));
check('ยังไม่ติ๊ก = ไม่มีตารางกรอกราคาให้กรอก',
  (await portal.locator('input[type=number]').count()) === 0);
check('ยังไม่ติ๊ก ปุ่มเปิดดูยังกดไม่ได้',
  await portal.locator('.gate-btn').isDisabled());
await portal.screenshot({ path: `${SHOTS}/ep-portal-gate.png`, fullPage: true });

await portal.locator('.gate-check input').check();
check('ติ๊กแล้วปุ่มเปิดใช้งาน', !(await portal.locator('.gate-btn').isDisabled()));
await portal.locator('.gate-btn').click();
await portal.waitForSelector('table', { timeout: 15000 });
const portalHtml = await portal.content();
check('รับทราบแล้วจึงเห็นรายการสินค้า',
  portalHtml.includes(decodeURIComponent(openedPart))
  && (await portal.locator('input[type=number]').count()) > 0);
check('หน้าผู้ขายไม่หลุดราคาเดิมของเรา',
  !portalHtml.includes('ราคาเดิม') && !portalHtml.includes('ราคาล่าสุดที่เคยซื้อ'));
await portal.screenshot({ path: `${SHOTS}/ep-portal.png`, fullPage: true });

// เสนอราคาจากทุกราย ผ่าน API (เร็วกว่าและครอบคลุมกว่า)
const prices = [1200000, 990000, 1450000, 1010000];
for (let i = 0; i < invites.length; i++) {
  // ต้องกดรับทราบเงื่อนไขก่อน ระบบจึงจะรับราคา
  await api(`/portal/${invites[i].token}/accept-terms`, 'POST',
    { accepted: true, accepted_by: 'ฝ่ายขาย' });
  const [st] = await api(`/portal/${invites[i].token}/quote`, 'POST', {
    lines: [{ part_num: decodeURIComponent(openedPart), unit_price: prices[i % prices.length], lead_time_days: 10 + i }],
    currency: 'THB', vat_percent: 7, contact_name: 'ฝ่ายขาย',
  });
  if (st !== 200) console.log('   quote failed', st);
}
await portal.close();

// ------------------------------------------------------------- เทียบราคา
await page.reload({ waitUntil: 'networkidle' });
await page.locator('.tab:has-text("เทียบราคา")').click();
await page.waitForSelector('table.compare-table');
const cmpHeaders = await page.locator('table.compare-table thead th').allInnerTexts();
check('ตารางเทียบราคามีคอลัมน์ "ราคาเดิม"', cmpHeaders.some((h) => h.includes('ราคาเดิม')), cmpHeaders);
check('มีคอลัมน์ของผู้ขายทุกราย', cmpHeaders.length >= invites.length + 3, cmpHeaders.length);
check('ไฮไลต์ราคาต่ำสุด', await page.locator('.compare-table .num-cell.lowest').count() > 0);
check('สรุปส่วนต่างเทียบราคาเดิม (บอกตรง ๆ ว่าถูกลงหรือแพงขึ้น)',
  await page.locator('.stat:has-text("ราคาเดิม") .num').count() > 0
  && /ประหยัดกว่าราคาเดิม|แพงกว่าราคาเดิม/.test(await page.locator('.compare-summary, .stat-row, body').first().innerText()));
await shot('ep-comparison');

// ------------------------------------------------------------- หน้าผู้ขาย
await page.goto(`${FE}/vendors`, { waitUntil: 'networkidle' });
await page.waitForSelector('table.vendor-table tbody tr');
check('หน้าผู้ขายเป็นตารางปกติ ไม่ใช่ grid',
  await page.locator('table.vendor-table').isVisible()
  && await page.locator('table.vendor-table tbody tr').count() > 5);
await shot('ep-vendors');

await page.locator('table.vendor-table tbody tr').first().click();
await page.waitForURL('**/vendors/**');
await page.waitForSelector('.stat-card');
await page.waitForSelector('.sk', { state: 'detached' });
check('หน้าผู้ขายแสดงข้อมูลบริษัทก่อน', await page.locator('h2:text-is("ข้อมูลบริษัท")').isVisible());
check('มีแท็บสินค้าที่เคยขาย', await page.locator('.tab:has-text("สินค้าที่เคยขายให้เรา")').isVisible());

// "สินค้าที่ซื้อจากรายนี้มากที่สุด" ต้องอ่านออกว่าเป็นของอะไร ไม่ใช่มีแต่รหัส
const topCard = page.locator('.card:has-text("สินค้าที่ซื้อจากรายนี้มากที่สุด")');
if (await topCard.count() > 0) {
  const topRows = await topCard.locator('table tbody tr').allInnerTexts();
  check('ตารางสินค้าที่ซื้อบ่อยแสดงชื่อสินค้า ไม่ใช่แค่รหัส',
    topRows.length > 0 && topRows.every((t) => /[A-Za-z]{4,}/.test(t.replace(/\d{2}-\d{3}-\d{2}-\d{2}-\d{3}/g, ''))),
    topRows.slice(0, 2));
  check('ชื่อสินค้าในตารางนั้นกดไปหน้าสินค้าได้',
    (await topCard.locator('table tbody tr a').first().getAttribute('href'))?.startsWith('/products/'));
}

await page.locator('.tab:has-text("สินค้าที่เคยขายให้เรา")').click();
await page.waitForTimeout(1200);
const vItemRows = await page.locator('table.vendor-table tbody tr').count();
check('แท็บสินค้าของผู้ขายมีข้อมูล', vItemRows > 0, vItemRows);
await shot('ep-vendor-detail');

await page.locator('.tab:has-text("รายการเคลื่อนไหว")').click();
await page.waitForTimeout(1200);
check('แท็บรายการเคลื่อนไหวของผู้ขายมีข้อมูล',
  await page.locator('table tbody tr').count() > 0);

// ------------------------------------------------------------- ความตรงเวลา
await page.goto(`${FE}/vendors`, { waitUntil: 'networkidle' });
await page.waitForSelector('table.vendor-table tbody tr');
const vHeaders = await page.locator('table.vendor-table thead th').allInnerTexts();
check('ตารางผู้ขายมีคอลัมน์ส่งตรงเวลา', vHeaders.some((h) => h.includes('ส่งตรงเวลา')), vHeaders);
check('แถวผู้ขายแสดง % และจำนวนงวด',
  /%/.test(await page.locator('table.vendor-table tbody tr .otd').first().innerText())
  && /งวด/.test(await page.locator('table.vendor-table tbody tr .otd-detail').first().innerText()));

await page.locator('label:has-text("ส่งตรงเวลาต่ำกว่า 70%") input').check();
await page.waitForTimeout(1300);
const lateRows = await page.locator('table.vendor-table tbody tr .otd').allInnerTexts();
check('กรองเฉพาะรายที่ส่งตรงเวลาต่ำกว่า 70% ได้',
  lateRows.length > 0 && lateRows.every((t) => parseFloat(t) <= 70), lateRows.slice(0, 4));
await shot('otd-vendors');
await page.locator('label:has-text("ส่งตรงเวลาต่ำกว่า 70%") input').uncheck();
await page.waitForTimeout(1000);

await page.locator('table.vendor-table tbody tr').first().click();
await page.waitForURL('**/vendors/**');
await page.waitForSelector('.sk', { state: 'detached' });
check('หน้าผู้ขายมีการ์ดส่งตรงเวลา', await page.locator('.stat-card:has-text("ส่งตรงเวลา")').count() > 0);

await page.locator('.tab:has-text("การส่งตรงเวลา")').click();
await page.waitForTimeout(1500);
const dlRows = await page.locator('.card:has-text("ประวัติการส่งของ") table tbody tr').count();
check('แท็บการส่งตรงเวลามีรายงวดจริง', dlRows > 1, dlRows);
check('แต่ละงวดบอกกำหนดส่งและผลการส่ง',
  await page.locator('th:text-is("กำหนดส่ง")').isVisible()
  && await page.locator('th:text-is("ผลการส่ง")').isVisible());
await shot('otd-vendor-detail');

await page.locator('.tab:has-text("ยังค้างส่ง")').click();
await page.waitForTimeout(1400);
const overdueTxt = await page.locator('.card:has-text("ประวัติการส่งของ") table tbody').innerText();
check('กรองงวดค้างส่งบนหน้าเว็บได้',
  /ยังไม่ได้รับ|ค้างมา|ไม่มีงวดส่งในหมวดนี้/.test(overdueTxt), overdueTxt.slice(0, 80));

await page.goto(`${FE}/products/${encodeURIComponent(decodeURIComponent(openedPart))}`,
  { waitUntil: 'networkidle' });
await page.waitForSelector('.sk', { state: 'detached' });
const itemVendorHeaders = await page
  .locator('.card:has-text("ผู้ขายที่เคยขายสินค้านี้") thead th').allInnerTexts();
check('ตารางผู้ขายในหน้าสินค้ามีทั้งราคาและความตรงเวลา',
  itemVendorHeaders.some((h) => h.includes('ราคาล่าสุดของรายนี้'))
  && itemVendorHeaders.some((h) => h.includes('ส่งตรงเวลา'))
  && itemVendorHeaders.some((h) => h.includes('เฉพาะสินค้านี้')), itemVendorHeaders);
check('มีป้ายความตรงเวลาในแถวผู้ขาย',
  await page.locator('.card:has-text("ผู้ขายที่เคยขายสินค้านี้") .otd').count() > 0);
await shot('otd-item');

await page.goto(`${FE}/dashboard`, { waitUntil: 'networkidle' });
await page.waitForSelector('.sk', { state: 'detached' }).catch(() => {});
check('หน้าภาพรวมมีบล็อกการส่งของตรงเวลา',
  await page.locator('h2:text-is("การส่งของตรงเวลา")').isVisible());
check('ภาพรวมแสดงผู้ขายที่ควรตามงาน',
  await page.locator('th:text-is("ผู้ขายที่ควรตามงาน")').isVisible());
check('ภาพรวมมีรายการงวดค้างส่งนานที่สุด',
  await page.locator('h2:text-is("งวดที่ค้างส่งนานที่สุด")').isVisible());
await shot('otd-dashboard');

// ------------------------------------------------------------- ตามงานส่งของ
await page.goto(`${FE}/deliveries`, { waitUntil: 'networkidle' });
check('มีเมนูตามงานส่งของ', await page.locator('.nav-item:has-text("ตามงานส่งของ")').isVisible());
await page.waitForSelector('table.vendor-table tbody tr');
const grpRows = await page.locator('table.vendor-table tbody tr').count();
check('มุมรายผู้ขายแสดงผู้ขายที่ค้างส่ง', grpRows > 1, grpRows);
check('บอกจำนวนผู้ขายและงวดรวม',
  /ผู้ขาย/.test(await page.locator('.result-line').innerText())
  && /งวด/.test(await page.locator('.result-line').innerText()));

await page.locator('table.vendor-table tbody tr').first().click();
await page.waitForTimeout(800);
const detailText = await page.locator('table.vendor-table > tbody').first().innerText();
check('กดผู้ขายแล้วเห็นรายการของที่ค้างจริง',
  /PO \d+/.test(detailText) && /งวดที่ \d+/.test(detailText), detailText.slice(0, 120));
check('มีปุ่มเปิดหน้าผู้ขายดูงวดทั้งหมด',
  await page.locator('a:has-text("เปิดหน้าผู้ขาย")').first().isVisible());
await shot('followup-vendor');

await page.locator('.tab:has-text("ดูรายงวด")').click();
await page.waitForTimeout(1400);
const relHeaders = await page.locator('table.vendor-table thead th').allInnerTexts();
check('มุมรายงวดมีคอลัมน์ผู้ขาย สินค้า และกำหนดส่ง',
  relHeaders.some((h) => h.includes('ผู้ขาย')) && relHeaders.some((h) => h.includes('สินค้า'))
  && relHeaders.some((h) => h.includes('กำหนดส่ง')), relHeaders);
const relText = await page.locator('table.vendor-table > tbody').first().innerText();
check('รายงวดบอกว่าค้างมากี่วัน', /ค้างมา [\d,]+ วัน/.test(relText), relText.slice(0, 120));
await shot('followup-release');

await page.selectOption('.filter-row select', { label: 'ส่งตรงเวลา / ก่อนกำหนด' });
await page.waitForTimeout(1500);
const okText = await page.locator('table.vendor-table > tbody').first().innerText();
check('ดูงวดที่ส่งตรงเวลาได้', /ตรงเวลา|ส่งก่อนกำหนด/.test(okText), okText.slice(0, 120));
check('งวดที่ส่งเร็วอ่านว่า "เร็ว" ไม่ใช่เลขติดลบ',
  /เร็ว [\d,]+ วัน|ตรงวัน/.test(okText) && !/-[\d,]+ วัน/.test(okText), okText.slice(0, 200));
check('ไม่มีคำว่าค้างมาในมุมส่งตรงเวลา', !/ค้างมา/.test(okText));
await shot('followup-ontime');

await page.selectOption('.filter-row select', { label: 'ทุกงวด' });
await page.waitForTimeout(1500);
const allText = await page.locator('table.vendor-table > tbody').first().innerText();
check('มุมทุกงวดมีทั้งที่ตรงเวลาและที่ช้า',
  /ตรงเวลา|ส่งก่อนกำหนด/.test(allText) && /ช้า/.test(allText), allText.slice(0, 160));

await page.selectOption('.filter-row select', { label: 'ยังค้างส่ง (ยังไม่ได้ของ)' });
await page.waitForTimeout(1300);
await page.fill('input[type="search"]', 'zzzzqqqq');
await page.waitForTimeout(1300);
check('ค้นไม่เจอแล้วบอกอย่างสุภาพ',
  /ไม่มีงานส่ง|ไม่มีงวด/.test(await page.locator('table.vendor-table > tbody').first().innerText()));

check('ไม่มี JavaScript error ระหว่างการทดสอบ', errors.length === 0, errors.slice(0, 3));

await browser.close();
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
