/**
 * หน้าจอของระบบสิทธิ์: หน่วยงาน / assign / ลบเข้าถังขยะ / กู้คืน
 *
 * ตรวจจากหน้าจอจริงของคนละคน (คนละ cookie คนละ context) ไม่ใช่ยิง API อย่างเดียว
 * เพราะสิ่งที่ผู้ใช้เชื่อคือ "สิ่งที่เห็นบนหน้าจอ" — ถ้า API กันแล้วแต่หน้าจอยังโชว์ชื่อ
 * โครงการค้างอยู่ คนก็ยังเห็นข้อมูลที่ไม่ควรเห็นอยู่ดี
 */
import { chromium } from 'playwright';
import { FE, API, CHROMIUM, token } from './_env.mjs';

const ADMIN = token();
let pass = 0, fail = 0;
const check = (l, c, e = '') => { c ? (pass++, console.log('PASS', l))
                                   : (fail++, console.log('FAIL', l, String(e).slice(0, 200))); };

const api = async (path, method = 'GET', body, token = ADMIN) => {
  const r = await fetch(API + path, {
    method,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  return [r.status, await r.json().catch(() => null)];
};

async function ensureUser(email, role, departments) {
  const [st] = await api('/users', 'POST', {
    email, display_name: email.split('@')[0], role, departments, is_active: true,
  });
  if (st === 409) {
    const [, found] = await api(`/users?q=${email}`);
    await api(`/users/${found.items[0].id}`, 'PATCH', { role, departments, is_active: true });
  }
  const [, tok] = await api(`/auth/token?email=${email}`, 'POST');
  return tok.access_token;
}

const BUY = 'ฝ่ายจัดซื้อ';
const PROJ = 'ฝ่ายโครงการ';
const owner = await ensureUser('ui.owner@precise.co.th', 'staff', [BUY]);
const mate = await ensureUser('ui.mate@precise.co.th', 'staff', [BUY]);
const outsider = await ensureUser('ui.outsider@precise.co.th', 'staff', [PROJ]);

const [, items] = await api('/catalog/items?limit=1');
// ชื่อไม่ซ้ำต่อรอบ + เก็บกวาดของค้างจากรอบที่ล้มกลางทาง
// ไม่งั้นเทสต์ "ต้องไม่เห็นชื่อนี้" จะไปเจอโครงการชื่อเดียวกันของรอบก่อนแล้วฟ้องผิด ๆ
const PREFIX = 'โครงการทดสอบสิทธิ์บนหน้าจอ';
const TITLE = `${PREFIX} #${process.pid}`;
const [, leftovers] = await api(`/boms?q=${encodeURIComponent(PREFIX)}&limit=100`);
for (const old of leftovers.items || []) {
  await api(`/boms/${old.id}`, 'DELETE');
  await api(`/boms/${old.id}/purge`, 'DELETE');
}
const [, oldTrash] = await api(`/boms?q=${encodeURIComponent(PREFIX)}&trash=true&limit=100`);
for (const old of oldTrash.items || []) await api(`/boms/${old.id}/purge`, 'DELETE');
const [, bom] = await api('/boms', 'POST', {
  title: TITLE, contingency_percent: 0, vat_percent: 7,
  lines: [{ name: items.items[0].description.slice(0, 40), qty: 3, uom: 'EA' }],
}, owner);

const browser = await chromium.launch({ executablePath: CHROMIUM });
const errs = [];

async function pageAs(token) {
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } });
  await ctx.addCookies([{ name: 'vendor_session', value: token, domain: 'localhost', path: '/' }]);
  const p = await ctx.newPage();
  p.on('pageerror', (e) => errs.push(String(e)));
  return p;
}

// ---- เจ้าของ: เห็นโครงการ เห็นแถบสิทธิ์ และมีปุ่มลบ
const own = await pageAs(owner);
await own.goto(`${FE}/boms`, { waitUntil: 'domcontentloaded' });
await own.waitForSelector('.vendor-table tbody tr', { timeout: 30000 });
check('เจ้าของเห็นโครงการของตัวเองในรายการ',
  (await own.locator(`.vendor-table:has-text("${TITLE}")`).count()) === 1);
const listNote = await own.locator('.card:has(.vendor-table) .card-head .cell-sub').innerText();
check('หน้ารายการบอกว่าเห็นเฉพาะของหน่วยงานไหน ไม่ปล่อยให้เข้าใจว่าเห็นทุกโครงการ',
  /เห็นเฉพาะของ/.test(listNote), listNote);
