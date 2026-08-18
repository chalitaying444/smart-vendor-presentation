'use client';

/**
 * ขอใบเสนอราคาจากหน้าสินค้า
 *
 * ไม่ต้องเพิ่มสินค้าเข้าระบบก่อนอีกแล้ว — RFQ อ้างรหัสสินค้าของ Epicor ตรง ๆ
 * ถ้าเปิดจากหน้ารายการ (ยังไม่รู้ว่าใครขาย) จะไปดึงรายชื่อผู้ขายของรหัสนั้นมาให้เลือกเอง
 */
import { useEffect, useState } from 'react';
import { Modal } from '@/components/ui';
import { api } from '@/lib/api';
import { money, shortDate } from '@/lib/format';

export default function RequestQuoteModal({
  partNum, description, uom, lastPrice, vendors: given, preselected, onClose, onDone, onError,
}) {
  const [vendors, setVendors] = useState(given || null);
  const [picked, setPicked] = useState(() => new Set(preselected || []));
  const [title, setTitle] = useState(`ขอราคา ${description || partNum}`.slice(0, 120));
  const [qty, setQty] = useState(1);
  const [due, setDue] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  // เปิดจากหน้ารายการ — ยังไม่มีรายชื่อผู้ขาย ต้องไปดึงมาก่อน
  useEffect(() => {
    if (given) return undefined;
    let alive = true;
    api.itemVendors(partNum)
      .then((d) => {
        if (!alive) return;
        setVendors(d.vendors || []);
        if (!preselected?.length) setPicked(new Set((d.vendors || []).map((v) => v.vendor_key)));
      })
      .catch((e) => { if (alive) setErr(e.message); });
    return () => { alive = false; };
  }, [given, partNum, preselected]);

  function toggle(key) {
    setPicked((p) => {
      const n = new Set(p);
      if (n.has(key)) n.delete(key); else n.add(key);
      return n;
    });
  }

  async function submit(e) {
    e.preventDefault();
    setErr('');
    if (picked.size === 0) { setErr('เลือกผู้ขายอย่างน้อย 1 ราย'); return; }
    setBusy(true);
    try {
      const rfq = await api.createRfq({
        title: title.trim() || `ขอราคา ${partNum}`,
        due_date: due || null,
        currency: 'THB',
        note,
        lines: [{ part_num: partNum, qty: Number(qty) || 1, uom: uom || '' }],
        vendor_keys: [...picked],
      });
      onDone(rfq.id);
    } catch (e2) {
      setErr(e2.message);
      onError?.(e2.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title="ขอใบเสนอราคา"
      subtitle={`${partNum}${description ? ` — ${description}` : ''}`}
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-secondary" onClick={onClose} disabled={busy}>ยกเลิก</button>
          <button className="btn btn-primary" form="rq-form" type="submit" disabled={busy}>
            {busy ? 'กำลังสร้าง…' : `สร้างใบขอราคา (${picked.size} ราย)`}
          </button>
        </>
      }
    >
      <form id="rq-form" onSubmit={submit}>
        {err && <div className="alert alert-error">{err}</div>}

        {lastPrice != null && (
          <div className="alert alert-info">
            ราคาล่าสุดที่เคยซื้อ <strong>{money(lastPrice)}</strong> บาท — ใช้เป็นฐานเทียบตอนผู้ขายเสนอราคากลับมา
          </div>
        )}

        <div className="field">
          <label htmlFor="rq-title">ชื่อใบขอราคา</label>
          <input id="rq-title" value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>

        <div className="kv-grid" style={{ gap: '0 16px' }}>
          <div className="field">
            <label htmlFor="rq-qty">จำนวนที่ต้องการ{uom ? ` (${uom})` : ''}</label>
            <input id="rq-qty" type="number" min="1" step="any" value={qty}
                   onChange={(e) => setQty(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="rq-due">กำหนดส่งราคา</label>
            <input id="rq-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} />
          </div>
        </div>

        <div className="field">
          <label htmlFor="rq-note">หมายเหตุถึงผู้ขาย</label>
          <input id="rq-note" value={note} onChange={(e) => setNote(e.target.value)}
                 placeholder="เช่น ต้องการของภายในเดือนนี้" />
        </div>

        <div className="field" style={{ marginBottom: 0 }}>
          <label>ขอราคาจากผู้ขาย</label>
          {vendors === null ? (
            <div className="hint">กำลังหาผู้ขายที่เคยขายรหัสนี้…</div>
          ) : vendors.length === 0 ? (
            <div className="hint">
              ไม่มีประวัติว่าใครเคยขายรหัสนี้ให้เรา — เลือกผู้ขายเองได้ที่หน้าใบขอราคาหลังสร้างเสร็จ
            </div>
          ) : (
            <div className="pick-list">
              {vendors.map((v) => (
                <label key={v.vendor_key} className="pick-row">
                  <input
                    type="checkbox"
                    checked={picked.has(v.vendor_key)}
                    onChange={() => toggle(v.vendor_key)}
                  />
                  <span>
                    <span className="cell-title">{v.name || v.vendor_id}</span>
                    {v.last_unit_cost != null && (
                      <span className="cell-sub">
                        {' '}· เคยขายที่ {money(v.last_unit_cost)} บาท ({shortDate(v.last_buy_date)})
                      </span>
                    )}
                  </span>
                </label>
              ))}
            </div>
          )}
        </div>
      </form>
    </Modal>
  );
}
