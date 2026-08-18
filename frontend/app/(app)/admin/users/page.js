'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import RequireAdmin from '@/components/RequireAdmin';
import { useAuth } from '@/components/AuthContext';
import { Modal, RoleBadge, StatusBadge, Toast, formatDate } from '@/components/ui';
import { IconPlus, IconSearch } from '@/components/icons';
import { api } from '@/lib/api';

const PAGE_SIZE = 20;
/* staff = ทำงานจัดซื้อได้เต็มที่ (สร้างโครงการ ออกใบขอราคา) แต่ไม่เห็นโครงการของหน่วยงานอื่น
   viewer = ดูอย่างเดียว · vendor = บัญชีฝั่งผู้ขาย ไม่ได้ใช้หน้าจอฝั่งในบริษัท */
const ROLES = [
  { value: 'admin', label: 'ผู้ดูแลระบบ (admin) — เห็นทุกโครงการ' },
  { value: 'staff', label: 'เจ้าหน้าที่จัดซื้อ (staff) — เห็นเฉพาะหน่วยงานตัวเอง' },
  { value: 'viewer', label: 'ดูอย่างเดียว (viewer)' },
  { value: 'vendor', label: 'เวนเดอร์ (vendor)' },
];

const emptyForm = { email: '', display_name: '', role: 'vendor', vendor_code: '',
                    departments: '', is_active: true };

export default function ManageUsersPage() {
  const me = useAuth();
  return (
    <RequireAdmin>
      <UsersTable me={me} />
    </RequireAdmin>
  );
}

