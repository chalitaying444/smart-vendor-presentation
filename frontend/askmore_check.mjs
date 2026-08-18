/**
 * ขอราคาเพิ่มจากหน้าวัสดุรายตัว (แท็บเทียบราคา)
 *
 * สิ่งที่ต้องพิสูจน์:
 *   1. ยังไม่เคยออกใบเลย ก็ออกได้จากหน้านี้ ไม่ต้องย้อนไปหน้าออกใบทั้งโครงการ
 *   2. ออกแล้วหัวรายการ/สถานะอัปเดตทันที ไม่ต้องรีเฟรชเอง
 *   3. เจ้าที่เชิญไปแล้วต้องเห็นธง "เชิญแล้ว" ก่อนกด
 *   4. ติ๊กเจ้าเดิมซ้ำ ต้องมีขั้นยืนยันโผล่มา ไม่ใช่ส่งซ้ำเงียบ ๆ
 */
import { chromium } from 'playwright';
import { FE, API, CHROMIUM, SHOTS, token } from './_env.mjs';

const TOK = token();
let pass = 0, fail = 0;
const check = (l, c, e = '') => { c ? (pass++, console.log('PASS', l))
                                    : (fail++, console.log('FAIL', l, String(e).slice(0, 220))); };

/** รอจนเงื่อนไขเป็นจริง — ใช้แทนการอ่านค่าทันที เพราะหน้าโหลดข้อมูลใหม่แบบ async
 *  คืน false เมื่อหมดเวลา จะได้รายงานเป็น FAIL ตามปกติ ไม่ใช่โยน error ทิ้งทั้งไฟล์ */
const until = async (fn, ms = 15000) => {
  const end = Date.now() + ms;
  for (;;) {
    try { if (await fn()) return true; } catch (e) { /* ยังไม่พร้อม */ }
    if (Date.now() > end) return false;
    await new Promise((r) => setTimeout(r, 250));
  }
};

