'use client';

import { createContext, useContext } from 'react';

/** ผู้ใช้ที่ล็อกอินอยู่ — โหลดครั้งเดียวที่ layout แล้วแชร์ให้ทุกหน้า */
export const AuthContext = createContext(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth ต้องอยู่ภายใต้ AppLayout');
  return ctx;
}

/** ให้แต่ละหน้าตั้งหัวข้อบนแถบบนได้ */
export const TopbarContext = createContext(() => {});