check('มีแท็บของฉัน/ถังขยะให้สลับดู',
  (await own.locator('.tab:has-text("ถังขยะ")').count()) === 1
  && (await own.locator('.tab:has-text("ของฉัน")').count()) === 1);

await own.goto(`${FE}/boms/${bom.id}`, { waitUntil: 'domcontentloaded' });
await own.waitForSelector('.access-card', { timeout: 30000 });
check('หน้าโครงการบอกหน่วยงานและเจ้าของไว้บนสุด',
  (await own.locator('.access-card').innerText()).includes(BUY)
  && (await own.locator('.access-card').innerText()).includes('ui.owner@precise.co.th'),
  await own.locator('.access-card').innerText());
check('เจ้าของเห็นปุ่มลบโครงการ',
  (await own.locator('.access-card .btn-danger').count()) === 1);

// เพิ่มคนนอกหน่วยงานเข้าโครงการจากหน้าจอจริง
await own.locator('.access-card .btn-secondary:has-text("จัดการสิทธิ์")').click();
await own.waitForSelector('#acc-email');
await own.fill('#acc-email', 'ui.outsider@precise.co.th');
await own.locator('button:has-text("เพิ่มเข้าโครงการ")').click();
await own.waitForSelector('.assignee-list li', { timeout: 20000 });
check('เพิ่มคนเข้าโครงการจากหน้าจอได้',
  (await own.locator('.assignee-list li').innerText()).includes('ui.outsider'),
  await own.locator('.assignee-list li').innerText());

// ---- คนในหน่วยงานเดียวกัน: เห็นโครงการ แต่ไม่มีปุ่มลบ
const team = await pageAs(mate);
await team.goto(`${FE}/boms/${bom.id}`, { waitUntil: 'domcontentloaded' });
await team.waitForSelector('.access-card', { timeout: 30000 });
check('คนในหน่วยงานเดียวกันเปิดโครงการได้',
  (await team.locator('h2').first().innerText()).includes(BUY));
check('แต่ไม่เห็นปุ่มลบ/จัดการสิทธิ์ เพราะไม่ใช่เจ้าของ',
  (await team.locator('.access-card .btn-danger').count()) === 0
  && (await team.locator('.access-card .btn-secondary').count()) === 0);

// ---- คนนอกหน่วยงาน (ถูกถอดออกก่อน): เปิดไม่ได้ และไม่เห็นในรายการ
await api(`/boms/${bom.id}/assignees`, 'POST', { remove: ['ui.outsider@precise.co.th'] }, owner);
const out = await pageAs(outsider);
await out.goto(`${FE}/boms`, { waitUntil: 'domcontentloaded' });
await out.waitForSelector('.vendor-table', { timeout: 30000 });
await out.waitForTimeout(1200);
check('คนหน่วยงานอื่นไม่เห็นชื่อโครงการนี้ในหน้ารายการเลย',
  !(await out.content()).includes(TITLE));
await out.goto(`${FE}/boms/${bom.id}`, { waitUntil: 'domcontentloaded' });
await out.waitForSelector('.alert-error', { timeout: 30000 });
const denied = await out.locator('.alert-error').innerText();
check('เปิดตรง ๆ ด้วยลิงก์ก็ไม่ได้ และบอกเหตุผลให้เข้าใจ',
  /หน่วยงาน/.test(denied) && /เพิ่มคุณเข้าโครงการ/.test(denied), denied);
check('หน้าที่ถูกปฏิเสธต้องไม่หลุดชื่อโครงการออกมา',
  !(await out.content()).includes(TITLE));

// ---- ลบเข้าถังขยะจากหน้าจอ แล้วกู้คืน
own.on('dialog', (d) => d.accept());
await own.goto(`${FE}/boms/${bom.id}`, { waitUntil: 'domcontentloaded' });
await own.waitForSelector('.access-card .btn-danger');
await own.locator('.access-card .btn-danger').click();
await own.waitForURL(/\/boms(\?|$)/, { timeout: 20000 });
await own.waitForSelector('.vendor-table', { timeout: 20000 });
await own.waitForTimeout(1200);
const afterDelete = await own.content();
check('ลบแล้วเด้งกลับหน้ารายการ และไม่เห็นโครงการนั้นแล้ว', !afterDelete.includes(TITLE));
check('หน้ารายการยืนยันให้เห็นว่าลบอะไรไป และกดกู้คืนต่อได้ทันที',
  /เข้าถังขยะแล้ว/.test(await own.locator('.alert-ok').innerText())
  && (await own.locator('.link-btn:has-text("เปิดถังขยะ")').count()) === 1,
  await own.locator('.alert-ok').innerText());

