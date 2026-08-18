'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * โหลดรายการทีละชุด (batch) แบบต่อท้าย
 *
 * จุดสำคัญ: คำค้นและฟิลเตอร์ถูกส่งไปให้ backend ค้นกับ "ข้อมูลทั้งฐาน"
 * ไม่ใช่กรองเฉพาะชุดที่โหลดมาแล้ว — `total` ที่ได้กลับมาคือจำนวนที่ตรงทั้งหมด
 *
 * @param fetcher  async ({ skip, limit, ...filters }) => { items, total, has_more }
 * @param filters  object ของฟิลเตอร์ (เปลี่ยนเมื่อไร = เริ่มโหลดใหม่จากศูนย์)
 * @param limit    ขนาดของแต่ละ batch
 */
export function useBatchList(fetcher, filters, limit = 30) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  // ข้อมูลประกอบที่มากับหน้ารายการ (เช่น หน่วยงานที่ผู้ใช้สังกัด) — ไม่ใช่ตัวรายการ
  const [meta, setMeta] = useState(null);

  const key = JSON.stringify(filters);
  const reqId = useRef(0);

  const fetchPage = useCallback(async (skip, append) => {
    const myReq = ++reqId.current;
    append ? setLoadingMore(true) : setLoading(true);
    setError('');
    try {
      const data = await fetcher({ ...JSON.parse(key), skip, limit });
      if (myReq !== reqId.current) return;      // มีคำขอใหม่กว่าแล้ว ทิ้งผลนี้
      setItems((prev) => (append ? [...prev, ...data.items] : data.items));
      setTotal(data.total);
      setHasMore(data.has_more);
      const { items: _items, total: _t, skip: _s, limit: _l, has_more: _h, ...rest } = data;
      setMeta(rest);
    } catch (err) {
      if (myReq === reqId.current) setError(err.message);
    } finally {
      if (myReq === reqId.current) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, [fetcher, key, limit]);

  useEffect(() => { fetchPage(0, false); }, [fetchPage]);

  const loadMore = useCallback(() => {
    if (loading || loadingMore || !hasMore) return;
    fetchPage(items.length, true);
  }, [fetchPage, items.length, hasMore, loading, loadingMore]);

  return { items, total, hasMore, loading, loadingMore, error, meta,
           loadMore, reload: () => fetchPage(0, false) };
}

/** ตัวช่วยหน่วงค่า (debounce) สำหรับช่องค้นหา */
export function useDebounced(value, delay = 350) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return v;
}

/** เรียก onHit เมื่อ element ที่ ref ชี้อยู่เลื่อนเข้ามาในจอ (infinite scroll) */
export function useOnScreen(onHit, enabled) {
  const ref = useRef(null);
  useEffect(() => {
    if (!enabled || !ref.current) return undefined;
    const io = new IntersectionObserver(
      (entries) => { if (entries[0].isIntersecting) onHit(); },
      { rootMargin: '300px' },
    );
    io.observe(ref.current);
    return () => io.disconnect();
  }, [onHit, enabled]);
  return ref;
}
