'use client';

/**
 * Layout กลางของทุกหน้าหลังล็อกอิน
 *
 * เมนูซ้าย + แถบบน + การตรวจสิทธิ์ อยู่ที่นี่ที่เดียว (global)
 * เวลาสลับหน้า Next.js จะเปลี่ยนเฉพาะเนื้อหาตรงกลาง เมนูไม่ re-render
 * และไม่เรียก /auth/me ซ้ำ — ผู้ใช้ถูกโหลดครั้งเดียวแล้วแชร์ผ่าน context
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { AuthContext, TopbarContext } from '@/components/AuthContext';
import {
  IconBudget, IconDashboard, IconUsers, IconVendor, IconSettings, IconLogout, IconSearchNav,
  IconRfq, IconDoc,
} from '@/components/icons';

const NAV = [
  { href: '/dashboard', label: 'ภาพรวม', Icon: IconDashboard },
  { href: '/products', label: 'ค้นหาสินค้า', Icon: IconSearchNav },
  { href: '/vendors', label: 'ผู้ขาย', Icon: IconVendor },
  { href: '/deliveries', label: 'ตามงานส่งของ', Icon: IconDoc },
  { href: '/boms', label: 'ประมาณราคา BOM', Icon: IconBudget },
  { href: '/rfqs', label: 'ใบขอราคา (RFQ)', Icon: IconRfq },
  { href: '/admin/users', label: 'จัดการผู้ใช้', Icon: IconUsers, adminOnly: true },
  { href: '/settings', label: 'ตั้งค่า', Icon: IconSettings, soon: true },
];

// หัวข้อเริ่มต้นของแต่ละเส้นทาง (หน้าที่ต้องการเปลี่ยนเองใช้ usePageTitle ได้)
const TITLES = [
  ['/dashboard', 'ภาพรวม', 'ยอดซื้อ ผู้ขายรายใหญ่ และของที่ราคาแกว่ง'],
  ['/products', 'ค้นหาสินค้า', 'ค้นแบบไม่ต้องตรงเป๊ะ — เห็นราคาล่าสุดทันที'],
  ['/vendors', 'ผู้ขาย', 'ผู้ขายทั้งหมดจาก Epicor'],
  ['/deliveries', 'ตามงานส่งของ', 'งวดไหนช้า ของใคร เป็นของอะไร'],
  ['/boms', 'ประมาณราคา BOM', 'เอา BOM ของโครงการมาตีงบจากราคาที่เคยซื้อจริง'],
  ['/rfqs', 'ใบขอราคา (RFQ)', 'ขอราคา เทียบกับราคาเดิม และประกาศผู้ชนะ'],
  ['/admin/users', 'จัดการผู้ใช้', 'ผู้ดูแลระบบ / ผู้ใช้ทั้งหมด'],
];

const ROLE_LABEL = { admin: 'ผู้ดูแลระบบ', staff: 'เจ้าหน้าที่', vendor: 'เวนเดอร์' };

export default function AppLayout({ children }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState(null);
  const [state, setState] = useState('loading');
  const [override, setOverride] = useState(null);

  useEffect(() => {
    let alive = true;
    api.me()
      .then((me) => { if (alive) { setUser(me); setState('ready'); } })
      .catch((err) => {
        if (!alive) return;
        if (err.status === 401) router.replace('/login');
        else setState('error');
      });
    return () => { alive = false; };
  }, [router]);

  const handleLogout = useCallback(async () => {
    try { await api.logout(); } finally { router.replace('/login'); }
  }, [router]);

  const base = useMemo(() => {
    const hit = TITLES.find(([href]) => pathname === href || pathname.startsWith(`${href}/`));
    return hit ? { title: hit[1], crumb: hit[2] } : { title: 'Vendor App', crumb: '' };
  }, [pathname]);

  // เปลี่ยนหน้าแล้วล้างหัวข้อที่หน้าเดิมตั้งไว้
  useEffect(() => { setOverride(null); }, [pathname]);

  if (state === 'loading') return <div className="center-screen">กำลังโหลด…</div>;
  if (state === 'error') {
    return (
      <div className="center-screen">
        <div className="card" style={{ padding: 28, maxWidth: 420, textAlign: 'center' }}>
          <h2 style={{ marginBottom: 8 }}>เชื่อมต่อระบบไม่ได้</h2>
          <p className="cell-sub" style={{ marginBottom: 18 }}>ตรวจสอบว่า backend ทำงานอยู่ที่พอร์ต 8000</p>
          <button className="btn btn-primary" onClick={() => window.location.reload()}>ลองใหม่</button>
        </div>
      </div>
    );
  }

  const isAdmin = user?.role === 'admin';
  const items = NAV.filter((n) => !n.adminOnly || isAdmin);
  const head = override || base;

  return (
    <AuthContext.Provider value={user}>
      <TopbarContext.Provider value={setOverride}>
        <div className="shell">
          <aside className="sidebar">
            <div className="brand">
              <div className="brand-mark">VA</div>
              <div>
                <div className="brand-name">Vendor App</div>
                <div className="brand-sub">จัดซื้อ · Epicor</div>
              </div>
            </div>

            <div className="nav-label">เมนู</div>
            {items.map(({ href, label, Icon, soon }) =>
              soon ? (
                <div key={href} className="nav-item disabled" title="กำลังพัฒนา">
                  <Icon /><span className="txt">{label}</span>
                </div>
              ) : (
                <Link
                  key={href}
                  href={href}
                  className={`nav-item${pathname === href || pathname.startsWith(`${href}/`) ? ' active' : ''}`}
                >
                  <Icon /><span className="txt">{label}</span>
                </Link>
              ),
            )}

            <div className="sidebar-foot">
              <div className="who">{user?.display_name || user?.email}</div>
              <div className="who-sub">{ROLE_LABEL[user?.role] || user?.role}</div>
              <button className="nav-item" style={{ marginTop: 10 }} onClick={handleLogout}>
                <IconLogout /><span className="txt">ออกจากระบบ</span>
              </button>
            </div>
          </aside>

          <div className="main">
            <header className="topbar">
              <div>
                <h1>{head.title}</h1>
                {head.crumb && <div className="crumb">{head.crumb}</div>}
              </div>
            </header>
            <div className="content">{children}</div>
          </div>
        </div>
      </TopbarContext.Provider>
    </AuthContext.Provider>
  );
}
