'use client';

/**
 * โครงหน้าระหว่างรอข้อมูล
 *
 * แนวคิด: วาดโครงที่รู้อยู่แล้วให้เห็นทันที (หัวตาราง ช่องค้นหา หัวการ์ด)
 * แล้วเติมเฉพาะส่วนที่ต้องรอ — ผู้ใช้เห็นว่าอะไรกำลังจะมาและอยู่ตรงไหน
 * ต่างจากข้อความ "กำลังโหลด…" ที่หน้าจอกระโดดทั้งหน้าเมื่อข้อมูลมาถึง
 *
 * จำนวนแถว/คอลัมน์ของโครงต้องตรงกับตารางจริง ไม่งั้นเนื้อหาจะเลื่อนตอนสลับ
 */

/** ชิ้นส่วนเล็กที่สุด — ใช้ประกอบทุกโครงหน้าด้านล่างในไฟล์นี้ */
function SkeletonText({ width = '100%' }) {
  return <span className="sk sk-text" style={{ width }} aria-hidden="true" />;
}

/** แถวตารางเปล่า — ใส่ความกว้างต่างกันเล็กน้อยให้ดูเป็นข้อความจริง */
export function SkeletonRows({ rows = 8, cols = 5, widths }) {
  const w = widths || Array.from({ length: cols }, (_, i) => (i === 0 ? '70%' : '45%'));
  return (
    <tbody aria-hidden="true">
      {Array.from({ length: rows }, (_, r) => (
        <tr key={r} className="sk-row">
          {Array.from({ length: cols }, (_, c) => (
            <td key={c}>
              <SkeletonText width={w[c] || '50%'} />
              {c === 0 && <SkeletonText width="38%" />}
            </td>
          ))}
        </tr>
      ))}
    </tbody>
  );
}

/** การ์ดตัวเลขสรุปเปล่า — ใช้คู่กับ .stat-row เพื่อจองพื้นที่ไว้ */
export function SkeletonStats({ count = 4 }) {
  return (
    <div className="stat-row" aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="stat-card">
          <SkeletonText width="52%" />
          <SkeletonText width="70%" />
          <SkeletonText width="86%" />
        </div>
      ))}
    </div>
  );
}

/** บล็อกเนื้อหาเปล่าทั่วไป (เช่น รายละเอียดบริษัท) */
export function SkeletonBlock({ lines = 4 }) {
  return (
    <div className="card-body" aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => (
        <SkeletonText key={i} width={`${90 - i * 12}%`} />
      ))}
    </div>
  );
}

/** ข้อความบอกสถานะสำหรับ screen reader — ภาพเป็นโครง แต่เสียงต้องบอกว่ากำลังโหลด */
export function LoadingAnnounce({ label = 'กำลังโหลดข้อมูล' }) {
  return <span className="sr-only" role="status" aria-live="polite">{label}</span>;
}
