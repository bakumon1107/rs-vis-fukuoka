'use client';

import { useEffect, useRef, useState } from 'react';

/**
 * 要素の幅（px）を測る。グラフを viewBox で縮めると、スマートフォンで文字が小さくなりすぎるので、実際の幅で描くのに使う。
 * 初回の描画（測る前）は fallback を返す
 */
export function useElementWidth<T extends HTMLElement>(fallback: number) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setWidth(el.clientWidth || fallback);
    measure();
    const ob = new ResizeObserver(measure);
    ob.observe(el);
    return () => ob.disconnect();
  }, [fallback]);
  return { ref, width };
}
