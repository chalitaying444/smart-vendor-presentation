'use client';

import { useEffect } from 'react';

export function Modal({ title, subtitle, onClose, children, footer }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

export function Toast({ message, type = 'info', onDone, duration = 3200 }) {
  useEffect(() => {
    if (!message) return undefined;
    const t = setTimeout(onDone, duration);
    return () => clearTimeout(t);
  }, [message, onDone, duration]);

  if (!message) return null;
  return <div className={`toast${type === 'error' ? ' error' : ''}`}>{message}</div>;
}

export function RoleBadge({ role }) {
  const label = { admin: 'ผู้ดูแลระบบ', staff: 'เจ้าหน้าที่', vendor: 'เวนเดอร์' }[role] || role;
  return <span className={`badge badge-${role}`}>{label}</span>;
}

export function StatusBadge({ active }) {
  return (
    <span className={`badge ${active ? 'badge-ok' : 'badge-off'}`}>
      <span className="dot" />
      {active ? 'ใช้งาน' : 'ระงับ'}
    </span>
  );
}

export function formatDate(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('th-TH', {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}
