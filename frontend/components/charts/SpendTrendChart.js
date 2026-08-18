'use client';

/**
 * มูลค่าซื้อรายปี — แนวโน้มตามเวลาที่หน้าอื่นในระบบยังไม่มี
 *
 * ทำไมเป็นแท่ง ไม่ใช่เส้น: แต่ละปีเป็นก้อนที่จบในตัว (งบของปีนั้น) ไม่ใช่ค่าที่
 * ไหลต่อเนื่องระหว่างจุด · แท่งสื่อ "ขนาดของแต่ละปี" ตรงกว่า
 *
 * ทำไมไม่เอาจำนวนผู้ขายมาใส่เป็นแกนที่สอง: กราฟสองแกนอ่านผิดง่ายที่สุด
 * จำนวนผู้ขายจึงอยู่ในคำอธิบายตอนแตะแท่งแทน ไม่ใช่เส้นซ้อนบนแท่ง
 *
 * ปีที่ยังไม่จบถูกวาดต่างจากปีที่จบแล้ว — ถ้าวาดเหมือนกันจะดูเหมือนยอดตกฮวบ
 * ทั้งที่แค่ยังนับไม่ครบปี ซึ่งเป็นการเข้าใจผิดที่ราคาแพง
 */
import { useMemo, useState } from 'react';
import { num, shortMoney } from '@/lib/format';
import useChartWidth, { NARROW } from './useChartWidth';

/** ปีที่มีบรรทัดใบสั่งซื้อน้อยกว่านี้คือช่วงตั้งระบบ ไม่ใช่ปีที่ดำเนินงานจริง */
const MIN_LINES = 100;