const api = async (path, method = 'GET', body) => {
  const r = await fetch(API + path, {
    method,
    headers: { Authorization: `Bearer ${TOK}`, 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  return [r.status, await r.json().catch(() => null)];
};

// ---- เตรียมโครงการที่มีของซึ่งมีผู้ขายหลายราย ไม่งั้นทดสอบ "เชิญเพิ่ม" ไม่ได้
const [, pool] = await api('/catalog/items?limit=40');
const target = pool.items.find((i) => i.vendor_count >= 3);
if (!target) { console.log('FAIL ไม่มีสินค้าที่มีผู้ขาย 3 รายขึ้นไปในข้อมูลทดสอบ'); process.exit(1); }

const [, bom] = await api('/boms', 'POST', {
  title: 'ทดสอบขอราคาเพิ่มจากหน้าวัสดุ',
  contingency_percent: 0, vat_percent: 7,
  lines: [{ name: target.description.slice(0, 40), qty: 4, uom: 'EA' }],
});
await api(`/boms/${bom.id}/lines/1`, 'PATCH', { part_num: target.part_num });

const b = await chromium.launch({ executablePath: CHROMIUM });
const ctx = await b.newContext({ viewport: { width: 1500, height: 1000 } });
await ctx.addCookies([{ name: 'vendor_session', value: TOK, domain: 'localhost', path: '/' }]);
const p = await ctx.newPage();
const errs = [];
p.on('pageerror', (e) => errs.push(String(e)));

const url = `${FE}/boms/${bom.id}/lines/1?tab=compare`;
await p.goto(url, { waitUntil: 'domcontentloaded' });
await p.waitForSelector('.ask-more', { timeout: 30000 });

check('ยังไม่มีราคา แต่ยังออกใบขอราคาได้จากหน้านี้เลย',
  (await p.locator('.ask-more').count()) === 1
  && /ยังไม่ได้เชิญใคร/.test(await p.locator('.empty').first().innerText()));
check('ใบที่จะออกบอกชัดว่ามีของอะไร จำนวนเท่าไร',
  /4/.test(await p.locator('.ask-more-head').innerText())
  && (await p.locator('.ask-more-head code').innerText()).includes(target.part_num));

await p.waitForSelector('.ask-more .vendor-pick tbody tr');
const rows = await p.locator('.ask-more .vendor-pick tbody tr').count();
check('มีรายชื่อผู้ขายที่เคยขายรหัสนี้ให้เลือก', rows >= 3, rows);
check('ยังไม่ได้เลือกใคร ปุ่มออกใบกดไม่ได้',
  await p.locator('.ask-more-bar .btn-primary').isDisabled());

await p.locator('.ask-more .vendor-pick tbody tr').nth(0).locator('input[type=checkbox]').check();
await p.locator('.ask-more .vendor-pick tbody tr').nth(1).locator('input[type=checkbox]').check();
check('ปุ่มบอกจำนวนใบที่จะออกตามที่ติ๊กไว้',
  /2 ใบ/.test(await p.locator('.ask-more-bar .btn-primary').innerText()),
  await p.locator('.ask-more-bar .btn-primary').innerText());

// ไม่ส่งอีเมลจริงในเทสต์ — ปลดติ๊ก "ออกแล้วส่งเลย"
await p.locator('.ask-more-bar .checkbox input').uncheck();
await p.locator('.ask-more-bar .btn-primary').click();
await p.waitForSelector('.ask-more .alert-ok', { timeout: 30000 });
check('ออกใบเพิ่มแล้วขึ้นเลขที่ใบให้กดต่อได้',
  (await p.locator('.ask-more .alert-ok a').count()) === 2,
  await p.locator('.ask-more .alert-ok').innerText());

check('หัวรายการอัปเดตเองว่าออกใบไหนไปแล้ว ไม่ต้องรีเฟรช',
  await until(async () => /RFQ-/.test(await p.locator('.kv-grid').innerText())),
  await p.locator('.kv-grid').innerText());
check('สถานะรายการขยับเป็น "ออกใบขอราคาแล้ว"',
  await until(async () => /ออกใบขอราคาแล้ว/.test(await p.locator('.card-head .stage').innerText())),
  await p.locator('.card-head .stage').innerText());

// ---- รอบสอง: เจ้าที่เชิญไปแล้วต้องเห็นธง
const flagged = await until(async () =>
  (await p.locator('.ask-more .vendor-pick .conf-manual').count()) === 2);
check('เจ้าที่เชิญไปแล้วติดธง "เชิญแล้ว" พร้อมเลขที่ใบ', flagged,
  await p.locator('.ask-more .vendor-pick').innerText());
check('ธงบอกเลขที่ใบที่เคยเชิญ ไม่ใช่แค่คำว่าเชิญแล้ว',
  /RFQ-/.test(await p.locator('.ask-more .vendor-pick .conf-manual').first().innerText()),
  await p.locator('.ask-more .vendor-pick .conf-manual').first().innerText());
check('ติ๊กที่เลือกไว้ถูกล้างหลังออกใบ ไม่ค้างไว้ให้กดซ้ำ',
  (await p.locator('.ask-more .vendor-pick input[type=checkbox]:checked').count()) === 0);

// เลือกเจ้าใหม่ที่ยังไม่เคยเชิญ → ต้องไม่มีขั้นยืนยันโผล่มา
const fresh = p.locator('.ask-more .vendor-pick tbody tr')
  .filter({ hasNot: p.locator('.conf-manual') }).first();
await fresh.locator('input[type=checkbox]').check();
check('เลือกเจ้าใหม่ ไม่ต้องยืนยันอะไรเพิ่ม',
  (await p.locator('.ask-more-repeat').count()) === 0);

// เลือกเจ้าที่เชิญไปแล้ว → ต้องมีขั้นยืนยัน
const oldOne = p.locator('.ask-more .vendor-pick tbody tr')
  .filter({ has: p.locator('.conf-manual') }).first();
await oldOne.locator('input[type=checkbox]').check();
await p.waitForSelector('.ask-more-repeat', { timeout: 10000 });
check('ติ๊กเจ้าที่เคยเชิญ ต้องมีขั้นยืนยันก่อน ไม่ส่งซ้ำเงียบ ๆ',
  (await p.locator('.ask-more-repeat').count()) === 1);
check('ขั้นยืนยันบอกชื่อเจ้าที่จะถามซ้ำ และบอกว่าถ้าไม่ติ๊กจะเกิดอะไร',
  /ไม่ติ๊ก = ระบบข้ามให้/.test(await p.locator('.ask-more-repeat').innerText()),
  await p.locator('.ask-more-repeat').innerText());

await p.locator('.ask-more-repeat input').check();
await p.locator('.ask-more-bar .btn-primary').click();
await p.waitForFunction(
  () => document.querySelectorAll('.ask-more .alert-ok a').length === 2,
  null, { timeout: 30000 },
);
check('ยืนยันแล้วออกใบให้ทั้งเจ้าใหม่และเจ้าเดิม',
  (await p.locator('.ask-more .alert-ok a').count()) === 2,
  await p.locator('.ask-more .alert-ok').innerText());

const [, fresh2] = await api(`/boms/${bom.id}`);
check('ทุกใบถูกจดไว้ที่บรรทัดเดิม ไม่ทับกัน',
  fresh2.lines[0].rfqs.length === 4, fresh2.lines[0].rfqs?.length);

// ---- ค้นหาผู้ขายเพิ่มจากหน้านี้ได้ด้วย
await p.locator('.ask-more .vendor-add button').first().click();
await p.waitForSelector('.vendor-add.open .vendor-found tbody tr', { timeout: 30000 });
check('ค้นหาผู้ขายเพิ่มได้จากหน้านี้เหมือนหน้าออกใบทั้งโครงการ',
  (await p.locator('.vendor-add.open .vendor-found tbody tr').count()) > 0);
check('ผลค้นก็บอกว่าเจ้าไหนเชิญไปแล้ว',
  (await p.locator('.vendor-add.open .vendor-found .conf-manual').count()) > 0);
// ธงต้องอยู่ในช่องชื่อผู้ขาย ไม่ใช่ช่องปุ่มที่แคบจนเลขที่ใบล้นออกนอกตาราง
const flagBox = await p.locator('.vendor-add.open .vendor-found .conf-manual').first().boundingBox();
const tableBox = await p.locator('.vendor-add.open .vendor-found').boundingBox();
check('ธง "เชิญแล้ว" ในผลค้นไม่ล้นออกนอกตาราง',
  flagBox.x + flagBox.width <= tableBox.x + tableBox.width + 1,
  JSON.stringify({ flagBox, tableBox }));

await p.screenshot({ path: `${SHOTS}/askmore.png`, fullPage: true });
check('ไม่มี JavaScript error', errs.length === 0, errs.join(' | '));

await b.close();
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
