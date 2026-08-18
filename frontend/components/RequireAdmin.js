'use client';

import Link from 'next/link';
import { useEffect, useContext } from 'react';
import { useAuth, TopbarContext } from '@/components/AuthContext';

/** ครอบเนื้อหาที่ให้เฉพาะ admin เห็น (เมนูซ้ายซ่อนอยู่แล้ว อันนี้กันเข้า URL ตรง ๆ) */
export default function RequireAdmin({ children }) {
  const user = useAuth();
  if (user?.role !== 'admin') {
    return (
      <div className="card" style={{ padding: 32, maxWidth: 460, margin: '40px auto', textAlign: 'center' }}>
        <h2 style={{ marginBottom: 8 }}>ไม่มีสิทธิ์เข้าถึง</h2>
        <p className="cell-sub" style={{ marginBottom: 18 }}>หน้านี้สำหรับผู้ดูแลระบบเท่านั้น</p>
        <Link className="btn btn-primary" href="/dashboard">กลับหน้าภาพรวม</Link>
      </div>
    );
  }
  return children;
}

/** ให้หน้าเปลี่ยนหัวข้อบนแถบบนได้ (เช่น หน้ารายละเอียดเวนเดอร์ใส่ชื่อบริษัท) */
export function usePageTitle(title, crumb) {
  const setTopbar = useContext(TopbarContext);
  useEffect(() => {
    if (title) setTopbar({ title, crumb });
  }, [title, crumb, setTopbar]);
}
