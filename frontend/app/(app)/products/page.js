'use client';

/**
 * ค้นหาสินค้า
 *
 * เปิดมาก็เห็นรายการทันที เรียงตามมูลค่าที่บริษัทเคยซื้อจริง
 * ช่องค้นหาไม่ต้องพิมพ์ให้ตรงเป๊ะ — พิมพ์รหัสไม่มีขีด สะกดผิดเล็กน้อย
 * หรือพิมพ์ชื่อผู้ขาย ก็เจอ (ฝั่ง backend ให้คะแนนความใกล้เคียงแล้วเรียงมาให้)
 */
import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { IconSearch } from '@/components/icons';
import { api, encodePart } from '@/lib/api';
import { money, num, pctLabel, pctTone, shortDate, shortMoney, sinceLabel } from '@/lib/format';
import RequestQuoteModal from '@/components/RequestQuoteModal';
import { Toast } from '@/components/ui';
import { LoadingAnnounce, SkeletonRows } from '@/components/Skeleton';

const PAGE = 40;

const SORTS = [
  { value: 'relevance', label: 'ตรงกับคำค้นที่สุด' },
  { value: 'amount', label: 'ซื้อเยอะที่สุด' },
  { value: 'recent', label: 'ซื้อล่าสุด' },
  { value: 'times', label: 'สั่งบ่อยที่สุด' },
  { value: 'spread', label: 'ราคาแกว่งมากที่สุด' },
  { value: 'part', label: 'รหัสสินค้า' },
];

export default function ProductsPage() {
  return (
    <Suspense fallback={<div className="empty">กำลังโหลด…</div>}>
      <ProductSearch />
    </Suspense>
  );
}

