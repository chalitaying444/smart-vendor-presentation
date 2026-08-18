/** @type {import('next').NextConfig} */

// ---------------------------------------------------------------------------
// Proxy ฝั่ง frontend
//
// เบราว์เซอร์ยิงไปที่ http://localhost:3000/api/... (same-origin)
// แล้ว Next.js forward ต่อไปยัง FastAPI ที่ BACKEND_URL
//
// ข้อดี: cookie `vendor_session` เป็น same-origin ไม่ต้องพึ่ง CORS
//        ขึ้น production เปลี่ยนแค่ BACKEND_URL ใน .env.local
//
// หมายเหตุ: ใช้ localhost (ไม่ใช่ 127.0.0.1) เพื่อให้ cookie ใช้ร่วมกับ backend ได้
// ---------------------------------------------------------------------------
const BACKEND_URL = (process.env.BACKEND_URL || 'http://localhost:8000').replace(/\/$/, '');

// ---------------------------------------------------------------------------
// เปิดให้เข้าผ่าน ngrok / โดเมนอื่นได้ตอน `next dev`
//
// โหมด dev ของ Next บล็อกคำขอที่มาจาก origin อื่นนอกจาก localhost ไว้ก่อน
// (กันคนอื่นในเครือข่ายยิงเข้ามาที่ dev server) พอเปิดผ่าน ngrok จึงโดนบล็อก
// ใส่โดเมนของ ngrok ไว้ให้ครบทุกแบบที่เขาแจก บวกกับที่ตั้งเองใน DEV_ORIGINS
//
// ตอน `next build` + `next start` (production) ไม่เกี่ยวกับค่านี้เลย
// ---------------------------------------------------------------------------
const EXTRA_ORIGINS = (process.env.DEV_ORIGINS || '')
  .split(',')
  .map((o) => o.trim().replace(/^https?:\/\//, '').replace(/\/$/, ''))
  .filter(Boolean);

const nextConfig = {
  reactStrictMode: true,

  allowedDevOrigins: [
    '*.ngrok-free.app', '*.ngrok-free.dev', '*.ngrok.app', '*.ngrok.io', '*.ngrok.dev',
    ...EXTRA_ORIGINS,
  ],

  async rewrites() {
    return [
      // REST API ทั้งหมด (รวม vendor_key ที่มี ':' เช่น /api/sourcing/vendors/partner%3A2beshop)
      { source: '/api/:path*', destination: `${BACKEND_URL}/api/:path*` },

      // ไม่มี proxy /files/* อีกแล้ว — ไฟล์ย้ายไปเก็บใน MongoDB
      // และโหลดผ่าน /api/files/<id> ที่ตรวจสิทธิ์ก่อน (backend ไม่ได้ mount /files ไว้แล้ว)
      // ลิงก์เก่าแบบ /files/quotes/... จะได้ 404 — ย้ายไฟล์เก่าด้วย
      // backend\scripts\migrate_uploads_to_mongo.py แล้วลิงก์จะถูกเขียนใหม่ให้เอง

      // เอกสาร API เปิดผ่าน frontend ได้เลย
      { source: '/docs', destination: `${BACKEND_URL}/docs` },
      { source: '/redoc', destination: `${BACKEND_URL}/redoc` },
      { source: '/openapi.json', destination: `${BACKEND_URL}/openapi.json` },
      { source: '/health', destination: `${BACKEND_URL}/health` },
    ];
  },
};

export default nextConfig;
