import './globals.css';

export const metadata = {
  title: 'Vendor App',
  description: 'ระบบจัดการเวนเดอร์ — เข้าสู่ระบบด้วยบัญชี Microsoft',
};

/**
 * suppressHydrationWarning ที่ <html> และ <body>
 *
 * ส่วนขยายของเบราว์เซอร์ (QuillBot ใส่ data-qb-installed, Grammarly ใส่ data-gr-ext-installed,
 * ตัวแปลภาษาใส่ class) เขียน attribute ลงบนสองแท็กนี้ก่อนที่ React จะ hydrate
 * ฝั่งเซิร์ฟเวอร์ไม่มี attribute พวกนั้น React จึงฟ้อง hydration mismatch —
 * เป็น error ที่แอปไม่ได้ทำอะไรผิดเลย แต่หน้าจอ dev overlay ขึ้นทับทุกครั้งจนบัง error จริง
 *
 * ตัวนี้ปิดเสียงเฉพาะ "attribute ของสองแท็กนี้" เท่านั้น ไม่ได้ปิดทั้งต้นไม้ —
 * hydration mismatch ที่เกิดในหน้าจริงยังฟ้องตามปกติ
 */
export default function RootLayout({ children }) {
  return (
    <html lang="th" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