await own.locator('.tab:has-text("ถังขยะ")').click();
await own.waitForTimeout(1500);
check('โครงการที่ลบไปอยู่ในถังขยะ', (await own.content()).includes(TITLE));
check('ในถังขยะมีปุ่มกู้คืน',
  (await own.locator('.vendor-table button:has-text("กู้คืน")').count()) >= 1);
await own.locator('.vendor-table button:has-text("กู้คืน")').first().click();
await own.waitForTimeout(1800);
check('กู้คืนแล้วหายออกจากถังขยะ', !(await own.content()).includes(TITLE));
await own.locator('.tab:has-text("ทั้งหมด")').click();
await own.waitForTimeout(1500);
check('กู้คืนแล้วกลับมาอยู่ในรายการปกติ', (await own.content()).includes(TITLE));

// ---- ลบโครงการแล้ว ผู้ขายที่ถือลิงก์ต้องเห็นว่า "ยกเลิกแล้ว"
const [, itemDetail] = await api(`/catalog/items/${encodeURIComponent(items.items[0].part_num)}`);
const vendorKeys = itemDetail.vendors.slice(0, 1).map((v) => v.vendor_key);
await api(`/boms/${bom.id}/lines/1`, 'PATCH', { part_num: items.items[0].part_num }, owner);
const [, issued] = await api(`/boms/${bom.id}/rfqs`, 'POST', {
  group_by: 'vendor', items: [{ line_no: 1, vendor_keys: vendorKeys }],
}, owner);
const newRfqId = issued.created[0].rfq_id;
await api(`/rfqs/${newRfqId}/send`, 'POST', { message: 'รบกวนเสนอราคา' }, owner);
const [, newInvites] = await api(`/rfqs/${newRfqId}/invites`, undefined, undefined, owner);
const vendorLink = newInvites[0].token;

const vendorPage = await browser.newPage();
await vendorPage.goto(`${FE}/portal/${vendorLink}`, { waitUntil: 'domcontentloaded' });
await vendorPage.waitForSelector('.gate-card', { timeout: 30000 });
check('ก่อนลบโครงการ ผู้ขายเปิดลิงก์แล้วเจอด่านรับทราบเงื่อนไขตามปกติ',
  (await vendorPage.locator('h1').innerText()).includes('เงื่อนไขการเสนอราคา'),
  await vendorPage.locator('h1').innerText());

await api(`/boms/${bom.id}`, 'DELETE', null, owner);
await vendorPage.reload({ waitUntil: 'domcontentloaded' });
await vendorPage.waitForSelector('.gate-card', { timeout: 30000 });
const cancelText = await vendorPage.locator('.gate-card').innerText();
check('ลบโครงการแล้ว ผู้ขายเปิดลิงก์เดิมเห็นว่าใบนี้ถูกยกเลิก',
  /ถูกยกเลิกแล้ว/.test(cancelText), cancelText.replace(/\n/g, ' | '));
check('หน้ายกเลิกยังบอกเลขที่ใบไว้ให้อ้างอิงตอนโทรถาม',
  cancelText.includes(issued.created[0].rfq_no), cancelText.replace(/\n/g, ' | '));
check('หน้ายกเลิกไม่มีช่องกรอกราคาหรือปุ่มแนบไฟล์เหลืออยู่',
  (await vendorPage.locator('input[type="number"]').count()) === 0
  && (await vendorPage.locator('.dropzone').count()) === 0);

await api(`/boms/${bom.id}/restore`, 'POST', null, owner);
await vendorPage.reload({ waitUntil: 'domcontentloaded' });
await vendorPage.waitForSelector('.gate-card', { timeout: 30000 });
check('กู้โครงการคืน ผู้ขายกลับมาเสนอราคาต่อได้',
  (await vendorPage.locator('h1').innerText()).includes('เงื่อนไขการเสนอราคา'),
  await vendorPage.locator('h1').innerText());

// ---- ยกเลิกใบขอราคาใบเดียวจากหน้าจอ (ไม่ได้ลบโครงการ)
// (handler ของ dialog ลงทะเบียนไว้แล้วตอนทดสอบลบโครงการ ลงซ้ำจะชนกัน)
await own.goto(`${FE}/rfqs/${newRfqId}`, { waitUntil: 'domcontentloaded' });
await own.waitForSelector('.card-head .btn-danger', { timeout: 30000 });
check('หน้าใบขอราคามีปุ่มยกเลิกใบนี้',
  (await own.locator('.card-head .btn-danger').innerText()).includes('ยกเลิกใบนี้'));
