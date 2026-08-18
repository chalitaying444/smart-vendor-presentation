'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { IconSearch, IconPlus } from '@/components/icons';
import { api } from '@/lib/api';
import { useBatchList, useDebounced, useOnScreen } from '@/components/useBatchList';
import { formatDate } from '@/components/ui';

const BATCH = 30;

export const RFQ_STATUS = {
  draft: { label: 'ร่าง', cls: 'badge-off' },
  sent: { label: 'ส่งแล้ว', cls: 'badge-admin' },
  quoted: { label: 'ได้รับราคาแล้ว', cls: 'badge-staff' },
  awarded: { label: 'ประกาศผู้ชนะแล้ว', cls: 'badge-ok' },
  closed: { label: 'ปิดแล้ว', cls: 'badge-off' },
  cancelled: { label: 'ยกเลิก', cls: 'badge-vendor' },
};

export function StatusBadge({ status }) {
  const s = RFQ_STATUS[status] || { label: status, cls: 'badge-off' };
  return <span className={`badge ${s.cls}`}>{s.label}</span>;
}

export default function RfqListPage() {
  const router = useRouter();
  const search = useSearchParams();
  const justCancelled = search.get('cancelled') || '';
  const revokedLinks = Number(search.get('links') || 0);
  const [term, setTerm] = useState('');
  const [status, setStatus] = useState('');
  const [trash, setTrash] = useState(false);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState('');
  const q = useDebounced(term, 350);

  const filters = useMemo(() => ({ q, status, trash }), [q, status, trash]);
  const fetcher = useCallback((p) => api.listRfqs(p), []);
  const { items, total, hasMore, loading, loadingMore, error, loadMore, reload } =
    useBatchList(fetcher, filters, BATCH);
  const sentinel = useOnScreen(loadMore, hasMore && !loading && !loadingMore);

  const [creating, setCreating] = useState(false);
  // ติ๊กเลือกหลายใบ — เก็บเป็น id ของแถวที่เลือก ไม่ใช่ "ทั้งหมดที่ค้นเจอ"
  // คำสั่งแบบ "ทั้งหมดที่ค้นเจอ" จะกวาดใบที่ไม่ได้อยู่บนหน้าจอไปด้วย
  // คนกดจึงไม่มีทางรู้ว่าเพิ่งยกเลิกอะไรไปกี่ใบ
  const [picked, setPicked] = useState(() => new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  // เปลี่ยนโหมด/คำค้น = ของที่ติ๊กไว้ไม่เกี่ยวกันแล้ว ต้องล้าง ไม่ใช่ปล่อยค้าง
  useEffect(() => { setPicked(new Set()); }, [trash, q, status]);

  const shown = items.map((r) => r.id);
  const allPicked = shown.length > 0 && shown.every((id) => picked.has(id));

  function toggle(id) {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    setPicked(allPicked ? new Set() : new Set(shown));
  }

  async function bulk() {
    const ids = [...picked];
    const cancelling = !trash;
    if (cancelling && !window.confirm(
      `ยกเลิกใบขอราคา ${ids.length} ใบที่เลือกไว้?\n\n`
      + 'ลิงก์ที่ส่งให้ผู้ขายของทุกใบจะใช้ไม่ได้ทันที และผู้ขายที่เปิดลิงก์เดิม '
      + 'จะเห็นว่า "ใบขอราคานี้ถูกยกเลิกแล้ว"\n\n'
      + 'กู้กลับมาได้จากแท็บ "ยกเลิกแล้ว"')) return;

    setBulkBusy(true); setNote('');
    try {
      const res = cancelling
        ? await api.bulkCancelRfqs(ids)
        : await api.bulkRestoreRfqs(ids);
      // ใบที่ทำไม่ได้ต้องบอกว่าใบไหนเพราะอะไร ไม่ใช่ข้ามเงียบ ๆ แล้วรายงานว่าสำเร็จ
      const skipped = (res.skipped || []).length;
      setNote(res.message + (skipped ? ` (${res.skipped.map((x) => x.reason).join(' · ')})` : ''));
      setPicked(new Set());
      reload();
    } catch (e) {
      setNote(e.message);
    } finally { setBulkBusy(false); }
  }

  async function restore(id) {
    setBusy(id);
    setNote('');
    try {
      const res = await api.restoreRfq(id);
      setNote(res.message || '');
      reload();
    } catch (e) {
      setNote(e.message);
    } finally { setBusy(''); }
  }

  return (
    <>
      {justCancelled && (
        <div className="alert alert-ok">
          ยกเลิก <strong>{justCancelled}</strong> แล้ว
          {revokedLinks > 0 && <> · ลิงก์ของผู้ขาย <strong>{revokedLinks} ราย</strong> ใช้ไม่ได้อีก</>}
          {' · '}
          <button className="link-btn" onClick={() => setTrash(true)}>ดูใบที่ยกเลิกไว้</button>
        </div>
      )}
      {note && <div className="alert alert-ok">{note}</div>}

      {picked.size > 0 && (
        <div className="bulk-bar">
          <span>เลือกไว้ <strong>{picked.size}</strong> ใบ</span>
          <button className="link-btn" onClick={() => setPicked(new Set())}>ล้างที่เลือก</button>
          <div className="spacer" />
          <button className={`btn btn-sm ${trash ? 'btn-secondary' : 'btn-danger'}`}
                  disabled={bulkBusy} onClick={bulk}>
            {bulkBusy
              ? 'กำลังทำ…'
              : trash ? `กู้คืน ${picked.size} ใบที่เลือก` : `ยกเลิก ${picked.size} ใบที่เลือก`}
          </button>
        </div>
      )}

      <div className="card" style={{ marginBottom: 18 }}>
        <div className="card-head">
          <div className="search-wrap">
            <IconSearch />
            <input type="search" value={term} onChange={(e) => setTerm(e.target.value)}
                   placeholder="ค้นหาเลขที่ RFQ หรือชื่อใบขอราคา…" />
          </div>
          <div className="toolbar">
            <select value={status} onChange={(e) => setStatus(e.target.value)} style={{ width: 'auto' }}>
              <option value="">ทุกสถานะ</option>
              {Object.entries(RFQ_STATUS).map(([k, v]) => (
                <option key={k} value={k}>{v.label}</option>
              ))}
            </select>
            <button className={`btn btn-secondary${trash ? ' btn-on' : ''}`}
                    onClick={() => setTrash((v) => !v)}>
              {trash ? '← กลับไปรายการปกติ' : 'ยกเลิกแล้ว'}
            </button>
            <Link className="btn btn-secondary" href="/matching">จับคู่ผู้ขายเพื่อสร้าง RFQ</Link>
            <button className="btn btn-primary" onClick={() => setCreating(true)}>
              <IconPlus /> สร้าง RFQ เปล่า
            </button>
          </div>
        </div>
        <div className="card-body" style={{ paddingTop: 0 }}>
          <div className="result-line" style={{ borderTop: 'none', paddingTop: 4 }}>
            {loading ? 'กำลังโหลด…' : <>พบ <strong>{total.toLocaleString('th-TH')}</strong> ใบ</>}
          </div>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="card">
        {!loading && items.length === 0 ? (
          <div className="empty">
            {trash ? (
              <>
                <strong>ไม่มีใบที่ยกเลิกไว้</strong>
                ใบที่ยกเลิกจะมาพักที่นี่ กู้กลับมาได้ และลิงก์ของผู้ขายจะใช้ได้อีกครั้ง
              </>
            ) : (
              <>
                <strong>ยังไม่มีใบขอราคา</strong>
                เริ่มจากหน้า <Link href="/matching">จับคู่ผู้ขาย</Link> เพื่อเลือกผู้ขายแล้วสร้าง RFQ
              </>
            )}
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 40 }}>
                    {/* ติ๊กหัวตาราง = เลือกทุกแถวที่เห็นอยู่ตอนนี้ (ไม่ใช่ทุกใบในระบบ) */}
                    <input type="checkbox" checked={allPicked} onChange={toggleAll}
                           disabled={!shown.length}
                           aria-label="เลือกทุกใบที่แสดงอยู่" title="เลือกทุกใบที่แสดงอยู่" />
                  </th>
                  <th>เลขที่ / ชื่อ</th><th>สถานะ</th><th>รายการ</th><th>ผู้ขาย</th>
                  <th>ใบเสนอราคา</th><th>กำหนดส่งราคา</th>
                  <th>{trash ? 'ยกเลิกเมื่อ' : 'สร้างเมื่อ'}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((r) => (
                  <tr key={r.id} className={trash ? '' : 'clickable'}
                      onClick={trash ? undefined : () => router.push(`/rfqs/${r.id}`)}>
                    <td className="pick-cell" onClick={(e) => e.stopPropagation()}>
                      <input type="checkbox" checked={picked.has(r.id)}
                             onChange={() => toggle(r.id)}
                             aria-label={`เลือก ${r.rfq_no || 'ใบนี้'}`} />
                    </td>
                    <td>
                      <div className="cell-title">{r.rfq_no || '(ยังไม่มีเลขที่)'}</div>
                      <div className="cell-sub">{r.title}</div>
                    </td>
                    <td><StatusBadge status={r.status} /></td>
                    <td>{r.lines?.length ?? r.line_count ?? '—'}</td>
                    <td>{r.vendor_count ?? '—'}</td>
                    <td>{r.quote_count ?? 0}</td>
                    <td className="cell-sub">{r.due_date || '—'}</td>
                    <td className="cell-sub">
                      {trash ? (
                        <>
                          <div>{formatDate(r.deleted_at)}</div>
                          <div>โดย {r.deleted_by || '—'}</div>
                          <button className="btn btn-secondary btn-sm" disabled={busy === r.id}
                                  onClick={(e) => { e.stopPropagation(); restore(r.id); }}>
                            {busy === r.id ? 'กำลังกู้…' : 'กู้คืน'}
                          </button>
                        </>
                      ) : formatDate(r.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {loading && <div className="empty">กำลังโหลด…</div>}
      </div>

      {hasMore && (
        <div ref={sentinel} className="load-more">
          <button className="btn btn-secondary" onClick={loadMore} disabled={loadingMore}>
            {loadingMore ? 'กำลังโหลด…' : 'โหลดเพิ่ม'}
          </button>
        </div>
      )}

      {creating && (
        <BlankRfqModal
          onClose={() => setCreating(false)}
          onDone={(id) => router.push(`/rfqs/${id}`)}
          onReload={reload}
        />
      )}
    </>
  );
}

function BlankRfqModal({ onClose, onDone }) {
  const [title, setTitle] = useState('');
  const [due, setDue] = useState('');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  async function submit(e) {
    e.preventDefault();
    setSaving(true); setErr('');
    try {
      const rfq = await api.createRfq({
        title: title.trim() || 'ใบขอราคาใหม่',
        due_date: due || null,
        currency: 'THB',
        lines: [],
        vendor_keys: [],
      });
      onDone(rfq.id);
    } catch (e2) {
      setErr(e2.message);
    } finally {
      setSaving(false);
    }
  }

  // ใช้ Modal จาก components/ui ผ่าน dynamic import ไม่ได้ในไฟล์นี้ จึงวาดเอง
  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal" role="dialog" aria-modal="true">
        <div className="modal-head">
          <h2>สร้าง RFQ เปล่า</h2>
          <p>สร้างใบก่อน แล้วค่อยเพิ่มสินค้าและผู้ขายทีหลัง</p>
        </div>
        <form onSubmit={submit}>
          <div className="modal-body">
            {err && <div className="alert alert-error">{err}</div>}
            <div className="field">
              <label htmlFor="b-title">ชื่อใบขอราคา</label>
              <input id="b-title" value={title} onChange={(e) => setTitle(e.target.value)}
                     placeholder="จัดซื้ออุปกรณ์เครือข่าย Q3" />
            </div>
            <div className="field" style={{ marginBottom: 0 }}>
              <label htmlFor="b-due">กำหนดส่งราคา</label>
              <input id="b-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} />
            </div>
          </div>
          <div className="modal-foot">
            <button type="button" className="btn btn-secondary" onClick={onClose} disabled={saving}>ยกเลิก</button>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'กำลังสร้าง…' : 'สร้าง'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
