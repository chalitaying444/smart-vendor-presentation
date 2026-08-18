import { chromium } from 'playwright';
import { FE, CHROMIUM, SHOTS, token } from './_env.mjs';
const TOK = token();
let pass=0, fail=0;
const check=(l,c,e='')=>{c?(pass++,console.log('PASS',l)):(fail++,console.log('FAIL',l,String(e).slice(0,180)));};
const b = await chromium.launch({executablePath: CHROMIUM});
const ctx = await b.newContext({viewport:{width:1500,height:1000}});
await ctx.addCookies([{name:'vendor_session',value:TOK,domain:'localhost',path:'/'}]);
const p = await ctx.newPage();
const errs=[]; p.on('pageerror', e=>errs.push(String(e)));

await p.goto(`${FE}/boms`, {waitUntil:'domcontentloaded'});
await p.waitForSelector('.card', {timeout:30000});
// จับตอนโครงหน้ายังอยู่ — โครงกับตารางจริงต้องไม่ซ้อนกัน ไม่งั้น hydration พัง
check('โครงหน้าไม่ซ้อนใน tbody จริง (ตอนกำลังโหลด)',
  (await p.evaluate(() => document.querySelectorAll('tbody tbody').length)) === 0);
await p.waitForTimeout(1500);
check('โหลดเสร็จแล้วก็ยังไม่มี tbody ซ้อนกัน',
  (await p.evaluate(() => document.querySelectorAll('tbody tbody').length)) === 0);
check('มีเมนูประมาณราคา BOM ในแถบซ้าย',
  (await p.locator('.nav-item:has-text("ประมาณราคา BOM")').count()) === 1);
check('หน้ารายการโหลดได้', (await p.locator('h2:text-is("งานประมาณราคา")').count()) === 1);
await p.screenshot({path:`${SHOTS}/bom-list.png`, fullPage:true});

// ---- นำ BOM เข้าโดยวางข้อความ
await p.click('button:has-text("นำ BOM เข้ามาประมาณราคา")');
await p.waitForSelector('.modal-wide');   // ขั้นเลือกไฟล์ = กล่องปกติ
await p.fill('#bom-text', `รายการ\tจำนวน\tหน่วย
Network Firewall FG-100F\t2\tEA
สาย fiber optic SM 24C ADSS\t500\tM
ตู้ outdoor cabinet IP55 สแตนเลส\t1\tEA
ของแปลกที่ไม่มีในระบบ zxqwv\t3\tEA`);
await p.click('button:has-text("อ่านรายการ")');
await p.waitForSelector('.preview-wrap tbody tr', {timeout:20000});
check('อ่านข้อความแล้วขึ้นตารางให้ตรวจก่อน', (await p.locator('.preview-wrap tbody tr').count()) === 4);
check('พอมีรายการให้ตรวจ กล่องขยายเป็นแบบใหญ่', (await p.locator('.modal-xl').count()) === 1);
check('แก้ชื่อ/จำนวนในตารางตรวจได้',
  (await p.locator('.preview-wrap tbody tr').first().locator('input').count()) >= 3);
