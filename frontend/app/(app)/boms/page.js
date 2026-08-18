'use client';

/**
 * ประมาณราคา BOM — หน้ารายการ + ตัวช่วยนำ BOM เข้าระบบ
 *
 * นำเข้าได้สองทาง: อัปโหลดไฟล์ Excel/CSV หรือวางข้อความจาก Excel ตรง ๆ
 * ทั้งสองทางจะแสดง "ผลที่อ่านได้" ให้ตรวจก่อนเสมอ ไม่บันทึกทันที —
 * เพราะไฟล์ BOM ของจริงมีหัวตารางแปลก ๆ เยอะ ถ้าอ่านผิดแล้วบันทึกเลย
 * คนจะไปเจอปัญหาตอนงบออกมาผิด ซึ่งสายเกินกว่าจะรู้ว่าผิดตั้งแต่ตอนอ่านไฟล์
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { IconPlus, IconSearch } from '@/components/icons';
import { api, uploadBomFile } from '@/lib/api';
import { useBatchList, useDebounced, useOnScreen } from '@/components/useBatchList';
import { SkeletonRows } from '@/components/Skeleton';
import { money, num, shortDate } from '@/lib/format';

const BATCH = 30;

const BOM_STATUS = {
  draft: { label: 'ร่าง', cls: 'badge-off' },
  estimated: { label: 'ประมาณราคาแล้ว', cls: 'badge-staff' },
  rfq_sent: { label: 'ออกใบขอราคาแล้ว', cls: 'badge-admin' },
  closed: { label: 'ปิดแล้ว', cls: 'badge-off' },
};

const SAMPLE = `รายการ\tจำนวน\tหน่วย
ตู้ควบคุม outdoor cabinet IP55\t2\tEA
สาย fiber optic SM 24C\t500\tM`;

/* มุมมองของหน้ารายการ — แยกเป็นแท็บ เพราะสามคำถามนี้คนละคำถามกัน:
   "งานของทีมมีอะไรบ้าง" / "งานที่ฉันรับผิดชอบ" / "ลบอะไรไปแล้วบ้าง" */
const VIEWS = [
  { key: 'all', label: 'ทั้งหมดที่เห็นได้', params: {} },
  { key: 'mine', label: 'ของฉัน', params: { mine: true } },
  { key: 'trash', label: 'ถังขยะ', params: { trash: true } },
];