await own.locator('.card-head .btn-danger').click();
await own.waitForURL(/\/rfqs\?cancelled=/, { timeout: 20000 });
await own.waitForTimeout(1500);
const cancelNote = await own.locator('.alert-ok').first().innerText();
check('ยกเลิกแล้วเด้งกลับรายการ พร้อมบอกว่าลิงก์ของผู้ขายกี่รายถูกตัด',
  /ใช้ไม่ได้อีก/.test(cancelNote), cancelNote.replace(/\n/g, ' | '));
// ดูแค่ในตาราง ไม่ใช่ทั้งหน้า — ข้อความแจ้งผลด้านบนมีเลขที่ใบอยู่ด้วยเป็นเรื่องปกติ
const tableText = await own.locator('table').first().innerText().catch(() => '');
check('ใบที่ยกเลิกไม่อยู่ในตารางรายการปกติแล้ว',
  !tableText.includes(issued.created[0].rfq_no), tableText.slice(0, 200));

await vendorPage.reload({ waitUntil: 'domcontentloaded' });
await vendorPage.waitForSelector('.gate-card', { timeout: 30000 });
check('ลิงก์ที่ออกไปแล้วถูกเพิกถอนทันทีที่ยกเลิกใบ',
  /ถูกยกเลิกแล้ว/.test(await vendorPage.locator('.gate-card').innerText()),
  await vendorPage.locator('.gate-card').innerText().then((t) => t.replace(/\n/g, ' | ')));

await own.locator('.link-btn:has-text("ดูใบที่ยกเลิกไว้")').click();
await own.waitForTimeout(1800);
check('มีโหมดดูใบที่ยกเลิกไว้ และเจอใบนั้น',
  (await own.content()).includes(issued.created[0].rfq_no));
await own.locator('table button:has-text("กู้คืน")').first().click();
await own.waitForTimeout(1800);
const alerts = (await own.locator('.alert-ok').allInnerTexts()).join(' | ');
check('กู้ใบขอราคากลับมาได้จากหน้าจอ', /ใช้ได้อีกครั้ง/.test(alerts), alerts);

await vendorPage.reload({ waitUntil: 'domcontentloaded' });
await vendorPage.waitForSelector('.gate-card', { timeout: 30000 });
check('กู้ใบแล้วลิงก์ของผู้ขายใช้ได้อีกครั้ง',
  (await vendorPage.locator('h1').innerText()).includes('เงื่อนไขการเสนอราคา'),
  await vendorPage.locator('h1').innerText());
await vendorPage.close();

// ---- ติ๊กเลือกหลายใบแล้วยกเลิกทีเดียว
const madeIds = [];
const madeNos = [];
for (const vk of itemDetail.vendors.slice(0, 2).map((v) => v.vendor_key)) {
  const [, more] = await api(`/boms/${bom.id}/rfqs`, 'POST', {
    group_by: 'vendor', allow_repeat: true,
    items: [{ line_no: 1, vendor_keys: [vk] }],
  }, owner);
  madeIds.push(more.created[0].rfq_id);
  madeNos.push(more.created[0].rfq_no);
  await api(`/rfqs/${more.created[0].rfq_id}/send`, 'POST', { message: 'ขอราคา' }, owner);
}

await own.goto(`${FE}/rfqs`, { waitUntil: 'domcontentloaded' });
await own.waitForSelector('table tbody tr', { timeout: 30000 });
await own.waitForTimeout(800);
check('ทุกแถวมีช่องติ๊กเลือก',
  (await own.locator('table tbody .pick-cell input[type=checkbox]').count())
  === (await own.locator('table tbody tr').count()));
check('ยังไม่ติ๊กอะไร ไม่มีแถบคำสั่งโผล่มากวน',
  (await own.locator('.bulk-bar').count()) === 0);

// ติ๊กหัวตาราง = เลือกทุกแถวที่เห็นอยู่
await own.locator('table thead input[type=checkbox]').check();
const rowCount = await own.locator('table tbody tr').count();
check('ติ๊กหัวตารางแล้วเลือกทุกแถวที่แสดงอยู่',
  (await own.locator('table tbody .pick-cell input:checked').count()) === rowCount, rowCount);
const barText = await own.locator('.bulk-bar').innerText();
check('แถบคำสั่งบอกจำนวนที่เลือกไว้ ไม่ต้องนับเอง',
  barText.includes(String(rowCount)) && /ยกเลิก/.test(barText), barText.replace(/\n/g, ' | '));

