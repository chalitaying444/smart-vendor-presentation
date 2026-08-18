'use client';

/**
 * ราคาที่ซื้อจริงย้อนหลัง — จุดละ 1 บรรทัดใบสั่งซื้อ เส้นเชื่อมตามผู้ขายแต่ละราย
 *
 * ทำไมเป็นกราฟเส้น+จุด: คำถามคือ "ราคาขยับไปทางไหนตามเวลา และใครขายถูกกว่า"
 * ซึ่งเป็นเรื่องแนวโน้มตามเวลา + การเทียบตัวตน จึงใช้แกนเวลาเดียว ไม่มีแกนที่สอง
 *
 * ธีมเป็นขาว-ดำ ชุดเส้นจึงเป็นการไล่ระดับเทา และแยกกันด้วย "ลายเส้น" อีกชั้นหนึ่ง
 * (ทึบ / ประยาว / ประสั้น) เพราะระดับความเข้มอย่างเดียวแยกยากเมื่อเส้นทับกัน
 * เกินสามรายจะยุบเป็น "อื่น ๆ" แทนการวนซ้ำ ซึ่งจะทำให้แยกไม่ออก
 */
import { useMemo, useState } from 'react';
import { money, shortDate } from '@/lib/format';

const W = 900;
const H = 300;
const PAD = { top: 16, right: 20, bottom: 34, left: 74 };
const MAX_SERIES = 3;

export default function PriceHistoryChart({ points, uom }) {
  const [hover, setHover] = useState(null);

  const model = useMemo(() => build(points), [points]);
  if (!model) return null;

  const { series, xMin, xSpan, yMin, ySpan, yTicks, xTicks } = model;
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const px = (t) => PAD.left + (xSpan ? ((t - xMin) / xSpan) * plotW : plotW / 2);
  const py = (v) => PAD.top + plotH - (ySpan ? ((v - yMin) / ySpan) * plotH : plotH / 2);

  return (
    <div className="viz-root">
      <svg
        className="viz-svg"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="กราฟราคาที่ซื้อจริงย้อนหลัง แยกตามผู้ขาย"
        onMouseLeave={() => setHover(null)}
      >
        {/* เส้นตารางแนวนอน — จางไว้ ไม่ให้แย่งสายตาจากข้อมูล */}
        {yTicks.map((v) => (
          <g key={v}>
            <line className="viz-grid" x1={PAD.left} x2={W - PAD.right} y1={py(v)} y2={py(v)} />
            <text className="viz-axis" x={PAD.left - 10} y={py(v)} textAnchor="end" dominantBaseline="middle">
              {money(v, 0)}
            </text>
          </g>
        ))}

        {xTicks.map((t) => (
          <text key={t} className="viz-axis" x={px(t)} y={H - 12} textAnchor="middle">
            {new Date(t).getFullYear() + 543}
          </text>
        ))}

        {series.map((s, si) => (
          <g key={s.key}>
            {/* กลุ่ม "อื่น ๆ" เป็นผู้ขายหลายรายรวมกัน — ลากเส้นเชื่อมจะสื่อผิดว่าเป็นแนวโน้มของรายเดียว */}
            {s.rows.length > 1 && s.key !== '__other__' && (
              <path
                className="viz-line"
                data-si={si + 1}
                style={{ stroke: `var(--series-${si + 1})` }}
                d={s.rows.map((r, i) => `${i ? 'L' : 'M'}${px(r.t)},${py(r.unit_cost)}`).join(' ')}
              />
            )}
            {s.rows.map((r) => (
              <circle
                key={r.key}
                className="viz-dot"
                style={{ fill: `var(--series-${si + 1})` }}
                cx={px(r.t)}
                cy={py(r.unit_cost)}
                r={hover?.key === r.key ? 7 : 5}
                onMouseEnter={() => setHover({ ...r, color: si + 1 })}
              />
            ))}
          </g>
        ))}

        {hover && (
          <line
            className="viz-crosshair"
            x1={px(hover.t)} x2={px(hover.t)} y1={PAD.top} y2={PAD.top + plotH}
          />
        )}
      </svg>

      {/* legend มีเสมอเมื่อมีตั้งแต่ 2 series — ตัวตนไม่ได้อาศัยสีอย่างเดียว */}
      <div className="viz-legend">
        {series.map((s, si) => (
          <span key={s.key} className="viz-legend-item">
            <span className="viz-swatch" style={{ background: `var(--series-${si + 1})` }} />
            {s.name} <span className="muted">({s.rows.length})</span>
          </span>
        ))}
      </div>

      {hover && (
        <div className="viz-tip">
          <strong>{money(hover.unit_cost)}</strong> บาท{uom ? ` / ${uom}` : ''}
          {' · '}{shortDate(hover.date)}
          {' · '}{hover.vendor_name}
          {hover.po_num ? ` · PO ${hover.po_num}` : ''}
          {hover.qty ? ` · ${hover.qty} ${uom || ''}` : ''}
        </div>
      )}
    </div>
  );
}

function build(points) {
  const rows = (points || [])
    .map((p, i) => ({ ...p, t: new Date(p.date).getTime(), key: `${p.po_num}-${i}` }))
    .filter((p) => Number.isFinite(p.t) && p.unit_cost != null);
  if (rows.length < 2) return null;

  // จัดกลุ่มตามผู้ขาย แล้วเก็บสามรายที่ซื้อบ่อยสุด ที่เหลือยุบเป็น "อื่น ๆ"
  const byVendor = new Map();
  rows.forEach((r) => {
    const k = r.vendor_id || r.vendor_name || '?';
    if (!byVendor.has(k)) byVendor.set(k, { key: k, name: r.vendor_name || k, rows: [] });
    byVendor.get(k).rows.push(r);
  });

  const ranked = [...byVendor.values()].sort((a, b) => b.rows.length - a.rows.length);
  const series = ranked.slice(0, MAX_SERIES);
  const rest = ranked.slice(MAX_SERIES);
  if (rest.length) {
    series.push({
      key: '__other__',
      name: `อื่น ๆ (${rest.length} ราย)`,
      rows: rest.flatMap((s) => s.rows).sort((a, b) => a.t - b.t),
    });
  }
  series.forEach((s) => s.rows.sort((a, b) => a.t - b.t));

  const ts = rows.map((r) => r.t);
  const vs = rows.map((r) => r.unit_cost);
  const xMin = Math.min(...ts);
  const xMax = Math.max(...ts);
  const rawMin = Math.min(...vs);
  const rawMax = Math.max(...vs);
  const pad = (rawMax - rawMin) * 0.12 || rawMax * 0.1 || 1;
  const yMin = Math.max(0, rawMin - pad);
  const yMax = rawMax + pad;

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(yMin + (yMax - yMin) * f));
  const years = [];
  for (let y = new Date(xMin).getFullYear(); y <= new Date(xMax).getFullYear(); y += 1) {
    const t = new Date(y, 0, 1).getTime();
    if (t >= xMin && t <= xMax) years.push(t);
  }

  return {
    series,
    xMin, xSpan: xMax - xMin,
    yMin, ySpan: yMax - yMin,
    yTicks: [...new Set(yTicks)],
    xTicks: years.length ? years : [xMin, xMax],
  };
}
