'use client';

/**
 * เงินกระจุกตัวที่กี่รายแรก — เส้นสะสมของมูลค่าซื้อ
 *
 * ทำไมเป็นเส้นสะสม ไม่ใช่ตารางอันดับ: คำถามคือ "ต้องดูแลกี่รหัสจึงคุมงบได้"
 * ตารางอันดับตอบได้แต่ว่าใครมากสุด ไม่ได้บอกว่าเส้นชันแค่ไหน ซึ่งเป็นคำตอบจริง
 *
 * ทำไมแกนนอนเป็น % ของจำนวนทั้งหมด ไม่ใช่จำนวนราย: เพื่อวางเส้นสินค้ากับเส้นผู้ขาย
 * ทับกันบนแกนเดียวได้ (8,619 รหัส เทียบ 1,129 ราย ถ้าใช้จำนวนจริงจะเทียบกันไม่ได้)
 * จำนวนรายจริงยังอ่านได้จากป้ายจุดตัดและจากการแตะบนเส้น
 */
import { useMemo, useState } from 'react';
import { num } from '@/lib/format';
import useChartWidth, { NARROW } from './useChartWidth';

const SERIES = [
  { key: 'items', label: 'สินค้า', color: 'var(--v2-1)', unit: 'รหัส' },
  { key: 'vendors', label: 'ผู้ขาย', color: 'var(--v2-2)', unit: 'ราย' },
];

