'use client';

// หน้านี้เป็นตัวสำรอง: ปกติ FastAPI จะ redirect ไป /dashboard ให้เลย
// แต่ถ้าตั้งค่าให้ callback มาที่ฝั่ง frontend ก็จะเช็คสถานะแล้วส่งต่อจากที่นี่
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';

export default function AuthCallbackPage() {
  const router = useRouter();

  useEffect(() => {
    api
      .me()
      .then(() => router.replace('/dashboard'))
      .catch((err) => router.replace(`/login?error=${encodeURIComponent(err.message)}`));
  }, [router]);

  return (
    <div className="center-screen">
      <p className="muted">กำลังเข้าสู่ระบบ…</p>
    </div>
  );
}
