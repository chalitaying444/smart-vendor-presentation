'use client';

/**
 * ความกว้างจริงของกล่องที่กราฟอยู่ — ใช้ปรับความละเอียดของกราฟตามขนาดหน้าจอ
 *
 * ทำไมต้องวัดเอง ไม่ใช้แค่ viewBox ย่อ-ขยาย: การย่อ SVG ทั้งใบทำให้ตัวอักษร
 * เล็กลงตามจนอ่านไม่ออกบนมือถือ และป้ายกำกับที่พอดีบนจอ 900px จะทับกันเองบนจอ 375px
 * วิธีที่ถูกคือคงขนาดตัวอักษรไว้ แล้ว "ลดจำนวนป้าย" ลงเมื่อที่แคบ
 *
 * คืนค่าเริ่มต้น 720 เพื่อให้การเรนเดอร์รอบแรกบนเซิร์ฟเวอร์ได้กราฟที่หน้าตาปกติ
 * ไม่ใช่กราฟกว้าง 0 แล้วกระโดดตอน hydrate
 */
import { useEffect, useRef, useState } from 'react';

export default function useChartWidth(fallback = 720) {
  const ref = useRef(null);
  const [width, setWidth] = useState(fallback);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    const measure = () => {
      const w = node.getBoundingClientRect().width;
      if (w > 0) setWidth(w);
    };
    measure();

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', measure);
      return () => window.removeEventListener('resize', measure);
    }
    const ro = new ResizeObserver(measure);
    ro.observe(node);
    return () => ro.disconnect();
  }, []);

  return [ref, width];
}

/** จอแคบกว่านี้ถือว่าเป็นมือถือ — ตรงกับจุดตัดที่ globals.css ใช้อยู่ */
export const NARROW = 560;
