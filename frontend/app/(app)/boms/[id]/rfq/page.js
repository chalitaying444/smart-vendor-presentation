'use client';

/**
 * ออกใบขอราคา "แยกใบต่อรายการ" จากงานประมาณราคา BOM — เป็นหน้าเต็ม ไม่ใช่กล่องซ้อน
 *
 * ทำไมต้องแยกใบ: ผู้ขายแต่ละเจ้าขายคนละอย่าง ถ้ารวมทุกรายการไว้ในใบเดียว
 * ทุกเจ้าจะได้เห็นของที่ตัวเองไม่ได้ขายไปด้วย ตอบกลับมาไม่ครบ เทียบราคายาก
 *
 * ทำไมเป็นหน้าเต็ม: งานนี้ต้องกวาดตาดูหลายรายการ เทียบราคากับสถิติส่งของ
 * แล้วค่อยตัดสินใจ — กล่องซ้อนบีบพื้นที่ และกดพลาดนอกกล่องทีเดียวงานหาย
 *
 * ผู้ขายที่แสดงให้เลือกคือเจ้าที่ **เคยขายรหัสนั้นให้เราจริง** พร้อมราคาล่าสุด
 * ของเจ้านั้นและสถิติการส่งตรงเวลา · ถ้าอยากเชิญเจ้าอื่นก็ค้นหาเพิ่มเองได้
 */
