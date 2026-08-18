'use client';

/**
 * หน้าเสนอราคาสำหรับผู้ขาย — เปิดด้วยลิงก์เฉพาะราย ไม่ต้องล็อกอิน
 * อยู่นอก route group (app) จึงไม่มีเมนูและไม่ผ่านการตรวจสิทธิ์
 *
 * ลำดับการใช้งานตั้งใจให้เป็นขั้น ๆ:
 *   1. อ่านและกดรับทราบเงื่อนไข  (ระบบบันทึกเวลาไว้เป็นหลักฐาน)
 *   2. กรอกราคา หรือแนบไฟล์ใบเสนอราคาของบริษัทตัวเอง
 *   3. ส่ง — แก้ไขและส่งใหม่ได้จนกว่าใบขอราคาจะปิด
 *
 * หน้านี้คือหน้าที่ "คนนอกบริษัท" เห็น จึงต้องอ่านง่ายและดูน่าเชื่อถือ
 * และต้องไม่หลุดข้อมูลภายใน (ราคาที่เคยซื้อ / รายชื่อผู้ขายรายอื่นที่ถูกเชิญ)
 */
import { use, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, fileUrl, uploadPortalAttachment } from '@/lib/api';
import { money, num, shortDate } from '@/lib/format';

export default function PortalPage({ params }) {
  const { token } = use(params);
  return <Portal token={token} />;
}

