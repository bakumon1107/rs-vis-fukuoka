import { localGovId } from '@/app/lib/local-gov/site-edition';
import Layout from './layout';

/**
 * 地方版（静的サイト）の入口。画面本体（page.tsx 等）は 'use client' で generateStaticParams を出せないので、
 * ここで書き出す自治体を決める（その自治体だけ。ほかの自治体 ID は 404）。metadata は layout.tsx のものを使う。
 */
export { metadata } from './layout';

export function generateStaticParams() {
  return [{ gov: localGovId() }];
}

export const dynamicParams = false;

export default Layout;