export default function SpendTrendChart({ data }) {
  const [ref, width] = useChartWidth();
  const [hover, setHover] = useState(null);
  const narrow = width < NARROW;

  const { years, skipped } = useMemo(() => {
    const all = data?.years || [];
    const keep = all.filter((y) => (y.lines || 0) >= MIN_LINES);
    return { years: keep, skipped: all.length - keep.length };
  }, [data]);

  if (years.length < 2) return null;

  const H = narrow ? 240 : 280;
  const PAD = { top: 24, right: 12, bottom: narrow ? 42 : 44, left: narrow ? 44 : 56 };
  const MIN_BAND_W = 52;
  // ความกว้างที่ใช้วาด = กว้างกว่ากรอบได้ ถ้าจำนวนปีเยอะจนแท่งจะแคบเกินนิ้ว
  const W = Math.max(280, width, PAD.left + PAD.right + years.length * MIN_BAND_W);
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  const max = Math.max(...years.map((y) => y.amount || 0));
  const py = (v) => PAD.top + plotH - (max ? (v / max) * plotH : 0);
  const band = plotW / years.length;
  // ช่องว่าง 2px ระหว่างแท่ง เพื่อให้ขอบแท่งอ่านเป็นเส้นแยก ไม่ใช่ก้อนติดกัน
  const barW = Math.max(10, Math.min(narrow ? 26 : 56, band - (narrow ? 8 : 22)));

  const millions = (v) => v / 1e6;
  const yTicks = [0, 0.5, 1].map((f) => f * max);

  // แต่ละแท่งต้องกว้างพอนิ้วแตะ — ถ้าที่ไม่พอ ให้กราฟกว้างเกินกรอบแล้วเลื่อนดูได้
  // ดีกว่าบีบให้พอดีจอจนแตะไม่โดนและตัวเลขปีทับกัน
  const scrolls = W > width;

  return (
    <div className="viz2" ref={ref}>
      <div className={scrolls ? 'viz2-scroll' : undefined}>
      <svg
        className="viz2-svg"
        style={scrolls ? { minWidth: W } : undefined}
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`กราฟแท่งมูลค่าซื้อรายปี ตั้งแต่ ${years[0].year} ถึง ${years[years.length - 1].year} สูงสุดปี ${
          years.reduce((a, b) => (b.amount > a.amount ? b : a)).year
        }`}
        onMouseLeave={() => setHover(null)}
      >
        {yTicks.map((t, i) => (
          <g key={`y${i}`}>
            <line className="viz2-grid" x1={PAD.left} x2={PAD.left + plotW} y1={py(t)} y2={py(t)} />
            <text className="viz2-ax" x={PAD.left - 7} y={py(t) + 4} textAnchor="end">
              {num(millions(t), 0)}
            </text>
          </g>
        ))}

        {years.map((y, i) => {
          const cx = PAD.left + i * band + band / 2;
          const x = cx - barW / 2;
          const top = py(y.amount || 0);
          const h = Math.max(2, py(0) - top);
          const r = Math.min(4, barW / 2);
          const active = hover?.year === y.year;
          return (
            <g key={y.year}>
              <path
                d={`M ${x} ${py(0)} L ${x} ${top + r} Q ${x} ${top} ${x + r} ${top} L ${
                  x + barW - r
                } ${top} Q ${x + barW} ${top} ${x + barW} ${top + r} L ${x + barW} ${py(0)} Z`}
                fill={y.partial ? 'var(--v2-4)' : 'var(--v2-1)'}
                fillOpacity={y.partial ? 0.55 : active ? 0.82 : 1}
              />
              {/* ป้ายค่าบนแท่ง — บนจอแคบแสดงเฉพาะแท่งที่กำลังแตะและแท่งสูงสุด กันตัวเลขทับกัน */}
              {(!narrow || active || y.amount === max) && (
                <text className="viz2-val" x={cx} y={top - 7} textAnchor="middle">
                  {num(millions(y.amount || 0), 0)}
                </text>
              )}
              <text
                className="viz2-ax"
                x={cx}
                y={H - PAD.bottom + 17}
                textAnchor="middle"
              >
                {narrow ? `'${String(y.year).slice(2)}` : y.year}
              </text>
              <rect
                className="viz2-hit"
                x={PAD.left + i * band}
                y={PAD.top}
                width={band}
                height={plotH}
                tabIndex={0}
                role="button"
                aria-label={`ปี ${y.year} มูลค่า ${shortMoney(y.amount)} บาท จาก ${num(
                  y.lines,
                )} บรรทัด ผู้ขาย ${num(y.vendors)} ราย${y.partial ? ' ยังไม่ครบปี' : ''}`}
                onMouseEnter={() => setHover(y)}
                onFocus={() => setHover(y)}
                onBlur={() => setHover(null)}
              />
            </g>
          );
        })}

        <line className="viz2-base" x1={PAD.left} x2={PAD.left + plotW} y1={py(0)} y2={py(0)} />
        {/* ไม่มีป้ายหน่วยลอยบนแกน — หัวการ์ดบอก "หน่วยล้านบาท" ไว้แล้ว
            และป้ายที่มุมซ้ายบนจะไปทับตัวเลขบนแท่งที่สูงสุดพอดี */}
      </svg>
      </div>

      <div className="viz2-legend">
        <span className="viz2-legend-item">
          <span className="viz2-sw" style={{ background: 'var(--v2-1)' }} />
          ปีที่จบแล้ว
        </span>
        {years.some((y) => y.partial) && (
          <span className="viz2-legend-item">
            <span className="viz2-sw" style={{ background: 'var(--v2-4)', opacity: 0.55 }} />
            ปีที่ยังไม่ครบ
          </span>
        )}
      </div>

      <div className="viz2-tip" aria-live="polite">
        {hover ? (
          <>
            <strong>ปี {hover.year}</strong>
            {hover.partial ? ' (ยังไม่ครบปี)' : ''} · {shortMoney(hover.amount)} บาท ·{' '}
            {num(hover.lines)} บรรทัด · ผู้ขาย {num(hover.vendors)} ราย · สินค้า{' '}
            {num(hover.parts)} รหัส
          </>
        ) : (
          'ชี้หรือแตะแท่งเพื่อดูจำนวนบรรทัด ผู้ขาย และรหัสสินค้าของปีนั้น'
        )}
      </div>

      {skipped > 0 && (
        <p className="viz2-note">
          ไม่แสดง {skipped} ปีแรกที่มีใบสั่งซื้อน้อยกว่า {MIN_LINES} บรรทัด — เป็นช่วงตั้งระบบ
          ไม่ใช่ปีที่ดำเนินงานจริง
        </p>
      )}

      <details className="viz2-table">
        <summary>ดูเป็นตาราง</summary>
        <table>
          <thead>
            <tr>
              <th>ปี</th>
              <th className="n">มูลค่า (ลบ.)</th>
              <th className="n">บรรทัด</th>
              <th className="n">ผู้ขาย</th>
              <th className="n">สินค้า</th>
            </tr>
          </thead>
          <tbody>
            {years.map((y) => (
              <tr key={y.year}>
                <td>
                  {y.year}
                  {y.partial ? ' *' : ''}
                </td>
                <td className="n">{num(millions(y.amount || 0), 1)}</td>
                <td className="n">{num(y.lines)}</td>
                <td className="n">{num(y.vendors)}</td>
                <td className="n">{num(y.parts)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
