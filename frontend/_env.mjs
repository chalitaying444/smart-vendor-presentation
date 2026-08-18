/**
 * ค่าที่ชุดทดสอบหน้าเว็บใช้ร่วมกัน — เปลี่ยนได้ด้วย environment variable
 *
 * ภาพหน้าจอถูกเก็บไว้ใน `frontend/_shots/` (อยู่ใน .gitignore) ไม่ใช่ path
 * ตายตัวของเครื่องใครเครื่องหนึ่ง — ไม่งั้นเทสต์จะรันได้เฉพาะบนเครื่องที่เขียนมัน
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));

export const FE = process.env.TEST_FRONTEND || 'http://localhost:3100';
export const API = process.env.TEST_API || 'http://127.0.0.1:8000/api';
export const CHROMIUM = process.env.TEST_CHROMIUM || '/opt/pw-browsers/chromium';
export const SHOTS = process.env.TEST_SHOTS || path.join(HERE, '_shots');

fs.mkdirSync(SHOTS, { recursive: true });

/** โทเคนของผู้ใช้ทดสอบ — จาก TEST_TOKEN ก่อน ไม่มีค่อยอ่านจากไฟล์ */
export function token() {
  if (process.env.TEST_TOKEN) return process.env.TEST_TOKEN.trim();
  const file = process.env.TEST_TOKEN_FILE || '/tmp/tok';
  if (!fs.existsSync(file)) {
    console.error(`ไม่พบโทเคนทดสอบที่ ${file}`);
    console.error(`ขอใหม่ด้วย: curl -s -X POST '${API}/auth/token?email=buyer@precise.co.th' > ${file}`);
    process.exit(1);
  }
  return fs.readFileSync(file, 'utf8').trim();
}