// เอาออกทีละใบให้เหลือเฉพาะสองใบที่เพิ่งออก แล้วยกเลิกเฉพาะสองใบนั้น
await own.locator('table thead input[type=checkbox]').uncheck();
check('ติ๊กหัวตารางซ้ำ = ล้างที่เลือกทั้งหมด',
  (await own.locator('.bulk-bar').count()) === 0);
for (const no of madeNos) {
  await own.locator(`table tbody tr:has-text("${no}") .pick-cell input`).check();
}
check('เลือกทีละใบได้ตามต้องการ',
  /2/.test(await own.locator('.bulk-bar').innerText()),
  await own.locator('.bulk-bar').innerText());

await own.locator('.bulk-bar .btn-danger').click();
await own.waitForSelector('.alert-ok', { timeout: 30000 });
await own.waitForTimeout(1500);
const bulkNote = await own.locator('.alert-ok').first().innerText();
check('ยกเลิกหลายใบทีเดียวแล้วรายงานผลรวม',
  /ยกเลิก 2 ใบ/.test(bulkNote) && /ใช้ไม่ได้อีก/.test(bulkNote), bulkNote);
const tableAfterBulk = await own.locator('table').first().innerText().catch(() => '');
check('ทั้งสองใบหายจากตารางแล้ว',
  madeNos.every((no) => !tableAfterBulk.includes(no)), tableAfterBulk.slice(0, 200));
check('ยกเลิกเสร็จแล้วล้างที่ติ๊กไว้ให้ ไม่ค้างไว้ให้กดซ้ำ',
  (await own.locator('.bulk-bar').count()) === 0);

// กู้คืนหลายใบจากโหมด "ยกเลิกแล้ว"
await own.locator('button:has-text("ยกเลิกแล้ว")').first().click();
await own.waitForTimeout(1800);
for (const no of madeNos) {
  await own.locator(`table tbody tr:has-text("${no}") .pick-cell input`).check();
}
check('ในโหมดยกเลิกแล้ว ปุ่มเปลี่ยนเป็นกู้คืนตามที่เลือก',
  /กู้คืน 2 ใบ/.test(await own.locator('.bulk-bar').innerText()),
  await own.locator('.bulk-bar').innerText());
await own.locator('.bulk-bar .btn-secondary').click();
await own.waitForTimeout(2000);
const restoreNote = (await own.locator('.alert-ok').allInnerTexts()).join(' | ');
check('กู้คืนหลายใบทีเดียวได้', /กู้กลับมา 2 ใบ/.test(restoreNote), restoreNote);

// ---- หน้าจัดการผู้ใช้ของ admin ตั้งหน่วยงานได้
const adminPage = await pageAs(ADMIN);
await adminPage.goto(`${FE}/admin/users`, { waitUntil: 'domcontentloaded' });
await adminPage.waitForSelector('table tbody tr', { timeout: 30000 });
check('ตารางผู้ใช้มีคอลัมน์หน่วยงาน',
  (await adminPage.locator('th:has-text("หน่วยงาน")').count()) === 1);
check('เห็นหน่วยงานที่ผู้ใช้สังกัดในตาราง',
  (await adminPage.locator(`tr:has-text("ui.owner") .chip`).first().innerText()) === BUY);

await adminPage.locator('tr:has-text("ui.owner") button:has-text("แก้ไข")').click();
await adminPage.waitForSelector('#f-dept');
check('ฟอร์มแก้ไขผู้ใช้มีช่องหน่วยงาน และเติมค่าเดิมมาให้',
  (await adminPage.inputValue('#f-dept')) === BUY);
await adminPage.fill('#f-dept', `${BUY}, ${PROJ}`);
await adminPage.locator('.modal button:has-text("บันทึก")').click();
await adminPage.waitForTimeout(1800);
const [, after] = await api('/users?q=ui.owner');
check('admin ตั้งให้คนเดียวสังกัดหลายหน่วยงานได้จากหน้าจอ',
  JSON.stringify(after.items[0].departments) === JSON.stringify([BUY, PROJ]),
  after.items[0].departments);

// เก็บกวาด
await api(`/users/${after.items[0].id}`, 'PATCH', { departments: [BUY] });
await api(`/boms/${bom.id}`, 'DELETE', null, owner);
await api(`/boms/${bom.id}/purge`, 'DELETE');

check('ไม่มี JavaScript error', errs.length === 0, errs.slice(0, 3));
await browser.close();
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
