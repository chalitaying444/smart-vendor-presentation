// Helper สำหรับเรียก FastAPI ผ่าน proxy /api ของ Next.js
const BASE = '';

/* หัวข้อมูลที่ต้องติดไปกับทุกคำขอ
 *
 * ngrok รุ่นฟรีจะขั้นหน้าเตือน "You are about to visit..." ให้กับคำขอที่มาจากเบราว์เซอร์
 * ซึ่งรวมถึง fetch ของหน้าเว็บด้วย ผลคือ API คืน HTML กลับมาแทน JSON แล้วหน้าจอ
 * จะขึ้น error งง ๆ ที่ไล่ต้นเหตุยากมาก · ใส่หัวข้อมูลนี้ไว้ ngrok จะข้ามหน้าเตือนให้
 * และไม่มีผลอะไรเลยเมื่อรันปกติที่ localhost
 */
const COMMON_HEADERS = { 'ngrok-skip-browser-warning': 'true' };

function qs(params = {}) {
  const clean = Object.fromEntries(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''),
  );
  const s = new URLSearchParams(clean).toString();
  return s ? `?${s}` : '';
}

async function request(path, options = {}) {
  const res = await fetch(`${BASE}/api${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...COMMON_HEADERS, ...(options.headers || {}) },
    ...options,
  });

  if (res.status === 204) return null;

  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }

  if (!res.ok) {
    const message = data?.detail || `เกิดข้อผิดพลาด (${res.status})`;
    const error = new Error(typeof message === 'string' ? message : JSON.stringify(message));
    error.status = res.status;
    throw error;
  }
  return data;
}

/** รหัสสินค้าอาจมี / หรืออักขระพิเศษ — เข้ารหัสทีละส่วนไม่ให้ path เพี้ยน */
export const encodePart = (partNum) =>
  String(partNum).split('/').map(encodeURIComponent).join('/');

export const api = {
  // ---- auth ----
  me: () => request('/auth/me'),
  logout: () => request('/auth/logout', { method: 'POST' }),

  // ---- users ----
  listUsers: (params = {}) => request(`/users${qs(params)}`),
  getUser: (id) => request(`/users/${id}`),
  createUser: (body) => request('/users', { method: 'POST', body: JSON.stringify(body) }),
  updateUser: (id, body) => request(`/users/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteUser: (id) => request(`/users/${id}`, { method: 'DELETE' }),

  // ---- สินค้า (จาก Epicor) ----
  searchItems: (params = {}) => request(`/catalog/items${qs(params)}`),
  suggestItems: (params = {}) => request(`/catalog/suggest${qs(params)}`),
  getItem: (partNum) => request(`/catalog/items/${encodePart(partNum)}`),
  itemTransactions: (partNum, params = {}) =>
    request(`/catalog/items/${encodePart(partNum)}/transactions${qs(params)}`),
  itemPriceHistory: (partNum) => request(`/catalog/items/${encodePart(partNum)}/price-history`),
  itemVendors: (partNum) => request(`/catalog/items/${encodePart(partNum)}/vendors`),
  catalogFacets: () => request('/catalog/facets'),
  overview: () => request('/catalog/overview'),
  refreshOverview: () => request('/catalog/overview/refresh', { method: 'POST' }),

  // ---- ผู้ขาย (จาก Epicor) ----
  listVendors: (params = {}) => request(`/vendors${qs(params)}`),
  getVendor: (key) => request(`/vendors/${encodeURIComponent(key)}`),
  vendorItems: (key, params = {}) =>
    request(`/vendors/${encodeURIComponent(key)}/items${qs(params)}`),
  vendorTransactions: (key, params = {}) =>
    request(`/vendors/${encodeURIComponent(key)}/transactions${qs(params)}`),
  vendorContacts: (key) => request(`/vendors/${encodeURIComponent(key)}/contacts`),
  vendorDeliveries: (key, params = {}) =>
    request(`/vendors/${encodeURIComponent(key)}/deliveries${qs(params)}`),
  updateVendorNote: (key, body) =>
    request(`/vendors/${encodeURIComponent(key)}/note`, { method: 'PATCH', body: JSON.stringify(body) }),

  // ---- ตามงานส่งของ ----
  listDeliveries: (params = {}) => request(`/deliveries${qs(params)}`),
  deliveriesByVendor: (params = {}) => request(`/deliveries/by-vendor${qs(params)}`),
  deliverySummary: () => request('/deliveries/summary'),

  // ---- ประมาณราคา BOM ----
  parseBom: (text) => request('/boms/parse', { method: 'POST', body: JSON.stringify({ text }) }),
  listBoms: (params = {}) => request(`/boms${qs(params)}`),
  getBom: (id) => request(`/boms/${id}`),
  createBom: (body) => request('/boms', { method: 'POST', body: JSON.stringify(body) }),
  updateBom: (id, body) => request(`/boms/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteBom: (id) => request(`/boms/${id}`, { method: 'DELETE' }),
  restoreBom: (id) => request(`/boms/${id}/restore`, { method: 'POST' }),
  purgeBom: (id) => request(`/boms/${id}/purge`, { method: 'DELETE' }),
  setBomAssignees: (id, body) =>
    request(`/boms/${id}/assignees`, { method: 'POST', body: JSON.stringify(body) }),
  listDepartments: () => request('/users/meta/departments'),
  bomCandidates: (id, lineNo, params = {}) =>
    request(`/boms/${id}/lines/${lineNo}/candidates${qs(params)}`),
  patchBomLine: (id, lineNo, body) =>
    request(`/boms/${id}/lines/${lineNo}`, { method: 'PATCH', body: JSON.stringify(body) }),
  addBomLine: (id, body) => request(`/boms/${id}/lines`, { method: 'POST', body: JSON.stringify(body) }),
  deleteBomLine: (id, lineNo) => request(`/boms/${id}/lines/${lineNo}`, { method: 'DELETE' }),
  rematchBom: (id) => request(`/boms/${id}/rematch`, { method: 'POST' }),
  bomComparison: (id) => request(`/boms/${id}/comparison`),
  bomAward: (id, body) => request(`/boms/${id}/award`, { method: 'POST', body: JSON.stringify(body) }),
  bomToRfq: (id, body) => request(`/boms/${id}/rfq`, { method: 'POST', body: JSON.stringify(body) }),
  bomRfqPlan: (id, params = {}) => request(`/boms/${id}/rfq-plan${qs(params)}`),
  bomVendorSearch: (id, lineNo, params = {}) =>
    request(`/boms/${id}/lines/${lineNo}/vendor-search${qs(params)}`),
  bomRfqsPerItem: (id, body) =>
    request(`/boms/${id}/rfqs`, { method: 'POST', body: JSON.stringify(body) }),

  // ---- RFQ ----
  listRfqs: (params = {}) => request(`/rfqs${qs(params)}`),
  getRfq: (id) => request(`/rfqs/${id}`),
  createRfq: (body) => request('/rfqs', { method: 'POST', body: JSON.stringify(body) }),
  updateRfq: (id, body) => request(`/rfqs/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  cancelRfq: (id) => request(`/rfqs/${id}`, { method: 'DELETE' }),
  restoreRfq: (id) => request(`/rfqs/${id}/restore`, { method: 'POST' }),
  bulkCancelRfqs: (ids) =>
    request('/rfqs/bulk-cancel', { method: 'POST', body: JSON.stringify({ rfq_ids: ids }) }),
  bulkRestoreRfqs: (ids) =>
    request('/rfqs/bulk-restore', { method: 'POST', body: JSON.stringify({ rfq_ids: ids }) }),
  rfqInvites: (id) => request(`/rfqs/${id}/invites`),
  rfqAddVendors: (id, vendor_keys) =>
    request(`/rfqs/${id}/vendors`, { method: 'POST', body: JSON.stringify({ vendor_keys }) }),
  rfqRemoveVendor: (id, key) =>
    request(`/rfqs/${id}/vendors/${encodeURIComponent(key)}`, { method: 'DELETE' }),
  rfqSuggested: (id) => request(`/rfqs/${id}/suggested-vendors`),
  rfqSend: (id, message) => request(`/rfqs/${id}/send`, { method: 'POST', body: JSON.stringify({ message }) }),
  rfqQuotes: (id) => request(`/rfqs/${id}/quotes`),
  rfqComparison: (id) => request(`/rfqs/${id}/comparison`),
  rfqAward: (id, body) => request(`/rfqs/${id}/award`, { method: 'POST', body: JSON.stringify(body) }),
  rfqClose: (id, reason) => request(`/rfqs/${id}/close`, { method: 'POST', body: JSON.stringify({ reason }) }),

  // ---- portal ของผู้ขาย (ไม่ต้องล็อกอิน) ----
  portalView: (token) => request(`/portal/${token}`),
  portalAcceptTerms: (token, body) =>
    request(`/portal/${token}/accept-terms`, { method: 'POST', body: JSON.stringify(body) }),
  portalDeleteAttachment: (token, fileId) =>
    request(`/portal/${token}/attachments/${encodeURIComponent(fileId)}`, { method: 'DELETE' }),
  portalQuote: (token, body) => request(`/portal/${token}/quote`, { method: 'POST', body: JSON.stringify(body) }),
  portalDecline: (token, reason) =>
    request(`/portal/${token}/decline`, { method: 'POST', body: JSON.stringify({ reason }) }),
};

/** อัปโหลดไฟล์แนบของผู้ขาย — ใช้ multipart จึงต้องไม่ตั้ง Content-Type เอง
 *  (ต้องปล่อยให้เบราว์เซอร์ใส่ boundary ให้) */
export async function uploadPortalAttachment(token, file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/api/portal/${token}/attachments`, {
    method: 'POST', credentials: 'include', body: form, headers: COMMON_HEADERS,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const message = data?.detail || `อัปโหลดไม่สำเร็จ (${res.status})`;
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }
  return data;
}

/** อ่าน BOM จากไฟล์ Excel/CSV — multipart เช่นกัน จึงห้ามตั้ง Content-Type เอง */
export async function uploadBomFile(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/api/boms/parse-file`, {
    method: 'POST', credentials: 'include', body: form, headers: COMMON_HEADERS,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const message = data?.detail || `อ่านไฟล์ไม่สำเร็จ (${res.status})`;
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }
  return data;
}

export const fileUrl = {
  rfqComparisonXlsx: (id) => `/api/rfqs/${id}/comparison.xlsx`,
  rfqDocument: (id, vendorKey) => `/api/rfqs/${id}/document/${encodeURIComponent(vendorKey)}`,
  portalDocument: (token) => `/api/portal/${token}/document`,
  bomExport: (id) => `/api/boms/${id}/export`,
};

// URL เริ่มล็อกอินกับ Microsoft (ให้เบราว์เซอร์ redirect ไปตรง ๆ)
export const MS_LOGIN_URL = '/api/auth/ms/login';
