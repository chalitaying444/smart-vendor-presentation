'use client';

/**
 * ป้ายบอกความตรงเวลาของผู้ขาย
 *
 * ใช้ที่เดียวกันทุกหน้า เพื่อให้สีและคำอ่านหมายถึงสิ่งเดียวกันเสมอ
 *
 * ตั้งใจไม่โชว์แค่ % ลอย ๆ เพราะตัวเลขเดียวหลอกได้:
 *   - 100% จาก 2 งวด ไม่เท่ากับ 92% จาก 200 งวด → ติดป้าย "ข้อมูลน้อย"
 *   - ผู้ขายที่ดองงานไว้จะ OTD สวย เพราะงวดที่ยังไม่ส่งไม่ถูกนับ → โชว์งวดค้างส่งคู่กัน
 */
import { num } from '@/lib/format';

const TONE = {
  excellent: 'otd-excellent',
  good: 'otd-good',
  fair: 'otd-fair',
  poor: 'otd-poor',
  thin: 'otd-thin',
  unknown: 'otd-unknown',
};

export default function OtdBadge({ delivery, showDetail = true, compact = false }) {
  if (!delivery || !delivery.has_data) {
    return <span className="otd otd-unknown">ยังไม่มีประวัติส่งของ</span>;
  }

  const { otd_pct: pct, releases, level, label, reliable } = delivery;

  return (
    <span className="otd-wrap">
      <span className={`otd ${TONE[level] || 'otd-unknown'}`}>
        {pct != null ? `${num(pct, 1)}%` : '—'}
        {!compact && <span className="otd-label"> {label}</span>}
      </span>
      {showDetail && (
        <span className="otd-detail">
          {num(releases)} งวด
          {delivery.median_days_late != null && (
            <> · ปกติ{delivery.median_days_late > 0
              ? `ช้า ${num(delivery.median_days_late, 1)} วัน`
              : delivery.median_days_late < 0
                ? `เร็ว ${num(Math.abs(delivery.median_days_late), 1)} วัน`
                : 'ตรงวัน'}</>
          )}
          {delivery.overdue_releases > 0 && (
            <> · <span className="otd-overdue">ค้างส่ง {num(delivery.overdue_releases)} งวด</span></>
          )}
          {!reliable && releases > 0 && <> · ข้อมูลยังน้อย</>}
        </span>
      )}
    </span>
  );
}

/** แถบสรุปความตรงเวลาแบบการ์ด ใช้ในหน้ารายละเอียดผู้ขาย */
export function OtdSummary({ delivery }) {
  if (!delivery?.has_data) {
    return (
      <div className="stat-card">
        <div className="stat-label">ความตรงเวลาในการส่ง</div>
        <div className="stat-value">—</div>
        <div className="stat-note">ยังไม่มีงวดส่งของที่วัดผลได้</div>
      </div>
    );
  }
  return (
    <div className={`stat-card otd-card ${TONE[delivery.level] || ''}`}>
      <div className="stat-label">ส่งตรงเวลา</div>
      <div className="stat-value">
        {num(delivery.otd_pct, 1)}<span className="unit">%</span>
      </div>
      <div className="stat-note">
        {delivery.label} · {num(delivery.on_time)}/{num(delivery.releases)} งวด
        {delivery.median_days_late != null && (
          <><br />มัธยฐาน {num(delivery.median_days_late, 1)} วัน
            {delivery.avg_days_late != null && ` · เฉลี่ย ${num(delivery.avg_days_late, 1)} วัน`}</>
        )}
        {delivery.overdue_releases > 0 && (
          <><br /><span className="otd-overdue">ยังค้างส่ง {num(delivery.overdue_releases)} งวด</span></>
        )}
      </div>
    </div>
  );
}
