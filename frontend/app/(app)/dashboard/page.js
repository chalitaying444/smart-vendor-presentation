'use client';

/** ภาพรวม — ตัวเลขที่ฝ่ายจัดซื้อดูก่อนเริ่มงาน แล้วกดเข้าไปทำต่อได้ทันที */
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api, encodePart } from '@/lib/api';
import { money, num, pctLabel, pctTone, shortDate, shortMoney } from '@/lib/format';
import { dateTime, sinceLabel } from '@/lib/format';
import { useAuth } from '@/components/AuthContext';
import { LoadingAnnounce, SkeletonRows, SkeletonStats } from '@/components/Skeleton';
import OtdBadge from '@/components/OtdBadge';
import { Toast } from '@/components/ui';
import ParetoChart from '@/components/charts/ParetoChart';
import SpendTrendChart from '@/components/charts/SpendTrendChart';

export default function DashboardPage() {
  const user = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const [toast, setToast] = useState(null);
  const [pareto, setPareto] = useState(null);
  const [trend, setTrend] = useState(null);

  useEffect(() => {
    api.overview().then(setData).catch((e) => setError(e.message));
    // สองชุดนี้โหลดแยกและไม่ทำให้หน้าพังถ้าล้มเหลว — เป็นส่วนเสริม ไม่ใช่แกนของหน้า
    api.pareto().then(setPareto).catch(() => {});
    api.spendTrend().then(setTrend).catch(() => {});
  }, []);

  async function refresh() {
    setRefreshing(true);
    try {
      setData(await api.refreshOverview());
      const [p, t] = await Promise.all([
        api.pareto().catch(() => null),
        api.spendTrend().catch(() => null),
      ]);
      if (p) setPareto(p);
      if (t) setTrend(t);
      setToast({ message: 'คำนวณข้อมูลสรุปใหม่แล้ว' });
    } catch (e) {
      setToast({ message: e.message, type: 'error' });
    } finally {
      setRefreshing(false);
    }
  }

  if (error) return <div className="alert alert-error">{error}</div>;

  // ยังไม่ได้ข้อมูล — วาดโครงหน้าไว้ก่อน ไม่ปล่อยจอว่าง
  if (!data) return <DashboardSkeleton />;

  const c = data.counts;
  const empty = !c.items;
  const snap = data.snapshot;

  return (
    <>
      {snap?.built_at && (
        <div className="snapshot-bar">
          <span>
            ตัวเลขสรุปคำนวณไว้เมื่อ <strong>{dateTime(snap.built_at)}</strong>
            {' '}({sinceLabel(snap.built_at)}) · อัปเดตอัตโนมัติวันละครั้ง
          </span>
          {snap.stale && <span className="tag tag-warn">กำลังคำนวณรอบใหม่</span>}
          <span className="spacer" />
          <button className="btn btn-secondary btn-sm" onClick={refresh} disabled={refreshing}>
            {refreshing ? 'กำลังคำนวณ…' : 'คำนวณใหม่ตอนนี้'}
          </button>
        </div>
      )}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-body">
          <h2 style={{ marginBottom: 4 }}>สวัสดี {user?.display_name || user?.email}</h2>
          <p className="cell-sub">
            ข้อมูลทั้งหมดมาจากฐานข้อมูล <code>epicor_procurement</code> ที่สคริปต์ ETL
            ดึงมาจาก Epicor ERPPRD — เริ่มจากค้นหาสินค้าที่ต้องการซื้อ แล้วขอใบเสนอราคาได้เลย
          </p>
        </div>
      </div>

      {empty && (
        <div className="alert alert-error" style={{ marginBottom: 16 }}>
          ยังไม่มีข้อมูลในฐานข้อมูล — รัน <code>python scripts\\04_etl_to_mongodb.py</code>{' '}
          ของโปรเจกต์ epicorExploreData ก่อน แล้วรีเฟรชหน้านี้
        </div>
      )}

      <div className="stat-row" style={{ marginBottom: 16 }}>
        <Stat label="รหัสสินค้า" value={num(c.items)} note={`มีราคาอ้างอิง ${num(c.priced_items)} รหัส`} href="/products" />
        <Stat label="ผู้ขาย" value={num(c.vendors)} note="จากทะเบียนผู้ขายใน Epicor" href="/vendors" />
        <Stat label="รายการเคลื่อนไหว" value={num(c.transactions)} note="ใบสั่งซื้อ + รับของ + ใบแจ้งหนี้" />
        <Stat label="ใบขอราคา" value="เปิดหน้า RFQ" note="ขอราคา เทียบราคา ประกาศผู้ชนะ" href="/rfqs" />
      </div>

      {data.by_doc_type?.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-head"><h2>มูลค่าแยกตามชนิดเอกสาร</h2></div>
          <div className="card-body">
            <div className="mini-stats">
              {data.by_doc_type.map((s) => (
                <div key={s.doc_type} className="mini-stat">
                  <span className="mini-label">{s.doc_type_label}</span>
                  <span className="mini-value">{shortMoney(s.amount)} บาท</span>
                  <span className="mini-note">{num(s.lines)} รายการ · ล่าสุด {shortDate(s.last_date)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {!empty && (trend || pareto) && (
        <div className="chart-grid" style={{ marginBottom: 16 }}>
          {trend && (
            <div className="card">
              <div className="card-head">
                <div>
                  <h2>มูลค่าซื้อรายปี</h2>
                  <p className="cell-sub">นับจากบรรทัดใบสั่งซื้อ · หน่วยล้านบาท</p>
                </div>
              </div>
              <div className="card-body">
                <SpendTrendChart data={trend} />
              </div>
            </div>
          )}
          {pareto && (
            <div className="card">
              <div className="card-head">
                <div>
                  <h2>เงินกระจุกอยู่ที่กี่รายแรก</h2>
                  <p className="cell-sub">
                    เส้นยิ่งชัน ยิ่งคุมงบได้ด้วยการดูแลรายการน้อยราย
                  </p>
                </div>
              </div>
              <div className="card-body">
                <ParetoChart data={pareto} />
              </div>
            </div>
          )}
        </div>
      )}

      <div className="two-col">
        <div className="card">
          <div className="card-head">
            <div>
              <h2>สินค้าที่ซื้อมากที่สุด</h2>
              <div className="cell-sub">เรียงตามมูลค่าสะสม</div>
            </div>
            <Link className="btn btn-secondary btn-sm" href="/products">ดูทั้งหมด</Link>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>สินค้า</th><th style={{ textAlign: 'right', width: 120 }}>ราคาล่าสุด</th>
                  <th style={{ textAlign: 'right', width: 110 }}>ยอดรวม</th></tr>
              </thead>
              <tbody>
                {data.top_items.map((it) => (
                  <tr key={it.part_num}>
                    <td>
                      <Link className="cell-title" href={`/products/${encodePart(it.part_num)}`}>
                        {it.description || it.part_num}
                      </Link>
                      <div className="cell-sub"><code>{it.part_num}</code></div>
                    </td>
                    <td className="num-cell">{money(it.last_price)}</td>
                    <td className="num-cell">{shortMoney(it.total_amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div>
              <h2>ผู้ขายรายใหญ่</h2>
              <div className="cell-sub">เรียงตามยอดสั่งซื้อ</div>
            </div>
            <Link className="btn btn-secondary btn-sm" href="/vendors">ดูทั้งหมด</Link>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>ผู้ขาย</th><th style={{ textAlign: 'right', width: 110 }}>ยอดสั่งซื้อ</th>
                  <th style={{ textAlign: 'right', width: 90 }}>รหัสสินค้า</th></tr>
              </thead>
              <tbody>
                {data.top_vendors.map((v) => (
                  <tr key={v.vendor_key}>
                    <td>
                      <Link className="cell-title" href={`/vendors/${encodeURIComponent(v.vendor_key)}`}>
                        {v.name}
                      </Link>
                      <div className="cell-sub"><code>{v.vendor_id}</code></div>
                    </td>
                    <td className="num-cell">{shortMoney(v.po_amount)}</td>
                    <td className="num-cell">{num(v.distinct_parts)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {data.delivery?.has_data && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-head">
            <div>
              <h2>การส่งของตรงเวลา</h2>
              <div className="cell-sub">
                วัดเป็นงวดส่งของ (PO Release) · งวดที่ยังไม่ส่งไม่ถูกนับใน % จึงแสดงงวดค้างส่งแยกไว้
              </div>
            </div>
            <Link className="btn btn-secondary btn-sm" href="/vendors">ดูรายผู้ขาย</Link>
          </div>
          <div className="card-body">
            <div className="mini-stats">
              <div className="mini-stat">
                <span className="mini-label">ส่งตรงเวลาทั้งบริษัท</span>
                <span className="mini-value">{num(data.delivery.otd_pct, 1)}%</span>
                <span className="mini-note">
                  {num(data.delivery.on_time)} จาก {num(data.delivery.measured)} งวดที่วัดผลได้
                </span>
              </div>
              <div className="mini-stat">
                <span className="mini-label">ยังค้างส่ง</span>
                <span className="mini-value">{num(data.delivery.overdue_releases)} งวด</span>
                <span className="mini-note">เลยกำหนดแล้วและยังไม่ได้รับของ</span>
              </div>
              {(data.delivery.by_status || []).slice(0, 3).map((s2) => (
                <div key={s2.status} className="mini-stat">
                  <span className="mini-label">{s2.status}</span>
                  <span className="mini-value">{num(s2.releases)} งวด</span>
                  <span className="mini-note">{s2.percent}%</span>
                </div>
              ))}
            </div>
          </div>

          <div className="two-col" style={{ gap: 0 }}>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>ผู้ขายที่ควรตามงาน</th><th style={{ minWidth: 180 }}>ส่งตรงเวลา</th></tr>
                </thead>
                <tbody>
                  {data.delivery.worst_vendors.map((v) => (
                    <tr key={v.vendor_key}>
                      <td>
                        <Link className="cell-title" href={`/vendors/${encodeURIComponent(v.vendor_key)}`}>
                          {v.name}
                        </Link>
                        <div className="cell-sub"><code>{v.vendor_id}</code></div>
                      </td>
                      <td><OtdBadge delivery={v} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>ผู้ขายที่ส่งตรงเวลาที่สุด</th><th style={{ minWidth: 180 }}>ส่งตรงเวลา</th></tr>
                </thead>
                <tbody>
                  {data.delivery.best_vendors.map((v) => (
                    <tr key={v.vendor_key}>
                      <td>
                        <Link className="cell-title" href={`/vendors/${encodeURIComponent(v.vendor_key)}`}>
                          {v.name}
                        </Link>
                        <div className="cell-sub"><code>{v.vendor_id}</code></div>
                      </td>
                      <td><OtdBadge delivery={v} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card-body" style={{ paddingTop: 0 }}>
            <div className="hint">
              นับเฉพาะผู้ขายที่มีอย่างน้อย {num(data.delivery.min_reliable_releases)} งวด —
              รายที่มีงวดน้อยเปอร์เซ็นต์แกว่งเกินกว่าจะเอามาจัดอันดับ
            </div>
          </div>
        </div>
      )}

      {data.delivery?.most_overdue?.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-head">
            <div>
              <h2>งวดที่ค้างส่งนานที่สุด</h2>
              <div className="cell-sub">เลยกำหนดแล้วแต่ยังไม่ได้รับของ — ควรตามงานก่อน</div>
            </div>
          </div>
          <div className="table-wrap">
            <table className="vendor-table">
              <thead>
                <tr>
                  <th style={{ minWidth: 260 }}>สินค้า</th>
                  <th style={{ minWidth: 220 }}>ผู้ขาย</th>
                  <th style={{ width: 120 }}>กำหนดส่ง</th>
                  <th style={{ textAlign: 'right', width: 110 }}>ค้างมา</th>
                  <th style={{ textAlign: 'right', width: 130 }}>มูลค่า</th>
                </tr>
              </thead>
              <tbody>
                {data.delivery.most_overdue.map((d) => (
                  <tr key={d.id}>
                    <td>
                      <Link className="cell-title" href={`/products/${encodePart(d.part_num)}`}>
                        {d.part_description || d.part_num}
                      </Link>
                      <div className="cell-sub">PO {d.po_num}/{d.po_line} · งวดที่ {d.po_rel_num}</div>
                    </td>
                    <td>
                      <Link href={`/vendors/${encodeURIComponent(d.vendor_key)}`}>{d.vendor_name}</Link>
                    </td>
                    <td className="cell-sub">{shortDate(d.promise_date)}</td>
                    <td className="num-cell otd-overdue">{num(d.days_overdue)} วัน</td>
                    <td className="num-cell">{money(d.value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {data.price_volatile?.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="card-head">
            <div>
              <h2>ของที่ราคาแกว่งมากที่สุด</h2>
              <div className="cell-sub">
                ราคาสูงสุดต่างจากต่ำสุดหลายเท่า — ควรขอราคาใหม่ก่อนสั่งรอบหน้า
              </div>
            </div>
          </div>
          <div className="table-wrap">
            <table className="vendor-table">
              <thead>
                <tr>
                  <th style={{ minWidth: 300 }}>สินค้า</th>
                  <th style={{ textAlign: 'right', width: 120 }}>ราคาล่าสุด</th>
                  <th style={{ textAlign: 'right', width: 120 }}>ถูกสุดที่เคยได้</th>
                  <th style={{ textAlign: 'right', width: 140 }}>ต่างจากถูกสุด</th>
                  <th style={{ textAlign: 'right', width: 90 }}>ผู้ขาย</th>
                </tr>
              </thead>
              <tbody>
                {data.price_volatile.map((it) => (
                  <tr key={it.part_num}>
                    <td>
                      <Link className="cell-title" href={`/products/${encodePart(it.part_num)}`}>
                        {it.description || it.part_num}
                      </Link>
                      <div className="cell-sub"><code>{it.part_num}</code></div>
                    </td>
                    <td className="num-cell">{money(it.last_price)}</td>
                    <td className="num-cell">{money(it.lowest_price)}</td>
                    <td className="num-cell">
                      <span className={`delta ${pctTone(it.last_vs_lowest_pct)}`}>
                        {pctLabel(it.last_vs_lowest_pct)}
                      </span>
                    </td>
                    <td className="num-cell">{it.vendor_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <Toast {...(toast || {})} onDone={() => setToast(null)} />
    </>
  );
}

/** โครงหน้าภาพรวม — โครงสร้างเดียวกับของจริง เนื้อหาจะไม่กระโดดตอนข้อมูลมาถึง */
function DashboardSkeleton() {
  return (
    <>
      <LoadingAnnounce label="กำลังโหลดภาพรวม" />
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-body">
          <div className="sk" style={{ width: '32%', height: 18 }} />
          <div className="sk" style={{ width: '78%' }} />
        </div>
      </div>

      <SkeletonStats count={4} />

      <div className="two-col">
        {[
          { title: 'สินค้าที่ซื้อมากที่สุด', sub: 'เรียงตามมูลค่าสะสม',
            cols: ['สินค้า', 'ราคาล่าสุด', 'ยอดรวม'] },
          { title: 'ผู้ขายรายใหญ่', sub: 'เรียงตามยอดสั่งซื้อ',
            cols: ['ผู้ขาย', 'ยอดสั่งซื้อ', 'รหัสสินค้า'] },
        ].map((card) => (
          <div key={card.title} className="card">
            <div className="card-head">
              <div>
                <h2>{card.title}</h2>
                <div className="cell-sub">{card.sub}</div>
              </div>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{card.cols[0]}</th>
                    <th style={{ textAlign: 'right', width: 120 }}>{card.cols[1]}</th>
                    <th style={{ textAlign: 'right', width: 110 }}>{card.cols[2]}</th>
                  </tr>
                </thead>
                <SkeletonRows rows={8} cols={3} widths={['74%', '52%', '46%']} />
              </table>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

function Stat({ label, value, note, href }) {
  const body = (
    <>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {note && <div className="stat-note">{note}</div>}
    </>
  );
  return href
    ? <Link className="stat-card stat-link" href={href}>{body}</Link>
    : <div className="stat-card">{body}</div>;
}
