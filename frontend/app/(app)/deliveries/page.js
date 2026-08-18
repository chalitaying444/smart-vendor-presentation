'use client';

/**
 * ตามงานส่งของ — ตอบคำถาม "ตอนนี้มีอะไรค้างอยู่บ้าง ของใคร เป็นของอะไร"
 *
 * หน้าผู้ขายดูได้ทีละราย ส่วนหน้านี้กวาดข้ามผู้ขายทั้งหมด และดูได้สองมุม:
 *   รายผู้ขาย — ใครค้างเยอะสุด กดเปิดดูของจริงที่ค้างอยู่
 *   รายงวด    — ทุกงวดเรียงจากช้าที่สุด ไล่ตามทีละรายการได้เลย
 */
import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { IconSearch } from '@/components/icons';
import { api, encodePart } from '@/lib/api';
import { money, num, shortDate, shortMoney } from '@/lib/format';
import { LoadingAnnounce, SkeletonRows } from '@/components/Skeleton';
import OtdBadge from '@/components/OtdBadge';

const PAGE = 50;

const SCOPES = [
  { key: 'overdue', label: 'ยังค้างส่ง (ยังไม่ได้ของ)' },
  { key: 'late', label: 'ส่งช้ากว่ากำหนด (ได้ของแล้ว)' },
  { key: 'ontime', label: 'ส่งตรงเวลา / ก่อนกำหนด' },
  { key: 'rescheduled', label: 'เคยเลื่อนกำหนด' },
  { key: 'all', label: 'ทุกงวด' },
];

/** มุมที่กำลังดูนี้ นับว่า "ดี" หรือ "มีปัญหา" — ใช้เลือกหัวคอลัมน์และสีให้ตรงความหมาย */
const GOOD_SCOPES = new Set(['ontime']);

const VIEWS = [
  { key: 'vendor', label: 'ดูรายผู้ขาย' },
  { key: 'release', label: 'ดูรายงวด' },
];

const MIN_DAYS = [
  { value: '', label: 'ทั้งหมด' },
  { value: '7', label: 'ช้าเกิน 7 วัน' },
  { value: '30', label: 'ช้าเกิน 30 วัน' },
  { value: '90', label: 'ช้าเกิน 90 วัน' },
];

export default function DeliveriesPage() {
  return (
    <Suspense fallback={<div className="empty">กำลังโหลด…</div>}>
      <DeliveryFollowUp />
    </Suspense>
  );
}