export default function ParetoChart({ data }) {
  const [ref, width] = useChartWidth();
  const [hover, setHover] = useState(null);
  const narrow = width < NARROW;

  const series = useMemo(
    () =>
      SERIES.map((s) => ({ ...s, ...(data?.[s.key] || {}) })).filter(
        (s) => (s.points || []).length > 1,
      ),
    [data],
  );

  if (!series.length) return null;

  const H = narrow ? 260 : 300;
  const PAD = { top: 18, right: narrow ? 14 : 20, bottom: narrow ? 46 : 44, left: narrow ? 40 : 46 };
  const W = Math.max(280, width);
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  // แกนนอน 0-100% ของจำนวนทั้งหมด · แกนตั้ง 0-100% ของมูลค่าสะสม
  const px = (sharePct) => PAD.left + (sharePct / 100) * plotW;
  const py = (pct) => PAD.top + plotH - (pct / 100) * plotH;

  const yTicks = narrow ? [0, 50, 100] : [0, 25, 50, 75, 100];
  const xTicks = narrow ? [0, 50, 100] : [0, 25, 50, 75, 100];

  return (
    <div className="viz2" ref={ref}>
      <svg
        className="viz2-svg"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={
          'กราฟเส้นสะสมแสดงการกระจุกตัวของมูลค่าซื้อ — ' +
          series
            .map(
              (s) =>
                `${s.label} ${num(s.thresholds?.p50?.n)} ${s.unit} แรก คิดเป็นครึ่งหนึ่งของมูลค่า`,
            )
            .join(' และ ')
        }
        onMouseLeave={() => setHover(null)}
      >
        {yTicks.map((t) => (
          <g key={`y${t}`}>
            <line className="viz2-grid" x1={PAD.left} x2={PAD.left + plotW} y1={py(t)} y2={py(t)} />
            <text className="viz2-ax" x={PAD.left - 7} y={py(t) + 4} textAnchor="end">
              {t}%
            </text>
          </g>
        ))}

        {/* เส้นอ้างอิงครึ่งงบ — จุดที่ใช้ตัดสินใจจริง */}
        <line
          x1={PAD.left}
          x2={PAD.left + plotW}
          y1={py(50)}
          y2={py(50)}
          stroke="var(--v2-muted)"
          strokeWidth="1.5"
          strokeDasharray="5 4"
        />

        {series.map((s) => {
          const d = s.points
            .map((p, i) => `${i ? 'L' : 'M'} ${px((p.n / s.count) * 100)} ${py(p.pct)}`)
            .join(' ');
          return <path key={s.key} className="viz2-line" d={d} stroke={s.color} />;
        })}

        {/* จุดตัด 50% ของแต่ละเส้น + ป้ายบอกจำนวนรายจริง */}
        {series.map((s, i) => {
          const th = s.thresholds?.p50;
          if (!th) return null;
          const cx = px((th.n / s.count) * 100);
          const label = `${num(th.n)} ${s.unit}`;
          // ป้ายของเส้นที่สองวางต่ำลงกันทับ เพราะจุดตัดทั้งสองอยู่ชิดซ้ายใกล้กัน
          const ty = py(50) - (i === 0 ? 10 : narrow ? 26 : 28);
          return (
            <g key={`th${s.key}`}>
              <line
                x1={cx}
                x2={cx}
                y1={py(50)}
                y2={py(0)}
                stroke={s.color}
                strokeWidth="1.5"
                strokeDasharray="4 3"
              />
              <circle className="viz2-dot" cx={cx} cy={py(50)} r="5" fill={s.color} />
              <text className="viz2-val" x={cx + 8} y={ty}>
                {label}
              </text>
            </g>
          );
        })}

        <line
          className="viz2-base"
          x1={PAD.left}
          x2={PAD.left + plotW}
          y1={py(0)}
          y2={py(0)}
        />
        {xTicks.map((t) => (
          <text
            key={`x${t}`}
            className="viz2-ax"
            x={px(t)}
            y={H - PAD.bottom + 17}
            textAnchor={t === 0 ? 'start' : t === 100 ? 'end' : 'middle'}
          >
            {t}%
          </text>
        ))}
        <text className="viz2-axlab" x={PAD.left} y={H - 6}>
          % ของจำนวนทั้งหมด (เรียงจากใช้เงินมากสุด)
        </text>

        {/* พื้นที่รับการแตะ/ชี้ — แบ่งเป็นแถบตั้งเต็มความสูง
            จำนวนแถบคิดจากความกว้างจริง ไม่ใช่ตัวเลขคงที่ เพื่อให้แต่ละแถบกว้างพอนิ้วแตะ
            (เกณฑ์ 44px ของ Apple) — บนจอแคบจึงได้แถบน้อยแต่ใหญ่ ไม่ใช่แถบเยอะแต่แตะไม่โดน */}
        {Array.from({
          length: Math.max(4, Math.min(24, Math.floor(plotW / (narrow ? 46 : 34)))),
        }).map((_, i, arr) => {
          const w = plotW / arr.length;
          const sharePct = ((i + 0.5) / arr.length) * 100;
          const readings = series.map((s) => {
            const idx = Math.round((sharePct / 100) * s.count);
            const p =
              s.points.find((q) => q.n >= idx) || s.points[s.points.length - 1];
            return { s, n: p.n, pct: p.pct };
          });
          return (
            <rect
              key={`hit${i}`}
              className="viz2-hit"
              x={PAD.left + i * w}
              y={PAD.top}
              width={w}
              height={plotH}
              tabIndex={0}
              role="button"
              aria-label={readings
                .map((r) => `${r.s.label} ${num(r.n)} ${r.s.unit} คิดเป็น ${r.pct}%`)
                .join(', ')}
              onMouseEnter={() => setHover(readings)}
              onFocus={() => setHover(readings)}
              onBlur={() => setHover(null)}
            />
          );
        })}
      </svg>

      <div className="viz2-legend">
        {series.map((s) => (
          <span key={s.key} className="viz2-legend-item">
            <span className="viz2-sw" style={{ background: s.color }} />
            {s.label} ({num(s.count)} {s.unit})
          </span>
        ))}
        <span className="viz2-legend-item" style={{ color: 'var(--v2-muted)' }}>
          — — เส้นครึ่งงบ (50%)
        </span>
      </div>

      <div className="viz2-tip" aria-live="polite">
        {hover
          ? hover
              .map((r) => `${r.s.label} ${num(r.n)} ${r.s.unit} แรก = ${r.pct}% ของมูลค่า`)
              .join('  ·  ')
          : 'ชี้หรือแตะบนกราฟเพื่อดูตัวเลขแต่ละช่วง'}
      </div>

      <details className="viz2-table">
        <summary>ดูเป็นตาราง</summary>
        <table>
          <thead>
            <tr>
              <th>สัดส่วนมูลค่า</th>
              {series.map((s) => (
                <th key={s.key} className="n">
                  {s.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {['p50', 'p80', 'p90'].map((k) => (
              <tr key={k}>
                <td>{k.slice(1)}%</td>
                {series.map((s) => {
                  const th = s.thresholds?.[k];
                  return (
                    <td key={s.key} className="n">
                      {th ? `${num(th.n)} ${s.unit} (${th.share_of_catalog}%)` : '—'}
                    </td>
                  );
                })}
              </tr>
            ))}
            <tr>
              <td>ทั้งหมด</td>
              {series.map((s) => (
                <td key={s.key} className="n">
                  {num(s.count)} {s.unit}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </details>
    </div>
  );
}
