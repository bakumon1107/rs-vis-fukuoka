'use client';

/**
 * CSS メディアクエリの真偽を React state で追う。SSR と初回描画では false（レイアウトのズレを避けるため
 * クライアントで一致した時点で true になる）。
 *
 * 用途: 640px 未満（Tailwind の `sm` 未満 = スマホ）でサイドパネルをボトムシートにする、
 * 図のフィット計算からパネル幅を除く、など CSS だけでは切り替えられない振る舞いの分岐。
 * 見た目だけの分岐は `sm:` のクラスで書き、このフックは使わない。
 */
import { useEffect, useState } from 'react';

/** Tailwind の `sm` ブレークポイント（640px）未満 */
export const NARROW_QUERY = '(max-width: 639px)';

/**
 * @param clientInitial true なら初回描画からクライアントの実際の値で始める。SSR されない（開いた後に描く）ダイアログなど、
 *   false → true の切り替えで中の部品が作り直される（通信が二重になる）のを避けたいときに使う。SSR される部分では使わない（hydration がずれる）
 */
export function useMediaQuery(query: string, clientInitial = false): boolean {
  const [matches, setMatches] = useState(() => clientInitial && typeof window !== 'undefined' && !!window.matchMedia && window.matchMedia(query).matches);
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mq = window.matchMedia(query);
    const update = () => setMatches(mq.matches);
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, [query]);
  return matches;
}

/** スマホ幅（640px 未満）か */
export const useIsNarrow = () => useMediaQuery(NARROW_QUERY);

/**
 * スマートフォンの横向き（幅は 640px 以上でも高さが 500px 未満）。パソコンの高さの低いウィンドウも入るが、
 * そこでも全部の列の図（縦に約 1,400px）は見通せないので、同じく3列にしてよい。
 * 最初にかんたんの図を出すかは、指で操作する画面（pointer: coarse）かも合わせて見る（page.tsx）
 */
export const LANDSCAPE_PHONE_QUERY = '(min-width: 640px) and (max-height: 499px)';
export const useIsLandscapePhone = () => useMediaQuery(LANDSCAPE_PHONE_QUERY);