function Portal({ token }) {
  const [view, setView] = useState(null);
  const [error, setError] = useState('');
  const [prices, setPrices] = useState({});
  const [lead, setLead] = useState({});
  const [contact, setContact] = useState({ contact_name: '', contact_email: '', contact_phone: '' });
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState('');
  const [declining, setDeclining] = useState(false);

  const [ticked, setTicked] = useState(false);
  const [acceptedBy, setAcceptedBy] = useState('');
  const [accepting, setAccepting] = useState(false);

  const [attachments, setAttachments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  const apply = useCallback((v) => {
    setView(v);
    setAttachments(v.quote?.attachments || []);
    const q = v.quote;
    if (q?.lines?.length) {
      setPrices(Object.fromEntries(q.lines.map((l) => [l.part_num, l.unit_price ?? ''])));
      setLead(Object.fromEntries(q.lines.map((l) => [l.part_num, l.lead_time_days ?? ''])));
      setContact({
        contact_name: q.contact_name || '',
        contact_email: q.contact_email || '',
        contact_phone: q.contact_phone || '',
      });
      setNote(q.note || '');
    }
  }, []);

  useEffect(() => {
    api.portalView(token).then(apply).catch((e) => setError(e.message));
  }, [token, apply]);

  const subtotal = useMemo(() => {
    if (!view?.lines) return 0;
    return view.lines.reduce((sum, l) => {
      const p = parseFloat(prices[l.part_num]);
      return sum + (Number.isFinite(p) ? p * (l.qty || 0) : 0);
    }, 0);
  }, [view, prices]);

  const vatPercent = view?.vat_percent ?? 7;
  const vat = subtotal * (vatPercent / 100);
  const quotedCount = view?.lines
    ? view.lines.filter((l) => Number.isFinite(parseFloat(prices[l.part_num]))).length
    : 0;

  async function accept() {
    setAccepting(true);
    setError('');
    try {
      await api.portalAcceptTerms(token, { accepted: true, accepted_by: acceptedBy.trim() });
      apply(await api.portalView(token));
    } catch (e) {
      setError(e.message);
    } finally {
      setAccepting(false);
    }
  }

  async function upload(file) {
    if (!file) return;
    setUploading(true);
    setError('');
    try {
      const res = await uploadPortalAttachment(token, file);
      setAttachments(res.attachments || []);
      setDone(`แนบไฟล์ “${file.name}” เรียบร้อยแล้ว`);
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  async function removeFile(fileId) {
    setError('');
    try {
      const res = await api.portalDeleteAttachment(token, fileId);
      setAttachments(res.attachments || []);
    } catch (e) {
      setError(e.message);
    }
  }

  async function submit(e) {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      const lines = view.lines.map((l) => {
        const raw = prices[l.part_num];
        const has = raw !== '' && raw != null && Number.isFinite(parseFloat(raw));
        return {
          part_num: l.part_num,
          unit_price: has ? parseFloat(raw) : null,
          lead_time_days:
            lead[l.part_num] === '' || lead[l.part_num] == null
              ? null : parseInt(lead[l.part_num], 10),
          no_quote: !has,
        };
      });
      await api.portalQuote(token, {
        lines, currency: view.currency, vat_percent: vatPercent, note, ...contact,
      });
      setDone('ส่งราคาเรียบร้อยแล้ว ขอบคุณครับ — แก้ไขและส่งใหม่ได้จนกว่าใบขอราคาจะปิด');
      apply(await api.portalView(token));
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  if (error && !view) {
    return (
      <div className="center-screen">
        <div className="card portal-card" style={{ padding: 32, maxWidth: 460, textAlign: 'center' }}>
          <h2 style={{ marginBottom: 8 }}>เปิดใบขอราคานี้ไม่ได้</h2>
          <p className="cell-sub" style={{ marginBottom: 0 }}>{error}</p>
        </div>
      </div>
    );
  }
  if (!view) return <div className="center-screen">กำลังโหลด…</div>;

  /* ---------- โครงการถูกลบ = ใบนี้ถูกยกเลิก ----------
     ผู้ขายถือลิงก์อยู่ในมือ และอาจกดเข้ามาอีกหลายวันให้หลัง ต้องบอกให้ชัดว่ายกเลิกแล้ว
     พร้อมเลขที่ใบไว้อ้างอิงตอนโทรถาม — ดีกว่าปล่อยให้เจอหน้า error ที่อ่านไม่ออก */
  if (view.cancelled) {
    return (
      <div className="portal-page">
        <header className="portal-head">
          <div className="portal-brand">
            <div className="brand-mark">VA</div>
            <div>
              <div className="portal-title">ใบขอราคา {view.rfq_no}</div>
              <div className="portal-sub">ระบบเสนอราคาออนไลน์สำหรับผู้ขาย</div>
            </div>
          </div>
        </header>
        <div className="portal-gate">
          <div className="card portal-card gate-card">
            <div className="gate-head">
              <LockIcon />
              <div>
                <h1>ใบขอราคานี้ถูกยกเลิกแล้ว</h1>
                <p>
                  ผู้ซื้อยกเลิกใบขอราคาเลขที่ <strong>{view.rfq_no}</strong> แล้ว
                  จึงไม่รับข้อมูลเพิ่มและไม่ต้องเสนอราคา ·
                  หากท่านเพิ่งได้รับลิงก์นี้ กรุณาติดต่อฝ่ายจัดซื้อเพื่อยืนยัน
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const closed = ['closed', 'awarded'].includes(view.status);
  const declined = view.invite_status === 'declined';
  const accepted = Boolean(view.terms_accepted_at);
  const locked = closed || declined;

  /* ---------- ด่านแรก: ยังไม่รับทราบเงื่อนไข = ยังไม่เห็นอะไรเลย ---------- */
  if (!accepted) {
    return (
      <div className="portal-page">
        <header className="portal-head">
          <div className="portal-brand">
            <div className="brand-mark">VA</div>
            <div>
              <div className="portal-title">ใบขอราคา {view.rfq_no}</div>
              <div className="portal-sub">ระบบเสนอราคาออนไลน์สำหรับผู้ขาย</div>
            </div>
          </div>
        </header>

        <div className="portal-gate">
          <ol className="portal-steps" aria-label="ขั้นตอนการเสนอราคา">
            <li className="current"><span className="step-no">1</span> รับทราบเงื่อนไข</li>
            <li><span className="step-no">2</span> กรอกราคา / แนบไฟล์</li>
            <li><span className="step-no">3</span> ส่งให้ผู้ซื้อ</li>
          </ol>

          {error && <div className="alert alert-error">{error}</div>}
          {closed && <div className="alert alert-info">ใบขอราคานี้ปิดรับราคาแล้ว</div>}
          {declined && <div className="alert alert-info">ท่านแจ้งไม่ขอเสนอราคาใบนี้ไว้</div>}

          <div className="card portal-card gate-card">
            <div className="gate-head">
              <LockIcon />
              <div>
                <h1>เงื่อนไขการเสนอราคา</h1>
                <p>
                  รายละเอียดใบขอราคาจะแสดงหลังจากท่านกดรับทราบเงื่อนไขด้านล่างแล้วเท่านั้น
                </p>
              </div>
            </div>

            <div className="gate-meta">
              <span className="gate-chip">เลขที่ {view.rfq_no}</span>
              <span className="gate-chip">{num(view.line_count)} รายการ</span>
              {view.due_date && (
                <span className="gate-chip">กำหนดส่งราคา {shortDate(view.due_date)}</span>
              )}
            </div>

            <ol className="terms-list gate-terms">
              {(view.terms || []).map((t, i) => <li key={i}>{t}</li>)}
            </ol>

            {!locked ? (
              <div className="gate-accept">
                <label className="checkbox gate-check">
                  <input type="checkbox" checked={ticked}
                         onChange={(e) => setTicked(e.target.checked)} />
                  <span>ข้าพเจ้าได้อ่านและเข้าใจเงื่อนไขข้างต้นแล้ว</span>
                </label>
                <div className="field gate-name">
                  <label htmlFor="gate-by">ชื่อผู้รับทราบ (ไม่บังคับ)</label>
                  <input id="gate-by" value={acceptedBy} autoComplete="name"
                         onChange={(e) => setAcceptedBy(e.target.value)}
                         placeholder="เช่น สมชาย ใจดี" />
                </div>
                <button className="btn btn-primary btn-lg gate-btn"
                        disabled={!ticked || accepting} onClick={accept}>
                  {accepting ? 'กำลังบันทึก…' : 'รับทราบเงื่อนไข และดูใบขอราคา'}
                </button>
              </div>
            ) : (
              <div className="hint">ใบขอราคานี้ไม่เปิดรับราคาแล้ว จึงไม่สามารถเปิดดูรายละเอียดได้</div>
            )}
          </div>

          <footer className="portal-foot">
            ระบบบันทึกวันเวลาที่กดรับทราบไว้เป็นหลักฐาน · ลิงก์นี้ออกให้เฉพาะราย
            กรุณาไม่ส่งต่อให้ผู้อื่น
            {view.terms_version && <> · เงื่อนไขฉบับ {view.terms_version}</>}
          </footer>
        </div>
      </div>
    );
  }

  return (
    <div className="portal-page">
      <header className="portal-head">
        <div className="portal-brand">
          <div className="brand-mark">VA</div>
          <div>
            <div className="portal-title">ใบขอราคา {view.rfq_no}</div>
            <div className="portal-sub">{view.title}</div>
          </div>
        </div>
        <a className="btn btn-secondary btn-sm" href={fileUrl.portalDocument(token)}>
          ดาวน์โหลดใบขอราคา (Excel)
        </a>
      </header>

      <div className="portal-body">
        {/* ---------- ขั้นตอน ---------- */}
        <ol className="portal-steps" aria-label="ขั้นตอนการเสนอราคา">
          <li className={accepted ? 'done' : 'current'}>
            <span className="step-no">{accepted ? '✓' : '1'}</span> รับทราบเงื่อนไข
          </li>
          <li className={!accepted ? '' : view.quote?.submitted_at ? 'done' : 'current'}>
            <span className="step-no">{view.quote?.submitted_at ? '✓' : '2'}</span> กรอกราคา / แนบไฟล์
          </li>
          <li className={view.quote?.submitted_at ? 'done' : ''}>
            <span className="step-no">{view.quote?.submitted_at ? '✓' : '3'}</span> ส่งให้ผู้ซื้อ
          </li>
        </ol>

        {done && <div className="alert alert-ok">{done}</div>}
        {error && <div className="alert alert-error">{error}</div>}
        {closed && <div className="alert alert-info">ใบขอราคานี้ปิดรับราคาแล้ว</div>}
        {declined && <div className="alert alert-info">ท่านแจ้งไม่ขอเสนอราคาใบนี้ไว้</div>}

        {/* ---------- ข้อมูลใบขอราคา ---------- */}
        <div className="card portal-card" style={{ marginBottom: 16 }}>
          <div className="card-head">
            <div>
              <h2>รายละเอียดใบขอราคา</h2>
              <div className="cell-sub">กรุณาตรวจสอบข้อมูลก่อนเสนอราคา</div>
            </div>
            {view.quote?.submitted_at && (
              <span className="otd otd-excellent">
                ส่งราคาแล้วเมื่อ {shortDate(view.quote.submitted_at)}
              </span>
            )}
          </div>
          <div className="card-body kv-grid">
            <KV label="เรียน" value={view.vendor?.name || view.vendor?.vendor_name} />
            <KV label="ผู้ติดต่อ" value={view.vendor?.contact_name} />
            <KV label="กำหนดส่งราคา" value={view.due_date ? shortDate(view.due_date) : ''} />
            <KV label="สกุลเงิน" value={view.currency} />
            <KV label="เงื่อนไขชำระเงิน" value={view.payment_terms} />
            <KV label="สถานที่ส่งมอบ" value={view.delivery_place} />
            {view.message && (
              <div className="kv" style={{ gridColumn: '1 / -1' }}>
                <span className="kv-label">ข้อความจากผู้ซื้อ</span>
                <span className="kv-value">{view.message}</span>
              </div>
            )}
          </div>
        </div>

        {/* ---------- เงื่อนไข (ย่อไว้ กดดูซ้ำได้) ---------- */}
        <details className="card portal-card portal-terms accepted" style={{ marginBottom: 16 }}>
          <summary>
            <span>
              <strong>เงื่อนไขการเสนอราคา</strong>
              <span className="cell-sub"> · รับทราบแล้วเมื่อ {shortDate(view.terms_accepted_at)}</span>
            </span>
            <span className="otd otd-excellent">รับทราบแล้ว</span>
          </summary>
          <div className="card-body">
            <ol className="terms-list">
              {(view.terms || []).map((t, i) => <li key={i}>{t}</li>)}
            </ol>
          </div>
        </details>

        {/* ---------- ฟอร์มเสนอราคา ---------- */}
        <fieldset className="portal-fieldset" disabled={locked}>
          <form onSubmit={submit}>
            <div className="card portal-card">
              <div className="card-head">
                <div>
                  <h2>ราคาที่เสนอ</h2>
                  <div className="cell-sub">
                    เว้นว่างไว้ = ไม่เสนอรายการนั้น · เสนอแล้ว {num(quotedCount)}/{num(view.lines.length)} รายการ
                  </div>
                </div>
              </div>
              <div className="table-wrap">
                <table className="quote-table">
                  <colgroup>
                    <col /><col style={{ width: 110 }} /><col style={{ width: 160 }} />
                    <col style={{ width: 130 }} /><col style={{ width: 150 }} />
                  </colgroup>
                  <thead>
                    <tr>
                      <th>สินค้า</th>
                      <th className="num-head">จำนวน</th>
                      <th className="num-head">ราคา/หน่วย</th>
                      <th className="num-head">ส่งของภายใน (วัน)</th>
                      <th className="num-head">รวม</th>
                    </tr>
                  </thead>
                  <tbody>
                    {view.lines.map((l) => {
                      const p = parseFloat(prices[l.part_num]);
                      return (
                        <tr key={l.part_num}>
                          <td className="item-cell">
                            <div className="cell-title">{l.name || l.description}</div>
                            <div className="cell-sub">
                              <code>{l.item_code}</code>
                              {l.remark && <> · {l.remark}</>}
                            </div>
                          </td>
                          <td className="num-cell qty-cell">
                            {num(l.qty, 2)} <span className="uom">{l.uom}</span>
                          </td>
                          <td>
                            <input type="number" min="0" step="0.01" inputMode="decimal"
                                   className="num-input" placeholder="0.00"
                                   aria-label={`ราคาต่อหน่วยของ ${l.name}`}
                                   value={prices[l.part_num] ?? ''}
                                   onChange={(e) =>
                                     setPrices((s) => ({ ...s, [l.part_num]: e.target.value }))} />
                          </td>
                          <td>
                            <input type="number" min="0" step="1" inputMode="numeric"
                                   className="num-input" placeholder="—"
                                   aria-label={`จำนวนวันส่งของของ ${l.name}`}
                                   value={lead[l.part_num] ?? ''}
                                   onChange={(e) =>
                                     setLead((s) => ({ ...s, [l.part_num]: e.target.value }))} />
                          </td>
                          <td className="num-cell">
                            {Number.isFinite(p) ? money(p * l.qty) : <span className="muted">—</span>}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td colSpan={4} className="cell-sub">รวมเป็นเงิน</td>
                      <td className="num-cell">{money(subtotal)}</td>
                    </tr>
                    <tr>
                      <td colSpan={4} className="cell-sub">ภาษีมูลค่าเพิ่ม {num(vatPercent, 2)}%</td>
                      <td className="num-cell">{money(vat)}</td>
                    </tr>
                    <tr>
                      <td colSpan={4} className="cell-title">รวมทั้งสิ้น</td>
                      <td className="num-cell">
                        <strong>{money(subtotal + vat)} {view.currency}</strong>
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>

              <div className="card-body contact-block">
                <h3 className="block-title">ข้อมูลผู้ติดต่อกลับ</h3>
                <div className="portal-grid">
                  <div className="field">
                    <label htmlFor="c-name">ชื่อผู้ติดต่อ</label>
                    <input id="c-name" type="text" autoComplete="name" value={contact.contact_name}
                           placeholder="ชื่อ–นามสกุล ผู้ประสานงาน"
                           onChange={(e) => setContact((c) => ({ ...c, contact_name: e.target.value }))} />
                  </div>
                  <div className="field">
                    <label htmlFor="c-email">อีเมล</label>
                    <input id="c-email" type="email" autoComplete="email" value={contact.contact_email}
                           placeholder="name@company.co.th"
                           onChange={(e) => setContact((c) => ({ ...c, contact_email: e.target.value }))} />
                  </div>
                  <div className="field">
                    <label htmlFor="c-phone">เบอร์โทร</label>
                    <input id="c-phone" type="tel" autoComplete="tel" value={contact.contact_phone}
                           placeholder="0X-XXX-XXXX"
                           onChange={(e) => setContact((c) => ({ ...c, contact_phone: e.target.value }))} />
                  </div>
                  <div className="field span-all" style={{ marginBottom: 0 }}>
                    <label htmlFor="c-note">หมายเหตุถึงผู้ซื้อ</label>
                    <textarea id="c-note" rows={3} value={note}
                              onChange={(e) => setNote(e.target.value)}
                              placeholder="เช่น เงื่อนไขการรับประกัน หรือรายละเอียดที่ต้องการแจ้งเพิ่ม" />
                  </div>
                </div>
              </div>

              <div className="portal-actions">
                <button type="button" className="btn btn-danger" disabled={saving}
                        onClick={() => setDeclining(true)}>
                  ไม่ขอเสนอราคา
                </button>
                <div className="spacer" />
                <button type="submit" className="btn btn-primary btn-lg" disabled={saving}>
                  {saving ? 'กำลังส่ง…' : view.quote?.submitted_at ? 'ส่งราคาที่แก้ไขแล้ว' : 'ส่งราคา'}
                </button>
              </div>
            </div>
          </form>

          {/* ---------- ไฟล์แนบ ---------- */}
          <div className="card portal-card" style={{ marginTop: 16 }}>
            <div className="card-head">
              <div>
                <h2>แนบใบเสนอราคาของบริษัทท่าน</h2>
                <div className="cell-sub">
                  แนบไฟล์ใบเสนอราคาตัวจริงได้ (PDF / Excel / รูปภาพ) แนบได้หลายไฟล์ ·
                  ขนาดไม่เกิน 20 MB ต่อไฟล์
                </div>
              </div>
            </div>
            <div className="card-body">
              <label className="dropzone">
                <input ref={fileRef} type="file" disabled={locked || uploading}
                       accept=".pdf,.xlsx,.xls,.csv,.png,.jpg,.jpeg,.doc,.docx,.zip"
                       onChange={(e) => upload(e.target.files?.[0])} />
                <span className="dropzone-main">
                  {uploading ? 'กำลังอัปโหลด…' : 'เลือกไฟล์ใบเสนอราคา'}
                </span>
                <span className="dropzone-sub">รองรับ PDF · Excel · Word · รูปภาพ · ZIP</span>
              </label>

              {attachments.length > 0 && (
                <ul className="file-list">
                  {attachments.map((f) => (
                    <li key={f.file_id}>
                      <a href={f.url} target="_blank" rel="noreferrer">{f.filename}</a>
                      <span className="cell-sub">
                        {(f.size / 1024).toLocaleString('th-TH', { maximumFractionDigits: 0 })} KB
                        {f.uploaded_at && ` · ${shortDate(f.uploaded_at)}`}
                      </span>
                      <button type="button" className="btn btn-danger btn-sm" disabled={locked}
                              onClick={() => removeFile(f.file_id)}>
                        ลบ
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <div className="hint">
                ถ้าแนบไฟล์อย่างเดียวโดยไม่กรอกราคาในตาราง ผู้ซื้อจะเทียบราคาอัตโนมัติไม่ได้ —
                แนะนำให้กรอกในตารางด้วยจะพิจารณาได้เร็วกว่า
              </div>
            </div>
          </div>
        </fieldset>

        <footer className="portal-foot">
          ลิงก์นี้ออกให้ <strong>{view.vendor?.name || view.vendor?.vendor_name}</strong> โดยเฉพาะ
          กรุณาไม่ส่งต่อให้ผู้อื่น
          {view.terms_version && <> · เงื่อนไขฉบับ {view.terms_version}</>}
        </footer>
      </div>

      {declining && (
        <DeclineBox
          token={token}
          onClose={() => setDeclining(false)}
          onDone={async () => {
            setDeclining(false);
            setDone('แจ้งไม่เสนอราคาเรียบร้อยแล้ว');
            apply(await api.portalView(token));
          }}
          onError={(m) => { setDeclining(false); setError(m); }}
        />
      )}
    </div>
  );
}

function LockIcon() {
  return (
    <svg className="gate-lock" viewBox="0 0 24 24" width="28" height="28"
         fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <rect x="4" y="10" width="16" height="11" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3" />
    </svg>
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

function DeclineBox({ token, onClose, onDone, onError }) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);

  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal" style={{ maxWidth: 440 }}>
        <div className="modal-head">
          <h2>ไม่ขอเสนอราคา</h2>
          <p>แจ้งผู้ซื้อว่าไม่สะดวกเสนอราคาใบนี้</p>
        </div>
        <div className="modal-body">
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor="d-reason">เหตุผล (ไม่บังคับ)</label>
            <input id="d-reason" value={reason} onChange={(e) => setReason(e.target.value)}
                   placeholder="เช่น ไม่มีสินค้าในสต็อก" />
          </div>
        </div>
        <div className="modal-foot">
          <button className="btn btn-secondary" onClick={onClose} disabled={busy}>ยกเลิก</button>
          <button className="btn btn-danger" disabled={busy}
                  onClick={async () => {
                    setBusy(true);
                    try { await api.portalDecline(token, reason); onDone(); }
                    catch (e) { onError(e.message); }
                    finally { setBusy(false); }
                  }}>
            ยืนยัน
          </button>
        </div>
      </div>
    </div>
  );
}
