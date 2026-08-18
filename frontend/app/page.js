'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    api
      .me()
      .then(() => router.replace('/dashboard'))
      .catch(() => router.replace('/login'));
  }, [router]);

  return (
    <div className="center-screen">
      <p className="muted">กำลังตรวจสอบสถานะการเข้าสู่ระบบ…</p>
    </div>
  );
}
