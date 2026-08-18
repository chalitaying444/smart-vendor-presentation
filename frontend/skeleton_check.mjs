/** ตรวจว่าโครงหน้าปรากฏก่อนข้อมูลจริง โดยหน่วง API เทียม */
import { chromium } from 'playwright';
import { FE, CHROMIUM, SHOTS, token } from './_env.mjs';

const TOK = token();
let pass = 0, fail = 0;
const check = (l, c, e = '') => { c ? (pass++, console.log('PASS', l)) : (fail++, console.log('FAIL', l, e)); };

const browser = await chromium.launch({ executablePath: CHROMIUM });
const ctx = await browser.newContext({ viewport: { width: 1500, height: 1000 } });
await ctx.addCookies([{ name: 'vendor_session', value: TOK, domain: 'localhost', path: '/' }]);

// หน่วงทุก API ที่ไม่ใช่ auth ไว้ 2.5 วินาที เพื่อจับภาพช่วง "กำลังรอ"
await ctx.route('**/api/**', async (route) => {
  if (route.request().url().includes('/api/auth/')) return route.continue();
  await new Promise((r) => setTimeout(r, 2500));
  return route.continue();
});

const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));

async function probe(path, label, expectHeaders) {
  await page.goto(FE + path);
  await page.waitForSelector('.sk', { timeout: 8000 });
  const skCount = await page.locator('.sk').count();
  check(`${label}: โครงหน้าปรากฏก่อนข้อมูล (${skCount} บล็อก)`, skCount > 3, skCount);

  for (const sel of expectHeaders) {
    check(`${label}: เห็น "${sel.label}" ตั้งแต่ยังโหลดไม่เสร็จ`,
      await page.locator(sel.locator).first().isVisible(), sel.locator);
  }
  await page.screenshot({ path: `${SHOTS}/sk-${label}.png`, fullPage: true });

  await page.waitForSelector('.sk', { state: 'detached', timeout: 15000 });
  check(`${label}: โครงหายไปเมื่อข้อมูลมาถึง`, await page.locator('.sk').count() === 0);
}

const H = (label, locator) => ({ label, locator });

await probe('/dashboard', 'dashboard', [
  H('สินค้าที่ซื้อมากที่สุด', 'h2:text-is("สินค้าที่ซื้อมากที่สุด")'),
  H('ผู้ขายรายใหญ่', 'h2:text-is("ผู้ขายรายใหญ่")'),
  H('หัวคอลัมน์ ราคาล่าสุด', 'th:text-is("ราคาล่าสุด")'),
]);
await probe('/products', 'products', [
  H('หัวคอลัมน์ ราคาล่าสุด', 'th:text-is("ราคาล่าสุด")'),
  H('หัวคอลัมน์ ยอดซื้อรวม', 'th:text-is("ยอดซื้อรวม")'),
  H('ช่องค้นหาพร้อมพิมพ์', 'input[type="search"]'),
  H('ตัวกรอง', '.filter-row'),
]);
await probe('/vendors', 'vendors', [
  H('หัวคอลัมน์ ยอดสั่งซื้อ', 'th:text-is("ยอดสั่งซื้อ")'),
  H('หัวคอลัมน์ เครดิต', 'th:text-is("เครดิต")'),
  H('ช่องค้นหาพร้อมพิมพ์', 'input[type="search"]'),
]);

// หน้ารายละเอียดสินค้า
await ctx.unroute('**/api/**');
await ctx.route('**/api/**', async (route) => {
  if (route.request().url().includes('/api/auth/')) return route.continue();
  await new Promise((r) => setTimeout(r, 2500));
  return route.continue();
});
const res = await fetch('http://127.0.0.1:8000/api/catalog/items?limit=1',
  { headers: { Authorization: `Bearer ${TOK}` } });
const part = (await res.json()).items[0].part_num;
await probe(`/products/${encodeURIComponent(part)}`, 'item', [
  H('หัวคอลัมน์ ผู้ขาย', 'th:text-is("ผู้ขาย")'),
  H('ปุ่มกลับ', 'a:has-text("กลับไปค้นหาสินค้า")'),
  H('หัวคอลัมน์ วันที่', 'th:text-is("วันที่")'),
]);

check('ไม่มี JavaScript error', errors.length === 0, errors.slice(0, 3));
await browser.close();
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