function UsersTable({ me }) {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [term, setTerm] = useState('');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [toast, setToast] = useState(null);

  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(null);
  const [removing, setRemoving] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = { skip: page * PAGE_SIZE, limit: PAGE_SIZE };
      if (query) params.q = query;
      const data = await api.listUsers(params);
      setRows(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [page, query]);

  useEffect(() => { load(); }, [load]);

  // หน่วงการค้นหา 350ms
  useEffect(() => {
    const t = setTimeout(() => { setQuery(term.trim()); setPage(0); }, 350);
    return () => clearTimeout(t);
  }, [term]);

  const stats = useMemo(() => ({
    admin: rows.filter((r) => r.role === 'admin').length,
    active: rows.filter((r) => r.is_active).length,
  }), [rows]);

  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1);

  return (
    <>
      <div className="stat-row">
        <div className="stat">
          <div className="label">ผู้ใช้ทั้งหมด</div>
          <div className="num">{total.toLocaleString('th-TH')}</div>
          <div className="sub">ในฐานข้อมูล user</div>
        </div>
        <div className="stat">
          <div className="label">ใช้งานอยู่ (หน้านี้)</div>
          <div className="num">{stats.active.toLocaleString('th-TH')}</div>
          <div className="sub">จาก {rows.length} รายการที่แสดง</div>
        </div>
        <div className="stat">
          <div className="label">ผู้ดูแลระบบ (หน้านี้)</div>
          <div className="num">{stats.admin.toLocaleString('th-TH')}</div>
          <div className="sub">สิทธิ์ admin</div>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="card">
        <div className="card-head">
          <div className="search-wrap">
            <IconSearch />
            <input
              type="search"
              placeholder="ค้นหาอีเมล ชื่อ หรือรหัสเวนเดอร์…"
              value={term}
              onChange={(e) => setTerm(e.target.value)}
            />
          </div>
          <button className="btn btn-primary" onClick={() => setCreating(true)}>
            <IconPlus /> เพิ่มผู้ใช้
          </button>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ผู้ใช้</th>
                <th>สิทธิ์</th>
                <th>หน่วยงาน</th>
                <th>สถานะ</th>
                <th>เข้าสู่ระบบล่าสุด</th>
                <th style={{ textAlign: 'right' }}>จัดการ</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={6} className="empty">กำลังโหลด…</td></tr>
              )}

              {!loading && rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="empty">
                    <strong>{query ? 'ไม่พบผู้ใช้ที่ตรงกับคำค้น' : 'ยังไม่มีผู้ใช้ในระบบ'}</strong>
                    {query ? 'ลองเปลี่ยนคำค้นหาดูอีกครั้ง' : 'กด “เพิ่มผู้ใช้” เพื่อสร้างรายการแรก'}
                  </td>
                </tr>
              )}

              {!loading && rows.map((u) => (
                <tr key={u.id}>
                  <td>
                    <div className="cell-title">{u.display_name || '—'}</div>
                    <div className="cell-sub">{u.email}</div>
                  </td>
                  <td><RoleBadge role={u.role} /></td>
                  <td>
                    {u.departments?.length
                      ? u.departments.map((d) => <span key={d} className="chip">{d}</span>)
                      : <span className="muted">ยังไม่สังกัด</span>}
                  </td>
                  <td><StatusBadge active={u.is_active} /></td>
                  <td className="cell-sub">{formatDate(u.last_login_at)}</td>
                  <td className="actions">
                    <button className="btn btn-secondary btn-sm" onClick={() => setEditing(u)}>แก้ไข</button>
                    <button
                      className="btn btn-danger btn-sm"
                      disabled={u.id === me.id}
                      title={u.id === me.id ? 'ลบบัญชีตัวเองไม่ได้' : 'ลบผู้ใช้'}
                      onClick={() => setRemoving(u)}
                    >
                      ลบ
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="pager">
          <span>
            {total === 0
              ? 'ไม่มีรายการ'
              : `แสดง ${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, total)} จาก ${total.toLocaleString('th-TH')} รายการ`}
          </span>
          <div className="pager-btns">
            <button className="btn btn-secondary btn-sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>ก่อนหน้า</button>
            <button className="btn btn-secondary btn-sm" disabled={page >= lastPage} onClick={() => setPage((p) => p + 1)}>ถัดไป</button>
          </div>
        </div>
      </div>

      {creating && (
        <UserForm
          mode="create"
          onClose={() => setCreating(false)}
          onDone={(msg) => { setCreating(false); setToast({ message: msg }); load(); }}
          onError={(msg) => setToast({ message: msg, type: 'error' })}
        />
      )}

      {editing && (
        <UserForm
          mode="edit"
          user={editing}
          isSelf={editing.id === me.id}
          onClose={() => setEditing(null)}
          onDone={(msg) => { setEditing(null); setToast({ message: msg }); load(); }}
          onError={(msg) => setToast({ message: msg, type: 'error' })}
        />
      )}

      {removing && (
        <ConfirmDelete
          user={removing}
          onClose={() => setRemoving(null)}
          onDone={(msg) => { setRemoving(null); setToast({ message: msg }); load(); }}
          onError={(msg) => setToast({ message: msg, type: 'error' })}
        />
      )}

      <Toast {...(toast || {})} onDone={() => setToast(null)} />
    </>
  );
}

/** ชื่อหน่วยงานพิมพ์คั่นด้วยจุลภาค — ตัดช่องว่างและตัวซ้ำออกให้ ไม่งั้น
 *  "ฝ่ายจัดซื้อ " กับ "ฝ่ายจัดซื้อ" จะกลายเป็นคนละหน่วยงานทันที */
const splitDepts = (text) => [...new Set(
  (text || '').split(',').map((d) => d.trim()).filter(Boolean),
)];

function UserForm({ mode, user, isSelf, onClose, onDone, onError }) {
  const [knownDepts, setKnownDepts] = useState([]);
  useEffect(() => {
    api.listDepartments().then((r) => setKnownDepts(r.items || [])).catch(() => {});
  }, []);
  const [form, setForm] = useState(
    mode === 'edit'
      ? {
          email: user.email,
          display_name: user.display_name || '',
          role: user.role,
          vendor_code: user.vendor_code || '',
          departments: (user.departments || []).join(', '),
          is_active: user.is_active,
        }
      : emptyForm,
  );
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const set = (k) => (e) => {
    const v = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    setForm((f) => ({ ...f, [k]: v }));
  };

  async function submit(e) {
    e.preventDefault();
    setErr('');
    if (mode === 'create' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) {
      setErr('รูปแบบอีเมลไม่ถูกต้อง');
      return;
    }
    setSaving(true);
    try {
      if (mode === 'create') {
        await api.createUser({
          email: form.email.trim(),
          display_name: form.display_name.trim() || null,
          role: form.role,
          vendor_code: form.vendor_code.trim() || null,
          departments: splitDepts(form.departments),
          is_active: form.is_active,
        });
        onDone('เพิ่มผู้ใช้เรียบร้อย');
      } else {
        await api.updateUser(user.id, {
          display_name: form.display_name.trim() || null,
          role: form.role,
          vendor_code: form.vendor_code.trim() || null,
          departments: splitDepts(form.departments),
          is_active: form.is_active,
        });
        onDone('บันทึกการแก้ไขเรียบร้อย');
      }
    } catch (e2) {
      setErr(e2.message);
      onError?.(e2.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      title={mode === 'create' ? 'เพิ่มผู้ใช้ใหม่' : 'แก้ไขผู้ใช้'}
      subtitle={mode === 'edit' ? user.email : 'ผู้ใช้จะเข้าสู่ระบบด้วยบัญชี Microsoft ของอีเมลนี้'}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={saving}>ยกเลิก</button>
          <button type="submit" form="user-form" className="btn btn-primary" disabled={saving}>
            {saving ? 'กำลังบันทึก…' : 'บันทึก'}
          </button>
        </>
      }
    >
      <form id="user-form" onSubmit={submit}>
        {err && <div className="alert alert-error">{err}</div>}

        {mode === 'create' && (
          <div className="field">
            <label htmlFor="f-email">อีเมล *</label>
            <input id="f-email" type="email" required value={form.email} onChange={set('email')} placeholder="somchai@company.com" />
            <div className="hint">ต้องเป็นอีเมลเดียวกับบัญชี Microsoft ที่ใช้ล็อกอิน</div>
          </div>
        )}

        <div className="field">
          <label htmlFor="f-name">ชื่อที่แสดง</label>
          <input id="f-name" type="text" value={form.display_name} onChange={set('display_name')} placeholder="สมชาย ใจดี" />
        </div>

        <div className="field">
          <label htmlFor="f-role">สิทธิ์การใช้งาน</label>
          <select id="f-role" value={form.role} onChange={set('role')} disabled={isSelf}>
            {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
          {isSelf && <div className="hint">เปลี่ยนสิทธิ์ของบัญชีตัวเองไม่ได้</div>}
        </div>

        <div className="field">
          <label htmlFor="f-dept">หน่วยงานที่สังกัด</label>
          <input id="f-dept" type="text" value={form.departments} onChange={set('departments')}
                 list="all-departments" placeholder="ฝ่ายจัดซื้อ, ฝ่ายโครงการ" />
          <datalist id="all-departments">
            {knownDepts.map((d) => <option key={d} value={d} />)}
          </datalist>
          <div className="hint">
            คั่นด้วยจุลภาคถ้าอยู่หลายหน่วยงาน · <strong>หน่วยงานแรกคือค่าตั้งต้น</strong>
            ตอนคนนี้สร้างโครงการใหม่ · คนนี้จะเห็นโครงการของทุกหน่วยงานที่สังกัด
            {' '}(ผู้ขายและรายการซื้อขายยังเห็นได้ทั้งหมดเหมือนเดิม)
          </div>
        </div>

        <div className="field">
          <label htmlFor="f-code">รหัสเวนเดอร์</label>
          <input id="f-code" type="text" value={form.vendor_code} onChange={set('vendor_code')} placeholder="V001" />
        </div>

        <div className="field" style={{ marginBottom: 0 }}>
          <label className="checkbox">
            <input type="checkbox" checked={form.is_active} onChange={set('is_active')} disabled={isSelf} />
            เปิดใช้งานบัญชีนี้
          </label>
          {isSelf && <div className="hint">ระงับบัญชีตัวเองไม่ได้</div>}
        </div>
      </form>
    </Modal>
  );
}

function ConfirmDelete({ user, onClose, onDone, onError }) {
  const [busy, setBusy] = useState(false);

  async function remove() {
    setBusy(true);
    try {
      await api.deleteUser(user.id);
      onDone('ลบผู้ใช้เรียบร้อย');
    } catch (err) {
      onError?.(err.message);
      onClose();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title="ยืนยันการลบผู้ใช้"
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-secondary" onClick={onClose} disabled={busy}>ยกเลิก</button>
          <button className="btn btn-danger" onClick={remove} disabled={busy}>
            {busy ? 'กำลังลบ…' : 'ลบผู้ใช้'}
          </button>
        </>
      }
    >
      <p style={{ margin: 0 }}>
        ต้องการลบ <strong>{user.display_name || user.email}</strong> ({user.email}) ออกจากระบบใช่หรือไม่?
      </p>
      <p className="cell-sub" style={{ marginBottom: 0 }}>
        การลบไม่สามารถย้อนกลับได้ หากเพียงต้องการปิดการใช้งานชั่วคราว ให้ใช้ “แก้ไข” แล้วเอาเครื่องหมายถูกออกจาก “เปิดใช้งานบัญชีนี้” แทน
      </p>
    </Modal>
  );
}
