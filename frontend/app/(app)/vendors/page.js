'use client';

/** รายชื่อผู้ขายจาก Epicor — ตารางปกติ ไม่ใช่ grid โหลดเพิ่มทีละชุด */
import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { IconSearch } from '@/components/icons';
import { api } from '@/lib/api';
import { num, shortDate, shortMoney, sinceLabel } from '@/lib/format';
import { LoadingAnnounce, SkeletonRows } from '@/components/Skeleton';
import OtdBadge from '@/components/OtdBadge';

const PAGE = 50;

const SORTS = [
  { value: 'amount', label: 'ยอดสั่งซื้อสูงสุด' },
  { value: 'recent', label: 'สั่งซื้อล่าสุด' },
  { value: 'parts', label: 'ขายของหลากหลายที่สุด' },
  { value: 'name', label: 'ชื่อผู้ขาย' },
];

export default function VendorsPage() {
  return (
    <Suspense fallback={<div className="empty">กำลังโหลด…</div>}>
      <VendorList />
    </Suspense>
  );
}

function VendorList() {
  const router = useRouter();
  const [term, setTerm] = useState('');
  const [sort, setSort] = useState('amount');
  const [onlyBuying, setOnlyBuying] = useState(true);
  const [onlyEmail, setOnlyEmail] = useState(false);
  const [onlyLate, setOnlyLate] = useState(false);
  const [data, setData] = useState(null);
  const [rows, setRows] = useState([]);
  const [skip, setSkip] = useState(0);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const reqId = useRef(0);

  const load = useCallback(async (nextSkip, append) => {
    const mine = ++reqId.current;
    setBusy(true);
    try {
      const res = await api.listVendors({
        q: term.trim(), sort, skip: nextSkip, limit: PAGE,
        has_purchase: onlyBuying ? true : undefined,
        has_email: onlyEmail ? true : undefined,
        // ต่ำกว่า 70% = "ต้องระวัง" ตามเกณฑ์เดียวกับป้ายสี
        otd_max: onlyLate ? 70 : undefined,
        reliable_only: onlyLate ? true : undefined,
      });
      if (mine !== reqId.current) return;
      setData(res);
      setRows((prev) => (append ? [...prev, ...res.items] : res.items));
      setError('');
    } catch (e) {
      if (mine === reqId.current) setError(e.message);
    } finally {
      if (mine === reqId.current) setBusy(false);
    }
  }, [term, sort, onlyBuying, onlyEmail, onlyLate]);

  useEffect(() => {
    const t = setTimeout(() => { setSkip(0); load(0, false); }, term ? 300 : 0);
    return () => clearTimeout(t);
  }, [load, term]);

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
              placeholder="ชื่อผู้ขาย รหัสผู้ขาย เลขผู้เสียภาษี ชื่อผู้ติดต่อ หรืออีเมล…"
              aria-label="ค้นหาผู้ขาย"
            />
          </div>

          <div className="filter-row">
            <label className="field-inline">
              <span>เรียงตาม</span>
              <select value={sort} onChange={(e) => setSort(e.target.value)}>
                {SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </label>
            <label className="checkbox">
              <input type="checkbox" checked={onlyBuying} onChange={(e) => setOnlyBuying(e.target.checked)} />
              เฉพาะรายที่เคยสั่งซื้อจริง
            </label>
            <label className="checkbox">
              <input type="checkbox" checked={onlyEmail} onChange={(e) => setOnlyEmail(e.target.checked)} />
              เฉพาะรายที่มีอีเมล
            </label>
            <label className="checkbox">
              <input type="checkbox" checked={onlyLate} onChange={(e) => setOnlyLate(e.target.checked)} />
              เฉพาะรายที่ส่งตรงเวลาต่ำกว่า 70%
            </label>
          </div>

          <div className="result-line">
            พบ <strong>{num(data?.total ?? 0)}</strong> ราย
            {rows.length > 0 && <> · แสดงแล้ว {num(rows.length)}</>}
            {busy && <span className="muted"> · กำลังโหลด…</span>}
            {busy && <LoadingAnnounce label="กำลังโหลดรายชื่อผู้ขาย" />}
          </div>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="card">
        {rows.length === 0 && !busy ? (
          <div className="empty"><strong>ไม่พบผู้ขายที่ตรงกับคำค้น</strong>ลองใช้คำที่สั้นลง</div>
        ) : (
          <div className="table-wrap">
            <table className="vendor-table">
              <thead>
                <tr>
                  <th style={{ minWidth: 300 }}>ผู้ขาย</th>
                  <th style={{ minWidth: 200 }}>ติดต่อ</th>
                  <th style={{ minWidth: 190 }}>ส่งตรงเวลา</th>
                  <th style={{ textAlign: 'right', width: 130 }}>ยอดสั่งซื้อ</th>
                  <th style={{ textAlign: 'right', width: 90 }}>ใบสั่งซื้อ</th>
                  <th style={{ textAlign: 'right', width: 90 }}>รหัสสินค้า</th>
                  <th style={{ width: 130 }}>สั่งล่าสุด</th>
                  <th style={{ width: 90 }}>เครดิต</th>
                </tr>
              </thead>
              {rows.length === 0 && busy && (
                <SkeletonRows rows={12} cols={8} widths={['70%', '62%', '56%', '48%', '30%', '30%', '58%', '34%']} />
              )}
              <tbody>
                {rows.map((v) => (
                  <tr
                    key={v.vendor_key}
                    className="clickable"
                    onClick={() => router.push(`/vendors/${encodeURIComponent(v.vendor_key)}`)}
                  >
                    <td>
                      <div className="cell-title">{v.name}</div>
                      <div className="cell-sub">
                        <code>{v.vendor_id}</code>
                        {v.inactive && <span className="tag tag-warn">ปิดใช้งาน</span>}
                        {!v.has_purchase && <span className="tag">ยังไม่เคยสั่งซื้อ</span>}
                      </div>
                    </td>
                    <td className="cell-sub">
                      {v.emails[0] || <span className="muted">ไม่มีอีเมล</span>}
                      {v.phones[0] && <div className="muted">{v.phones[0]}</div>}
                    </td>
                    <td><OtdBadge delivery={v.delivery} /></td>
                    <td className="num-cell">{shortMoney(v.po_amount)}</td>
                    <td className="num-cell">{num(v.po_count)}</td>
                    <td className="num-cell">{num(v.distinct_parts)}</td>
                    <td className="cell-sub">
                      {shortDate(v.last_buy_date)}
                      <div className="muted">{sinceLabel(v.last_buy_date)}</div>
                    </td>
                    <td className="cell-sub">{v.terms_code || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {data?.has_more && (
        <div className="load-more">
          <button
            className="btn btn-secondary"
            disabled={busy}
            onClick={() => { const n = skip + PAGE; setSkip(n); load(n, true); }}
          >
            {busy ? 'กำลังโหลด…' : `โหลดเพิ่มอีก ${Math.min(PAGE, data.total - rows.length)} ราย`}
          </button>
        </div>
      )}
    </>
  );
}
