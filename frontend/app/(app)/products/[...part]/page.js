'use client';

/**
 * รายละเอียดสินค้า 1 รหัส
 *
 * ตอบสามคำถามที่ฝ่ายจัดซื้อถามบ่อยที่สุด ในหน้าเดียว
 *   1. ตอนนี้ราคาเท่าไร  — การ์ดราคาล่าสุด / ต่ำสุด / สูงสุด
 *   2. ใครขายได้บ้าง     — ตารางผู้ขายพร้อมราคาล่าสุดของแต่ละราย
 *   3. ที่ผ่านมาซื้อยังไง — ตาราง transaction จริงทุกใบ (สั่งซื้อ/รับของ/ใบแจ้งหนี้)
 *
 * ใช้ route แบบ catch-all เพราะรหัสสินค้าของ Epicor มี "/" ปนได้
 */
import { use, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { money, num, pctLabel, pctTone, shortDate, shortMoney, sinceLabel } from '@/lib/format';
import RequestQuoteModal from '@/components/RequestQuoteModal';
import { Toast } from '@/components/ui';
import { usePageTitle } from '@/components/RequireAdmin';
import PriceHistoryChart from '@/components/PriceHistoryChart';
import { LoadingAnnounce, SkeletonRows, SkeletonStats } from '@/components/Skeleton';
import OtdBadge from '@/components/OtdBadge';

const TX_PAGE = 25;

const TABS = [
  { key: '', label: 'ทั้งหมด' },
  { key: 'PO_LINE', label: 'ใบสั่งซื้อ' },
  { key: 'RECEIPT_LINE', label: 'รับของ' },
  { key: 'AP_INVOICE_LINE', label: 'ใบแจ้งหนี้' },
];

export default function ItemDetailPage({ params }) {
  const { part } = use(params);
  const partNum = decodeURIComponent((part || []).join('/'));
  return <ItemDetail partNum={partNum} />;
}

function ItemDetail({ partNum }) {
  const router = useRouter();
  const [item, setItem] = useState(null);
  const [error, setError] = useState('');
  const [asking, setAsking] = useState(false);
  const [picked, setPicked] = useState(new Set());
  const [toast, setToast] = useState(null);

  const [docType, setDocType] = useState('');
  const [tx, setTx] = useState(null);
  const [txRows, setTxRows] = useState([]);
  const [txSkip, setTxSkip] = useState(0);
  const [txLoading, setTxLoading] = useState(true);
  const [history, setHistory] = useState(null);

  useEffect(() => {
    let alive = true;
    api.getItem(partNum)
      .then((d) => { if (alive) setItem(d); })
      .catch((e) => { if (alive) setError(e.message); });
    api.itemPriceHistory(partNum)
      .then((d) => { if (alive) setHistory(d.points || []); })
      .catch(() => { if (alive) setHistory([]); });
    return () => { alive = false; };
  }, [partNum]);

  const loadTx = useCallback(async (skip, append) => {
    setTxLoading(true);
    try {
      const res = await api.itemTransactions(partNum, {
        doc_type: docType || undefined, skip, limit: TX_PAGE,
      });
      setTx(res);
      setTxRows((prev) => (append ? [...prev, ...res.items] : res.items));
    } finally {
      setTxLoading(false);
    }
  }, [partNum, docType]);

  useEffect(() => { setTxSkip(0); loadTx(0, false).catch((e) => setError(e.message)); }, [loadTx]);

  usePageTitle(item?.description || partNum, item ? `รหัส ${partNum}` : '');

  const price = item?.price;
  const vendors = useMemo(() => item?.vendors || [], [item]);
  const bestVendor = useMemo(
    () => vendors.find((v) => v.last_unit_cost != null) || null,
    [vendors],
  );

  if (error) {
    return (
      <>
        <div className="alert alert-error">{error}</div>
        <Link className="btn btn-secondary" href="/products">กลับไปค้นหาสินค้า</Link>
      </>
    );
  }
  if (!item) return <ItemSkeleton partNum={partNum} />;

  const allPicked = picked.size > 0 && picked.size === vendors.length;

  return (
    <>
      <div className="toolbar" style={{ marginBottom: 14 }}>
        <Link className="btn btn-secondary btn-sm" href="/products">← กลับไปค้นหาสินค้า</Link>
        <div className="spacer" />
        <button
          className="btn btn-primary"
          onClick={() => { setPicked(new Set(vendors.map((v) => v.vendor_key))); setAsking(true); }}
          disabled={vendors.length === 0}
        >
          ขอใบเสนอราคาจากทุกราย ({vendors.length})
        </button>
      </div>

      {/* ---------- ราคา ---------- */}
      <div className="stat-row" style={{ marginBottom: 16 }}>
        <PriceCard
          label="ราคาล่าสุดที่ซื้อ"
          point={price?.last}
          tone="primary"
          note={price?.last_vs_lowest_pct != null
            ? `${pctLabel(price.last_vs_lowest_pct)} เทียบราคาถูกสุดที่เคยได้`
            : ''}
          noteTone={pctTone(price?.last_vs_lowest_pct)}
        />
        <PriceCard label="ถูกที่สุดที่เคยซื้อได้" point={price?.lowest} tone="good" />
        <PriceCard label="แพงที่สุดที่เคยซื้อ" point={price?.highest} tone="warn" />
        <div className="stat-card">
          <div className="stat-label">สรุปการซื้อ</div>
          <div className="stat-value">{num(item.times_ordered)} <span className="unit">ครั้ง</span></div>
          <div className="stat-note">
            รวม {shortMoney(item.total_amount)} บาท · {num(item.total_qty)} {item.uom}
            <br />ผู้ขาย {item.vendor_count} ราย
            {price?.multi_currency && <><br /><span className="tag tag-warn">ซื้อหลายสกุลเงิน เทียบราคาตรง ๆ ไม่ได้</span></>}
          </div>
        </div>
      </div>

      {bestVendor && price?.last?.vendor_id && bestVendor.vendor_id !== price.last.vendor_id && (
        <div className="alert alert-info" style={{ marginBottom: 16 }}>
          ครั้งล่าสุดซื้อจาก <strong>{price.last.vendor_name}</strong> ที่ {money(price.last.unit_cost)} บาท
          แต่ <strong>{bestVendor.name}</strong> เคยขายให้ที่ {money(bestVendor.last_unit_cost)} บาท
          — ควรขอราคาจากทั้งสองรายเพื่อเทียบ
        </div>
      )}

      {/* ---------- ผู้ขาย ---------- */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head">
          <div>
            <h2>ผู้ขายที่เคยขายสินค้านี้ให้เรา</h2>
            <div className="cell-sub">
              เรียงจากราคาล่าสุดถูกสุด · ดูความตรงเวลาประกอบก่อนตัดสินใจ ·
              ติ๊กเลือกแล้วกดขอใบเสนอราคา
            </div>
          </div>
          <div className="toolbar">
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => setPicked(allPicked ? new Set() : new Set(vendors.map((v) => v.vendor_key)))}
              disabled={vendors.length === 0}
            >
              {allPicked ? 'ยกเลิกเลือกทั้งหมด' : 'เลือกทั้งหมด'}
            </button>
            <button
              className="btn btn-primary btn-sm"
              disabled={picked.size === 0}
              onClick={() => setAsking(true)}
            >
              ขอใบเสนอราคา ({picked.size})
            </button>
          </div>
        </div>

        {vendors.length === 0 ? (
          <div className="empty">ยังไม่มีประวัติว่าใครเคยขายรหัสนี้ให้เรา</div>
        ) : (
          <div className="table-wrap">
            <table className="vendor-table">
              <thead>
                <tr>
                  <th style={{ width: 44 }}>เลือก</th>
                  <th style={{ minWidth: 260 }}>ผู้ขาย</th>
                  <th style={{ textAlign: 'right', width: 140 }}>ราคาล่าสุดของรายนี้</th>
                  <th style={{ minWidth: 185 }}>ส่งตรงเวลา (ทุกสินค้า)</th>
                  <th style={{ minWidth: 150 }}>ตรงเวลาเฉพาะสินค้านี้</th>
                  <th style={{ width: 130 }}>ขายล่าสุด</th>
                  <th style={{ textAlign: 'right', width: 120 }}>ต่ำสุด</th>
                  <th style={{ textAlign: 'right', width: 80 }}>ครั้ง</th>
                </tr>
              </thead>
              <tbody>
                {vendors.map((v, i) => (
                  <tr key={v.vendor_key} className={i === 0 && v.last_unit_cost != null ? 'row-best' : ''}>
                    <td>
                      <input
                        type="checkbox"
                        checked={picked.has(v.vendor_key)}
                        onChange={() => setPicked((p) => {
                          const n = new Set(p);
                          if (n.has(v.vendor_key)) n.delete(v.vendor_key); else n.add(v.vendor_key);
                          return n;
                        })}
                        aria-label={`เลือก ${v.name}`}
                      />
                    </td>
                    <td>
                      <Link className="cell-title" href={`/vendors/${encodeURIComponent(v.vendor_key)}`}>
                        {v.name || v.vendor_id}
                      </Link>
                      <div className="cell-sub">
                        <code>{v.vendor_id}</code>
                        {i === 0 && v.last_unit_cost != null && (
                          <span className="tag tag-ok">ราคาล่าสุดถูกสุด</span>
                        )}
                      </div>
                    </td>
                    <td className="num-cell">
                      {v.last_unit_cost != null
                        ? <strong>{money(v.last_unit_cost)}</strong>
                        : <span className="muted">—</span>}
                    </td>
                    <td><OtdBadge delivery={v.delivery} /></td>
                    <td className="cell-sub">
                      {v.delivery_this_item ? (
                        <>
                          <span className="cell-title">{num(v.delivery_this_item.otd_pct, 1)}%</span>
                          <div className="muted">
                            {num(v.delivery_this_item.on_time)}/{num(v.delivery_this_item.releases)} งวด
                            {v.delivery_this_item.median_days_late != null
                              && ` · ปกติ ${num(v.delivery_this_item.median_days_late, 1)} วัน`}
                          </div>
                        </>
                      ) : <span className="muted">ไม่มีประวัติ</span>}
                    </td>
                    <td className="cell-sub">
                      {shortDate(v.last_buy_date)}
                      <div className="muted">{sinceLabel(v.last_buy_date)}</div>
                    </td>
                    <td className="num-cell">{money(v.min_unit_cost)}</td>
                    <td className="num-cell">{num(v.times)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ---------- กราฟราคา ---------- */}
      {history && history.length > 1 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-head">
            <div>
              <h2>ราคาที่ซื้อจริงย้อนหลัง</h2>
              <div className="cell-sub">แต่ละจุดคือใบสั่งซื้อ 1 บรรทัด · สีต่างกันคือคนละผู้ขาย</div>
            </div>
          </div>
          <div className="card-body">
            <PriceHistoryChart points={history} uom={item.uom} />
          </div>
        </div>
      )}

      {/* ---------- transaction ---------- */}
      <div className="card">
        <div className="card-head">
          <div>
            <h2>รายการเคลื่อนไหวทั้งหมด</h2>
            <div className="cell-sub">ทุกใบสั่งซื้อ การรับของ และใบแจ้งหนี้ที่อ้างถึงรหัสนี้</div>
          </div>
        </div>

        {item.summary?.length > 0 && (
          <div className="card-body" style={{ paddingBottom: 0 }}>
            <div className="mini-stats">
              {item.summary.map((s) => (
                <div key={s.doc_type} className="mini-stat">
                  <span className="mini-label">{s.doc_type_label}</span>
                  <span className="mini-value">{num(s.lines)} รายการ</span>
                  <span className="mini-note">{shortMoney(s.amount)} บาท · ล่าสุด {shortDate(s.last_date)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="tabs">
          {TABS.map((t) => (
            <button
              key={t.key || 'all'}
              className={`tab${docType === t.key ? ' active' : ''}`}
              onClick={() => setDocType(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th style={{ width: 110 }}>วันที่</th>
                <th style={{ width: 110 }}>ประเภท</th>
                <th style={{ minWidth: 220 }}>ผู้ขาย</th>
                <th style={{ width: 120 }}>เอกสาร</th>
                <th style={{ textAlign: 'right', width: 90 }}>จำนวน</th>
                <th style={{ textAlign: 'right', width: 130 }}>ราคา/หน่วย</th>
                <th style={{ textAlign: 'right', width: 140 }}>มูลค่า</th>
              </tr>
            </thead>
            {txRows.length === 0 && txLoading && (
              <SkeletonRows rows={8} cols={7} widths={['62%', '48%', '72%', '58%', '38%', '52%', '58%']} />
            )}
            <tbody>
              {txRows.length === 0 && !txLoading ? (
                <tr><td colSpan={7} className="empty-cell">ไม่มีรายการในหมวดนี้</td></tr>
              ) : txRows.map((t) => (
                <tr key={t.id}>
                  <td className="cell-sub">{shortDate(t.date)}</td>
                  <td><span className={`tag tag-${t.doc_type}`}>{t.doc_type_label}</span></td>
                  <td>
                    <Link href={`/vendors/${encodeURIComponent(t.vendor_key)}`}>{t.vendor_name}</Link>
                  </td>
                  <td className="cell-sub">
                    {t.po_num ? <>PO {t.po_num}{t.po_line ? `/${t.po_line}` : ''}</> : null}
                    {t.pack_slip ? <>ใบส่งของ {t.pack_slip}</> : null}
                    {t.invoice_num ? <>INV {t.invoice_num}</> : null}
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
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => { const n = txSkip + TX_PAGE; setTxSkip(n); loadTx(n, true); }}
            >
              โหลดเพิ่ม (เหลืออีก {num(tx.total - txRows.length)} รายการ)
            </button>
          </div>
        )}
      </div>

      {asking && (
        <RequestQuoteModal
          partNum={partNum}
          description={item.description}
          uom={item.uom}
          lastPrice={price?.last?.unit_cost}
          vendors={vendors}
          preselected={[...picked]}
          onClose={() => setAsking(false)}
          onDone={(rfqId) => router.push(`/rfqs/${rfqId}`)}
          onError={(m) => setToast({ message: m, type: 'error' })}
        />
      )}

      <Toast {...(toast || {})} onDone={() => setToast(null)} />
    </>
  );
}

/** โครงหน้าสินค้า — การ์ดราคา 4 ใบ + ตารางผู้ขาย + ตารางรายการเคลื่อนไหว */
function ItemSkeleton({ partNum }) {
  return (
    <>
      <LoadingAnnounce label={`กำลังโหลดข้อมูลสินค้า ${partNum}`} />
      <div className="toolbar" style={{ marginBottom: 14 }}>
        <Link className="btn btn-secondary btn-sm" href="/products">← กลับไปค้นหาสินค้า</Link>
      </div>

      <SkeletonStats count={4} />

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head">
          <div style={{ minWidth: 260 }}>
            <div className="sk" style={{ width: '52%', height: 15 }} />
            <div className="sk" style={{ width: '72%' }} />
          </div>
        </div>
        <div className="table-wrap">
          <table className="vendor-table">
            <thead>
              <tr>
                <th style={{ width: 44 }}>&nbsp;</th>
                <th style={{ minWidth: 260 }}>ผู้ขาย</th>
                <th style={{ width: 140 }}>&nbsp;</th>
                <th style={{ width: 130 }}>&nbsp;</th>
                <th style={{ width: 120 }}>&nbsp;</th>
                <th style={{ width: 120 }}>&nbsp;</th>
              </tr>
            </thead>
            <SkeletonRows rows={4} cols={7} widths={['24%', '76%', '54%', '62%', '56%', '58%', '42%']} />
          </table>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <div style={{ minWidth: 260 }}>
            <div className="sk" style={{ width: '46%', height: 15 }} />
            <div className="sk" style={{ width: '68%' }} />
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th style={{ width: 110 }}>วันที่</th>
                <th style={{ width: 110 }}>ประเภท</th>
                <th style={{ minWidth: 220 }}>ผู้ขาย</th>
                <th style={{ width: 120 }}>เอกสาร</th>
                <th style={{ width: 90 }}>&nbsp;</th>
                <th style={{ width: 130 }}>&nbsp;</th>
                <th style={{ width: 140 }}>&nbsp;</th>
              </tr>
            </thead>
            <SkeletonRows rows={10} cols={7} widths={['62%', '48%', '72%', '58%', '38%', '52%', '58%']} />
          </table>
        </div>
      </div>
    </>
  );
}

function PriceCard({ label, point, tone, note, noteTone }) {
  return (
    <div className={`stat-card stat-${tone || ''}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">
        {point?.unit_cost != null ? money(point.unit_cost) : '—'}
        <span className="unit"> {point?.currency || 'THB'}</span>
      </div>
      <div className="stat-note">
        {point?.date ? (
          <>
            {shortDate(point.date)} · {sinceLabel(point.date)}
            {point.vendor_name && <><br />{point.vendor_name}</>}
            {point.po_num && <> · PO {point.po_num}</>}
          </>
        ) : 'ยังไม่เคยมีราคาซื้อ'}
        {note && <div className={`delta ${noteTone || ''}`}>{note}</div>}
      </div>
    </div>
  );
}
