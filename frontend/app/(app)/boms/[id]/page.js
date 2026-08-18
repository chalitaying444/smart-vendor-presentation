'use client';

/**
 * งานประมาณราคาหนึ่งงาน — ตารางรายการ + งบรวม + แก้ทีละบรรทัด
 *
 * สิ่งที่ตั้งใจให้เห็นก่อนตัวเลขงบเสมอ:
 *   - ตีราคาได้กี่รายการจากทั้งหมด (ยอดรวมคิดเฉพาะที่มีราคา)
 *   - บรรทัดไหนจับคู่แบบไม่แน่ใจ หรือมีหลายรหัสที่ราคาต่างกันมาก
 *   - บรรทัดไหนใช้ราคาที่เก่ากว่าหนึ่งปี
 * ตัวเลขงบที่ดูสะอาดแต่ไม่บอกที่มา อันตรายกว่าตัวเลขที่บอกข้อจำกัดของตัวเอง
 */
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { use } from 'react';
import { api, fileUrl } from '@/lib/api';
import { usePageTitle } from '@/components/RequireAdmin';
import { SkeletonBlock, SkeletonRows, SkeletonStats } from '@/components/Skeleton';
import { money, num, shortDate, sinceLabel } from '@/lib/format';

// ขั้นตอนของแต่ละรายการ — อ่านจากสถานะจริงของใบขอราคา ไม่ใช่ธงที่คนกดเอง
const STAGE = {
  no_match: { label: 'ยังไม่จับคู่', cls: 'stage-none' },
  estimated: { label: 'ตีราคาแล้ว', cls: 'stage-est' },
  rfq_draft: { label: 'ออกใบขอราคาแล้ว', cls: 'stage-rfq' },
  rfq_sent: { label: 'รอผู้ขายเสนอราคา', cls: 'stage-wait' },
  quoted: { label: 'ได้รับราคาแล้ว', cls: 'stage-quoted' },
  awarded: { label: 'อนุมัติราคาแล้ว', cls: 'stage-ok' },
};

const CONFIDENCE = {
  high: { label: 'ตรงมาก', cls: 'conf-high' },
  medium: { label: 'น่าจะใช่', cls: 'conf-medium' },
  low: { label: 'ไม่แน่ใจ', cls: 'conf-low' },
};

export default function BomDetailPage({ params }) {
  const { id } = use(params);
  return <BomDetail id={id} />;
}

