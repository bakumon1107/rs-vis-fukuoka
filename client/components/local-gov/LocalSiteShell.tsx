import type { ReactNode } from 'react';
import { LOCAL_THEME_VARS } from '@/app/lib/local-gov/site';
import { LocalSiteFooter } from './LocalSiteFooter';
import { LocalSiteHeader } from './LocalSiteHeader';

/** 地方版の配色。本家の globals.css の :root より強い `html:root` で CSS 変数だけを上書きする */
const THEME_CSS = `html:root{${Object.entries(LOCAL_THEME_VARS).map(([k, v]) => `${k}:${v}`).join(';')}}`;

/**
 * 地方版（NEXT_PUBLIC_SITE_EDITION=local）の外枠。ルートレイアウトが国版の AppHeaderProvider の代わりに置く。
 * 配色の上書き・地方版のヘッダー（AI ボタンなし）・フッターを付ける。
 */
export function LocalSiteShell({ children }: { children: ReactNode }) {
  return <>
    <style dangerouslySetInnerHTML={{ __html: THEME_CSS }} />
    <LocalSiteHeader />
    {children}
    <LocalSiteFooter />
  </>;
}
