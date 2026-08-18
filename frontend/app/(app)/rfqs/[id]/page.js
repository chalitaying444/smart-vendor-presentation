'use client';

import { use, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api, encodePart, fileUrl } from '@/lib/api';
import { shortDate, num as fmtNum } from '@/lib/format';
import OtdBadge from '@/components/OtdBadge';
import { Modal, Toast, formatDate } from '@/components/ui';
import { usePageTitle } from '@/components/RequireAdmin';
import { StatusBadge } from '../page';

const INVITE_STATUS = {
  pending: 'ยังไม่ส่ง',
  sent: 'ส่งแล้ว รอราคา',
  quoted: 'เสนอราคาแล้ว',
  declined: 'ปฏิเสธ',
  awarded: 'ผู้ชนะ',
};

const money = (n, cur = 'THB') =>
  n == null ? '—' : `${Number(n).toLocaleString('th-TH', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${cur}`;

export default function RfqDetailPage({ params }) {
  const { id } = use(params);
  return <Detail id={id} />;
}

function Detail({ id }) {
  const [rfq, setRfq] = useState(null);
  const [invites, setInvites] = useState([]);
  const [comparison, setComparison] = useState(null);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('lines');
  const [toast, setToast] = useState(null);
  const [sending, setSending] = useState(false);
  const [awarding, setAwarding] = useState(null);
  const [addingVendors, setAddingVendors] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const router = useRouter();

  const load = useCallback(async () => {
    try {
      const data = await api.getRfq(id);
      setRfq(data);
      const inv = await api.rfqInvites(id).catch(() => []);
      setInvites(Array.isArray(inv) ? inv : inv.items || []);
      if (['sent', 'quoted', 'awarded', 'closed'].includes(data.status)) {
        api.rfqComparison(id).then(setComparison).catch(() => setComparison(null));
      }
    } catch (err) {
      setError(err.message);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);
  usePageTitle(rfq ? `${rfq.rfq_no || 'RFQ'} · ${rfq.title}` : 'ใบขอราคา', 'รายละเอียดใบขอราคา');

  if (error) {
    return (
      <>
        <div className="alert alert-error">{error}</div>
        <Link className="btn btn-secondary" href="/rfqs">กลับไปรายการ RFQ</Link>
      </>
    );
  }
  if (!rfq) return <div className="empty">กำลังโหลด…</div>;

  const quotedCount = invites.filter((i) => i.status === 'quoted').length;
  const canSend = rfq.lines?.length > 0 && invites.length > 0 && !['closed'].includes(rfq.status);

  const TABS = [
    { key: 'lines', label: 'รายการสินค้า', count: rfq.lines?.length || 0 },
    { key: 'vendors', label: 'ผู้ขายที่เชิญ', count: invites.length },
    { key: 'compare', label: 'เทียบราคา', count: quotedCount },
  ];

  async function copy(text) {
    try {
      await navigator.clipboard.writeText(text);
      setToast({ message: 'คัดลอกลิงก์แล้ว' });
    } catch {
      setToast({ message: text, type: 'error' });
    }
  }

  return (
    <>
      <div className="toolbar" style={{ marginBottom: 14 }}>
        <Link className="btn btn-secondary btn-sm" href="/rfqs">← กลับไปรายการ</Link>
        <a className="btn btn-secondary btn-sm" href={fileUrl.rfqComparisonXlsx(id)}>
          ดาวน์โหลดตารางเทียบราคา (Excel)
        </a>
      </div>

      <div className="card">
        <div className="card-head" style={{ borderBottom: 'none', paddingBottom: 8 }}>
          <div>
            <h2 style={{ fontSize: 17 }}>{rfq.rfq_no || '(ยังไม่มีเลขที่)'} · {rfq.title}</h2>
            <div className="cell-sub">
              สกุลเงิน {rfq.currency}
              {rfq.due_date && ` · กำหนดส่งราคา ${rfq.due_date}`}
              {rfq.sent_at && ` · ส่งเมื่อ ${formatDate(rfq.sent_at)}`}
            </div>
          </div>
          <div className="toolbar">
            <StatusBadge status={rfq.status} />
            {canSend && (
              <button className="btn btn-primary btn-sm" onClick={() => setSending(true)}>
                {rfq.status === 'draft' ? 'ส่งใบขอราคา' : 'ส่งซ้ำ / ส่งเพิ่ม'}
              </button>
            )}
            {quotedCount > 0 && rfq.status !== 'closed' && (
              <button className="btn btn-secondary btn-sm" onClick={() => setAwarding({})}>ประกาศผู้ชนะ</button>
            )}
            {/* ยกเลิกใบ = ตัดลิงก์ของผู้ขายทันที ต้องบอกผลข้างเคียงให้ครบก่อนกด */}
            <button className="btn btn-danger btn-sm" disabled={cancelling}
                    onClick={async () => {
                      if (!window.confirm(
                        `ยกเลิก ${rfq.rfq_no || 'ใบนี้'}?\n\n` +
                        'ลิงก์ที่ส่งให้ผู้ขายจะใช้ไม่ได้ทันที และผู้ขายที่เปิดลิงก์เดิม ' +
                        'จะเห็นว่า "ใบขอราคานี้ถูกยกเลิกแล้ว" · เสนอราคาเข้ามาไม่ได้อีก\n\n' +
                        'กู้กลับมาได้จากแท็บ "ยกเลิกแล้ว" ในหน้ารายการ')) return;
                      setCancelling(true);
                      try {
                        const res = await api.cancelRfq(id);
                        router.push(`/rfqs?cancelled=${encodeURIComponent(res.rfq_no)}`
                                    + `&links=${res.links_revoked || 0}`);
                      } catch (e) {
                        setToast({ message: e.message, type: 'error' });
                      } finally { setCancelling(false); }
                    }}>
              {cancelling ? 'กำลังยกเลิก…' : 'ยกเลิกใบนี้'}
            </button>
          </div>
        </div>

        <div className="tabs">
          {TABS.map((t) => (
            <button key={t.key} className={`tab${tab === t.key ? ' active' : ''}`} onClick={() => setTab(t.key)}>
              {t.label}<span className="tab-count">{t.count}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="card tab-panel">
        {tab === 'lines' && (
          rfq.lines?.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>รหัสสินค้า</th><th>สินค้า</th><th>จำนวน</th><th>หน่วย</th>
                    <th style={{ textAlign: 'right' }}>ราคาล่าสุดที่เคยซื้อ</th></tr>
                </thead>
                <tbody>
                  {rfq.lines.map((l) => (
                    <tr key={l.part_num}>
                      <td>
                        <Link href={`/products/${encodePart(l.part_num)}`}><code>{l.part_num}</code></Link>
                      </td>
                      <td className="cell-title">{l.name}</td>
                      <td>{l.qty}</td>
                      <td>{l.uom}</td>
                      <td className="num-cell">
                        {l.last_price != null ? (
                          <>
                            {money(l.last_price, rfq.currency)}
                            <div className="cell-sub">
                              {shortDate(l.last_price_date)}
                              {l.last_price_vendor ? ` · ${l.last_price_vendor}` : ''}
                            </div>
                          </>
                        ) : <span className="muted">ไม่เคยซื้อ</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty">
              <strong>ยังไม่มีรายการสินค้าในใบนี้</strong>
              เริ่มจากหน้า <Link href="/products">ค้นหาสินค้า</Link> แล้วกด “ขอใบเสนอราคา”
            </div>
          )
        )}

        {tab === 'vendors' && (
          <>
            <div className="card-head" style={{ borderBottom: '1px solid var(--border)' }}>
              <div className="cell-sub">
                ผู้ขายที่ยังไม่มีอีเมลต้องส่งลิงก์ให้เองทางไลน์หรือช่องทางอื่น
              </div>
              <button className="btn btn-secondary btn-sm" onClick={() => setAddingVendors(true)}>
                เพิ่มผู้ขายที่ระบบแนะนำ
              </button>
            </div>
            {invites.length === 0 ? (
              <div className="empty"><strong>ยังไม่ได้เชิญผู้ขาย</strong>กด “เพิ่มผู้ขายที่ระบบแนะนำ” ด้านบน</div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr><th>ผู้ขาย</th><th>สถานะ</th><th>อีเมล</th><th>ลิงก์สำหรับผู้ขาย</th><th style={{ textAlign: 'right' }}>จัดการ</th></tr>
                  </thead>
                  <tbody>
                    {invites.map((v) => (
                      <tr key={v.vendor_key}>
                        <td>
                          <div className="cell-title">{v.vendor_name || v.vendor_key}</div>
                          <div className="cell-sub">{v.vendor_key}</div>
                        </td>
                        <td><span className="badge badge-off">{INVITE_STATUS[v.status] || v.status}</span></td>
                        <td className="cell-sub">
                          {v.contact_email || <span className="badge badge-vendor">ไม่มีอีเมล</span>}
                        </td>
                        <td>
                          {v.portal_url ? (
                            <div className="link-cell">
                              <code>{v.portal_url}</code>
                              <button className="btn btn-secondary btn-sm" onClick={() => copy(v.portal_url)}>คัดลอก</button>
                            </div>
                          ) : <span className="muted">ยังไม่ได้ส่ง</span>}
                        </td>
                        <td className="actions">
                          {v.portal_url && (
                            <a className="btn btn-secondary btn-sm" href={fileUrl.rfqDocument(id, v.vendor_key)}>
                              ใบขอราคา
                            </a>
                          )}
                          <button
                            className="btn btn-danger btn-sm"
                            onClick={async () => {
                              try {
                                await api.rfqRemoveVendor(id, v.vendor_key);
                                setToast({ message: 'ถอดผู้ขายออกแล้ว' });
                                load();
                              } catch (e) { setToast({ message: e.message, type: 'error' }); }
                            }}
                          >
                            ถอด
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {tab === 'compare' && (
          !comparison || !comparison.vendors?.length ? (
            <div className="empty">
              <strong>ยังไม่มีใบเสนอราคาเข้ามา</strong>
              เมื่อผู้ขายกรอกราคาผ่านลิงก์ที่ส่งไป ตารางเทียบราคาจะขึ้นที่นี่
            </div>
          ) : (
            <Comparison data={comparison} currency={rfq.currency} onAward={(vk) => setAwarding({ vendor_key: vk })} />
          )
        )}
      </div>

      {sending && (
        <SendModal
          rfqId={id}
          count={invites.length}
          onClose={() => setSending(false)}
          onDone={(res) => {
            setSending(false);
            setToast({ message: `ออกใบขอราคาให้ผู้ขาย ${res.sent} รายแล้ว` });
            setTab('vendors');
            load();
          }}
          onError={(m) => setToast({ message: m, type: 'error' })}
        />
      )}

      {addingVendors && (
        <SuggestModal
          rfqId={id}
          existing={invites.map((i) => i.vendor_key)}
          onClose={() => setAddingVendors(false)}
          onDone={(n) => { setAddingVendors(false); setToast({ message: `เพิ่มผู้ขาย ${n} ราย` }); load(); }}
          onError={(m) => setToast({ message: m, type: 'error' })}
        />
      )}

      {awarding && (
        <AwardModal
          rfqId={id}
          vendors={comparison?.vendors || []}
          preset={awarding.vendor_key}
          onClose={() => setAwarding(null)}
          onDone={() => { setAwarding(null); setToast({ message: 'ประกาศผู้ชนะเรียบร้อย' }); load(); }}
          onError={(m) => setToast({ message: m, type: 'error' })}
        />
      )}

      <Toast {...(toast || {})} onDone={() => setToast(null)} />
    </>
  );
}

function Comparison({ data, currency, onAward }) {
  const vendors = data.vendors;
  return (
    <>
      <div className="stat-row" style={{ margin: 20 }}>
        <div className="stat">
          <div className="label">ซื้อเจ้าเดียวถูกสุด</div>
          <div className="num" style={{ fontSize: 18 }}>{money(data.single_vendor_total, currency)}</div>
          <div className="sub">{vendors.find((v) => v.vendor_key === data.best_total_vendor_key)?.vendor_name || '—'}</div>
        </div>
        <div className="stat">
          <div className="label">แยกซื้อรายบรรทัด (ถูกสุดทุกบรรทัด)</div>
          <div className="num" style={{ fontSize: 18 }}>{money(data.split_award_total, currency)}</div>
          <div className="sub">ประหยัดกว่า {money(data.split_saving, currency)}</div>
        </div>
        <div className="stat">
          {/* ค่าติดลบ = เสนอมาแพงกว่าที่เคยซื้อ ต้องบอกตรง ๆ ไม่ใช่เรียกว่า "ประหยัด" ติดลบ */}
          <div className="label">
            {data.saving_vs_last_price >= 0 ? 'ประหยัดกว่าราคาเดิม' : 'แพงกว่าราคาเดิม'}
          </div>
          <div
            className={`num delta ${data.saving_vs_last_price >= 0 ? 'down' : 'up'}`}
            style={{ fontSize: 18 }}
          >
            {money(Math.abs(data.saving_vs_last_price ?? 0), currency)}
          </div>
          <div className="sub">
            {data.baseline_total != null
              ? `เทียบราคาเดิมรวม ${money(data.baseline_total, currency)}`
              : 'ยังไม่มีราคาเดิมให้เทียบ'}
          </div>
        </div>
        <div className="stat">
          <div className="label">ใบเสนอราคาที่ได้รับ</div>
          <div className="num" style={{ fontSize: 18 }}>{vendors.length}</div>
          <div className="sub">จากผู้ขายที่เชิญ</div>
        </div>
      </div>

      {(() => {
        const cheapest = vendors.find((v) => v.vendor_key === data.best_total_vendor_key);
        const risky = cheapest?.delivery?.has_data
          && cheapest.delivery.reliable
          && ['poor', 'fair'].includes(cheapest.delivery.level);
        const better = vendors.find((v) => v.total != null
          && v.vendor_key !== cheapest?.vendor_key
          && ['excellent', 'good'].includes(v.delivery?.level));
        if (!risky) return null;
        return (
          <div className="alert alert-info" style={{ marginBottom: 14 }}>
            เจ้าที่เสนอราคารวมถูกที่สุดคือ <strong>{cheapest.vendor_name}</strong> แต่ส่งตรงเวลาเพียง{' '}
            <strong>{fmtNum(cheapest.delivery.otd_pct, 1)}%</strong> จาก {fmtNum(cheapest.delivery.releases)} งวด
            {cheapest.delivery.median_days_late > 0
              && ` (ปกติช้า ${fmtNum(cheapest.delivery.median_days_late, 1)} วัน)`}
            {better && <> — {better.vendor_name} ส่งตรงเวลา {fmtNum(better.delivery.otd_pct, 1)}% ถ้างานนี้เร่งควรเทียบดูด้วย</>}
          </div>
        );
      })()}

      <div className="table-wrap">
        <table className="compare-table">
          <thead>
            <tr>
              <th>สินค้า</th><th>จำนวน</th>
              <th style={{ textAlign: 'right' }}>
                ราคาเดิม
                <div className="cell-sub" style={{ textTransform: 'none' }}>ครั้งล่าสุดที่ซื้อ</div>
              </th>
              {vendors.map((v) => (
                <th key={v.vendor_key} style={{ textAlign: 'right' }}>
                  {v.vendor_name}
                  <div className="cell-sub" style={{ textTransform: 'none' }}>
                    รวม {money(v.total, v.currency || currency)}
                  </div>
                  {/* ถูกที่สุดไม่ได้แปลว่าดีที่สุด — ให้เห็นประวัติการส่งพร้อมกันตรงนี้ */}
                  <div style={{ textTransform: 'none', fontWeight: 400, marginTop: 4 }}>
                    <OtdBadge delivery={v.delivery} compact />
                  </div>
                  {/* ใบเสนอราคาตัวจริงที่ผู้ขายแนบมา — ตัวเลขในตารางคือสิ่งที่เขาคีย์
                      เอกสารฉบับเต็มมักมีเงื่อนไขที่ไม่ได้อยู่ในช่องกรอก */}
                  {v.attachments?.length > 0 && (
                    <div className="cell-sub attach-links" style={{ textTransform: 'none' }}>
                      {v.attachments.map((f) => (
                        <a key={f.file_id} href={f.url} title={f.filename}>
                          {f.filename}
                        </a>
                      ))}
                    </div>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => (
              <tr key={row.part_num}>
                <td>
                  <div className="cell-title">{row.name}</div>
                  <div className="cell-sub">{row.item_code}</div>
                </td>
                <td>{row.qty} {row.uom}</td>
                <td className="num-cell baseline">
                  {row.last_price != null ? (
                    <>
                      {money(row.last_price, '')}
                      <div className="cell-sub">
                        {shortDate(row.last_price_date)}
                        {row.best_vs_last_pct != null && (
                          <div className={`delta ${row.best_vs_last_pct > 0 ? 'up' : 'down'}`}>
                            ที่เสนอมา {row.best_vs_last_pct > 0 ? '+' : ''}
                            {Number(row.best_vs_last_pct).toLocaleString('th-TH', { maximumFractionDigits: 1 })}%
                          </div>
                        )}
                      </div>
                    </>
                  ) : <span className="muted">ไม่เคยซื้อ</span>}
                </td>
                {vendors.map((v) => {
                  const cell = row.cells.find((c) => c.vendor_key === v.vendor_key);
                  if (!cell || cell.no_quote || cell.unit_price == null) {
                    return <td key={v.vendor_key} className="num-cell muted">ไม่เสนอ</td>;
                  }
                  return (
                    <td key={v.vendor_key} className={`num-cell${cell.is_lowest ? ' lowest' : ''}`}>
                      {money(cell.unit_price, '')}
                      <div className="cell-sub">
                        รวม {money(cell.amount, '')}
                        {cell.lead_time_days != null && ` · ${cell.lead_time_days} วัน`}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={2} className="cell-title">รวมทั้งใบ</td>
              <td className="num-cell baseline">
                {data.baseline_total != null ? (
                  <>
                    <strong>{money(data.baseline_total, '')}</strong>
                    <div className="cell-sub">ถ้าซื้อที่ราคาเดิม</div>
                  </>
                ) : <span className="muted">—</span>}
              </td>
              {vendors.map((v) => (
                <td key={v.vendor_key} className="num-cell">
                  <strong>{money(v.total, '')}</strong>
                  <div style={{ marginTop: 6 }}>
                    <button className="btn btn-secondary btn-sm" onClick={() => onAward(v.vendor_key)}>
                      เลือกเจ้านี้
                    </button>
                  </div>
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
    </>
  );
}

function SendModal({ rfqId, count, onClose, onDone, onError }) {
  const [message, setMessage] = useState('รบกวนเสนอราคาตามรายการที่แนบมา ขอบคุณครับ');
  const [busy, setBusy] = useState(false);

  async function send() {
    setBusy(true);
    try {
      onDone(await api.rfqSend(rfqId, message));
    } catch (e) {
      onError?.(e.message);
      onClose();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title="ส่งใบขอราคา"
      subtitle={`ระบบจะสร้างใบขอราคาและลิงก์เฉพาะรายให้ผู้ขาย ${count} ราย`}
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-secondary" onClick={onClose} disabled={busy}>ยกเลิก</button>
          <button className="btn btn-primary" onClick={send} disabled={busy}>
            {busy ? 'กำลังออกใบ…' : 'ออกใบขอราคา'}
          </button>
        </>
      }
    >
      <div className="field">
        <label htmlFor="s-msg">ข้อความถึงผู้ขาย</label>
        <textarea id="s-msg" className="bom-input" rows={4} value={message}
                  onChange={(e) => setMessage(e.target.value)} />
      </div>
      <div className="alert alert-info" style={{ marginBottom: 0 }}>
        ระบบยังไม่ได้ต่อกับอีเมลขาออก — หลังกดปุ่มนี้จะได้<strong>ลิงก์เฉพาะราย</strong>ในแท็บ “ผู้ขายที่เชิญ”
        ให้คัดลอกส่งทางอีเมล/ไลน์เอง ผู้ขายเปิดลิงก์แล้วกรอกราคาได้เลยโดยไม่ต้องล็อกอิน
      </div>
    </Modal>
  );
}

function SuggestModal({ rfqId, existing, onClose, onDone, onError }) {
  const [list, setList] = useState(null);
  const [picked, setPicked] = useState(new Set());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.rfqSuggested(rfqId)
      .then((d) => setList((Array.isArray(d) ? d : d.vendors || d.items || [])
        .filter((v) => !existing.includes(v.vendor_key))))
      .catch((e) => { onError?.(e.message); setList([]); });
  }, [rfqId, existing, onError]);

  async function add() {
    setBusy(true);
    try {
      await api.rfqAddVendors(rfqId, [...picked]);
      onDone(picked.size);
    } catch (e) {
      onError?.(e.message);
      onClose();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title="เพิ่มผู้ขายเข้าใบขอราคา"
      subtitle="ผู้ขายที่เคยขายรหัสสินค้าเหล่านี้ให้เราจริง ตามประวัติใน Epicor"
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-secondary" onClick={onClose} disabled={busy}>ยกเลิก</button>
          <button className="btn btn-primary" onClick={add} disabled={busy || picked.size === 0}>
            {busy ? 'กำลังเพิ่ม…' : `เพิ่ม ${picked.size} ราย`}
          </button>
        </>
      }
    >
      {!list ? <p className="muted">กำลังโหลด…</p>
        : list.length === 0 ? (
          <p className="muted">
            ไม่มีผู้ขายที่แนะนำเพิ่มเติม — ดูรายชื่อทั้งหมดได้ที่หน้า <Link href="/vendors">ผู้ขาย</Link>
          </p>
        ) : (
          <table style={{ fontSize: 12.5 }}>
            <tbody>
              {list.map((v) => (
                <tr key={v.vendor_key}>
                  <td style={{ width: 32 }}>
                    <input
                      type="checkbox"
                      checked={picked.has(v.vendor_key)}
                      onChange={() => setPicked((p) => {
                        const n = new Set(p);
                        n.has(v.vendor_key) ? n.delete(v.vendor_key) : n.add(v.vendor_key);
                        return n;
                      })}
                    />
                  </td>
                  <td>
                    <div className="cell-title">{v.vendor_name || v.name}</div>
                    <div className="cell-sub">{v.vendor_key}</div>
                  </td>
                  <td className="cell-sub">
                    {v.covered_items != null && <div>ครอบคลุม {v.covered_items} รายการ ({v.coverage_percent}%)</div>}
                    {v.avg_last_price != null && <div>ราคาล่าสุดเฉลี่ย {money(v.avg_last_price, '')}</div>}
                    {v.has_email === false ? 'ไม่มีอีเมล' : (v.emails?.[0] || '')}
                  </td>
                  <td><OtdBadge delivery={v.delivery} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
    </Modal>
  );
}

function AwardModal({ rfqId, vendors, preset, onClose, onDone, onError }) {
  const [vendorKey, setVendorKey] = useState(preset || vendors[0]?.vendor_key || '');
  const [reason, setReason] = useState('ราคาต่ำสุดและกำหนดส่งเหมาะสม');
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      await api.rfqAward(rfqId, { vendor_key: vendorKey, reason });
      onDone();
    } catch (e) {
      onError?.(e.message);
      onClose();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title="ประกาศผู้ชนะ"
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-secondary" onClick={onClose} disabled={busy}>ยกเลิก</button>
          <button className="btn btn-primary" onClick={submit} disabled={busy || !vendorKey}>
            {busy ? 'กำลังบันทึก…' : 'ยืนยันผู้ชนะ'}
          </button>
        </>
      }
    >
      <div className="field">
        <label htmlFor="a-vendor">ผู้ขายที่ชนะ</label>
        <select id="a-vendor" value={vendorKey} onChange={(e) => setVendorKey(e.target.value)}>
          {vendors.map((v) => (
            <option key={v.vendor_key} value={v.vendor_key}>
              {v.vendor_name} — {money(v.total, v.currency)}
            </option>
          ))}
        </select>
      </div>
      <div className="field" style={{ marginBottom: 0 }}>
        <label htmlFor="a-reason">เหตุผล</label>
        <input id="a-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>
    </Modal>
  );
}
