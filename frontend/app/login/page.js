'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { api, MS_LOGIN_URL } from '@/lib/api';
import { IconMicrosoft } from '@/components/icons';

const HIGHLIGHTS = [
  'เข้าสู่ระบบด้วยบัญชี Microsoft ขององค์กร ไม่ต้องจำรหัสผ่านเพิ่ม',
  'กำหนดสิทธิ์ผู้ดูแลระบบ เจ้าหน้าที่ และเวนเดอร์ได้แยกกัน',
  'ข้อมูลผู้ใช้ถูกบันทึกและตรวจสอบย้อนหลังได้ทุกครั้งที่ล็อกอิน',
];

function LoginInner() {
  const router = useRouter();
  const params = useSearchParams();
  const error = params.get('error');
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    api.me().then(() => router.replace('/dashboard')).catch(() => setChecking(false));
  }, [router]);

  return (
    <div className="auth-screen">
      <section className="auth-art">
        <div className="brand" style={{ padding: 0 }}>
          <div className="brand-mark">VA</div>
          <div>
            <div className="brand-name">Vendor App</div>
            <div className="brand-sub">ระบบจัดการเวนเดอร์</div>
          </div>
        </div>

        <div>
          <h2>จัดการเวนเดอร์และสิทธิ์ผู้ใช้ ในที่เดียว</h2>
          <ul>
            {HIGHLIGHTS.map((t) => (
              <li key={t}><span className="tick">✓</span>{t}</li>
            ))}
          </ul>
        </div>

        <p style={{ marginBottom: 0, fontSize: 12 }}>© {new Date().getFullYear()} Vendor App</p>
      </section>

      <section className="auth-pane">
        <div className="auth-box">
          <h1>เข้าสู่ระบบ</h1>
          <p className="lead">ใช้บัญชี Microsoft ขององค์กรเพื่อเข้าใช้งาน</p>

          {error && <div className="alert alert-error">{error}</div>}

          <button
            className="btn btn-ms"
            disabled={checking}
            onClick={() => { window.location.href = MS_LOGIN_URL; }}
          >
            <IconMicrosoft />
            {checking ? 'กำลังตรวจสอบสถานะ…' : 'ลงชื่อเข้าใช้ด้วย Microsoft'}
          </button>

          <p className="auth-note">
            หากเข้าสู่ระบบไม่ได้ ให้ตรวจสอบค่า <code>MS_TENANT_ID</code> / <code>MS_CLIENT_ID</code> /{' '}
            <code>MS_CLIENT_SECRET</code> ในไฟล์ <code>.env</code> และ Redirect URI ที่ลงทะเบียนไว้ใน Azure
          </p>
        </div>
      </section>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="center-screen">กำลังโหลด…</div>}>
      <LoginInner />
    </Suspense>
  );
}
