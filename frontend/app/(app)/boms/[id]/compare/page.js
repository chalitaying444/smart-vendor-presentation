'use client';

/**
 * เทียบราคาทั้งโครงการ — มองเป็น "รายสินค้า" ไม่ใช่รายผู้ขาย
 *
 * ใบขอราคาออกเป็นใบต่อผู้ขาย (เขาจะได้ตอบครั้งเดียวจบ) แต่ตอนตัดสินใจ
 * คำถามคือ "ของชิ้นนี้ ใครให้ราคาดีที่สุด" ไม่ใช่ "ใบไหนถูกสุด" —
 * หน้านี้จึงรวมราคาจากทุกใบของโครงการกลับมาเรียงเป็นแถวละสินค้า คอลัมน์ละผู้ขาย
 *
 * ช่องว่างสามแบบถูกแยกให้ชัด: ไม่ได้เชิญ / เชิญแล้วยังไม่ตอบ / ตอบแล้วแต่ไม่เสนอรายการนี้
 * ถ้าแสดงเป็นขีดเหมือนกันหมด คนอ่านจะสรุปผิดว่า "เจ้านี้ไม่มีของ"
 */
import { use, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { usePageTitle } from '@/components/RequireAdmin';
import OtdBadge from '@/components/OtdBadge';
import { SkeletonBlock } from '@/components/Skeleton';
import { money, num, pctLabel } from '@/lib/format';

export default function BomComparePage({ params }) {
  const { id } = use(params);
  return <Compare bomId={id} />;
}

function Compare({ bomId }) {
  const [data, setData] = useState(null);
  const [bom, setBom] = useState(null);
  const [choice, setChoice] = useState({});     // line_no -> vendor_key
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState('');

  usePageTitle('เทียบราคารายสินค้า', bom ? `${bom.bom_no} · ${bom.title}` : '');

  const load = useCallback(async () => {
    try {
      const [cmp, doc] = await Promise.all([api.bomComparison(bomId), api.getBom(bomId)]);
      setData(cmp);
      setBom(doc);
    } catch (e) { setError(e.message); }
  }, [bomId]);

  useEffect(() => { load(); }, [load]);

  const pending = useMemo(
    () => Object.entries(choice).filter(([, key]) => key).length,
    [choice],
  );

  async function approve() {
    setBusy(true); setError(''); setDone('');
    try {
      const awards = Object.entries(choice)
        .filter(([, key]) => key)
        .map(([lineNo, key]) => ({ line_no: Number(lineNo), vendor_key: key }));
      const res = await api.bomAward(bomId, { awards, reason: 'เลือกจากหน้าเทียบราคารายสินค้า' });
      setDone(`อนุมัติราคาแล้ว ${num(awards.length)} รายการ (ใบขอราคา ${res.awarded.length} ใบ)`);
      setChoice({});
      await load();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  if (error && !data) return <div className="alert alert-error">{error}</div>;
  if (!data) return <div className="card"><SkeletonBlock lines={6} /></div>;

  const { vendors, rows, summary, currency } = data;

  if (!rows.length) {
    return (
      <>
        <div className="page-back"><Link href={`/boms/${bomId}`}>← กลับไปหน้างานประมาณราคา</Link></div>
        <div className="card"><div className="empty">
          <strong>ยังไม่มีอะไรให้เทียบ</strong>
          ต้องออกใบขอราคาก่อน แล้วรอให้ผู้ขายเสนอราคากลับมา
        </div></div>
      </>
    );
  }

  return (
    <>
      <div className="page-back">
        <Link href={`/boms/${bomId}`}>← กลับไปหน้างานประมาณราคา</Link>
      </div>

      {done && <div className="alert alert-ok">{done}</div>}
      {error && <div className="alert alert-error">{error}</div>}

      <div className="rfq-summary">
        <span>
          ได้ราคาแล้ว <strong>{num(summary.quoted_lines)}</strong>/{num(summary.line_count)} รายการ
        </span>
        <span>
          ผู้ขายตอบแล้ว <strong>{num(summary.quoted_vendors)}</strong>/{num(summary.invited_vendors)} ราย
        </span>
        {summary.waiting_lines > 0 && (
          <span className="tone-warn">
            ยังไม่มีราคา {num(summary.waiting_lines)} รายการ — ตัวเลขรวมยังไม่ครบโครงการ
          </span>
        )}
      </div>

      <div className="stat-row">
        <div className="stat-card">
          <div className="stat-label">งบที่ตั้งไว้ (เฉพาะรายการที่มีราคาแล้ว)</div>
          <div className="stat-value">{money(summary.estimate_total)}</div>
          <div className="stat-note">จากราคาซื้อล่าสุด</div>
        </div>
        <div className="stat-card stat-primary">
          <div className="stat-label">เลือกเจ้าถูกสุดของแต่ละชิ้น</div>
          <div className="stat-value">{money(summary.best_total)} {currency}</div>
          {summary.best_vs_estimate_pct != null && (
            <div className={`stat-note ${summary.best_vs_estimate_pct > 0 ? 'tone-warn' : 'tone-ok'}`}>
              {summary.best_vs_estimate_pct > 0 ? 'แพงกว่า' : 'ถูกกว่า'}งบ{' '}
              {Math.abs(summary.best_vs_estimate_pct)}%
            </div>
          )}
        </div>
        <div className="stat-card">
          <div className="stat-label">เลือกผู้ชนะไว้แล้ว</div>
          <div className="stat-value">{num(pending)}</div>
          <div className="stat-note">รายการที่ยังไม่กดอนุมัติ</div>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <div>
            <h2>ราคาที่เสนอมา — แถวละสินค้า</h2>
            <div className="cell-sub">
              ติ๊กเลือกผู้ชนะของแต่ละแถว แล้วกดอนุมัติทีเดียว ·
              ระบบจะไปประกาศผลในใบขอราคาที่ถูกต้องให้เอง
            </div>
          </div>
          <button className="btn btn-primary" disabled={busy || !pending} onClick={approve}>
            {busy ? 'กำลังอนุมัติ…' : `อนุมัติราคาที่เลือก ${num(pending)} รายการ`}
          </button>
        </div>

        <div className="table-wrap">
          <table className="quote-table compare-grid">
            <thead>
              <tr>
                <th className="sticky-col">สินค้า</th>
                <th className="num-head">จำนวน</th>
                <th className="num-head">งบที่ตั้งไว้</th>
                {vendors.map((v) => (
                  <th key={v.vendor_key} className="vendor-col">
                    <div className="cell-title">{v.vendor_name}</div>
                    <div className="cell-sub">
                      <OtdBadge delivery={v.delivery} compact showDetail={false} />
                      {v.has_quote
                        ? ` · เสนอ ${num(v.quoted_lines)} รายการ · รวม ${money(v.total)}`
                        : ' · ยังไม่ตอบ'}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const locked = Boolean(r.award);
                return (
                  <tr key={r.line_no}>
                    <td className="sticky-col">
                      <div className="cell-title">{r.name}</div>
                      <div className="cell-sub">
                        <code>{r.part_num}</code> {r.item_description}
                      </div>
                      {locked && (
                        <div className="cell-sub">
                          <span className="stage stage-ok">อนุมัติแล้ว</span>{' '}
                          {r.award.vendor_name}
                        </div>
                      )}
                    </td>
                    <td className="num-cell qty-cell">
                      {num(r.qty, 2)} <span className="uom">{r.uom}</span>
                    </td>
                    <td className="num-cell">
                      {r.estimate_unit_price == null
                        ? <span className="muted">—</span>
                        : money(r.estimate_unit_price)}
                    </td>
                    {r.cells.map((c) => (
                      <td key={c.vendor_key}
                          className={`num-cell quote-cell${c.is_lowest ? ' lowest' : ''}`}>
                        {c.unit_price == null ? (
                          <span className="muted">
                            {!c.invited ? 'ไม่ได้เชิญ' : c.no_quote ? 'ไม่เสนอรายการนี้' : 'รอตอบ'}
                          </span>
                        ) : (
                          <label className="quote-pick">
                            {!locked && (
                              <input type="radio" name={`win-${r.line_no}`}
                                     checked={choice[r.line_no] === c.vendor_key}
                                     aria-label={`เลือกผู้ชนะของ ${r.name}`}
                                     onChange={() => setChoice((s) => ({
                                       ...s, [r.line_no]: c.vendor_key,
                                     }))} />
                            )}
                            <span>
                              <strong>{money(c.unit_price)}</strong>
                              <span className="cell-sub">
                                {money(c.amount)}
                                {c.lead_time_days != null && ` · ส่ง ${num(c.lead_time_days)} วัน`}
                              </span>
                            </span>
                          </label>
                        )}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr>
                <td className="sticky-col cell-title">ถูกสุดรายชิ้นรวม</td>
                <td />
                <td className="num-cell">{money(summary.estimate_total)}</td>
                <td colSpan={vendors.length} className="num-cell">
                  <strong>{money(summary.best_total)} {currency}</strong>
                  {summary.best_vs_estimate_pct != null && (
                    <span className={summary.best_vs_estimate_pct > 0 ? ' tone-warn' : ' tone-ok'}>
                      {' '}({pctLabel(summary.best_vs_estimate_pct)} เทียบงบ)
                    </span>
                  )}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>

        <div className="card-body">
          <div className="hint" style={{ marginTop: 0 }}>
            ราคาต่ำสุดของแต่ละแถวถูกไฮไลต์ไว้ แต่ <strong>ถูกสุดไม่ได้แปลว่าดีสุดเสมอ</strong> —
            ดูวันส่งของและสถิติการส่งตรงเวลาบนหัวคอลัมน์ประกอบด้วย
          </div>
        </div>
      </div>
    </>
  );
}