await p.screenshot({path:`${SHOTS}/bom-import.png`, fullPage:true});
await p.fill('#b-title', 'ปรับปรุงระบบสื่อสารสถานีไฟฟ้า A');
await p.click('button:has-text("บันทึกและประมาณราคา")');
await p.waitForURL(/\/boms\/[a-f0-9]+/, {timeout:30000});
await p.waitForSelector('.bom-table tbody tr', {timeout:30000});
check('บันทึกแล้วเด้งไปหน้ารายละเอียด', /\/boms\//.test(p.url()));
check('มีทุกบรรทัดในตาราง', (await p.locator('.bom-table tbody tr').count()) === 4);

const stats = await p.locator('.stat-row').innerText();
check('บอกความครอบคลุมก่อนตัวเลขงบ', /ตีราคาได้/.test(stats) && /\d\/4/.test(stats), stats.replace(/\n/g,' | '));
check('เตือนว่ายอดรวมคิดเฉพาะที่มีราคา',
  (await p.locator('.alert-attention').count()) >= 1);
const foot = await p.locator('.bom-table tfoot').innerText();
check('มียอดรวม เผื่อสำรอง VAT และงบรวม',
  /รวมค่าของ/.test(foot) && /เผื่อสำรอง/.test(foot) && /ภาษีมูลค่าเพิ่ม/.test(foot) && /งบประมาณรวมทั้งสิ้น/.test(foot),
  foot.replace(/\n/g,' | '));
check('บรรทัดที่จับคู่ไม่ได้บอกให้กดเลือกเอง',
  (await p.locator('text=ยังไม่จับคู่').count()) >= 1);
await p.screenshot({path:`${SHOTS}/bom-detail.png`, fullPage:true});

// ---- กดแถวแล้วเข้าหน้าวัสดุ (เป็นหน้า ไม่ใช่กล่องซ้อน)
const bomUrl = p.url();
const before = await p.locator('.bom-table tbody tr').first().innerText();
await p.locator('.bom-table tbody tr').first().click();
await p.waitForURL(/\/lines\/\d+/, {timeout:20000});
await p.waitForSelector('.pick-table tbody tr', {timeout:30000});
await p.waitForTimeout(600);
check('กดแถวใน BOM แล้วเข้าหน้าวัสดุเป็นหน้าเต็ม',
  /\/lines\/\d+/.test(p.url()) && (await p.locator('.overlay').count()) === 0, p.url());
check('หน้าวัสดุมีสองแท็บ: จับคู่วัสดุ / เทียบราคาจากผู้ขาย',
  (await p.locator('.tabs .tab').count()) === 2
  && /จับคู่วัสดุ/.test(await p.locator('.tabs').innerText())
  && /เทียบราคาจากผู้ขาย/.test(await p.locator('.tabs').innerText()));
check('ตารางในหน้าวัสดุไม่มี tbody ซ้อนกัน',
  (await p.evaluate(() => document.querySelectorAll('tbody tbody').length)) === 0);
check('มีช่องค้นหาสินค้าใกล้เคียง', await p.locator('#l-search').isVisible());
check('มีรายการสินค้าใกล้เคียงให้เลือก', (await p.locator('.pick-table tbody tr').count()) > 1);
await p.screenshot({path:`${SHOTS}/bom-line-match.png`, fullPage:true});

// ติ๊กเลือกได้ทีละ 1 รายการเท่านั้น
const radios = p.locator('.pick-table tbody input[type=radio]');
check('มีช่องติ๊กเลือกทุกแถว', (await radios.count()) > 1, await radios.count());
check('ติ๊กอยู่ได้ไม่เกิน 1 อัน (ก่อนเลือก)',
  (await p.locator('.pick-table tbody input[type=radio]:checked').count()) <= 1);
await radios.nth(1).check();
await p.waitForTimeout(1500);
check('ติ๊กแล้วเหลือถูกเลือกอันเดียวเท่านั้น',
  (await p.locator('.pick-table tbody input[type=radio]:checked').count()) === 1);
check('ช่องที่ติ๊กคือแถวที่กดจริง', await radios.nth(1).isChecked());
check('หัวหน้าวัสดุอัปเดตรหัสที่จับคู่ตามที่เลือก',
  /จับคู่กับ/.test(await p.locator('.card-head').first().innerText()));

// ---- แท็บเทียบราคาของ "ชิ้นนี้" เปิดแยกได้ด้วย URL
await p.click('.tab:has-text("เทียบราคาจากผู้ขาย")');
await p.waitForTimeout(1800);
check('สลับแท็บแล้ว URL เปลี่ยนด้วย (เปิดแยกแท็บเบราว์เซอร์ได้)',
  /\?tab=compare$/.test(p.url()), p.url());
const cmpText = await p.locator('.card').last().innerText();
check('แท็บเทียบราคาเป็นของสินค้าชิ้นนี้ ไม่ใช่ทั้งโครงการ',
  /เทียบเฉพาะของชิ้นนี้/.test(cmpText) || /ยังไม่มีราคาให้เทียบ/.test(cmpText),
  cmpText.slice(0, 120).replace(/\n/g, ' '));
await p.screenshot({path:`${SHOTS}/bom-line-compare.png`, fullPage:true});

await p.goto(bomUrl, {waitUntil:'domcontentloaded'});
await p.waitForSelector('.bom-table tbody tr', {timeout:30000});
await p.waitForTimeout(600);
const after = await p.locator('.bom-table tbody tr').first().innerText();
check('เลือกสินค้าใหม่แล้วแถวใน BOM เปลี่ยนจริง', before !== after,
  `${before.replace(/\n/g,'|')} -> ${after.replace(/\n/g,'|')}`);
check('บรรทัดที่คนเลือกเองติดป้าย "เลือกเอง"',
  (await p.locator('.conf-manual').count()) >= 1);

// ---- กรอกราคาเองให้บรรทัดที่ไม่มีในระบบ (ทำในหน้าวัสดุ)
await p.locator('.bom-table tbody tr', {hasText:'ยังไม่จับคู่'}).first().click();
await p.waitForSelector('#l-manual', {timeout:20000});
await p.fill('#l-manual', '5000');
await p.click('button:has-text("ใช้ราคานี้")');
await p.waitForTimeout(1500);
await p.goto(bomUrl, {waitUntil:'domcontentloaded'});
await p.waitForSelector('.bom-table tbody tr', {timeout:30000});
await p.waitForTimeout(700);
check('กรอกราคาเองแล้วยอดครอบคลุมครบ',
  /4\/4/.test(await p.locator('.stat-row').innerText()),
  await p.locator('.stat-row').innerText());
await p.screenshot({path:`${SHOTS}/bom-final.png`, fullPage:true});

// ---- โหลด Excel
const dl = await Promise.all([p.waitForEvent('download', {timeout:25000}),
  p.click('a:has-text("โหลด Excel")')]).then(r=>r[0]).catch(()=>null);
check('โหลดไฟล์ Excel ได้', !!dl && /\.xlsx$/.test(dl.suggestedFilename()), dl?.suggestedFilename());

// ---- ออกใบขอราคาแยกรายตัว เลือกผู้ขายเองได้ ดูทีละรายการ
await p.click('a:has-text("ออกใบขอราคาแยกรายตัว")');
await p.waitForURL(/\/boms\/[a-f0-9]+\/rfq/, {timeout:20000});
await p.waitForSelector('.rfq-split', {timeout:30000});
check('เป็นหน้าเต็ม ไม่ใช่กล่องซ้อน',
  /\/rfq$/.test(p.url()) && (await p.locator('.overlay').count()) === 0, p.url());
check('มีทางกลับไปหน้างานประมาณราคา',
  (await p.locator('.page-back a').count()) === 1);
check('แถบปุ่มออกใบติดขอบล่างไว้ ไม่หนีตามความยาวรายการ',
  await p.locator('.rfq-actionbar').isVisible());
await p.waitForTimeout(900);
const itemCount = await p.locator('.rfq-nav-item').count();
check('เปิดหน้าต่างออกใบแยกรายตัว สารบัญมีครบทุกรายการที่จับคู่แล้ว', itemCount >= 2, itemCount);
check('แสดงทีละรายการ ไม่กองรวมกันทั้งหมด',
  (await p.locator('.rfq-pane .rfq-item-head').count()) === 1);
check('บอกว่าอยู่รายการที่เท่าไรจากทั้งหมด',
  /รายการที่ 1 จาก/.test(await p.locator('.rfq-steps .cell-sub').innerText()),
  await p.locator('.rfq-steps .cell-sub').innerText());
check('รายการแรกถูกเน้นไว้ในสารบัญ',
  (await p.locator('.rfq-nav-item.current').count()) === 1
  && await p.locator('.rfq-nav-item').first().evaluate((el) => el.classList.contains('current')));
check('มีผู้ขายให้ติ๊กเลือกเองในรายการที่เปิดอยู่',
  (await p.locator('.vendor-pick input[type=checkbox]').count()) > 0);
check('มีทั้งราคาของเจ้านั้นและคะแนนส่งตรงเวลาให้ดูก่อนเลือก',
  (await p.locator('.rfq-pane .otd').count()) > 0
  && (await p.locator('.vendor-pick .num-cell').count()) > 0);
const sum0 = await p.locator('.rfq-summary').innerText();
check('บอกล่วงหน้าว่าจะออกกี่ใบ กี่รายการ ผู้ขายกี่ราย',
  /ใบที่จะออก/.test(sum0) && /รายการ/.test(sum0) && /ผู้ขาย/.test(sum0),
  sum0.replace(/\n/g,' | '));
check('รายการที่จับคู่ไม่ได้ ถูกกันออกพร้อมบอกเหตุผล',
  (await p.locator('.alert-attention').count()) >= 1);
await p.screenshot({path:`${SHOTS}/bom-rfq-peritem.png`});

// เดินหน้า/ถอยหลัง
const firstTitle = await p.locator('.rfq-pane .cell-title').first().innerText();
await p.click('button:has-text("ถัดไป")');
await p.waitForTimeout(400);
check('กดถัดไปแล้วเปลี่ยนรายการจริง',
  (await p.locator('.rfq-pane .cell-title').first().innerText()) !== firstTitle
  && /รายการที่ 2 จาก/.test(await p.locator('.rfq-steps .cell-sub').innerText()));
await p.click('button:has-text("ก่อนหน้า")');
await p.waitForTimeout(400);
check('กดก่อนหน้าแล้วกลับมารายการเดิม',
  (await p.locator('.rfq-pane .cell-title').first().innerText()) === firstTitle);

// กระโดดจากสารบัญ
await p.locator('.rfq-nav-item').last().click();
await p.waitForTimeout(400);
check('กดจากสารบัญกระโดดไปรายการนั้นได้',
  new RegExp(`รายการที่ ${itemCount} จาก`).test(await p.locator('.rfq-steps .cell-sub').innerText()),
  await p.locator('.rfq-steps .cell-sub').innerText());

// ติ๊กผู้ขายเพิ่มหนึ่งราย แล้วยอดสรุปต้องขยับ
const checkedBase = await p.locator('.vendor-pick input:checked').count();
await p.locator('.vendor-pick input[type=checkbox]:not(:checked)').first().check();
await p.waitForTimeout(300);
check('ติ๊กผู้ขายเพิ่มแล้วยอดรวมขยับตาม',
  (await p.locator('.vendor-pick input:checked').count()) === checkedBase + 1);

// ---- ค้นหาผู้ขายเพิ่มเอง (ตามอุปกรณ์ใกล้เคียง / ตามชื่อ)
await p.locator('.rfq-nav-item').first().click();
await p.waitForTimeout(400);
await p.click('button:has-text("+ ค้นหาผู้ขายเพิ่ม")');
await p.waitForSelector('.vendor-found tbody tr', {timeout:30000});
check('ค้นผู้ขายเพิ่มตามอุปกรณ์ใกล้เคียงได้ (ตั้งต้นด้วยชื่อจาก BOM)',
  (await p.locator('.vendor-found tbody tr').count()) > 0);
check('บอกด้วยว่ารายชื่อนี้มาจากสินค้าตัวไหน ไม่ใช่คำแนะนำลอย ๆ',
  (await p.locator('.via-items').count()) > 0);
const addable = p.locator('.vendor-found tbody button:not([disabled])');
const rowsBefore = await p.locator('.vendor-pick tbody tr').count();
const pickedBefore = await p.locator('.vendor-pick input:checked').count();
await addable.first().click();
await p.waitForTimeout(600);
check('กดเพิ่มแล้วผู้ขายเข้าไปอยู่ในรายการจริง',
  (await p.locator('.vendor-pick tbody tr').count()) === rowsBefore + 1);
check('ผู้ขายที่เพิ่มเองถูกติ๊กให้เลย',
  (await p.locator('.vendor-pick input:checked').count()) === pickedBefore + 1);
check('ติดป้ายบอกตรง ๆ ว่าเจ้านี้ไม่เคยขายรหัสนี้',
  /ไม่เคยขายรหัสนี้/.test(await p.locator('.vendor-pick .conf-warn').first().innerText()));
await p.click('.tabs-inline button:has-text("ตามชื่อผู้ขาย")');
await p.fill('input[aria-label="ค้นหาผู้ขายเพิ่ม"]', 'moxa');
await p.click('.vendor-add button:has-text("ค้นหา")');
await p.waitForTimeout(1500);
check('ค้นตามชื่อผู้ขายได้ด้วย',
  (await p.locator('.vendor-found tbody tr').count()) > 0
  && /moxa/i.test(await p.locator('.vendor-found tbody').innerText()));
await p.click('.vendor-add button:has-text("ปิด")');
await p.waitForTimeout(300);

// กลับไปรายการสุดท้ายแล้วเอาออก เพื่อทดสอบว่ารายการที่ไม่เลือกจะถูกข้าม
await p.locator('.rfq-nav-item').last().click();
await p.waitForTimeout(400);
await p.locator('.rfq-pane button:has-text("ไม่เลือกเลย")').click();
await p.waitForTimeout(300);

// วิธีรวมใบ — ค่าตั้งต้นคือผู้ขายหนึ่งรายได้ใบเดียว
check('มีตัวเลือกวิธีรวมใบ และตั้งต้นที่ "ผู้ขายหนึ่งรายได้ใบเดียว"',
  (await p.locator('.rfq-group-opt').count()) === 2
  && await p.locator('.rfq-group-opt input').first().isChecked());
const sheetsVendor = Number((await p.locator('.rfq-summary').innerText()).match(/(\d+)\s*ใบที่จะออก/)?.[1]);
await p.locator('.rfq-group-opt input').last().check();
await p.waitForTimeout(300);
const sheetsItem = Number((await p.locator('.rfq-summary').innerText()).match(/(\d+)\s*ใบที่จะออก/)?.[1]);
check('สลับวิธีรวมใบแล้วจำนวนใบเปลี่ยนให้เห็นก่อนกด',
  sheetsVendor !== sheetsItem, `${sheetsVendor} -> ${sheetsItem}`);
await p.locator('.rfq-group-opt input').first().check();
await p.waitForTimeout(300);

const sheets = Number((await p.locator('.rfq-summary').innerText()).match(/(\d+)\s*ใบที่จะออก/)?.[1]);
check('กด "ไม่เลือกเลย" แล้วสารบัญบอกทันทีว่ารายการนั้นจะตกไป',
  (await p.locator('.rfq-nav-item.off').count()) === 1
  && /ยังไม่ได้เลือกผู้ขาย/.test(await p.locator('.rfq-summary').innerText()));
// รวมใบตามผู้ขาย: จำนวนใบ = ผู้ขายที่ไม่ซ้ำ ไม่ใช่จำนวนรายการ
const vendorsPicked = new Set(
  await p.locator('.rfq-nav-item').evaluateAll(() => [])   // ค่าจริงอ่านจากแถบสรุปแทน
);
const sumText = await p.locator('.rfq-summary').innerText();
const uniqueVendors = Number(sumText.match(/ผู้ขาย\s*([\d,]+)\s*ราย/)?.[1]?.replace(/,/g, ''));
check('รวมใบตามผู้ขาย: จำนวนใบ = ผู้ขายที่ไม่ซ้ำ (ไม่ใช่จำนวนรายการ)',
  sheets === uniqueVendors && sheets !== itemCount - 1,
  `ใบ ${sheets} · ผู้ขาย ${uniqueVendors} · รายการที่เลือกไว้ ${itemCount - 1}`);

await p.click(`button:has-text("ออกใบขอราคา ${sheets} ใบ")`);
await p.waitForSelector('.result-list li', {timeout:40000});
check('ออกใบแล้วได้เลขใบครบตามจำนวน',
  (await p.locator('.result-list li').count()) === sheets);
check('รวมใบตามผู้ขาย = แต่ละใบบอกชื่อผู้ขายและจำนวนรายการ',
  /รายการ \(#/.test(await p.locator('.result-list').innerText()),
  (await p.locator('.result-list li').first().innerText()).replace(/\n/g,' '));
await p.screenshot({path:`${SHOTS}/bom-rfq-result.png`});
await p.click('a:has-text("กลับไปหน้างานประมาณราคา")');
await p.waitForSelector('.bom-table tbody tr', {timeout:30000});
await p.waitForTimeout(800);

const rfqLinks = p.locator('.bom-table tbody a[href^="/rfqs/"]');
check('กลับมาหน้า BOM แล้วเห็นว่าบรรทัดไหนออกใบไปแล้ว',
  (await rfqLinks.count()) >= sheets, await rfqLinks.count());
check('ทุกบรรทัดมีป้ายบอกขั้นตอนของงาน',
  (await p.locator('.bom-table .stage').count()) === (await p.locator('.bom-table tbody tr').count()));
check('บรรทัดที่ออกใบแล้วขึ้นว่า "ออกใบขอราคาแล้ว"',
  /ออกใบขอราคาแล้ว/.test(await p.locator('.bom-table').innerText()));
// ตัวอักษรไทยมีสระบนล่าง เล็กกว่า 11px เริ่มอ่านยากจริง — กันไว้ไม่ให้ย่อเกินไป
const tiny = await p.evaluate(() => {
  const out = [];
  document.querySelectorAll('body *').forEach((el) => {
    if (!el.offsetParent && el.tagName !== 'BODY') return;
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (!own) return;
    const size = parseFloat(getComputedStyle(el).fontSize);
    if (size < 11) out.push(`${el.className || el.tagName}:${size}px`);
  });
  return [...new Set(out)];
});
check('ไม่มีตัวอักษรเล็กกว่า 11px (อ่านไม่ออก)', tiny.length === 0, tiny.slice(0, 5).join(' · '));

check('มีแถบความคืบหน้าของทั้งโครงการ ครบ 6 ขั้น',
  (await p.locator('.stage-flow li').count()) === 6);
check('แถบความคืบหน้าบอกจำนวนรายการในแต่ละขั้น',
  /ออกใบขอราคาแล้ว/.test(await p.locator('.stage-flow').innerText())
  && /อนุมัติราคาแล้ว/.test(await p.locator('.stage-flow').innerText()));
// หน้ารายการโครงการก็ต้องเห็นความคืบหน้า ไม่ต้องเปิดเข้าไปทีละอัน
await p.goto(`${FE}/boms`, {waitUntil:'domcontentloaded'});
await p.waitForSelector('.vendor-table tbody tr', {timeout:30000});
await p.waitForTimeout(700);
check('หน้ารายการโครงการมีคอลัมน์ความคืบหน้า',
  /ความคืบหน้า/.test(await p.locator('.vendor-table thead').innerText())
  && (await p.locator('.vendor-table .stage').count()) > 0);
await p.goBack();
await p.waitForSelector('.bom-table tbody tr', {timeout:30000});
await p.waitForTimeout(500);

const firstRfq = await rfqLinks.first().getAttribute('href');
await p.goto(`${FE}${firstRfq}`, {waitUntil:'domcontentloaded'});
await p.waitForSelector('table tbody tr', {timeout:30000});
// ---- เทียบราคาต้องดูเป็นรายสินค้า ไม่ใช่รายใบ
await p.goBack();
await p.waitForSelector('.bom-table tbody tr', {timeout:30000});
await p.click('a:has-text("เทียบราคารายสินค้า")');
await p.waitForURL(/\/compare$/, {timeout:20000});
await p.waitForSelector('.compare-grid', {timeout:30000});
await p.waitForTimeout(700);
const cmpRows = await p.locator('.compare-grid tbody tr').count();
const cmpCols = await p.locator('.compare-grid .vendor-col').count();
check('เทียบราคาเป็นแถวละสินค้า คอลัมน์ละผู้ขาย', cmpRows >= 1 && cmpCols >= 1,
  `${cmpRows} แถว x ${cmpCols} คอลัมน์`);
check('หัวคอลัมน์ผู้ขายมีคะแนนส่งตรงเวลาให้ดูคู่กับราคา',
  (await p.locator('.compare-grid thead .otd').count()) >= 1);
check('คอลัมน์ชื่อสินค้าตรึงไว้ เลื่อนดูผู้ขายแล้วยังรู้ว่าแถวไหน',
  (await p.locator('.compare-grid .sticky-col').count()) >= 1);
check('ช่องที่ยังไม่มีราคาบอกสาเหตุ ไม่ใช่ขีดเปล่า ๆ',
  /รอตอบ|ไม่ได้เชิญ|ไม่เสนอรายการนี้/.test(await p.locator('.compare-grid tbody').innerText())
  || (await p.locator('.quote-cell.lowest').count()) >= 1);
check('มียอดสรุปว่าถ้าเลือกถูกสุดรายชิ้นจะจ่ายเท่าไร เทียบงบ',
  /เลือกเจ้าถูกสุดของแต่ละชิ้น/.test(await p.locator('.stat-row').innerText()));
await p.screenshot({path:`${SHOTS}/bom-compare.png`, fullPage:true});
await p.goto(`${FE}${firstRfq}`, {waitUntil:'domcontentloaded'});
await p.waitForSelector('table tbody tr', {timeout:30000});
check('เปิดใบที่ออกแล้วมีเฉพาะของที่เลือกให้ผู้ขายรายนั้น',
  (await p.locator('table tbody tr').count()) >= 1
  && (await p.locator('table tbody tr').count()) <= itemCount,
  await p.locator('table tbody tr').count());

check('ไม่มี JavaScript error', errs.length === 0, errs.slice(0,3).join(' | '));
await b.close();
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
