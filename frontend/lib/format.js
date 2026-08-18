/** ตัวช่วยจัดรูปแบบตัวเลข/วันที่ ให้ทุกหน้าแสดงเหมือนกัน */

export function money(value, digits = 2) {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  if (Number.isNaN(n)) return '—';
  return n.toLocaleString('th-TH', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** ตัวเลขใหญ่ ๆ อ่านง่ายขึ้น: 129,458,179 -> 129.5 ล้าน */
export function shortMoney(value) {
  const n = Number(value);
  if (!n) return '—';
  const abs = Math.abs(n);
  if (abs >= 1e9) return `${(n / 1e9).toLocaleString('th-TH', { maximumFractionDigits: 2 })} พันล้าน`;
  if (abs >= 1e6) return `${(n / 1e6).toLocaleString('th-TH', { maximumFractionDigits: 1 })} ล้าน`;
  if (abs >= 1e3) return `${(n / 1e3).toLocaleString('th-TH', { maximumFractionDigits: 0 })} พัน`;
  return money(n, 0);
}

export function num(value, digits = 0) {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  if (Number.isNaN(n)) return '—';
  return n.toLocaleString('th-TH', { maximumFractionDigits: digits });
}

export function shortDate(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('th-TH', { year: 'numeric', month: 'short', day: 'numeric' });
}

export function dateTime(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('th-TH', {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

/** ซื้อครั้งล่าสุดเมื่อไร — บอกเป็น "เมื่อ 3 เดือนก่อน" อ่านแล้วตัดสินใจได้เร็วกว่าวันที่ */
export function sinceLabel(value) {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '';
  const days = Math.floor((Date.now() - d.getTime()) / 86400000);
  if (days < 0) return 'ในอนาคต';
  if (days < 31) return `${days} วันก่อน`;
  const months = Math.floor(days / 30);
  if (months < 24) return `${months} เดือนก่อน`;
  return `${Math.floor(days / 365)} ปีก่อน`;
}

/** ราคาล่าสุดเทียบราคาต่ำสุด — บวกคือแพงกว่าที่เคยซื้อได้ */
export function pctLabel(value) {
  if (value === null || value === undefined) return '';
  const n = Number(value);
  if (Number.isNaN(n)) return '';
  const sign = n > 0 ? '+' : '';
  return `${sign}${n.toLocaleString('th-TH', { maximumFractionDigits: 1 })}%`;
}

export function pctTone(value) {
  if (value === null || value === undefined) return '';
  const n = Number(value);
  if (Number.isNaN(n) || Math.abs(n) < 1) return '';
  return n > 0 ? 'up' : 'down';
}