function BomDetail({ id }) {
  const router = useRouter();
  const [bom, setBom] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [done, setDone] = useState('');

  usePageTitle(bom?.title || 'ประมาณราคา BOM',
    bom ? `${bom.bom_no} · ${bom.lines.length} รายการ` : '');

  const load = useCallback(async () => {
    try { setBom(await api.getBom(id)); }
    catch (e) { setError(e.message); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  async function run(key, fn) {
    setBusy(key); setError(''); setDone('');
    try { const next = await fn(); if (next) setBom(next); return next; }
    catch (e) { setError(e.message); }
    finally { setBusy(''); }
  }

  if (error && !bom) return <div className="alert alert-error">{error}</div>;
  if (!bom) {
    return (
      <>
        <SkeletonStats count={4} />
        <div className="card" style={{ marginTop: 18 }}>
          <div className="card-head"><SkeletonBlock lines={1} /></div>
          <table><SkeletonRows rows={6} cols={6} /></table>
        </div>
      </>
    );
  }

  const t = bom.totals;
  const needsAttention = t.unpriced_lines + t.ambiguous_lines + t.low_confidence_lines;

  return (
    <>
      {done && <div className="alert alert-ok">{done}</div>}
      {error && <div className="alert alert-error">{error}</div>}

      {/* โครงการที่อยู่ในถังขยะยังเปิดดูได้ แต่ต้องบอกให้ชัดว่ามันถูกลบไปแล้ว
          ไม่งั้นคนจะแก้งานต่อไปเรื่อย ๆ แล้วสงสัยว่าทำไมคนอื่นหาไม่เจอ */}
      {bom.deleted_at && (
        <div className="alert alert-attention">
          <strong>โครงการนี้อยู่ในถังขยะ</strong> — ลบโดย {bom.deleted_by || 'ไม่ทราบ'}{' '}
          เมื่อ {shortDate(bom.deleted_at)} · คนอื่นจะไม่เห็นโครงการนี้แล้ว
          {bom.can_manage && (
            <>
              {' '}
              <button className="btn btn-secondary btn-sm" disabled={busy === 'restore'}
                      onClick={() => run('restore', async () => {
                        const res = await api.restoreBom(id);
                        setDone(res.message || 'กู้โครงการกลับมาแล้ว');
                        return api.getBom(id);
                      })}>
                {busy === 'restore' ? 'กำลังกู้…' : 'กู้คืน'}
              </button>
            </>
          )}
        </div>
      )}

      {/* ส่งเลขที่ที่ลบไปกับ URL ด้วย สองเหตุผล: หน้ารายการจะได้ยืนยันให้เห็นว่าลบอะไรไป
          และ URL ที่ต่างกันทำให้ Next โหลดรายการใหม่จริง ไม่หยิบของเดิมที่แคชไว้มาแสดง
          (ซึ่งจะยังมีโครงการที่เพิ่งลบค้างอยู่ในตาราง) */}
      <ProjectAccess bom={bom} id={id} busy={busy} run={run} setDone={setDone}
                     onDeleted={(res) => router.push(
                       `/boms?deleted=${encodeURIComponent(bom.bom_no)}`
                       + `&rfqs=${res?.rfqs_cancelled || 0}`)} />

      {/* ---------- ความครอบคลุมมาก่อนตัวเลขงบ ---------- */}
      <div className="stat-row">
        <StatCard label="รายการทั้งหมด" value={num(t.line_count)} sub={`${bom.bom_no}`} />
        <StatCard label="ตีราคาได้" value={`${num(t.priced_lines)}/${num(t.line_count)}`}
                  sub={`คิดเป็น ${t.coverage_percent}% ของรายการ`}
                  tone={t.unpriced_lines ? 'warn' : 'ok'} />
        <StatCard label="ต้องดูเพิ่ม" value={num(needsAttention)}
                  sub="ยังไม่มีราคา / ไม่แน่ใจ / มีหลายรหัส"
                  tone={needsAttention ? 'warn' : 'ok'} />
        <StatCard label={`งบประมาณรวม (${bom.currency})`} value={money(t.total)}
                  sub={`รวมเผื่อสำรอง ${t.contingency_percent}% และ VAT ${t.vat_percent}%`} />
      </div>

      {/* เดินไปถึงไหนแล้ว — ตัวเลขทุกช่องมาจากสถานะจริงของใบขอราคา */}
      {bom.progress && (
        <div className="card" style={{ marginBottom: 18 }}>
          <div className="card-head">
            <div>
              <h2>ความคืบหน้าของโครงการ</h2>
              <div className="cell-sub">
                ออกใบขอราคาแล้ว {num(bom.progress.asked_lines)}/{num(t.line_count)} รายการ ·
                อนุมัติราคาแล้ว {num(bom.progress.awarded_lines)} รายการ
                {bom.progress.waiting_lines > 0 &&
                  ` · รอผู้ขายตอบ ${num(bom.progress.waiting_lines)} รายการ`}
              </div>
            </div>
            {bom.progress.awarded_lines > 0 && (
              <div className="approved-box">
                <div className="cell-sub">ราคาที่อนุมัติแล้วรวม</div>
                <div className="cell-title">{money(bom.progress.approved_amount)} {bom.currency}</div>
                {bom.progress.approved_vs_estimate_pct != null && (
                  <div className={`cell-sub ${bom.progress.approved_vs_estimate_pct > 0 ? 'tone-warn' : 'tone-ok'}`}>
                    {bom.progress.approved_vs_estimate_pct > 0 ? 'แพงกว่า' : 'ถูกกว่า'}งบที่ตั้งไว้{' '}
                    {Math.abs(bom.progress.approved_vs_estimate_pct)}%
                  </div>
                )}
              </div>
            )}
          </div>
          <div className="card-body">
            <ol className="stage-flow">
              {bom.progress.stages.map((st) => (
                <li key={st.key} className={`${st.count ? 'on' : ''} ${STAGE[st.key]?.cls || ''}`}>
                  <span className="stage-count">{num(st.count)}</span>
                  <span className="stage-name">{STAGE[st.key]?.label || st.label}</span>
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}

      {t.unpriced_lines > 0 && (
        <div className="alert alert-attention">
          ยอดรวมนี้คิดจาก <strong>{num(t.priced_lines)} รายการที่มีราคา</strong> เท่านั้น ·
          อีก {num(t.unpriced_lines)} รายการยังไม่มีราคา งบจริงจะสูงกว่านี้
        </div>
      )}
      {t.ambiguous_lines > 0 && (
        <div className="alert alert-attention">
          มี {num(t.ambiguous_lines)} รายการที่เจอหลายรหัสตรงพอ ๆ กันแต่ราคาต่างกันมาก —
          กดที่แถวนั้นเพื่อเลือกรหัสที่ใช่ ก่อนเอาตัวเลขไปใช้จริง
        </div>
      )}

      {/* ---------- แถบเครื่องมือ ---------- */}
      <div className="card" style={{ marginBottom: 18 }}>
        <div className="card-head">
          <div>
            <h2>รายการใน BOM</h2>
            <div className="cell-sub">
              กดที่แถวเพื่อเปิดหน้าวัสดุ — ค้นหาสินค้าใกล้เคียง และเทียบราคาจากผู้ขายแต่ละเจ้า
            </div>
          </div>
          <div className="toolbar">
            <button className="btn btn-secondary" disabled={busy === 'rematch'}
                    onClick={() => run('rematch', async () => {
                      const next = await api.rematchBom(id);
                      setDone('จับคู่ใหม่แล้ว (ข้ามบรรทัดที่เลือกเอง)');
                      return next;
                    })}>
              {busy === 'rematch' ? 'กำลังจับคู่…' : 'ให้ระบบจับคู่ใหม่'}
            </button>
            <a className="btn btn-secondary" href={fileUrl.bomExport(id)}>โหลด Excel</a>
            {/* เทียบราคาต้องดูเป็นรายสินค้า ไม่ใช่รายใบ — ใบหนึ่งมีผู้ขายเจ้าเดียว
                เปิดทีละใบจึงเทียบอะไรไม่ได้ */}
            {bom.progress?.asked_lines > 0 && (
              <Link className="btn btn-secondary" href={`/boms/${id}/compare`}>
                เทียบราคารายสินค้า
              </Link>
            )}
            {/* แยกใบเป็นค่าตั้งต้น — ผู้ขายแต่ละเจ้าขายคนละอย่าง
                รวมทุกอย่างไว้ใบเดียวจะได้ราคากลับมาไม่ครบ */}
            <button className="btn btn-secondary" disabled={busy === 'rfq' || !t.priced_lines}
                    title="รวมทุกรายการไว้ในใบเดียว ส่งให้ผู้ขายชุดเดียวกันทั้งใบ"
                    onClick={() => run('rfq', async () => {
                      const res = await api.bomToRfq(id, {});
                      router.push(`/rfqs/${res.rfq.id}`);
                    })}>
              {busy === 'rfq' ? 'กำลังออกใบ…' : 'ออกใบรวมทั้งใบ'}
            </button>
            {/* เป็นหน้าเต็ม ไม่ใช่กล่องซ้อน — งานเลือกผู้ขายต้องใช้พื้นที่และเวลา
                กดพลาดนอกกล่องทีเดียวงานที่เลือกไว้หายหมด */}
            <Link className={`btn btn-primary${t.priced_lines ? '' : ' disabled'}`}
                  href={t.priced_lines ? `/boms/${id}/rfq` : '#'}
                  aria-disabled={!t.priced_lines}>
              ออกใบขอราคาแยกรายตัว
            </Link>
          </div>
        </div>

        <div className="table-wrap">
          <table className="quote-table bom-table">
            <colgroup>
              <col style={{ width: 44 }} /><col /><col style={{ width: 96 }} />
              <col style={{ width: 250 }} /><col style={{ width: 132 }} />
              <col style={{ width: 168 }} /><col style={{ width: 190 }} />
            </colgroup>
            <thead>
              <tr>
                <th>#</th>
                <th>รายการตาม BOM</th>
                <th className="num-head">จำนวน</th>
                <th>สินค้าที่จับคู่</th>
                <th className="num-head">ราคา/หน่วย</th>
                <th className="num-head">จำนวนเงิน</th>
                <th>สถานะ</th>
              </tr>
            </thead>
            <tbody>
              {bom.lines.map((l) => (
                <tr key={l.line_no} className="row-link"
                    onClick={() => router.push(`/boms/${id}/lines/${l.line_no}`)}
                    title="กดเพื่อเปิดหน้าวัสดุรายการนี้">
                  <td className="cell-sub">{l.line_no}</td>
                  <td>
                    <div className="cell-title">{l.name}</div>
                    {l.remark && <div className="cell-sub">{l.remark}</div>}
                  </td>
                  <td className="num-cell qty-cell">
                    {num(l.qty, 2)} <span className="uom">{l.uom}</span>
                  </td>
                  <td>
                    {l.matched ? (
                      <>
                        <div className="cell-title">{l.item_description || l.part_num}</div>
                        <div className="cell-sub">
                          <code>{l.part_num}</code>
                          {l.match_source === 'manual' ? (
                            <span className="conf conf-manual">เลือกเอง</span>
                          ) : (
                            <span className={`conf ${CONFIDENCE[l.confidence]?.cls}`}>
                              {CONFIDENCE[l.confidence]?.label}
                            </span>
                          )}
                          {l.ambiguous && (
                            <span className="conf conf-warn"
                                  title={`ราคาในกลุ่มที่ตรงพอกันต่างกัน ${l.alt_price_ratio} เท่า`}>
                              มีอีก {num(l.alt_count)} รหัสที่ตรงพอกัน
                            </span>
                          )}
                        </div>
                      </>
                    ) : l.manual_price != null ? (
                      <span className="cell-sub">ไม่มีในระบบ — ใช้ราคาที่กรอกเอง</span>
                    ) : (
                      <span className="tag tag-warn">ยังไม่จับคู่ — กดเพื่อเลือก</span>
                    )}
                  </td>
                  <td className="num-cell">
                    {l.unit_price == null
                      ? <span className="muted">—</span>
                      : (
                        <>
                          {money(l.unit_price)}
                          <div className="cell-sub">
                            {l.price_source === 'manual'
                              ? 'กรอกเอง'
                              : <span className={l.price_stale ? 'tone-warn' : ''}>
                                  {l.price_date ? sinceLabel(l.price_date) : 'ราคาล่าสุด'}
                                </span>}
                          </div>
                        </>
                      )}
                  </td>
                  <td className="num-cell">
                    {l.amount == null
                      ? <span className="muted">—</span>
                      : <strong>{money(l.amount)}</strong>}
                  </td>
                  {/* ออกใบไปแล้วต้องเห็น ไม่งั้นกดออกซ้ำแล้วได้ใบซ้ำโดยไม่รู้ตัว */}
                  <td onClick={(e) => e.stopPropagation()}>
                    <span className={`stage ${STAGE[l.stage]?.cls || 'stage-none'}`}>
                      {STAGE[l.stage]?.label || l.stage_label}
                    </span>
                    {l.rfqs?.length > 0 && (
                      <div className="cell-sub">
                        {l.rfqs.map((r, i) => (
                          <span key={r.rfq_id}>
                            {i > 0 && ' · '}
                            <Link href={`/rfqs/${r.rfq_id}`}>{r.rfq_no}</Link>
                          </span>
                        ))}
                        {l.quote_count > 0 && <> · ได้ราคา {num(l.quote_count)} ราย</>}
                      </div>
                    )}
                    {l.award && (
                      <div className="cell-sub">
                        ผู้ชนะ {l.award.vendor_name} · {money(l.award.unit_price)}
                        {l.award.vs_estimate_pct != null && (
                          <span className={l.award.vs_estimate_pct > 0 ? ' tone-warn' : ' tone-ok'}>
                            {' '}({l.award.vs_estimate_pct > 0 ? '+' : ''}{l.award.vs_estimate_pct}% เทียบงบ)
                          </span>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={5} className="cell-sub">
                  รวมค่าของ ({num(t.priced_lines)} รายการที่มีราคา)
                </td>
                <td className="num-cell">{money(t.subtotal)}</td>
                <td />
              </tr>
              <tr>
                <td colSpan={5} className="cell-sub">เผื่อสำรอง {t.contingency_percent}%</td>
                <td className="num-cell">{money(t.contingency_amount)}</td>
                <td />
              </tr>
              <tr>
                <td colSpan={5} className="cell-sub">ภาษีมูลค่าเพิ่ม {t.vat_percent}%</td>
                <td className="num-cell">{money(t.vat_amount)}</td>
                <td />
              </tr>
              <tr>
                <td colSpan={5} className="cell-title">งบประมาณรวมทั้งสิ้น</td>
                <td className="num-cell">
                  <strong>{money(t.total)} {bom.currency}</strong>
                </td>
                <td />
              </tr>
            </tfoot>
          </table>
        </div>

        <div className="card-body" style={{ borderTop: '1px solid var(--border)' }}>
          <div className="portal-grid">
            <div className="field" style={{ marginBottom: 0 }}>
              <label htmlFor="cont">เผื่อสำรอง (%)</label>
              <input id="cont" type="number" min="0" max="100" step="1"
                     defaultValue={t.contingency_percent}
                     onBlur={(e) => {
                       const v = Number(e.target.value);
                       if (v !== t.contingency_percent) {
                         run('meta', () => api.updateBom(id, { contingency_percent: v }));
                       }
                     }} />
            </div>
            <div className="field" style={{ marginBottom: 0 }}>
              <label htmlFor="vat">ภาษีมูลค่าเพิ่ม (%)</label>
              <input id="vat" type="number" min="0" max="100" step="1"
                     defaultValue={t.vat_percent}
                     onBlur={(e) => {
                       const v = Number(e.target.value);
                       if (v !== t.vat_percent) {
                         run('meta', () => api.updateBom(id, { vat_percent: v }));
                       }
                     }} />
            </div>
          </div>
          <div className="hint">
            ตัวเลขนี้ประมาณจากราคาที่บริษัทเคยซื้อจริง ไม่ใช่ราคาเสนอจากผู้ขาย —
            ใช้ตั้งงบเบื้องต้น ราคาจริงต้องขอใบเสนอราคาอีกครั้ง
          </div>
        </div>
      </div>

    </>
  );
}

function StatCard({ label, value, sub, tone }) {
  const cls = tone === 'warn' ? ' stat-warn' : tone === 'ok' ? ' stat-good' : '';
  return (
    <div className={`stat-card${cls}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-note">{sub}</div>}
    </div>
  );
}


/* ------------------------------------------------- ใครเห็น/ใครดูแลโครงการนี้

   วางไว้บนสุดของหน้า เพราะเป็นคำถามที่ต้องรู้ก่อนจะเริ่มแก้งาน:
   "โครงการนี้ของหน่วยงานไหน ใครดูแล และเราแก้ได้ไหม"
   ถ้าซ่อนไว้ใต้สุด คนจะแก้ไปแล้วค่อยรู้ว่าไม่ใช่งานของตัวเอง
*/
function ProjectAccess({ bom, id, busy, run, setDone, onDeleted }) {
  const [open, setOpen] = useState(false);
  const [depts, setDepts] = useState([]);
  const [dept, setDept] = useState(bom.department || '');
  const [email, setEmail] = useState('');
  const [warn, setWarn] = useState('');

  useEffect(() => { setDept(bom.department || ''); }, [bom.department]);
  useEffect(() => {
    if (!open) return;
    api.listDepartments().then((r) => setDepts(r.items || [])).catch(() => setDepts([]));
  }, [open]);

  const assignees = bom.assignees || [];

  return (
    <div className="card access-card">
      <div className="card-head">
        <div>
          <h2>
            {bom.department || <span className="muted">ยังไม่ระบุหน่วยงาน</span>}
            <span className="cell-sub"> · เจ้าของ {bom.owner}</span>
          </h2>
          <div className="cell-sub">
            {assignees.length
              ? `เพิ่มคนเข้าโครงการไว้ ${num(assignees.length)} คน: ${assignees.join(', ')}`
              : 'คนในหน่วยงานเดียวกันเห็นโครงการนี้ได้ · คนนอกหน่วยงานต้องถูกเพิ่มเข้ามาก่อน'}
          </div>
        </div>
        {bom.can_manage && (
          <div className="toolbar">
            <button className="btn btn-secondary btn-sm" onClick={() => setOpen((v) => !v)}>
              {open ? 'ปิด' : 'จัดการสิทธิ์'}
            </button>
            {!bom.deleted_at && (
              <button className="btn btn-danger btn-sm" disabled={busy === 'delete'}
                      onClick={async () => {
                        // บอกผลข้างเคียงให้ครบก่อนกด — ใบขอราคาที่ผู้ขายถืออยู่จะถูกยกเลิกด้วย
                        // ถ้าไม่บอก คนกดจะรู้ตอนผู้ขายโทรมาถามว่าทำไมลิงก์ใช้ไม่ได้
                        if (!window.confirm(
                          `ย้าย ${bom.bom_no} เข้าถังขยะ?\n\n` +
                          'คนอื่นจะไม่เห็นโครงการนี้ และใบขอราคาที่ออกจากโครงการนี้จะถูกยกเลิก ' +
                          '(ผู้ขายที่เปิดลิงก์จะเห็นว่า "ยกเลิกแล้ว" และเสนอราคาไม่ได้)\n\n' +
                          'กู้กลับมาได้จากแท็บถังขยะ — ใบขอราคาจะกลับมาด้วย')) return;
                        await run('delete', async () => {
                          const res = await api.deleteBom(id);
                          onDeleted(res);
                        });
                      }}>
                {busy === 'delete' ? 'กำลังลบ…' : 'ลบโครงการ'}
              </button>
            )}
          </div>
        )}
      </div>

      {open && bom.can_manage && (
        <div className="card-body">
          {warn && <div className="alert alert-attention">{warn}</div>}
          <div className="portal-grid">
            <div className="field">
              <label htmlFor="acc-dept">หน่วยงานเจ้าของโครงการ</label>
              <input id="acc-dept" list="dept-options" value={dept}
                     placeholder="เช่น ฝ่ายจัดซื้อ"
                     onChange={(e) => setDept(e.target.value)} />
              <datalist id="dept-options">
                {depts.map((d) => <option key={d} value={d} />)}
              </datalist>
              <div className="hint">
                เปลี่ยนหน่วยงาน = เปลี่ยนว่าใครเห็นโครงการนี้ · เลือกจากรายการที่มีอยู่จะดีกว่า
                พิมพ์เองใหม่ เพราะ &quot;จัดซื้อ&quot; กับ &quot;ฝ่ายจัดซื้อ&quot; จะกลายเป็นคนละหน่วยงาน
              </div>
            </div>
            <div className="field">
              <label htmlFor="acc-email">เพิ่มคนเข้าโครงการ (อีเมล)</label>
              <input id="acc-email" type="email" value={email} placeholder="name@precise.co.th"
                     onChange={(e) => setEmail(e.target.value)} />
              <div className="hint">ใช้กับคนนอกหน่วยงาน — คนในหน่วยงานเดียวกันเห็นอยู่แล้ว</div>
            </div>
          </div>

          <div className="toolbar">
            <button className="btn btn-secondary btn-sm"
                    disabled={busy === 'dept' || dept === (bom.department || '')}
                    onClick={() => run('dept', async () => {
                      const next = await api.updateBom(id, { department: dept.trim() });
                      setDone('ย้ายโครงการไปหน่วยงาน ' + (dept.trim() || '(ไม่ระบุ)') + ' แล้ว');
                      return next;
                    })}>
              บันทึกหน่วยงาน
            </button>
            {/* run() เอาค่าที่คืนไปตั้งเป็นข้อมูลโครงการ จึงต้องคืน "โครงการที่โหลดใหม่"
                ไม่ใช่ผลลัพธ์ของการ assign — ส่วนรายชื่อที่ไม่พบส่งออกทาง state แทน */}
            <button className="btn btn-secondary btn-sm" disabled={busy === 'assign' || !email.trim()}
                    onClick={() => {
                      setWarn('');
                      return run('assign', async () => {
                        const res = await api.setBomAssignees(id, { add: [email.trim()] });
                        if (res.unknown?.length) {
                          setWarn('ไม่พบผู้ใช้ ' + res.unknown.join(', ') +
                                  ' — ต้องมีบัญชีในระบบก่อนจึงเพิ่มเข้าโครงการได้');
                        } else {
                          setEmail('');
                          setDone('เพิ่ม ' + email.trim() + ' เข้าโครงการแล้ว');
                        }
                        return api.getBom(id);
                      });
                    }}>
              เพิ่มเข้าโครงการ
            </button>
          </div>

          {assignees.length > 0 && (
            <ul className="assignee-list">
              {assignees.map((a) => (
                <li key={a}>
                  <span>{a}</span>
                  <button className="btn btn-danger btn-sm" disabled={busy === 'unassign'}
                          onClick={() => run('unassign', async () => {
                            await api.setBomAssignees(id, { remove: [a] });
                            setDone('ถอด ' + a + ' ออกจากโครงการแล้ว');
                            return api.getBom(id);
                          })}>
                    ถอดออก
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