function ProductSearch() {
  const router = useRouter();
  const params = useSearchParams();

  const [term, setTerm] = useState(params.get('q') || '');
  const [sort, setSort] = useState('relevance');
  const [filters, setFilters] = useState({ single_source: false, price_volatile: false, has_price: false });
  const [data, setData] = useState(null);
  const [rows, setRows] = useState([]);
  const [skip, setSkip] = useState(0);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [quoteFor, setQuoteFor] = useState(null);
  const [toast, setToast] = useState(null);
  const reqId = useRef(0);

  const load = useCallback(async (nextSkip, append) => {
    const mine = ++reqId.current;
    setBusy(true);
    try {
      const query = { q: term.trim(), sort, skip: nextSkip, limit: PAGE };
      if (filters.single_source) query.single_source = true;
      if (filters.price_volatile) query.price_volatile = true;
      if (filters.has_price) query.has_price = true;

      const res = await api.searchItems(query);
      if (mine !== reqId.current) return;      // ผลเก่ามาช้า — ทิ้งไป
      setData(res);
      setRows((prev) => (append ? [...prev, ...res.items] : res.items));
      setError('');
    } catch (e) {
      if (mine === reqId.current) setError(e.message);
    } finally {
      if (mine === reqId.current) setBusy(false);
    }
  }, [term, sort, filters]);

  // พิมพ์แล้วรอ 300ms ค่อยยิง — ไม่ให้ยิงทุกตัวอักษร
  useEffect(() => {
    const t = setTimeout(() => { setSkip(0); load(0, false); }, term ? 300 : 0);
    return () => clearTimeout(t);
  }, [load, term]);

  function loadMore() {
    const next = skip + PAGE;
    setSkip(next);
    load(next, true);
  }

  const total = data?.total ?? 0;
  const fuzzy = data?.fuzzy_terms || [];

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
              placeholder="พิมพ์รหัสสินค้า คำอธิบาย หรือชื่อผู้ขาย — ไม่ต้องตรงเป๊ะ"
              aria-label="ค้นหาสินค้า"
              autoFocus
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
              <input
                type="checkbox"
                checked={filters.has_price}
                onChange={(e) => setFilters({ ...filters, has_price: e.target.checked })}
              />
              เฉพาะที่มีราคาล่าสุด
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={filters.single_source}
                onChange={(e) => setFilters({ ...filters, single_source: e.target.checked })}
              />
              ผู้ขายรายเดียว (เสี่ยง)
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={filters.price_volatile}
                onChange={(e) => setFilters({ ...filters, price_volatile: e.target.checked })}
              />
              ราคาแกว่งผิดปกติ
            </label>
            {term && (
              <button className="btn btn-secondary btn-sm" onClick={() => setTerm('')}>ล้างคำค้น</button>
            )}
          </div>

          <div className="result-line">
            พบ <strong>{num(total)}</strong> รหัสสินค้า
            {rows.length > 0 && <> · แสดงแล้ว {num(rows.length)}</>}
            {busy && <span className="muted"> · กำลังค้นหา…</span>}
            {busy && <LoadingAnnounce label="กำลังค้นหาสินค้า" />}
          </div>

          {fuzzy.length > 0 && (
            <div className="hint" style={{ marginTop: 6 }}>
              ไม่พบคำที่พิมพ์ตรง ๆ — แสดงผลของคำที่ใกล้เคียงแทน:{' '}
              <strong>{fuzzy.join(', ')}</strong>
            </div>
          )}
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="card">
        {rows.length === 0 && !busy ? (
          <div className="empty">
            <strong>ไม่พบสินค้าที่ตรงกับคำค้น</strong>
            ลองพิมพ์สั้นลง หรือใช้คำในคำอธิบายสินค้า เช่น “switch”, “cable”, “relay”
          </div>
        ) : (
          <div className="table-wrap">
            <table className="vendor-table">
              <thead>
                <tr>
                  <th style={{ minWidth: 340 }}>สินค้า</th>
                  <th style={{ textAlign: 'right', width: 140 }}>ราคาล่าสุด</th>
                  <th style={{ width: 130 }}>ซื้อล่าสุด</th>
                  <th style={{ textAlign: 'right', width: 130 }}>ต่ำสุดที่เคยได้</th>
                  <th style={{ textAlign: 'right', width: 80 }}>ผู้ขาย</th>
                  <th style={{ textAlign: 'right', width: 120 }}>ยอดซื้อรวม</th>
                  <th style={{ textAlign: 'right', width: 140 }}>ขอราคา</th>
                </tr>
              </thead>
              {/* ยังไม่เคยได้ข้อมูลเลย = วาดโครงแถวไว้ก่อน ไม่ปล่อยหน้าว่าง */}
              {rows.length === 0 && busy && (
                <SkeletonRows rows={10} cols={7} widths={['72%', '54%', '60%', '54%', '30%', '46%', '70%']} />
              )}
              <tbody>
                {rows.map((it) => (
                  <tr
                    key={it.part_num}
                    className="clickable"
                    onClick={() => router.push(`/products/${encodePart(it.part_num)}`)}
                  >
                    <td>
                      <div className="cell-title">{it.description || it.part_num}</div>
                      <div className="cell-sub">
                        <code>{it.part_num}</code>
                        {it.uom && <> · หน่วย {it.uom}</>}
                        {it.single_source && <span className="tag tag-warn">ผู้ขายรายเดียว</span>}
                        {it.price_volatile && <span className="tag tag-warn">ราคาแกว่ง</span>}
                      </div>
                    </td>
                    <td className="num-cell">
                      {it.last_price != null ? (
                        <>
                          <strong>{money(it.last_price)}</strong>
                          {it.last_vs_lowest_pct != null && (
                            <div className={`cell-sub delta ${pctTone(it.last_vs_lowest_pct)}`}>
                              {pctLabel(it.last_vs_lowest_pct)} จากถูกสุด
                            </div>
                          )}
                        </>
                      ) : <span className="muted">ยังไม่มีราคา</span>}
                    </td>
                    <td className="cell-sub">
                      {shortDate(it.last_buy_date)}
                      <div className="muted">{sinceLabel(it.last_buy_date)}</div>
                    </td>
                    <td className="num-cell">{money(it.lowest_price)}</td>
                    <td className="num-cell">{it.vendor_count}</td>
                    <td className="num-cell">{shortMoney(it.total_amount)}</td>
                    <td className="actions">
                      <button
                        className="btn btn-primary btn-sm"
                        onClick={(e) => { e.stopPropagation(); setQuoteFor(it); }}
                      >
                        ขอใบเสนอราคา
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {data?.has_more && (
        <div className="load-more">
          <button className="btn btn-secondary" onClick={loadMore} disabled={busy}>
            {busy ? 'กำลังโหลด…' : `โหลดเพิ่มอีก ${Math.min(PAGE, total - rows.length)} รายการ`}
          </button>
        </div>
      )}

      {quoteFor && (
        <RequestQuoteModal
          partNum={quoteFor.part_num}
          description={quoteFor.description}
          onClose={() => setQuoteFor(null)}
          onDone={(rfqId) => router.push(`/rfqs/${rfqId}`)}
          onError={(m) => setToast({ message: m, type: 'error' })}
        />
      )}

      <Toast {...(toast || {})} onDone={() => setToast(null)} />
    </>
  );
}
