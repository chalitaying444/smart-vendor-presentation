'use client';

/** รายละเอียดผู้ขาย — ข้อมูลบริษัทและผู้ติดต่อก่อน แล้วค่อยสลับแท็บดูสินค้า/รายการเคลื่อนไหว */
import { use, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { api, encodePart } from '@/lib/api';
import { money, num, shortDate, shortMoney, sinceLabel } from '@/lib/format';
import { usePageTitle } from '@/components/RequireAdmin';
import { LoadingAnnounce, SkeletonBlock, SkeletonRows, SkeletonStats } from '@/components/Skeleton';
import { OtdSummary } from '@/components/OtdBadge';

const PAGE = 30;

const TABS = [
  { key: 'company', label: 'ข้อมูลบริษัทและผู้ติดต่อ' },
  { key: 'items', label: 'สินค้าที่เคยขายให้เรา' },
  { key: 'delivery', label: 'การส่งตรงเวลา' },
  { key: 'tx', label: 'รายการเคลื่อนไหว' },
];

const DELIVERY_FILTERS = [
  { key: 'all', label: 'ทุกงวด' },
  { key: 'late', label: 'เฉพาะที่ส่งช้า' },
  { key: 'overdue', label: 'ยังค้างส่ง' },
  { key: 'rescheduled', label: 'เคยเลื่อนกำหนด' },
];

export default function VendorDetailPage({ params }) {
  const { id } = use(params);
  return <VendorDetail vendorKey={decodeURIComponent(id)} />;
}

function VendorDetail({ vendorKey }) {
  const [vendor, setVendor] = useState(null);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('company');

  const [items, setItems] = useState(null);
  const [itemRows, setItemRows] = useState([]);
  const [itemSkip, setItemSkip] = useState(0);
  const [itemTerm, setItemTerm] = useState('');

  const [tx, setTx] = useState(null);
  const [txRows, setTxRows] = useState([]);
  const [txSkip, setTxSkip] = useState(0);
  const [itemsLoading, setItemsLoading] = useState(true);
  const [txLoading, setTxLoading] = useState(true);

  const [dl, setDl] = useState(null);
  const [dlRows, setDlRows] = useState([]);
  const [dlSkip, setDlSkip] = useState(0);
  const [dlFilter, setDlFilter] = useState('all');
  const [dlLoading, setDlLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    api.getVendor(vendorKey)
      .then((d) => { if (alive) setVendor(d); })
      .catch((e) => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [vendorKey]);

  const loadItems = useCallback(async (skip, append) => {
    setItemsLoading(true);
    try {
      const res = await api.vendorItems(vendorKey, { q: itemTerm.trim(), skip, limit: PAGE });
      setItems(res);
      setItemRows((prev) => (append ? [...prev, ...res.items] : res.items));
    } finally {
      setItemsLoading(false);
    }
  }, [vendorKey, itemTerm]);

  const loadTx = useCallback(async (skip, append) => {
    setTxLoading(true);
    try {
      const res = await api.vendorTransactions(vendorKey, { skip, limit: PAGE });
      setTx(res);
      setTxRows((prev) => (append ? [...prev, ...res.items] : res.items));
    } finally {
      setTxLoading(false);
    }
  }, [vendorKey]);

  useEffect(() => {
    if (tab !== 'items') return undefined;
    const t = setTimeout(() => { setItemSkip(0); loadItems(0, false).catch((e) => setError(e.message)); },
      itemTerm ? 300 : 0);
    return () => clearTimeout(t);
  }, [tab, loadItems, itemTerm]);

  const loadDeliveries = useCallback(async (skip, append) => {
    setDlLoading(true);
    try {
      const res = await api.vendorDeliveries(vendorKey, {
        skip, limit: PAGE,
        only_late: dlFilter === 'late' ? true : undefined,
        only_overdue: dlFilter === 'overdue' ? true : undefined,
        only_rescheduled: dlFilter === 'rescheduled' ? true : undefined,
        sort: dlFilter === 'overdue' ? 'overdue' : dlFilter === 'late' ? 'latest' : 'recent',
      });
      setDl(res);
      setDlRows((prev) => (append ? [...prev, ...res.items] : res.items));
    } finally {
      setDlLoading(false);
    }
  }, [vendorKey, dlFilter]);

  useEffect(() => {
    if (tab !== 'delivery') return;
    setDlSkip(0);
    loadDeliveries(0, false).catch((e) => setError(e.message));
  }, [tab, loadDeliveries]);

  useEffect(() => {
    if (tab !== 'tx' || txRows.length) return;
    setTxSkip(0);
    loadTx(0, false).catch((e) => setError(e.message));
  }, [tab, loadTx, txRows.length]);

  usePageTitle(vendor?.name || 'ผู้ขาย', vendor ? `รหัสผู้ขาย ${vendor.vendor_id}` : '');

  if (error) {
    return (
      <>
        <div className="alert alert-error">{error}</div>
        <Link className="btn btn-secondary" href="/vendors">กลับไปรายชื่อผู้ขาย</Link>
      </>
    );
  }
  if (!vendor) return <VendorSkeleton />;

  return (
    <>
      <div className="toolbar" style={{ marginBottom: 14 }}>
        <Link className="btn btn-secondary btn-sm" href="/vendors">← กลับไปรายชื่อผู้ขาย</Link>
      </div>

      <div className="stat-row" style={{ marginBottom: 16 }}>
        <Stat label="ยอดสั่งซื้อรวม" value={shortMoney(vendor.po_amount)} unit="บาท"
              note={`${num(vendor.po_count)} ใบสั่งซื้อ · ${num(vendor.po_lines)} บรรทัด`} />
        <Stat label="รหัสสินค้าที่เคยขาย" value={num(vendor.distinct_parts)} unit="รหัส"
              note={vendor.first_buy_date ? `ซื้อครั้งแรก ${shortDate(vendor.first_buy_date)}` : ''} />
        <Stat label="สั่งซื้อล่าสุด" value={shortDate(vendor.last_buy_date)}
              note={sinceLabel(vendor.last_buy_date)} />
        <OtdSummary delivery={vendor.delivery} />
      </div>

      {vendor.delivery?.has_data && !vendor.delivery.reliable && (
        <div className="alert alert-info" style={{ marginBottom: 16 }}>
          ผู้ขายรายนี้มีงวดส่งที่วัดผลได้เพียง {num(vendor.delivery.releases)} งวด —
          เปอร์เซ็นต์ยังแกว่งง่าย ควรใช้ประกอบกับข้อมูลอื่นแทนการตัดสินจากตัวเลขนี้อย่างเดียว
        </div>
      )}

      {vendor.delivery?.overdue_releases > 0 && (
        <div className="alert alert-error" style={{ marginBottom: 16 }}>
          ผู้ขายรายนี้ยังค้างส่งอยู่ <strong>{num(vendor.delivery.overdue_releases)} งวด</strong> —
          งวดที่ยังไม่ส่งไม่ถูกนับใน % ข้างบน จึงต้องดูตัวเลขนี้ประกอบเสมอ
          <button className="btn btn-secondary btn-sm" style={{ marginLeft: 10 }}
                  onClick={() => { setTab('delivery'); setDlFilter('overdue'); }}>
            ดูงวดที่ค้างส่ง
          </button>
        </div>
      )}

      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.key} className={`tab${tab === t.key ? ' active' : ''}`} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'company' && (
        <>
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="card-head"><h2>ข้อมูลบริษัท</h2></div>
            <div className="card-body">
              <div className="kv-grid">
                <KV label="ชื่อผู้ขาย" value={vendor.name} />
                <KV label="รหัสผู้ขาย" value={vendor.vendor_id} />
                <KV label="เลขประจำตัวผู้เสียภาษี" value={vendor.tax_id} />
                <KV label="อีเมล" value={
                  vendor.emails?.length
                    ? vendor.emails.map((e) => <a key={e} href={`mailto:${e}`}>{e}</a>)
                        .reduce((acc, el) => (acc === null ? [el] : [...acc, ', ', el]), null)
                    : ''
                } />
                <KV label="โทรศัพท์" value={vendor.phones?.join(' · ')} />
                <KV label="เงื่อนไขชำระเงิน" value={vendor.terms_code} />
                <KV label="สกุลเงิน" value={vendor.currency} />
                <KV label="กลุ่มผู้ขาย" value={vendor.group_code} />
                <KV
                  label="ที่อยู่"
                  value={[vendor.address?.line1, vendor.address?.line2, vendor.address?.city,
                          vendor.address?.state, vendor.address?.zip, vendor.address?.country]
                    .filter(Boolean).join(' ')}
                />
                <KV label="สถานะ" value={vendor.inactive ? 'ปิดใช้งานใน Epicor' : 'ใช้งานอยู่'} />
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-head">
              <div>
                <h2>ช่องทางติดต่อ ({vendor.contacts?.length || 0})</h2>
                <div className="cell-sub">
                  รวมทั้งผู้ติดต่อรายบุคคลและอีเมลกลางของบริษัท ·
                  ระบบใช้อีเมลรายแรกเป็นค่าเริ่มต้นตอนส่งใบขอราคา
                </div>
              </div>
            </div>
            {(vendor.contacts || []).length === 0 ? (
              <div className="empty">
                <strong>ไม่มีช่องทางติดต่อของผู้ขายรายนี้ใน Epicor</strong>
                ทั้งทะเบียนผู้ขายและรายชื่อผู้ติดต่อไม่มีอีเมลหรือเบอร์โทร —
                ต้องกรอกอีเมลเองตอนส่งใบขอราคา
              </div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>ชื่อ</th><th>หน้าที่</th><th>อีเมล</th><th>โทรศัพท์</th></tr>
                  </thead>
                  <tbody>
                    {vendor.contacts.map((c, i) => (
                      <tr key={`${c.email}-${c.phone}-${i}`}>
                        <td>
                          <span className="cell-title">{c.name || '—'}</span>
                          {c.is_primary && <span className="tag tag-ok">ใช้ส่งใบขอราคา</span>}
                          {c.is_company && <span className="tag">อีเมลกลางของบริษัท</span>}
                        </td>
                        <td className="cell-sub">{c.function || '—'}</td>
                        <td className="cell-sub">
                          {c.email ? <a href={`mailto:${c.email}`}>{c.email}</a> : '—'}
                        </td>
                        <td className="cell-sub">{c.phone || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {(vendor.top_parts || []).length > 0 && (
            <div className="card" style={{ marginTop: 16 }}>
              <div className="card-head">
                <div>
                  <h2>สินค้าที่ซื้อจากรายนี้มากที่สุด</h2>
                  <div className="cell-sub">เรียงตามมูลค่าสะสม · กดชื่อสินค้าเพื่อดูราคาและผู้ขายรายอื่น</div>
                </div>
              </div>
              <div className="table-wrap">
                <table className="vendor-table">
                  <thead>
                    <tr>
                      <th style={{ minWidth: 320 }}>สินค้า</th>
                      <th style={{ width: 80 }}>หน่วย</th>
                      <th style={{ textAlign: 'right', width: 90 }}>ครั้ง</th>
                      <th style={{ textAlign: 'right', width: 110 }}>จำนวน</th>
                      <th style={{ textAlign: 'right', width: 140 }}>มูลค่า</th>
                    </tr>
                  </thead>
                  <tbody>
                    {vendor.top_parts.map((p) => (
                      <tr key={p.part_num}>
                        <td>
                          <Link className="cell-title" href={`/products/${encodePart(p.part_num)}`}>
                            {p.description || p.part_num}
                          </Link>
                          <div className="cell-sub">
                            <code>{p.part_num}</code>
                            {p.in_catalog === false && (
                              <span className="tag">ไม่มีในทะเบียนสินค้า</span>
                            )}
                          </div>
                        </td>
                        <td className="cell-sub">{p.uom || '—'}</td>
                        <td className="num-cell">{num(p.times)}</td>
                        <td className="num-cell">{num(p.qty, 2)}</td>
                        <td className="num-cell">{money(p.amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {tab === 'items' && (
        <div className="card">
          <div className="card-body" style={{ paddingBottom: 10 }}>
            <input
              type="search"
              value={itemTerm}
              onChange={(e) => setItemTerm(e.target.value)}
              placeholder="กรองสินค้าของผู้ขายรายนี้…"
              aria-label="กรองสินค้า"
            />
            <div className="result-line">พบ <strong>{num(items?.total ?? 0)}</strong> รหัสสินค้า</div>
          </div>
          <div className="table-wrap">
            <table className="vendor-table">
              <thead>
                <tr>
                  <th style={{ minWidth: 320 }}>สินค้า</th>
                  <th style={{ textAlign: 'right', width: 140 }}>ราคาล่าสุดของรายนี้</th>
                  <th style={{ width: 130 }}>ขายล่าสุด</th>
                  <th style={{ textAlign: 'right', width: 90 }}>ครั้ง</th>
                  <th style={{ textAlign: 'right', width: 90 }}>ผู้ขายรวม</th>
                  <th style={{ textAlign: 'right', width: 130 }}>ราคาล่าสุดที่เราซื้อ</th>
                </tr>
              </thead>
              {itemRows.length === 0 && itemsLoading && (
                <SkeletonRows rows={8} cols={6} widths={['74%', '52%', '58%', '32%', '32%', '52%']} />
              )}
              <tbody>
                {itemRows.length === 0 && !itemsLoading ? (
                  <tr><td colSpan={6} className="empty-cell">ไม่พบสินค้า</td></tr>
                ) : itemRows.map((it) => (
                  <tr key={it.part_num}>
                    <td>
                      <Link className="cell-title" href={`/products/${encodePart(it.part_num)}`}>
                        {it.description || it.part_num}
                      </Link>
                      <div className="cell-sub"><code>{it.part_num}</code></div>
                    </td>
                    <td className="num-cell">{money(it.vendor_last_price)}</td>
                    <td className="cell-sub">{shortDate(it.vendor_last_date)}</td>
                    <td className="num-cell">{num(it.vendor_times)}</td>
                    <td className="num-cell">{it.vendor_count}</td>
                    <td className="num-cell">{money(it.last_price)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {items?.has_more && (
            <div className="load-more">
              <button className="btn btn-secondary btn-sm"
                      onClick={() => { const n = itemSkip + PAGE; setItemSkip(n); loadItems(n, true); }}>
                โหลดเพิ่ม
              </button>
            </div>
          )}
        </div>
      )}

      {tab === 'delivery' && (
        <div className="card">
          <div className="card-head">
            <div>
              <h2>ประวัติการส่งของ</h2>
              <div className="cell-sub">
                หน่วยคือ “งวดส่งของ” (PO Release) — สินค้าบรรทัดเดียวอาจแบ่งส่งหลายงวด
                และแต่ละงวดมีวันกำหนดของตัวเอง
              </div>
            </div>
          </div>

          {(dl?.by_status || vendor.delivery_by_status || []).length > 0 && (
            <div className="card-body" style={{ paddingBottom: 6 }}>
              <div className="mini-stats">
                {(dl?.by_status || vendor.delivery_by_status).map((s2) => (
                  <div key={s2.status} className="mini-stat">
                    <span className="mini-label">{s2.status}</span>
                    <span className="mini-value">{num(s2.releases)} งวด</span>
                    <span className="mini-note">{s2.percent}% · {shortMoney(s2.value)} บาท</span>
                  </div>
                ))}
              </div>
              <div className="hint">
                วันที่ใช้ตัดสินคือวันกำหนดส่งใน PO เทียบกับวันที่คลังบันทึกรับของ —
                ถ้าเห็นช้า 1-3 วันเยอะผิดปกติ อาจเป็นเรื่องจังหวะการคีย์รับของ ไม่ใช่ความผิดผู้ขาย
              </div>
            </div>
          )}

          <div className="tabs">
            {DELIVERY_FILTERS.map((f) => (
              <button key={f.key} className={`tab${dlFilter === f.key ? ' active' : ''}`}
                      onClick={() => setDlFilter(f.key)}>
                {f.label}
              </button>
            ))}
          </div>

          <div className="table-wrap">
            <table className="vendor-table">
              <thead>
                <tr>
                  <th style={{ minWidth: 280 }}>สินค้า</th>
                  <th style={{ width: 110 }}>เอกสาร</th>
                  <th style={{ width: 120 }}>กำหนดส่ง</th>
                  <th style={{ width: 120 }}>รับของจริง</th>
                  <th style={{ width: 150 }}>ผลการส่ง</th>
                  <th style={{ textAlign: 'right', width: 110 }}>จำนวน</th>
                  <th style={{ textAlign: 'right', width: 130 }}>มูลค่า</th>
                </tr>
              </thead>
              {dlRows.length === 0 && dlLoading && (
                <SkeletonRows rows={8} cols={7} widths={['74%', '48%', '58%', '58%', '62%', '40%', '52%']} />
              )}
              <tbody>
                {dlRows.length === 0 && !dlLoading ? (
                  <tr><td colSpan={7} className="empty-cell">ไม่มีงวดส่งในหมวดนี้</td></tr>
                ) : dlRows.map((d) => (
                  <tr key={d.id}>
                    <td>
                      <Link className="cell-title" href={`/products/${encodePart(d.part_num)}`}>
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
                      {d.last_receipt_date ? shortDate(d.last_receipt_date)
                        : <span className="muted">ยังไม่ได้รับ</span>}
                    </td>
                    <td>
                      <span className={`otd ${d.overdue ? 'otd-poor'
                        : d.on_time ? 'otd-excellent'
                          : d.days_late > 30 ? 'otd-poor' : 'otd-fair'}`}>
                        {d.status}
                      </span>
                      <div className="cell-sub">
                        {d.days_late != null && (d.days_late > 0
                          ? `ช้า ${num(d.days_late)} วัน`
                          : d.days_late < 0 ? `เร็ว ${num(Math.abs(d.days_late))} วัน` : 'ตรงวัน')}
                        {d.overdue && `ค้างมา ${num(d.days_overdue)} วัน`}
                        {d.rescheduled && (
                          <div className="otd-overdue">
                            เคยเลื่อนกำหนด
                            {d.days_late_vs_original != null && (
                              d.days_late_vs_original > 0
                                ? ` · เทียบกำหนดเดิมช้า ${num(d.days_late_vs_original)} วัน`
                                : d.days_late_vs_original < 0
                                  ? ` · เทียบกำหนดเดิมยังเร็ว ${num(Math.abs(d.days_late_vs_original))} วัน`
                                  : ' · ตรงกำหนดเดิมพอดี'
                            )}
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="num-cell">
                      {num(d.qty_received, 2)}/{num(d.qty_released, 2)}
                      {!d.qty_complete && d.delivered && <div className="cell-sub otd-overdue">รับไม่ครบ</div>}
                    </td>
                    <td className="num-cell">{money(d.value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {dl?.has_more && (
            <div className="load-more">
              <button className="btn btn-secondary btn-sm"
                      onClick={() => { const n = dlSkip + PAGE; setDlSkip(n); loadDeliveries(n, true); }}>
                โหลดเพิ่ม (เหลืออีก {num(dl.total - dlRows.length)})
              </button>
            </div>
          )}
        </div>
      )}

      {tab === 'tx' && (
        <div className="card">
          {tx?.summary?.length > 0 && (
            <div className="card-body" style={{ paddingBottom: 0 }}>
              <div className="mini-stats">
                {tx.summary.map((s) => (
                  <div key={s.doc_type} className="mini-stat">
                    <span className="mini-label">{s.doc_type_label}</span>
                    <span className="mini-value">{num(s.lines)} รายการ</span>
                    <span className="mini-note">{shortMoney(s.amount)} บาท</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 110 }}>วันที่</th>
                  <th style={{ width: 110 }}>ประเภท</th>
                  <th style={{ minWidth: 300 }}>สินค้า</th>
                  <th style={{ textAlign: 'right', width: 90 }}>จำนวน</th>
                  <th style={{ textAlign: 'right', width: 130 }}>ราคา/หน่วย</th>
                  <th style={{ textAlign: 'right', width: 140 }}>มูลค่า</th>
                </tr>
              </thead>
              {txRows.length === 0 && txLoading && (
                <SkeletonRows rows={8} cols={6} widths={['62%', '48%', '74%', '38%', '52%', '58%']} />
              )}
              <tbody>
                {txRows.length === 0 && !txLoading ? (
                  <tr><td colSpan={6} className="empty-cell">ไม่มีรายการ</td></tr>
                ) : txRows.map((t) => (
                  <tr key={t.id}>
                    <td className="cell-sub">{shortDate(t.date)}</td>
                    <td><span className={`tag tag-${t.doc_type}`}>{t.doc_type_label}</span></td>
                    <td>
                      <Link href={`/products/${encodePart(t.part_num)}`}>{t.part_description || t.part_num}</Link>
                      <div className="cell-sub"><code>{t.part_num}</code></div>
                    </td>
                    <td className="num-cell">{num(t.qty, 2)}</td>
                    <td className="num-cell">{money(t.unit_cost)}</td>
                    <td className="num-cell">{money(t.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {tx?.has_more && (
            <div className="load-more">
              <button className="btn btn-secondary btn-sm"
                      onClick={() => { const n = txSkip + PAGE; setTxSkip(n); loadTx(n, true); }}>
                โหลดเพิ่ม (เหลืออีก {num(tx.total - txRows.length)})
              </button>
            </div>
          )}
        </div>
      )}
    </>
  );
}

/** โครงหน้าผู้ขาย — การ์ดตัวเลข + แท็บ + บล็อกข้อมูลบริษัท */
function VendorSkeleton() {
  return (
    <>
      <LoadingAnnounce label="กำลังโหลดข้อมูลผู้ขาย" />
      <div className="toolbar" style={{ marginBottom: 14 }}>
        <Link className="btn btn-secondary btn-sm" href="/vendors">← กลับไปรายชื่อผู้ขาย</Link>
      </div>
      <SkeletonStats count={4} />
      <div className="tabs">
        {TABS.map((t) => (
          <button key={t.key} className="tab" disabled>{t.label}</button>
        ))}
      </div>
      <div className="card">
        <div className="card-head">
          <div style={{ minWidth: 220 }}><div className="sk" style={{ width: '46%', height: 15 }} /></div>
        </div>
        <SkeletonBlock lines={6} />
      </div>
    </>
  );
}

function Stat({ label, value, unit, note }) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}{unit && <span className="unit"> {unit}</span>}</div>
      {note && <div className="stat-note">{note}</div>}
    </div>
  );
}

function KV({ label, value }) {
  return (
    <div className="kv">
      <span className="kv-label">{label}</span>
      <span className="kv-value">{value || '—'}</span>
    </div>
  );
}