export default function BomListPage() {
  const search = useSearchParams();
  const justDeleted = search.get('deleted') || '';
  const cancelledRfqs = Number(search.get('rfqs') || 0);
  const [term, setTerm] = useState('');
  const [view, setView] = useState('all');
  const [dept, setDept] = useState('');
  const q = useDebounced(term, 350);
  const filters = useMemo(
    () => ({ q, ...(VIEWS.find((v) => v.key === view)?.params || {}), department: dept }),
    [q, view, dept],
  );
  const fetcher = useCallback((p) => api.listBoms(p), []);
  const { items, total, hasMore, loading, loadingMore, error, loadMore, reload, meta } =
    useBatchList(fetcher, filters, BATCH);
  const sentinel = useOnScreen(loadMore, hasMore && !loading && !loadingMore);
  const [importing, setImporting] = useState(false);
  const [busy, setBusy] = useState('');
  const myDepts = meta?.departments || [];

  const [note, setNote] = useState('');

  async function restore(id) {
    setBusy(id);
    try {
      const res = await api.restoreBom(id);
      setNote(res.message || '');
      reload();
    } finally { setBusy(''); }
  }

  return (
    <>
      {justDeleted && (
        <div className="alert alert-ok">
          ย้าย <strong>{justDeleted}</strong> เข้าถังขยะแล้ว — คนอื่นจะไม่เห็นโครงการนี้
          {cancelledRfqs > 0 && (
            <> · ยกเลิกใบขอราคา <strong>{num(cancelledRfqs)} ใบ</strong> ด้วย
              (ผู้ขายที่เปิดลิงก์จะเห็นว่ายกเลิกแล้ว)</>
          )}
          {' · '}
          <button className="link-btn" onClick={() => setView('trash')}>เปิดถังขยะเพื่อกู้คืน</button>
        </div>
      )}

      {note && <div className="alert alert-ok">{note}</div>}

      <div className="card" style={{ marginBottom: 18 }}>
        <div className="card-head">
          <div className="search-wrap">
            <IconSearch />
            <input type="search" value={term} onChange={(e) => setTerm(e.target.value)}
                   placeholder="ค้นหาชื่อโครงการ หรือเลขที่ BOM…" />
          </div>
          <div className="toolbar">
            <button className="btn btn-primary" onClick={() => setImporting(true)}>
              <IconPlus /> นำ BOM เข้ามาประมาณราคา
            </button>
          </div>
        </div>
        <div className="card-body" style={{ paddingTop: 0 }}>
          <div className="hint" style={{ marginTop: 0 }}>
            ระบบจะจับคู่รายการใน BOM กับสินค้าที่เคยซื้อจริง แล้วใช้ <strong>ราคาซื้อล่าสุด</strong>
            ตีเป็นงบเบื้องต้น — ทุกบรรทัดกดเข้าไปแก้หรือเลือกสินค้าใหม่ได้
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <div>
            <h2>งานประมาณราคา</h2>
            <div className="cell-sub">
              {loading ? 'กำลังโหลด…' : `${num(total)} งาน`}
              {/* บอกให้ชัดว่านี่ไม่ใช่ "ทุกโครงการในบริษัท" — ไม่งั้นคนจะนึกว่าของหาย */}
              {!meta?.is_admin && (
                myDepts.length
                  ? ` · เห็นเฉพาะของ ${myDepts.join(' / ')} และโครงการที่ถูกเพิ่มเข้าไป`
                  : ' · ยังไม่ได้สังกัดหน่วยงาน จึงเห็นเฉพาะโครงการของตัวเอง'
              )}
            </div>
          </div>
          <div className="tabs tabs-inline">
            {VIEWS.map((v) => (
              <button key={v.key} className={`tab${view === v.key ? ' active' : ''}`}
                      onClick={() => setView(v.key)}>{v.label}</button>
            ))}
          </div>
          {myDepts.length > 1 && (
            <div className="field-inline">
              <label htmlFor="dept-filter">หน่วยงาน</label>
              <select id="dept-filter" value={dept} onChange={(e) => setDept(e.target.value)}>
                <option value="">ทุกหน่วยงานที่สังกัด</option>
                {myDepts.map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
          )}
        </div>
        {error && <div className="alert alert-error" style={{ margin: 16 }}>{error}</div>}
        <div className="table-wrap">
          <table className="vendor-table">
            <thead>
              <tr>
                <th style={{ minWidth: 260 }}>โครงการ</th>
                <th style={{ width: 150 }}>หน่วยงาน / เจ้าของ</th>
                <th style={{ width: 150 }}>สถานะ</th>
                <th style={{ width: 160 }}>ตีราคาได้</th>
                <th style={{ width: 190 }}>ความคืบหน้า</th>
                <th style={{ width: 160, textAlign: 'right' }}>งบประมาณ</th>
                <th style={{ width: 130 }}>แก้ไขล่าสุด</th>
              </tr>
            </thead>
            {/* SkeletonRows วาดกลุ่มแถวของตัวเอง จึงต้องเป็นพี่น้องกับกลุ่มแถวจริง
                ไม่ใช่ลูกของมัน — ไม่งั้น HTML จะซ้อนกันแล้ว hydration พัง */}
            {loading && <SkeletonRows rows={5} cols={7}
                                      widths={['70%', '52%', '46%', '54%', '58%', '52%', '48%']} />}
            <tbody>
              {!loading && items.map((b) => (
                <tr key={b.id} className="row-link">
                  <td>
                    <Link href={`/boms/${b.id}`} className="cell-title">{b.title}</Link>
                    <div className="cell-sub">
                      <code>{b.bom_no}</code> · {num(b.line_count)} รายการ
                      {b.rfq_no && <> · ออกใบขอราคา {b.rfq_no} แล้ว</>}
                    </div>
                  </td>
                  <td>
                    <div>{b.department || <span className="muted">ไม่ระบุหน่วยงาน</span>}</div>
                    <div className="cell-sub">{b.owner}</div>
                  </td>
                  <td>
                    <span className={`badge ${(BOM_STATUS[b.status] || {}).cls || 'badge-off'}`}>
                      {(BOM_STATUS[b.status] || {}).label || b.status}
                    </span>
                  </td>
                  <td>
                    <Coverage priced={b.priced_lines} total={b.line_count}
                              percent={b.coverage_percent} />
                  </td>
                  <td><Progress p={b.progress} total={b.line_count} /></td>
                  <td className="num-cell">
                    {b.total ? <strong>{money(b.total)}</strong> : <span className="muted">—</span>}
                    <div className="cell-sub">{b.currency}</div>
                  </td>
                  <td>
                    {view === 'trash' ? (
                      <>
                        <div className="cell-sub">ลบเมื่อ {shortDate(b.deleted_at)}</div>
                        {b.can_manage && (
                          <button className="btn btn-secondary btn-sm" disabled={busy === b.id}
                                  onClick={() => restore(b.id)}>
                            {busy === b.id ? 'กำลังกู้…' : 'กู้คืน'}
                          </button>
                        )}
                      </>
                    ) : shortDate(b.updated_at)}
                  </td>
                </tr>
              ))}
              {!loading && !items.length && (
                <tr><td colSpan={7}>
                  <div className="empty">
                    {view === 'trash' ? (
                      <>
                        <strong>ถังขยะว่าง</strong>
                        โครงการที่ลบจะมาพักที่นี่ และกู้คืนได้
                      </>
                    ) : (
                      <>
                        <strong>ยังไม่มีงานประมาณราคา{view === 'mine' ? 'ของคุณ' : ''}</strong>
                        เอา BOM ของโครงการมาวางหรืออัปโหลดไฟล์ แล้วระบบจะตีงบให้จากราคาที่เคยซื้อ
                      </>
                    )}
                  </div>
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
        {hasMore && <div ref={sentinel} className="load-more">กำลังโหลดเพิ่ม…</div>}
      </div>

      {importing && (
        <ImportBox onClose={() => setImporting(false)} onDone={reload} />
      )}
    </>
  );
}

/** ความคืบหน้าแบบย่อ — เห็นจากหน้ารายการได้เลยว่าโครงการไหนค้างอยู่ขั้นไหน */
function Progress({ p, total }) {
  if (!p || !p.stages) return <span className="muted">—</span>;
  const asked = p.asked_lines || 0;
  const awarded = p.awarded_lines || 0;
  if (!asked) return <span className="stage stage-est">ยังไม่ออกใบขอราคา</span>;
  if (awarded >= total) return <span className="stage stage-ok">อนุมัติราคาครบแล้ว</span>;
  return (
    <div>
      <span className={`stage ${awarded ? 'stage-quoted' : 'stage-rfq'}`}>
        ออกใบแล้ว {num(asked)}/{num(total)}
      </span>
      <div className="cell-sub">
        {awarded > 0 && <>อนุมัติแล้ว {num(awarded)} · </>}
        {p.waiting_lines > 0 ? `รอผู้ขายตอบ ${num(p.waiting_lines)}` : 'ยังไม่มีที่รอตอบ'}
      </div>
    </div>
  );
}

function Coverage({ priced, total, percent }) {
  const full = total > 0 && priced === total;
  return (
    <div>
      <div className={`cell-title${full ? '' : ' tone-warn'}`}>
        {num(priced)}/{num(total)} รายการ
      </div>
      <div className="cover-bar" title={`${percent}%`}>
        <span style={{ width: `${Math.min(percent || 0, 100)}%` }}
              className={full ? 'ok' : 'partial'} />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ นำเข้า */
function ImportBox({ onClose, onDone }) {
  const router = useRouter();
  const [mode, setMode] = useState('paste');
  const [text, setText] = useState('');
  const [lines, setLines] = useState(null);
  const [title, setTitle] = useState('');
  const [note, setNote] = useState('');
  const [department, setDepartment] = useState('');
  const [depts, setDepts] = useState([]);
  const [contingency, setContingency] = useState(10);
  const [vat, setVat] = useState(7);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const fileRef = useRef(null);

  // หน่วยงานตั้งต้น = หน่วยงานแรกที่ตัวเองสังกัด · ย้ายไปหน่วยงานอื่นได้ถ้าอยู่หลายหน่วยงาน
  useEffect(() => {
    api.listBoms({ limit: 1 })
      .then((r) => {
        setDepts(r.departments || []);
        setDepartment((prev) => prev || (r.departments || [])[0] || '');
      })
      .catch(() => {});
  }, []);

  async function readText() {
    setBusy(true); setError('');
    try {
      const res = await api.parseBom(text);
      if (!res.count) throw new Error('อ่านแล้วไม่พบรายการ — ตรวจว่ามีชื่อรายการและจำนวนหรือไม่');
      setLines(res.lines);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  async function readFile(file) {
    if (!file) return;
    setBusy(true); setError('');
    try {
      const res = await uploadBomFile(file);
      setLines(res.lines);
      if (!title) setTitle(file.name.replace(/\.[^.]+$/, ''));
    } catch (e) { setError(e.message); } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  }

  function editLine(index, patch) {
    setLines((rows) => rows.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  async function save() {
    setBusy(true); setError('');
    try {
      const clean = lines
        .filter((l) => (l.name || '').trim() && Number(l.qty) > 0)
        .map((l) => ({
          name: l.name.trim(), qty: Number(l.qty),
          uom: l.uom || '', part_hint: l.part_hint || '', remark: l.remark || '',
        }));
      if (!clean.length) throw new Error('ไม่มีรายการที่บันทึกได้');
      const bom = await api.createBom({
        title: title.trim() || 'ประมาณราคาโครงการ',
        department: department.trim(),
        note: note.trim(),
        contingency_percent: Number(contingency) || 0,
        vat_percent: Number(vat) || 0,
        lines: clean,
      });
      onDone?.();
      router.push(`/boms/${bom.id}`);
    } catch (e) { setError(e.message); setBusy(false); }
  }

  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      {/* ขั้นเลือกไฟล์ยังไม่มีตาราง ใช้กล่องปกติ · พอมีรายการให้ตรวจค่อยขยายเต็มจอ
          กล่องใหญ่โล่ง ๆ ตอนยังไม่มีอะไรให้ดู อ่านยากกว่ากล่องพอดีตัว */}
      <div className={`modal ${lines ? 'modal-xl' : 'modal-wide'}`}>
        <div className="modal-head">
          <h2>นำ BOM เข้ามาประมาณราคา</h2>
          <p>ระบบจะอ่านรายการให้ก่อน ตรวจแล้วค่อยกดบันทึก</p>
        </div>

        <div className="modal-body">
          {error && <div className="alert alert-error">{error}</div>}

          {!lines && (
            <>
              <div className="tabs tabs-inline">
                <button className={`tab${mode === 'paste' ? ' active' : ''}`}
                        onClick={() => setMode('paste')}>วางข้อความ</button>
                <button className={`tab${mode === 'file' ? ' active' : ''}`}
                        onClick={() => setMode('file')}>อัปโหลดไฟล์</button>
              </div>

              {mode === 'paste' ? (
                <div className="field" style={{ marginTop: 14 }}>
                  <label htmlFor="bom-text">วางจาก Excel ได้เลย (คัดลอกทั้งคอลัมน์)</label>
                  <textarea id="bom-text" rows={9} value={text} spellCheck={false}
                            onChange={(e) => setText(e.target.value)}
                            placeholder={SAMPLE} style={{ fontFamily: 'var(--mono, monospace)' }} />
                  <div className="hint">
                    รองรับทั้งแบบมีหัวตารางและไม่มี · คั่นด้วย tab, comma, ; หรือ | ก็ได้
                  </div>
                  <button className="btn btn-primary" style={{ marginTop: 12 }}
                          disabled={busy || !text.trim()} onClick={readText}>
                    {busy ? 'กำลังอ่าน…' : 'อ่านรายการ'}
                  </button>
                </div>
              ) : (
                <div style={{ marginTop: 14 }}>
                  <label className="dropzone">
                    <input ref={fileRef} type="file" accept=".xlsx,.xlsm,.csv,.txt,.tsv"
                           disabled={busy} onChange={(e) => readFile(e.target.files?.[0])} />
                    <span className="dropzone-main">
                      {busy ? 'กำลังอ่านไฟล์…' : 'เลือกไฟล์ BOM'}
                    </span>
                    <span className="dropzone-sub">Excel (.xlsx) · CSV · TXT · ไม่เกิน 5 MB</span>
                  </label>
                  <div className="hint">
                    ระบบจะหาคอลัมน์ชื่อรายการ / จำนวน / หน่วย / รหัส จากหัวตารางให้เอง
                  </div>
                </div>
              )}
            </>
          )}

          {lines && (
            <>
              <div className="alert alert-info">
                อ่านได้ {num(lines.length)} รายการ — ตรวจชื่อกับจำนวนให้ถูกก่อนบันทึก
                แก้ตรงนี้ได้เลย
              </div>
              <div className="table-wrap preview-wrap">
                <table className="quote-table">
                  <colgroup><col style={{ width: 46 }} /><col /><col style={{ width: 110 }} />
                    <col style={{ width: 90 }} /><col style={{ width: 60 }} /></colgroup>
                  <thead>
                    <tr>
                      <th>#</th><th>รายการ</th>
                      <th className="num-head">จำนวน</th><th>หน่วย</th><th />
                    </tr>
                  </thead>
                  <tbody>
                    {lines.map((l, i) => (
                      <tr key={i}>
                        <td className="cell-sub">{i + 1}</td>
                        <td><input type="text" value={l.name}
                                   onChange={(e) => editLine(i, { name: e.target.value })} /></td>
                        <td><input type="number" className="num-input" min="0" step="any" value={l.qty}
                                   onChange={(e) => editLine(i, { qty: e.target.value })} /></td>
                        <td><input type="text" value={l.uom || ''}
                                   onChange={(e) => editLine(i, { uom: e.target.value })} /></td>
                        <td>
                          <button className="btn btn-danger btn-sm" title="เอาออก"
                                  onClick={() => setLines((r) => r.filter((_, x) => x !== i))}>
                            ลบ
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="portal-grid" style={{ marginTop: 16 }}>
                <div className="field">
                  <label htmlFor="b-title">ชื่อโครงการ</label>
                  <input id="b-title" type="text" value={title}
                         onChange={(e) => setTitle(e.target.value)}
                         placeholder="เช่น ปรับปรุงระบบสื่อสารสถานีไฟฟ้า A" />
                </div>
                <div className="field">
                  <label htmlFor="b-dept">หน่วยงานเจ้าของโครงการ</label>
                  {depts.length > 1 ? (
                    <select id="b-dept" value={department}
                            onChange={(e) => setDepartment(e.target.value)}>
                      {depts.map((d) => <option key={d} value={d}>{d}</option>)}
                    </select>
                  ) : (
                    <input id="b-dept" type="text" value={department}
                           onChange={(e) => setDepartment(e.target.value)}
                           placeholder="เช่น ฝ่ายจัดซื้อ" />
                  )}
                  <div className="hint">คนในหน่วยงานนี้จะเห็นโครงการนี้ทุกคน</div>
                </div>
                <div className="field">
                  <label htmlFor="b-cont">เผื่อสำรอง (%)</label>
                  <input id="b-cont" type="number" min="0" max="100" step="1" value={contingency}
                         onChange={(e) => setContingency(e.target.value)} />
                </div>
                <div className="field">
                  <label htmlFor="b-vat">ภาษีมูลค่าเพิ่ม (%)</label>
                  <input id="b-vat" type="number" min="0" max="100" step="1" value={vat}
                         onChange={(e) => setVat(e.target.value)} />
                </div>
                <div className="field span-all" style={{ marginBottom: 0 }}>
                  <label htmlFor="b-note">หมายเหตุ</label>
                  <input id="b-note" type="text" value={note}
                         onChange={(e) => setNote(e.target.value)}
                         placeholder="เช่น ประมาณการรอบแรก ยังไม่รวมค่าติดตั้ง" />
                </div>
              </div>
            </>
          )}
        </div>

        <div className="modal-foot">
          {lines && (
            <button className="btn btn-secondary" disabled={busy}
                    onClick={() => setLines(null)}>ย้อนกลับ</button>
          )}
          <div className="spacer" />
          <button className="btn btn-secondary" onClick={onClose} disabled={busy}>ยกเลิก</button>
          {lines && (
            <button className="btn btn-primary" disabled={busy} onClick={save}>
              {busy ? 'กำลังจับคู่สินค้า…' : `บันทึกและประมาณราคา ${lines.length} รายการ`}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
