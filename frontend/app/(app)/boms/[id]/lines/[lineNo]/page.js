'use client';

/**
 * หน้าวัสดุหนึ่งรายการของโครงการ — เปิดจากแถวในหน้า BOM
 *
 * เป็นหน้าเต็ม ไม่ใช่กล่องซ้อน เพราะงานตรงนี้มีสองเรื่องที่ต้องสลับไปมา:
 *   แท็บ "จับคู่วัสดุ"  — ของชิ้นนี้คือรหัสไหนกันแน่ (ค้นหาสินค้าใกล้เคียง แล้วเลือก)
 *   แท็บ "เทียบราคา"   — ผู้ขายแต่ละเจ้าเสนอมาเท่าไร เทียบกับราคาที่เคยซื้อจริง
 *
 * แท็บผูกกับ URL (?tab=compare) จึงเปิดแยกแท็บของเบราว์เซอร์ได้ และแชร์ลิงก์ได้
 */
import { use, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { usePageTitle } from '@/components/RequireAdmin';
import OtdBadge from '@/components/OtdBadge';
import VendorSearch from '@/components/VendorSearch';
import { SkeletonBlock, SkeletonRows } from '@/components/Skeleton';
import { money, num, pctLabel, shortDate, sinceLabel } from '@/lib/format';

const CONFIDENCE = {
  high: { label: 'ตรงมาก', cls: 'conf-high' },
  medium: { label: 'น่าจะใช่', cls: 'conf-medium' },
  low: { label: 'ไม่แน่ใจ', cls: 'conf-low' },
};

const STAGE = {
  no_match: 'stage-none', estimated: 'stage-est', rfq_draft: 'stage-rfq',
  rfq_sent: 'stage-wait', quoted: 'stage-quoted', awarded: 'stage-ok',
};

export default function BomLinePage({ params }) {
  const { id, lineNo } = use(params);
  return <LinePage bomId={id} lineNo={Number(lineNo)} />;
}

function LinePage({ bomId, lineNo }) {
  const router = useRouter();
  const search = useSearchParams();
  const tab = search.get('tab') === 'compare' ? 'compare' : 'match';

  const [bom, setBom] = useState(null);
  const [error, setError] = useState('');
  const [done, setDone] = useState('');

  const line = bom?.lines?.find((l) => l.line_no === lineNo) || null;
  usePageTitle(line ? line.name : 'วัสดุในโครงการ',
    bom ? `${bom.bom_no} · รายการที่ ${lineNo}` : '');

  const load = useCallback(async () => {
    try { setBom(await api.getBom(bomId)); }
    catch (e) { setError(e.message); }
  }, [bomId]);

  useEffect(() => { load(); }, [load]);

  if (error && !bom) return <div className="alert alert-error">{error}</div>;
  if (!bom) return <div className="card"><SkeletonBlock lines={6} /></div>;
  if (!line) {
    return (
      <div className="card"><div className="empty">
        <strong>ไม่พบรายการที่ {lineNo}</strong>
        อาจถูกลบไปแล้ว — กลับไปดูที่หน้าโครงการ
      </div></div>
    );
  }

  const go = (next) =>
    router.replace(`/boms/${bomId}/lines/${lineNo}${next === 'compare' ? '?tab=compare' : ''}`,
      { scroll: false });

  return (
    <>
      <div className="page-back">
        <Link href={`/boms/${bomId}`}>← กลับไปโครงการ {bom.title}</Link>
      </div>

      {done && <div className="alert alert-ok">{done}</div>}
      {error && <div className="alert alert-error">{error}</div>}

      {/* ---------- หัวรายการ ---------- */}
      <div className="card" style={{ marginBottom: 18 }}>
        <div className="card-head">
          <div>
            <h2>รายการที่ {line.line_no} · {line.name}</h2>
            <div className="cell-sub">
              จำนวน {num(line.qty, 2)} {line.uom}
              {line.matched && <> · จับคู่กับ <code>{line.part_num}</code> {line.item_description}</>}
              {line.remark && <> · {line.remark}</>}
            </div>
          </div>
          <div className="toolbar">
            <span className={`stage ${STAGE[line.stage] || 'stage-none'}`}>{line.stage_label}</span>
            {line.matched && (
              <Link className="btn btn-secondary btn-sm"
                    href={`/products/${encodeURIComponent(line.part_num)}`}>
                ดูประวัติสินค้านี้
              </Link>
            )}
          </div>
        </div>
        <div className="card-body kv-grid">
          <KV label="ราคาที่ใช้ตีงบ"
              value={line.unit_price == null ? '—' : `${money(line.unit_price)} / ${line.uom || 'หน่วย'}`}
              sub={line.price_source === 'manual' ? 'กรอกเอง'
                   : line.price_date ? `ราคาซื้อล่าสุด ${sinceLabel(line.price_date)}` : ''} />
          <KV label="เป็นเงิน" value={line.amount == null ? '—' : money(line.amount)} />
          <KV label="ใบขอราคา"
              value={line.rfqs?.length
                ? line.rfqs.map((r) => r.rfq_no).join(' · ')
                : 'ยังไม่ได้ออก'}
              sub={line.quote_count ? `ได้ราคากลับมา ${num(line.quote_count)} ราย` : ''} />
          <KV label="ผลอนุมัติ"
              value={line.award ? `${line.award.vendor_name} · ${money(line.award.unit_price)}` : '—'}
              sub={line.award?.vs_estimate_pct != null
                ? `${pctLabel(line.award.vs_estimate_pct)} เทียบงบที่ตั้งไว้` : ''} />
        </div>
      </div>

      {/* ---------- แท็บ ---------- */}
      <div className="card">
        <div className="tabs">
          <button className={`tab${tab === 'match' ? ' active' : ''}`} onClick={() => go('match')}>
            จับคู่วัสดุ
          </button>
          <button className={`tab${tab === 'compare' ? ' active' : ''}`}
                  onClick={() => go('compare')}>
            เทียบราคาจากผู้ขาย
            {line.quote_count > 0 && <span className="tab-count">{num(line.quote_count)}</span>}
          </button>
        </div>

        {tab === 'match'
          ? <MatchTab bomId={bomId} line={line}
                      onSaved={(next) => { setBom(next); setDone('บันทึกแล้ว'); }}
                      onError={setError} />
          : <CompareTab bomId={bomId} line={line}
                        onIssued={(msg) => { setDone(msg); load(); }} />}
      </div>
    </>
  );
}

function KV({ label, value, sub }) {
  return (
    <div className="kv">
      <span className="kv-label">{label}</span>
      <span className="kv-value">
        {value}
        {sub && <div className="cell-sub">{sub}</div>}
      </span>
    </div>
  );
}

/* ------------------------------------------------- แท็บจับคู่วัสดุ */
function MatchTab({ bomId, line, onSaved, onError }) {
  const [term, setTerm] = useState('');
  const [cands, setCands] = useState(null);
  const [qty, setQty] = useState(line.qty);
  const [manual, setManual] = useState(line.manual_price ?? '');
  const [busy, setBusy] = useState('');
  const [picked, setPicked] = useState(null);

  useEffect(() => { setPicked(null); }, [line.part_num]);
  const chosenPart = picked ?? line.part_num;

  const search = useCallback(async (q) => {
    setCands(null);
    try { setCands((await api.bomCandidates(bomId, line.line_no, { q, limit: 15 })).items); }
    catch (e) { onError(e.message); setCands([]); }
  }, [bomId, line.line_no, onError]);

  useEffect(() => { search(''); }, [search]);

  async function apply(patch, key) {
    setBusy(key);
    try { onSaved(await api.patchBomLine(bomId, line.line_no, patch)); }
    catch (e) { onError(e.message); setPicked(null); }
    finally { setBusy(''); }
  }

  return (
    <>
      <div className="card-body" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="portal-grid">
          <div className="field">
            <label htmlFor="l-qty">จำนวนที่ต้องใช้</label>
            <input id="l-qty" type="number" min="0" step="any" value={qty}
                   onChange={(e) => setQty(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="l-manual">ราคา/หน่วย ที่กรอกเอง</label>
            <input id="l-manual" type="number" min="0" step="0.01" value={manual}
                   placeholder="ใช้เมื่อไม่มีสินค้านี้ในระบบ"
                   onChange={(e) => setManual(e.target.value)} />
          </div>
        </div>
        <div className="toolbar">
          <button className="btn btn-secondary btn-sm" disabled={busy === 'qty'}
                  onClick={() => apply({ qty: Number(qty) }, 'qty')}>บันทึกจำนวน</button>
          <button className="btn btn-secondary btn-sm" disabled={busy === 'price'}
                  onClick={() => apply(
                    manual === '' ? { clear_manual_price: true } : { manual_price: Number(manual) },
                    'price')}>
            {manual === '' ? 'ล้างราคาที่กรอกเอง' : 'ใช้ราคานี้'}
          </button>
          {line.matched && (
            <button className="btn btn-danger btn-sm" disabled={busy === 'unlink'}
                    onClick={() => apply({ part_num: '' }, 'unlink')}>ยกเลิกการจับคู่</button>
          )}
        </div>
      </div>

      <div className="card-body" style={{ paddingBottom: 0 }}>
        <div className="field" style={{ marginBottom: 8 }}>
          <label htmlFor="l-search">ค้นหาสินค้าใกล้เคียง</label>
          <input id="l-search" type="search" value={term}
                 placeholder={`เว้นว่าง = ใช้ "${line.name}" ค้นให้ · หรือพิมพ์สเปกอื่น แล้วกด Enter`}
                 onChange={(e) => setTerm(e.target.value)}
                 onKeyDown={(e) => { if (e.key === 'Enter') search(term); }} />
          <div className="hint" style={{ marginTop: 6 }}>
            <strong>ติ๊กได้ทีละ 1 รายการเท่านั้น</strong> — หนึ่งบรรทัดใน BOM ผูกกับสินค้าได้รหัสเดียว
          </div>
        </div>
      </div>

      <div className="table-wrap">
        <table className="quote-table pick-table">
          <colgroup><col style={{ width: 46 }} /><col /><col style={{ width: 104 }} />
            <col style={{ width: 130 }} /><col style={{ width: 120 }} /></colgroup>
          <thead>
            <tr>
              <th><span className="sr-only">เลือก</span></th>
              <th>สินค้า</th><th>ความตรง</th>
              <th className="num-head">ราคาล่าสุด</th><th className="num-head">ซื้อล่าสุด</th>
            </tr>
          </thead>
          {cands === null && <SkeletonRows rows={5} cols={5}
                                           widths={['40%', '74%', '40%', '52%', '48%']} />}
          <tbody>
            {cands?.map((c) => {
              const on = c.part_num === chosenPart;
              const choose = () => {
                if (on) return;
                setPicked(c.part_num);
                apply({ part_num: c.part_num }, 'pick');
              };
              return (
                <tr key={c.part_num} className={`row-link${on ? ' picked' : ''}`} onClick={choose}>
                  <td className="pick-cell" onClick={(e) => e.stopPropagation()}>
                    <input type="radio" name="pick-part" checked={on}
                           aria-label={`ใช้ ${c.description || c.part_num}`} onChange={choose} />
                  </td>
                  <td>
                    <div className="cell-title">{c.description || c.part_num}</div>
                    <div className="cell-sub">
                      <code>{c.part_num}</code> · ผู้ขาย {num(c.vendor_count)} ราย
                      {on && (
                        <span className="conf conf-manual">
                          {busy === 'pick' && picked === c.part_num ? 'กำลังบันทึก…' : 'ใช้อยู่'}
                        </span>
                      )}
                    </div>
                  </td>
                  <td>
                    <span className={`conf ${CONFIDENCE[c.confidence]?.cls}`}>
                      {CONFIDENCE[c.confidence]?.label}
                    </span>
                  </td>
                  <td className="num-cell">
                    {c.last_price == null ? <span className="muted">ไม่มีราคา</span> : money(c.last_price)}
                  </td>
                  <td className="num-cell cell-sub">{shortDate(c.last_price_date)}</td>
                </tr>
              );
            })}
            {cands?.length === 0 && (
              <tr><td colSpan={5}>
                <div className="empty">
                  <strong>ไม่เจอสินค้าที่ใกล้เคียง</strong>
                  ลองพิมพ์คำอื่น หรือกรอกราคาเองด้านบน
                </div>
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

/* ------------------------------------------------- แท็บเทียบราคา */
function CompareTab({ bomId, line, onIssued }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  const [round, setRound] = useState(0);      // ออกใบเพิ่มแล้วให้โหลดตารางใหม่

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [cmp, hist] = await Promise.all([
          api.bomComparison(bomId),
          line.part_num ? api.itemVendors(line.part_num) : Promise.resolve({ vendors: [] }),
        ]);
        if (!alive) return;
        const row = cmp.rows.find((r) => r.line_no === line.line_no);
        const past = Object.fromEntries((hist.vendors || []).map((v) => [v.vendor_key, v]));
        const byKey = Object.fromEntries(cmp.vendors.map((v) => [v.vendor_key, v]));
        // เอาเฉพาะเจ้าที่ถูกเชิญให้เสนอราคาของชิ้นนี้ — เจ้าอื่นในโครงการไม่เกี่ยว
        const cells = (row?.cells || []).filter((c) => c.invited);
        setRows({
          row,
          currency: cmp.currency,
          vendors: cells.map((c) => ({
            ...c,
            vendor: byKey[c.vendor_key] || {},
            history: past[c.vendor_key] || null,
          })),
        });
      } catch (e) { if (alive) setError(e.message); }
    })();
    return () => { alive = false; };
  }, [bomId, line.line_no, line.part_num, round]);

  const askMore = (
    <AskMore bomId={bomId} line={line}
             onIssued={(msg) => { setRound((r) => r + 1); onIssued?.(msg); }} />
  );

  if (error) return <div className="alert alert-error" style={{ margin: 16 }}>{error}</div>;
  if (!rows) return <SkeletonBlock lines={5} />;
  if (!rows.row || !rows.vendors.length) {
    return (
      <>
        <div className="empty">
          <strong>ยังไม่มีราคาให้เทียบ</strong>
          {line.matched
            ? 'ยังไม่ได้เชิญใครเสนอราคาของชิ้นนี้ — เลือกผู้ขายด้านล่างแล้วออกใบขอราคาได้เลย'
            : 'ต้องจับคู่รายการนี้กับสินค้าในระบบก่อน จึงจะออกใบขอราคาได้'}
        </div>
        {line.matched && askMore}
      </>
    );
  }

  const { row, vendors, currency } = rows;
  return (
    <>
      <div className="card-body" style={{ paddingBottom: 6 }}>
        <div className="cell-sub">
          เทียบเฉพาะของชิ้นนี้ · จำนวน {num(row.qty, 2)} {row.uom} ·
          งบที่ตั้งไว้ {money(row.estimate_unit_price)}/หน่วย
          {row.best_vs_estimate_pct != null && (
            <> · ราคาดีที่สุดที่ได้มา{' '}
              <span className={row.best_vs_estimate_pct > 0 ? 'tone-warn' : 'tone-ok'}>
                {pctLabel(row.best_vs_estimate_pct)} เทียบงบ
              </span>
            </>
          )}
        </div>
      </div>

      <div className="table-wrap">
        <table className="quote-table">
          <colgroup><col /><col style={{ width: 150 }} /><col style={{ width: 150 }} />
            <col style={{ width: 120 }} /><col style={{ width: 230 }} /></colgroup>
          <thead>
            <tr>
              <th>ผู้ขาย</th>
              <th className="num-head">ราคาที่เสนอมา</th>
              <th className="num-head">เคยซื้อจากเจ้านี้</th>
              <th className="num-head">ส่งของภายใน</th>
              <th>ส่งตรงเวลา</th>
            </tr>
          </thead>
          <tbody>
            {vendors.map((v) => {
              const past = v.history?.last_unit_cost;
              const diff = (v.unit_price != null && past)
                ? round1((v.unit_price - past) / past * 100) : null;
              return (
                <tr key={v.vendor_key} className={v.is_lowest ? 'picked' : ''}>
                  <td>
                    <div className="cell-title">
                      {v.vendor.vendor_name || v.vendor_key}
                      {v.is_lowest && <span className="conf conf-high">ถูกที่สุด</span>}
                      {row.award?.vendor_key === v.vendor_key && (
                        <span className="stage stage-ok">อนุมัติแล้ว</span>
                      )}
                    </div>
                    <div className="cell-sub"><code>{v.vendor.vendor_id}</code></div>
                  </td>
                  <td className="num-cell">
                    {v.unit_price == null ? (
                      <span className="muted">{v.no_quote ? 'ไม่เสนอรายการนี้' : 'รอตอบ'}</span>
                    ) : (
                      <>
                        <strong>{money(v.unit_price)}</strong>
                        <div className="cell-sub">รวม {money(v.amount)} {currency}</div>
                      </>
                    )}
                  </td>
                  <td className="num-cell">
                    {past == null ? <span className="muted">ไม่เคยซื้อ</span> : (
                      <>
                        {money(past)}
                        {diff != null && (
                          <div className={`cell-sub ${diff > 0 ? 'tone-warn' : 'tone-ok'}`}>
                            {pctLabel(diff)} จากที่เคยซื้อ
                          </div>
                        )}
                      </>
                    )}
                  </td>
                  <td className="num-cell">
                    {v.lead_time_days == null
                      ? <span className="muted">—</span>
                      : `${num(v.lead_time_days)} วัน`}
                  </td>
                  <td><OtdBadge delivery={v.vendor.delivery} compact /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="card-body">
        <div className="hint" style={{ marginTop: 0 }}>
          คอลัมน์ "เคยซื้อจากเจ้านี้" คือราคาที่บริษัทเคยจ่ายให้เจ้านั้นจริงสำหรับรหัสนี้ —
          ใช้ดูว่าที่เสนอมารอบนี้ <strong>ถูกลงหรือแพงขึ้นจากเดิม</strong> ไม่ใช่แค่เทียบกันเองในรอบนี้ ·
          เลือกผู้ชนะได้ที่{' '}
          <Link href={`/boms/${bomId}/compare`}>หน้าเทียบราคาทั้งโครงการ</Link>
        </div>
      </div>

      {askMore}
    </>
  );
}

/* ------------------------------------------------- ขอราคาเพิ่มสำหรับรายการนี้

   อยู่ท้ายแท็บเทียบราคา เพราะคำถาม "ควรถามใครเพิ่มไหม" เกิดขึ้นตอนดูราคาที่ได้มาแล้ว
   ไม่ใช่ตอนเริ่มโครงการ — ได้มา 2 เจ้าแล้วรู้สึกว่าแพง ก็ควรถามเพิ่มได้จากตรงนั้นเลย
   ไม่ต้องย้อนกลับไปหน้าออกใบของทั้งโครงการ

   ออกเป็นใบละผู้ขาย (group_by=vendor) เหมือนที่อื่นของระบบ ผู้ขายจะได้เห็นเฉพาะของตัวเอง
*/
function AskMore({ bomId, line, onIssued }) {
  const [known, setKnown] = useState(null);    // ผู้ขายที่เคยขายรหัสนี้ + ธงว่าเชิญไปแล้ว
  const [extra, setExtra] = useState([]);      // ที่ค้นเพิ่มเอง
  const [picked, setPicked] = useState(() => new Set());
  const [send, setSend] = useState(true);
  const [message, setMessage] = useState('');
  const [repeat, setRepeat] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const reload = useCallback(async () => {
    setKnown(null);
    try {
      const plan = await api.bomRfqPlan(bomId, { line_no: line.line_no });
      setKnown(plan.items?.[0]?.vendors || []);
    } catch (e) { setError(e.message); setKnown([]); }
  }, [bomId, line.line_no]);

  useEffect(() => { reload(); }, [reload]);
  // เปลี่ยนรหัสที่จับคู่ = รายชื่อผู้ขายชุดเดิมใช้ไม่ได้แล้ว ต้องล้างที่ติ๊กไว้ด้วย
  useEffect(() => { setPicked(new Set()); setExtra([]); }, [line.part_num]);

  const vendors = [...(known || []), ...extra];
  const chosen = [...picked];
  const repeats = vendors.filter((v) => picked.has(v.vendor_key) && v.invited);

  function toggle(key) {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }

  function addFound(v) {
    if (!vendors.some((x) => x.vendor_key === v.vendor_key)) {
      setExtra((prev) => [...prev, { ...v, added: true, times: 0, last_unit_cost: null }]);
    }
    setPicked((prev) => new Set(prev).add(v.vendor_key));
  }

  async function submit() {
    setBusy(true); setError(''); setResult(null);
    try {
      const res = await api.bomRfqsPerItem(bomId, {
        items: [{ line_no: line.line_no, vendor_keys: chosen }],
        group_by: 'vendor',
        allow_repeat: repeat,
        send,
        message,
      });
      setResult(res);
      setPicked(new Set());
      setExtra([]);
      await reload();
      onIssued?.(`ออกใบขอราคาเพิ่มแล้ว ${num(res.created.length)} ใบ`);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  return (
    <div className="card-body ask-more">
      <div className="ask-more-head">
        <h3>ขอราคาเพิ่มสำหรับรายการนี้</h3>
        <div className="cell-sub">
          ออกใบละหนึ่งผู้ขาย · แต่ละใบมีเฉพาะ{' '}
          <code>{line.part_num}</code> {line.item_description || line.name}{' '}
          จำนวน {num(line.qty, 2)} {line.uom}
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {result && (
        <div className="alert alert-ok">
          ออกใบขอราคาแล้ว {num(result.created.length)} ใบ —{' '}
          {result.created.map((c) => (
            <Link key={c.rfq_id} href={`/rfqs/${c.rfq_id}`}>{c.rfq_no}</Link>
          )).reduce((all, el) => (all.length ? [...all, ' · ', el] : [el]), [])}
          {result.repeated?.length > 0 && (
            <div className="cell-sub">
              ข้ามเจ้าที่เชิญไปแล้ว {num(result.repeated.length)} ราย —
              ถ้าตั้งใจขอราคาใหม่จากเจ้าเดิม ให้ติ๊ก "ขอซ้ำจากเจ้าที่เคยเชิญ" แล้วออกอีกครั้ง
            </div>
          )}
        </div>
      )}

      {known === null ? <SkeletonBlock lines={3} /> : (
        <div className="table-wrap">
          <table className="quote-table vendor-pick">
            <colgroup><col style={{ width: 46 }} /><col />
              <col style={{ width: 140 }} /><col style={{ width: 210 }} /></colgroup>
            <thead>
              <tr>
                <th><span className="sr-only">เลือก</span></th>
                <th>ผู้ขาย</th>
                <th className="num-head">ราคาล่าสุดของเจ้านี้</th>
                <th>ส่งตรงเวลา</th>
              </tr>
            </thead>
            <tbody>
              {vendors.map((v) => {
                const on = picked.has(v.vendor_key);
                return (
                  <tr key={v.vendor_key} className={`row-link${on ? ' picked' : ''}`}
                      onClick={() => toggle(v.vendor_key)}>
                    <td className="pick-cell" onClick={(e) => e.stopPropagation()}>
                      <input type="checkbox" checked={on}
                             aria-label={`เชิญ ${v.name}`}
                             onChange={() => toggle(v.vendor_key)} />
                    </td>
                    <td>
                      <div className="cell-title">{v.name}</div>
                      <div className="cell-sub">
                        <code>{v.vendor_id}</code>
                        {v.added
                          ? <span className="conf conf-warn">เพิ่มเอง · ไม่เคยขายรหัสนี้</span>
                          : <> · เคยซื้อ {num(v.times)} ครั้ง
                              {v.last_buy_date && <> · ล่าสุด {shortDate(v.last_buy_date)}</>}</>}
                        {v.invited && (
                          <span className="conf conf-manual">
                            เชิญแล้ว{v.invited_rfqs?.length ? ` · ${v.invited_rfqs.join(' · ')}` : ''}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="num-cell">
                      {v.last_unit_cost == null
                        ? <span className="muted">{v.added ? '—' : 'ไม่มีราคา'}</span>
                        : money(v.last_unit_cost)}
                    </td>
                    <td>
                      <OtdBadge delivery={v.delivery} compact />
                      {v.delivery_this_item && (
                        <div className="cell-sub">
                          เฉพาะรหัสนี้ {num(v.delivery_this_item.otd_pct, 1)}%
                          จาก {num(v.delivery_this_item.releases)} งวด
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
              {vendors.length === 0 && (
                <tr><td colSpan={4}>
                  <div className="empty">
                    <strong>ไม่มีผู้ขายที่เคยขายรหัสนี้ในระบบ</strong>
                    ค้นหาผู้ขายเพิ่มด้านล่างได้
                  </div>
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <VendorSearch bomId={bomId} lineNo={line.line_no} lineName={line.name}
                    already={vendors.map((v) => v.vendor_key)} onAdd={addFound} />

      {/* เตือนเฉพาะตอนที่ติ๊กเจ้าที่เชิญไปแล้วจริง ๆ — ไม่ใช่ขึ้นค้างไว้ตลอดจนคนเลิกอ่าน */}
      {repeats.length > 0 && (
        <label className="checkbox ask-more-repeat">
          <input type="checkbox" checked={repeat}
                 onChange={(e) => setRepeat(e.target.checked)} />
          <span>
            ขอซ้ำจากเจ้าที่เคยเชิญ ({repeats.map((v) => v.name).join(', ')}) —
            <span className="cell-sub">
              {' '}ไม่ติ๊ก = ระบบข้ามให้ · ติ๊กเมื่อราคาเดิมหมดอายุ หรือเปลี่ยนรหัสที่จับคู่ใหม่
            </span>
          </span>
        </label>
      )}

      <div className="ask-more-bar">
        <label className="checkbox">
          <input type="checkbox" checked={send} onChange={(e) => setSend(e.target.checked)} />
          <span>ออกแล้วส่งให้ผู้ขายเลย</span>
        </label>
        {send && (
          <input type="text" value={message} aria-label="ข้อความถึงผู้ขาย"
                 placeholder="ข้อความถึงผู้ขาย เช่น รบกวนเสนอราคาภายในสัปดาห์นี้"
                 onChange={(e) => setMessage(e.target.value)} />
        )}
        <button className="btn btn-primary" disabled={busy || !chosen.length} onClick={submit}>
          {busy ? 'กำลังออกใบ…' : `ออกใบขอราคา ${num(chosen.length)} ใบ`}
        </button>
      </div>
    </div>
  );
}

const round1 = (n) => Math.round(n * 10) / 10;
