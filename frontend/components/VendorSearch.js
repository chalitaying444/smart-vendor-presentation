'use client';

/**
 * ค้นหาผู้ขายเพิ่มสำหรับรายการหนึ่งใน BOM — ใช้ร่วมกันระหว่าง
 * หน้าออกใบขอราคาทั้งโครงการ และหน้าวัสดุรายตัว (แท็บเทียบราคา)
 *
 * ค้นได้สองทาง เพราะคนใช้มาจากสองสถานการณ์:
 *   - รู้ชื่อเจ้าที่อยากเชิญอยู่แล้ว → ค้นตามชื่อ
 *   - ไม่รู้ว่าใครขายของแบบนี้ → ค้นจากอุปกรณ์ที่ใกล้เคียง แล้วดูว่าใครเคยขายของพวกนั้น
 * แบบหลังจะบอกเสมอว่ารายชื่อนี้ "มาจากสินค้าตัวไหน" ไม่ใช่คำแนะนำลอย ๆ ที่ตรวจย้อนไม่ได้
 *
 * ผลค้นติดธง invited มาจากหลังบ้าน = เจ้านี้ถูกเชิญให้เสนอราคาของบรรทัดนี้ไปแล้ว
 * ต้องเห็นก่อนกด ไม่ใช่ไปรู้ตอนออกใบซ้ำ
 */
import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import OtdBadge from '@/components/OtdBadge';
import { money, num } from '@/lib/format';

const MODES = [
  { key: 'item', label: 'ตามอุปกรณ์ที่ใกล้เคียง' },
  { key: 'name', label: 'ตามชื่อผู้ขาย' },
];

export default function VendorSearch({ bomId, lineNo, lineName, already, onAdd }) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState('item');
  const [term, setTerm] = useState('');
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const run = useCallback(async (by, q) => {
    if (by === 'name' && !q.trim()) return;
    setBusy(true); setError('');
    try {
      setRes(await api.bomVendorSearch(bomId, lineNo, { by, q: q.trim(), limit: 12 }));
    } catch (e) { setError(e.message); setRes({ items: [] }); } finally { setBusy(false); }
  }, [bomId, lineNo]);

  // เปลี่ยนรายการ = เริ่มใหม่ทุกครั้ง ไม่งั้นจะเห็นผลค้นของรายการก่อนหน้าค้างอยู่
  useEffect(() => { setOpen(false); setTerm(''); setRes(null); setMode('item'); }, [lineNo]);

  function start() {
    setOpen(true);
    run('item', '');          // ตั้งต้นด้วยชื่อจาก BOM — เป็นสิ่งที่กำลังหาอยู่พอดี
  }

  if (!open) {
    return (
      <div className="vendor-add">
        <button type="button" className="btn btn-secondary btn-sm" onClick={start}>
          + ค้นหาผู้ขายเพิ่ม
        </button>
        <span className="cell-sub">
          รายชื่อด้านบนคือเจ้าที่เคยขายรหัสนี้ · อยากเชิญเจ้าอื่นก็ค้นเพิ่มได้
          ทั้งตามชื่อผู้ขายและตามอุปกรณ์ที่ใกล้เคียง
        </span>
      </div>
    );
  }

  return (
    <div className="vendor-add open">
      <div className="tabs tabs-inline">
        {MODES.map((m) => (
          <button key={m.key} type="button"
                  className={`tab${mode === m.key ? ' active' : ''}`}
                  onClick={() => { setMode(m.key); setRes(null); run(m.key, term); }}>
            {m.label}
          </button>
        ))}
      </div>

      <div className="vendor-add-bar">
        <input type="search" value={term} autoFocus
               aria-label="ค้นหาผู้ขายเพิ่ม"
               placeholder={mode === 'item'
                 ? `เว้นว่าง = ใช้ "${lineName}" ค้นให้ · หรือพิมพ์สเปกอื่น แล้วกด Enter`
                 : 'ชื่อผู้ขาย รหัสผู้ขาย หรืออีเมล… แล้วกด Enter'}
               onChange={(e) => setTerm(e.target.value)}
               onKeyDown={(e) => { if (e.key === 'Enter') run(mode, term); }} />
        <button type="button" className="btn btn-secondary btn-sm"
                disabled={busy || (mode === 'name' && !term.trim())}
                onClick={() => run(mode, term)}>{busy ? 'กำลังค้น…' : 'ค้นหา'}</button>
        <button type="button" className="btn btn-secondary btn-sm"
                onClick={() => setOpen(false)}>ปิด</button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {mode === 'item' && res?.via_items?.length > 0 && (
        <div className="hint" style={{ marginTop: 0 }}>
          ค้นจากสินค้าที่ใกล้เคียง:{' '}
          {res.via_items.slice(0, 3).map((i) => i.description || i.part_num).join(' · ')}
        </div>
      )}

      {res && (
        res.items.length === 0 ? (
          <div className="hint">ไม่เจอผู้ขายที่ตรงกับคำค้นนี้</div>
        ) : (
          <div className="table-wrap preview-wrap">
            <table className="quote-table vendor-found">
              <colgroup><col /><col style={{ width: 236 }} /><col style={{ width: 128 }} /></colgroup>
              <thead>
                <tr><th>ผู้ขาย</th><th>ส่งตรงเวลา</th><th /></tr>
              </thead>
              <tbody>
                {res.items.map((v) => {
                  const added = already.includes(v.vendor_key);
                  return (
                    <tr key={v.vendor_key}>
                      <td>
                        <div className="cell-title">{v.name}</div>
                        <div className="cell-sub">
                          <code>{v.vendor_id}</code>
                          {v.po_count ? <> · เคยซื้อ {num(v.po_count)} ครั้ง</> : <> · ยังไม่เคยซื้อ</>}
                          {v.inactive && <span className="conf conf-warn">ปิดใช้งานใน Epicor</span>}
                          {/* เชิญไปแล้วก็ยังเพิ่มได้ (ราคาอาจหมดอายุ) แต่ต้องรู้ตัวก่อนกด */}
                          {v.invited && (
                            <span className="conf conf-manual">
                              เชิญแล้ว{v.invited_rfqs?.length ? ` · ${v.invited_rfqs.join(' · ')}` : ''}
                            </span>
                          )}
                        </div>
                        {v.via_items?.length > 0 && (
                          <div className="cell-sub via-items">
                            เคยขาย: {v.via_items.map((i) => (
                              <span key={i.part_num}>
                                {i.description || i.part_num}
                                {i.last_unit_cost != null && ` (${money(i.last_unit_cost)})`}
                              </span>
                            )).reduce((all, el) => all.length ? [...all, ' · ', el] : [el], [])}
                          </div>
                        )}
                      </td>
                      <td><OtdBadge delivery={v.delivery} compact /></td>
                      <td className="actions">
                        <button type="button" className="btn btn-secondary btn-sm"
                                disabled={added} onClick={() => onAdd(v)}>
                          {added ? 'เพิ่มแล้ว' : 'เพิ่ม'}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  );
}