function DeliveryFollowUp() {
  const [scope, setScope] = useState('overdue');
  const [view, setView] = useState('vendor');
  const [term, setTerm] = useState('');
  const [minDays, setMinDays] = useState('');
  const [expanded, setExpanded] = useState(new Set());

  const [grouped, setGrouped] = useState(null);
  const [list, setList] = useState(null);
  const [rows, setRows] = useState([]);
  const [skip, setSkip] = useState(0);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const reqId = useRef(0);

  const filters = useCallback(() => ({
    q: term.trim(),
    // ตัวกรอง "ช้าอย่างน้อยกี่วัน" ไม่มีความหมายกับมุมที่ส่งตรงเวลา
    min_days_late: (minDays && !GOOD_SCOPES.has(scope)) ? minDays : undefined,
    only_overdue: scope === 'overdue' ? true : undefined,
    only_late: scope === 'late' ? true : undefined,
    only_on_time: scope === 'ontime' ? true : undefined,
    only_rescheduled: scope === 'rescheduled' ? true : undefined,
  }), [term, minDays, scope]);

  const load = useCallback(async (nextSkip, append) => {
    const mine = ++reqId.current;
    setBusy(true);
    try {
      if (view === 'vendor') {
        const res = await api.deliveriesByVendor({ ...filters(), sort: 'releases' });
        if (mine !== reqId.current) return;
        setGrouped(res);
      } else {
        const res = await api.listDeliveries({
          ...filters(),
          sort: scope === 'overdue' ? 'overdue'
            : scope === 'ontime' ? 'earliest'
              : scope === 'all' ? 'recent' : 'latest',
          skip: nextSkip, limit: PAGE,
        });
        if (mine !== reqId.current) return;
        setList(res);
        setRows((prev) => (append ? [...prev, ...res.items] : res.items));
      }
      setError('');
    } catch (e) {
      if (mine === reqId.current) setError(e.message);
    } finally {
      if (mine === reqId.current) setBusy(false);
    }
  }, [view, scope, filters]);

  useEffect(() => {
    const t = setTimeout(() => { setSkip(0); setExpanded(new Set()); load(0, false); },
      term ? 300 : 0);
    return () => clearTimeout(t);
  }, [load, term]);

  function toggle(vendorId) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(vendorId)) next.delete(vendorId); else next.add(vendorId);
      return next;
    });
  }

  const overdueMode = scope === 'overdue';
  const goodMode = GOOD_SCOPES.has(scope);
  const mixedMode = scope === 'all' || scope === 'rescheduled';

  // หัวคอลัมน์ "ความช้า" ต้องอ่านให้ตรงกับมุมที่ดูอยู่ ไม่งั้นเลข -5 จะดูเหมือนช้า
  const daysHeader = overdueMode ? 'ค้างมา' : goodMode ? 'เร็วกว่ากำหนด' : mixedMode ? 'ผลการส่ง' : 'ช้า';
  const countHeader = overdueMode ? 'งวดค้างส่ง'
    : goodMode ? 'งวดที่ตรงเวลา' : mixedMode ? 'จำนวนงวด' : 'งวดที่ช้า';
  const extremeHeader = overdueMode ? 'ค้างนานสุด'
    : goodMode ? 'เร็วสุด' : mixedMode ? 'ช้าสุด' : 'ช้าสุด';

  /** เทียบกับกำหนดเดิมก่อนถูกเลื่อน — ค่าติดลบคือยังเร็วกว่ากำหนดเดิม */
  function vsOriginal(days) {
    if (days == null) return null;
    if (days > 0) return `เทียบกำหนดเดิมช้า ${num(days)} วัน`;
    if (days < 0) return `เทียบกำหนดเดิมยังเร็ว ${num(Math.abs(days))} วัน`;
    return 'ตรงกำหนดเดิมพอดี';
  }

  /** แสดงจำนวนวันให้อ่านออกว่าเร็วหรือช้า ไม่ใช่เลขติดลบลอย ๆ */
  function daysCell(d) {
    if (d.overdue) return <span className="otd-overdue">ค้างมา {num(d.days_overdue)} วัน</span>;
    if (d.days_late == null) return <span className="muted">—</span>;
    if (d.days_late > 0) return <span className="otd-overdue">ช้า {num(d.days_late)} วัน</span>;
    if (d.days_late < 0) return <span className="otd-ontime">เร็ว {num(Math.abs(d.days_late))} วัน</span>;
    return <span className="otd-ontime">ตรงวัน</span>;
  }

  return (
    <>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-body" style={{ paddingBottom: 14 }}>
          <div className="search-wrap" style={{ maxWidth: '100%', marginBottom: 12 }}>
            <IconSearch />
            <input
              type="search"
              value={term}
              onChange={(e) => setTerm(e.target.value)}
              placeholder="ชื่อผู้ขาย รหัสสินค้า ชื่อสินค้า หรือเลข PO…"
              aria-label="ค้นหางานส่งของ"
            />
          </div>

          <div className="filter-row">
            <label className="field-inline">
              <span>ดูเฉพาะ</span>
              <select value={scope} onChange={(e) => setScope(e.target.value)}>
                {SCOPES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
              </select>
            </label>
            <label className="field-inline">
              <span>ความช้า</span>
              <select value={minDays} onChange={(e) => setMinDays(e.target.value)}>
                {MIN_DAYS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
              </select>
            </label>
            <div className="spacer" />
            <div className="tabs" style={{ border: 0 }}>
              {VIEWS.map((v) => (
                <button key={v.key} className={`tab${view === v.key ? ' active' : ''}`}
                        onClick={() => setView(v.key)}>
                  {v.label}
                </button>
              ))}
            </div>
          </div>

          <div className="result-line">
            {view === 'vendor' ? (
              <>
                <strong>{num(grouped?.total_vendors ?? 0)}</strong> ผู้ขาย ·{' '}
                {num(grouped?.total_releases ?? 0)} งวด ·
                มูลค่ารวม {shortMoney(grouped?.total_value)} บาท
              </>
            ) : (
              <>พบ <strong>{num(list?.total ?? 0)}</strong> งวด
                {rows.length > 0 && <> · แสดงแล้ว {num(rows.length)}</>}</>
            )}
            {busy && <span className="muted"> · กำลังโหลด…</span>}
            {busy && <LoadingAnnounce label="กำลังโหลดงานส่งของ" />}
          </div>

          <div className="hint">
            {overdueMode
              ? 'งวดที่เลยกำหนดแล้วแต่ยังไม่ได้รับของ — งวดพวกนี้ไม่ถูกนับใน % ส่งตรงเวลา จึงต้องไล่ดูแยก'
              : goodMode
                ? 'งวดที่ได้ของภายในกำหนด รวมที่ส่งมาก่อนกำหนดด้วย'
                : 'วันที่ใช้ตัดสินคือกำหนดส่งใน PO เทียบกับวันที่คลังบันทึกรับของ'}
          </div>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {/* ---------------- รายผู้ขาย ---------------- */}
      {view === 'vendor' && (
        <div className="card">
          <div className="table-wrap">
            <table className="vendor-table">
              <thead>
                <tr>
                  <th style={{ width: 40 }} />
                  <th style={{ minWidth: 280 }}>ผู้ขาย</th>
                  <th style={{ minWidth: 190 }}>ส่งตรงเวลาโดยรวม</th>
                  <th style={{ textAlign: 'right', width: 110 }}>{countHeader}</th>
                  <th style={{ textAlign: 'right', width: 120 }}>{extremeHeader}</th>
                  <th style={{ textAlign: 'right', width: 130 }}>มูลค่ารวม</th>
                </tr>
              </thead>
              {!grouped && busy && (
                <SkeletonRows rows={10} cols={6} widths={['20%', '76%', '58%', '34%', '40%', '52%']} />
              )}
              <tbody>
                {grouped && grouped.vendors.length === 0 && !busy && (
                  <tr><td colSpan={6} className="empty-cell">
                    {goodMode ? 'ไม่มีงวดที่ส่งตรงเวลาตรงกับคำค้นนี้'
                      : 'ไม่มีงานส่งที่ตรงกับเงื่อนไขนี้ — ดีแล้ว'}
                  </td></tr>
                )}
                {(grouped?.vendors || []).map((v) => {
                  const open = expanded.has(v.vendor_id);
                  return [
                    <tr key={v.vendor_id} className="clickable" onClick={() => toggle(v.vendor_id)}>
                      <td className="cell-sub" style={{ textAlign: 'center' }}>{open ? '▾' : '▸'}</td>
                      <td>
                        <span className="cell-title">{v.vendor_name}</span>
                        <div className="cell-sub">
                          <code>{v.vendor_id}</code>
                          {v.rescheduled > 0 && (
                            <span className="tag tag-warn">เคยเลื่อนกำหนด {v.rescheduled} งวด</span>
                          )}
                        </div>
                      </td>
                      <td><OtdBadge delivery={v.delivery} /></td>
                      <td className="num-cell"><strong>{num(v.releases)}</strong></td>
                      <td className={`num-cell${goodMode ? ' otd-ontime' : ' otd-overdue'}`}>
                        {goodMode && v.worst_days < 0
                          ? `เร็ว ${num(Math.abs(v.worst_days))} วัน`
                          : `${num(v.worst_days)} วัน`}
                      </td>
                      <td className="num-cell">{money(v.value)}</td>
                    </tr>,
                    open && (
                      <tr key={`${v.vendor_id}-detail`}>
                        <td />
                        <td colSpan={5} style={{ padding: 0 }}>
                          <table style={{ width: '100%' }}>
                            <thead>
                              <tr>
                                <th style={{ minWidth: 260 }}>สินค้า</th>
                                <th style={{ width: 120 }}>เอกสาร</th>
                                <th style={{ width: 115 }}>กำหนดส่ง</th>
                                <th style={{ width: 150 }}>{daysHeader}</th>
                                <th style={{ textAlign: 'right', width: 120 }}>มูลค่า</th>
                              </tr>
                            </thead>
                            <tbody>
                              {v.items.map((d) => (
                                <tr key={d.id}>
                                  <td>
                                    <Link className="cell-title"
                                          href={`/products/${encodePart(d.part_num)}`}>
                                      {d.part_description || d.part_num}
                                    </Link>
                                    <div className="cell-sub"><code>{d.part_num}</code></div>
                                  </td>
                                  <td className="cell-sub">
                                    PO {d.po_num}/{d.po_line}
                                    <div className="muted">งวดที่ {d.po_rel_num}</div>
                                  </td>
                                  <td className="cell-sub">
                                    {shortDate(d.promise_date)}
                                    <div className="muted">
                                      {d.promise_source === 'PromiseDt' ? 'ผู้ขายรับปาก' : 'กำหนดในระบบ'}
                                    </div>
                                  </td>
                                  <td className="cell-sub">
                                    {daysCell(d)}
                                    {d.rescheduled && (
                                      <div className="otd-overdue">
                                        {vsOriginal(d.days_late_vs_original) || 'เคยเลื่อนกำหนด'}
                                      </div>
                                    )}
                                  </td>
                                  <td className="num-cell">{money(d.value)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          <div className="card-body" style={{ paddingTop: 8, paddingBottom: 12 }}>
                            <Link className="btn btn-secondary btn-sm"
                                  href={`/vendors/${encodeURIComponent(v.vendor_key)}`}>
                              เปิดหน้าผู้ขาย — ดูงวดทั้งหมด {num(v.releases)} งวด
                            </Link>
                          </div>
                        </td>
                      </tr>
                    ),
                  ];
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ---------------- รายงวด ---------------- */}
      {view === 'release' && (
        <>
          <div className="card">
            <div className="table-wrap">
              <table className="vendor-table">
                <thead>
                  <tr>
                    <th style={{ minWidth: 260 }}>สินค้า</th>
                    <th style={{ minWidth: 220 }}>ผู้ขาย</th>
                    <th style={{ width: 115 }}>เอกสาร</th>
                    <th style={{ width: 115 }}>กำหนดส่ง</th>
                    <th style={{ width: 115 }}>รับของจริง</th>
                    <th style={{ width: 165 }}>{daysHeader}</th>
                    <th style={{ textAlign: 'right', width: 125 }}>มูลค่า</th>
                  </tr>
                </thead>
                {rows.length === 0 && busy && (
                  <SkeletonRows rows={12} cols={7}
                                widths={['74%', '70%', '52%', '58%', '58%', '48%', '52%']} />
                )}
                <tbody>
                  {rows.length === 0 && !busy ? (
                    <tr><td colSpan={7} className="empty-cell">
                      {goodMode ? 'ไม่มีงวดที่ส่งตรงเวลาตรงกับคำค้นนี้'
                        : 'ไม่มีงานส่งที่ตรงกับเงื่อนไขนี้ — ดีแล้ว'}
                    </td></tr>
                  ) : rows.map((d) => (
                    <tr key={d.id}>
                      <td>
                        <Link className="cell-title" href={`/products/${encodePart(d.part_num)}`}>
                          {d.part_description || d.part_num}
                        </Link>
                        <div className="cell-sub"><code>{d.part_num}</code></div>
                      </td>
                      <td>
                        <Link href={`/vendors/${encodeURIComponent(d.vendor_key)}`}>
                          {d.vendor_name}
                        </Link>
                        <div className="cell-sub"><code>{d.vendor_id}</code></div>
                      </td>
                      <td className="cell-sub">
                        PO {d.po_num}/{d.po_line}
                        <div className="muted">งวดที่ {d.po_rel_num}</div>
                      </td>
                      <td className="cell-sub">
                        {shortDate(d.promise_date)}
                        <div className="muted">
                          {d.promise_source === 'PromiseDt' ? 'ผู้ขายรับปาก' : 'กำหนดในระบบ'}
                        </div>
                      </td>
                      <td className="cell-sub">
                        {d.last_receipt_date
                          ? shortDate(d.last_receipt_date)
                          : <span className="muted">ยังไม่ได้รับ</span>}
                      </td>
                      <td>
                        <span className={`otd ${d.overdue ? 'otd-poor'
                          : d.on_time ? 'otd-excellent'
                            : d.days_late > 30 ? 'otd-poor' : 'otd-fair'}`}>
                          {d.status}
                        </span>
                        <div className="cell-sub">
                          {daysCell(d)}
                          {d.rescheduled && (
                            <div className="otd-overdue">
                              เคยเลื่อนกำหนด
                              {vsOriginal(d.days_late_vs_original)
                                && ` · ${vsOriginal(d.days_late_vs_original)}`}
                            </div>
                          )}
                          {d.delivered && !d.qty_complete && (
                            <div className="otd-overdue">
                              รับไม่ครบ {num(d.qty_received, 2)}/{num(d.qty_released, 2)}
                            </div>
                          )}
                        </div>
                      </td>
                      <td className="num-cell">{money(d.value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {list?.has_more && (
            <div className="load-more">
              <button className="btn btn-secondary" disabled={busy}
                      onClick={() => { const n = skip + PAGE; setSkip(n); load(n, true); }}>
                {busy ? 'กำลังโหลด…' : `โหลดเพิ่มอีก ${Math.min(PAGE, list.total - rows.length)} งวด`}
              </button>
            </div>
          )}
        </>
      )}
    </>
  );
}