import { use, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { usePageTitle } from '@/components/RequireAdmin';
import OtdBadge from '@/components/OtdBadge';
import VendorSearch from '@/components/VendorSearch';
import { SkeletonBlock } from '@/components/Skeleton';
import { money, num, shortDate } from '@/lib/format';

export default function BomRfqPage({ params }) {
  const { id } = use(params);
  return <RfqBuilder bomId={id} />;
}

function RfqBuilder({ bomId }) {
  const [plan, setPlan] = useState(null);
  const [picked, setPicked] = useState({});      // line_no -> Set(vendor_key)
  const [extra, setExtra] = useState({});        // line_no -> ผู้ขายที่ค้นหาเพิ่มเอง
  const [idx, setIdx] = useState(0);
  const [groupBy, setGroupBy] = useState('vendor');
  const [send, setSend] = useState(false);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  usePageTitle('ออกใบขอราคาแยกรายตัว',
    plan ? `${plan.bom_no} · ${plan.title}` : '');

  useEffect(() => {
    api.bomRfqPlan(bomId)
      .then((p) => {
        setPlan(p);
        setPicked(Object.fromEntries(p.items.map((it) => [
          it.line_no,
          new Set(it.vendors.filter((v) => v.suggested).map((v) => v.vendor_key)),
        ])));
      })
      .catch((e) => setError(e.message));
  }, [bomId]);

  const items = plan?.items || [];
  const current = items[idx] || null;
  const vendorsOf = useCallback(
    (it) => [...(it?.vendors || []), ...(extra[it?.line_no] || [])],
    [extra],
  );

  const summary = useMemo(() => {
    const entries = Object.values(picked);
    const withVendors = entries.filter((s) => s.size > 0);
    const vendors = new Set();
    withVendors.forEach((s) => s.forEach((k) => vendors.add(k)));
    return {
      lines: withVendors.length,
      vendors: vendors.size,
      // รวมตามผู้ขาย = ได้ใบเท่าจำนวนเจ้าที่ไม่ซ้ำ · แยกตามรายการ = ได้ใบเท่าจำนวนรายการ
      sheets: groupBy === 'vendor' ? vendors.size : withVendors.length,
      invites: entries.reduce((sum, s) => sum + s.size, 0),
      empty: entries.length - withVendors.length,
    };
  }, [picked, groupBy]);

  function toggle(lineNo, vendorKey) {
    setPicked((state) => {
      const next = new Set(state[lineNo] || []);
      if (next.has(vendorKey)) next.delete(vendorKey);
      else next.add(vendorKey);
      return { ...state, [lineNo]: next };
    });
  }

  function setAll(lineNo, vendors, on) {
    setPicked((state) => ({
      ...state,
      [lineNo]: on ? new Set(vendors.map((v) => v.vendor_key)) : new Set(),
    }));
  }

  /** เพิ่มผู้ขายที่ค้นหาเจอ — ติ๊กให้เลยเพราะการกดเพิ่มคือความตั้งใจจะเชิญอยู่แล้ว */
  function addVendor(lineNo, vendor) {
    setExtra((state) => {
      const rows = state[lineNo] || [];
      if (rows.some((v) => v.vendor_key === vendor.vendor_key)) return state;
      return { ...state, [lineNo]: [...rows, { ...vendor, added: true }] };
    });
    setPicked((state) => ({
      ...state,
      [lineNo]: new Set([...(state[lineNo] || []), vendor.vendor_key]),
    }));
  }

  async function submit() {
    setBusy(true); setError('');
    try {
      const payloadItems = items
        .map((it) => ({ line_no: it.line_no, vendor_keys: [...(picked[it.line_no] || [])] }))
        .filter((it) => it.vendor_keys.length > 0);
      setResult(await api.bomRfqsPerItem(bomId,
        { items: payloadItems, group_by: groupBy, send, message }));
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  /* ---------------- ผลลัพธ์ ---------------- */
  if (result) {
    return (
      <div className="card">
        <div className="card-head">
          <div>
            <h2>
            ออกใบขอราคาแล้ว {num(result.created.length)} ใบ
            {result.group_by === 'vendor' && ' (ใบละหนึ่งผู้ขาย)'}
          </h2>
            <div className="cell-sub">
              {send ? 'ส่งลิงก์ให้ผู้ขายเรียบร้อยแล้ว'
                    : 'ยังไม่ได้ส่ง — เปิดแต่ละใบเพื่อตรวจแล้วกดส่ง'}
            </div>
          </div>
          <Link className="btn btn-secondary" href={`/boms/${bomId}`}>
            กลับไปหน้างานประมาณราคา
          </Link>
        </div>
        <div className="card-body">
          <ul className="result-list">
            {result.created.map((c) => (
              <li key={c.rfq_no}>
                <Link href={`/rfqs/${c.rfq_id}`}><strong>{c.rfq_no}</strong></Link>
                <span className="cell-sub">
                  {result.group_by === 'vendor' ? (
                    <>{c.vendor_name} · {num(c.line_count)} รายการ (#{(c.lines || []).join(', #')})</>
                  ) : (
                    <>รายการที่ {c.line_no} · <code>{c.part_num}</code> ·
                      เชิญ {num(c.vendor_count)} ราย</>
                  )}
                  {c.sent ? ` · ส่งแล้ว ${num(c.sent)}` : ''}
                </span>
              </li>
            ))}
          </ul>
          {result.skipped?.length > 0 && (
            <div className="alert alert-attention" style={{ marginTop: 14 }}>
              ไม่ได้ออกใบให้ {num(result.skipped.length)} รายการ —{' '}
              {result.skipped.map((s) => `#${s.line_no} ${s.reason}`).join(' · ')}
            </div>
          )}
          {/* ตัดเจ้าที่เชิญไปแล้วออกให้ ต้องบอกว่าตัดใครออก ไม่ใช่เงียบ ๆ */}
          {result.repeated?.length > 0 && (
            <div className="alert alert-attention" style={{ marginTop: 14 }}>
              ข้ามผู้ขายที่เชิญให้เสนอราคารายการนั้นไปแล้ว {num(result.repeated.length)} ราย —{' '}
              {result.repeated.map((r) => `#${r.line_no} ${r.rfq_nos.filter(Boolean).join('/')}`).join(' · ')}
              {' '}· ถ้าต้องการขอราคาใหม่จากเจ้าเดิม ให้เปิดหน้าวัสดุรายตัวแล้วติ๊ก
              "ขอซ้ำจากเจ้าที่เคยเชิญ"
            </div>
          )}
        </div>
      </div>
    );
  }

  if (error && !plan) return <div className="alert alert-error">{error}</div>;
  if (!plan) return <div className="card"><SkeletonBlock lines={6} /></div>;

  const chosen = current ? (picked[current.line_no] || new Set()) : new Set();
  const currentVendors = vendorsOf(current);

  return (
    <>
      <div className="page-back">
        <Link href={`/boms/${bomId}`}>← กลับไปหน้างานประมาณราคา</Link>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="rfq-summary">
        <span><strong>{num(summary.sheets)}</strong> ใบที่จะออก</span>
        <span>{num(summary.lines)} รายการ · ผู้ขาย {num(summary.vendors)} ราย</span>
        {summary.empty > 0 && (
          <span className="tone-warn">
            {num(summary.empty)} รายการยังไม่ได้เลือกผู้ขาย — จะข้ามไป
          </span>
        )}
      </div>

      {/* วิธีรวมใบ — เปลี่ยนจำนวนใบที่จะออกทันที ให้เห็นผลก่อนกด */}
      <div className="rfq-group">
        <span className="rfq-group-label">ออกใบแบบไหน</span>
        <label className={`rfq-group-opt${groupBy === 'vendor' ? ' on' : ''}`}>
          <input type="radio" name="group-by" checked={groupBy === 'vendor'}
                 onChange={() => setGroupBy('vendor')} />
          <span>
            <strong>ผู้ขายหนึ่งรายได้ใบเดียว</strong>
            <span className="cell-sub">
              เจ้าที่ขายหลายรายการในโครงการนี้ จะได้ใบเดียวที่มีของครบ ตอบง่ายกว่า ตามน้อยกว่า
            </span>
          </span>
        </label>
        <label className={`rfq-group-opt${groupBy === 'item' ? ' on' : ''}`}>
          <input type="radio" name="group-by" checked={groupBy === 'item'}
                 onChange={() => setGroupBy('item')} />
          <span>
            <strong>หนึ่งรายการหนึ่งใบ</strong>
            <span className="cell-sub">
              แยกใบตามสินค้า ผู้ขายรายเดียวกันอาจได้หลายใบ
            </span>
          </span>
        </label>
      </div>

      {plan.skipped.length > 0 && (
        <div className="alert alert-attention">
          {num(plan.skipped.length)} รายการออกใบไม่ได้เพราะยังไม่ได้จับคู่กับสินค้าในระบบ:{' '}
          {plan.skipped.map((s) => `#${s.line_no} ${s.name}`).join(' · ')}
        </div>
      )}

      {/* ดูทีละรายการ — สารบัญบอกว่าอยู่ตรงไหนและเหลืออะไร */}
      <div className="rfq-split rfq-split-page">
        <nav className="rfq-nav" aria-label="รายการที่จะออกใบขอราคา">
          {items.map((it, i) => {
            const n = (picked[it.line_no] || new Set()).size;
            return (
              <button key={it.line_no} type="button"
                      className={`rfq-nav-item${i === idx ? ' current' : ''}${n === 0 ? ' off' : ''}`}
                      aria-current={i === idx ? 'true' : undefined}
                      onClick={() => setIdx(i)}>
                <span className="rfq-nav-no">{it.line_no}</span>
                <span className="rfq-nav-text">
                  <span className="rfq-nav-name">{it.name}</span>
                  <span className="rfq-nav-sub">
                    {n === 0 ? 'ยังไม่เลือกผู้ขาย' : `เลือก ${num(n)} ราย`}
                  </span>
                </span>
              </button>
            );
          })}
        </nav>

        <div className="rfq-pane">
          {current && (
            <>
              <div className="rfq-item-head">
                <div>
                  <div className="cell-title">
                    รายการที่ {current.line_no} · {current.name}
                  </div>
                  <div className="cell-sub">
                    <code>{current.part_num}</code> {current.item_description} ·
                    จำนวน {num(current.qty, 2)} {current.uom}
                    {current.unit_price != null && <> · ราคาเดิม {money(current.unit_price)}</>}
                    {current.rfq_no && (
                      <span className="conf conf-warn">ออกใบ {current.rfq_no} ไปแล้ว</span>
                    )}
                  </div>
                </div>
                <div className="rfq-item-actions">
                  <span className="cell-sub">
                    เลือก {num(chosen.size)}/{num(currentVendors.length)}
                  </span>
                  <button type="button" className="btn btn-secondary btn-sm"
                          onClick={() => setAll(current.line_no, currentVendors,
                                                chosen.size === 0)}>
                    {chosen.size === 0 ? 'เลือกทุกราย' : 'ไม่เลือกเลย'}
                  </button>
                </div>
              </div>

              {currentVendors.length === 0 ? (
                <div className="hint" style={{ margin: '14px 16px' }}>
                  ไม่มีประวัติว่าเคยซื้อรหัสนี้จากใคร — ค้นหาผู้ขายเพิ่มด้านล่างได้
                </div>
              ) : (
                <div className="table-wrap">
                  <table className="quote-table vendor-pick">
                    <colgroup>
                      <col style={{ width: 44 }} /><col />
                      <col style={{ width: 150 }} /><col style={{ width: 280 }} />
                    </colgroup>
                    <thead>
                      <tr>
                        <th><span className="sr-only">เลือก</span></th>
                        <th>ผู้ขาย</th>
                        <th className="num-head">ราคาล่าสุดของเจ้านี้</th>
                        <th>ส่งตรงเวลา</th>
                      </tr>
                    </thead>
                    <tbody>
                      {currentVendors.map((v) => {
                        const on = chosen.has(v.vendor_key);
                        return (
                          <tr key={v.vendor_key}
                              className={`row-link${on ? ' picked' : ''}`}
                              onClick={() => toggle(current.line_no, v.vendor_key)}>
                            <td className="pick-cell" onClick={(e) => e.stopPropagation()}>
                              <input type="checkbox" checked={on}
                                     aria-label={`เชิญ ${v.name}`}
                                     onChange={() => toggle(current.line_no, v.vendor_key)} />
                            </td>
                            <td>
                              <div className="cell-title">{v.name}</div>
                              <div className="cell-sub">
                                <code>{v.vendor_id}</code>
                                {v.added ? (
                                  /* บอกตรง ๆ ว่าเจ้านี้ไม่มีประวัติขายรหัสนี้
                                     ไม่งั้นช่องราคาว่างจะถูกอ่านว่า "ยังไม่เคยเก็บราคา" */
                                  <span className="conf conf-warn">
                                    เพิ่มเอง · ไม่เคยขายรหัสนี้
                                  </span>
                                ) : (
                                  <>
                                    {' '}· เคยซื้อ {num(v.times)} ครั้ง
                                    {v.last_buy_date && <> · ล่าสุด {shortDate(v.last_buy_date)}</>}
                                  </>
                                )}
                                {/* เชิญไปแล้วยังเลือกซ้ำได้ แต่ต้องเห็นก่อนกด ไม่ใช่รู้ตอนออกใบ */}
                                {v.invited && (
                                  <span className="conf conf-manual">
                                    เชิญแล้ว{v.invited_rfqs?.length ? ` · ${v.invited_rfqs.join(' · ')}` : ''}
                                  </span>
                                )}
                              </div>
                            </td>
                            <td className="num-cell">
                              {v.last_unit_cost == null
                                ? <span className="muted">{v.added ? '—' : 'ไม่มีราคา'}</span>
                                : money(v.last_unit_cost)}
                            </td>
                            <td>
                              <OtdBadge delivery={v.delivery} compact />
                              {v.delivery_this_item && (
                                <div className="cell-sub">
                                  เฉพาะรหัสนี้ {num(v.delivery_this_item.otd_pct, 1)}%
                                  จาก {num(v.delivery_this_item.releases)} งวด
                                </div>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              <VendorSearch
                bomId={bomId}
                lineNo={current.line_no}
                lineName={current.name}
                already={currentVendors.map((v) => v.vendor_key)}
                onAdd={(v) => addVendor(current.line_no, v)}
              />
            </>
          )}
        </div>
      </div>

      {/* แถบทำงานติดขอบล่าง — เลื่อนดูรายการยาว ๆ แล้วปุ่มไม่หนีไปไหน */}
      <div className="rfq-actionbar">
        {items.length > 0 && (
          <div className="rfq-steps">
            <button className="btn btn-secondary btn-sm" disabled={idx === 0}
                    onClick={() => setIdx((i) => Math.max(i - 1, 0))}>← ก่อนหน้า</button>
            <span className="cell-sub">รายการที่ {idx + 1} จาก {num(items.length)}</span>
            <button className="btn btn-secondary btn-sm" disabled={idx >= items.length - 1}
                    onClick={() => setIdx((i) => Math.min(i + 1, items.length - 1))}>
              ถัดไป →
            </button>
          </div>
        )}
        <label className="checkbox rfq-send">
          <input type="checkbox" checked={send} onChange={(e) => setSend(e.target.checked)} />
          <span>ออกแล้วส่งให้ผู้ขายเลย</span>
        </label>
        {send && (
          <input type="text" className="rfq-msg" value={message}
                 aria-label="ข้อความถึงผู้ขาย"
                 onChange={(e) => setMessage(e.target.value)}
                 placeholder="ข้อความถึงผู้ขาย เช่น รบกวนเสนอราคาภายในสัปดาห์นี้" />
        )}
        <div className="spacer" />
        <button className="btn btn-primary btn-lg" disabled={busy || !summary.sheets}
                onClick={submit}>
          {busy ? 'กำลังออกใบ…' : `ออกใบขอราคา ${num(summary.sheets)} ใบ`}
        </button>
      </div>
    </>
  );
}
