import type { Metadata } from 'next';
import Link from 'next/link';
import { localNavItems, localSiteConfig } from '@/app/lib/local-gov/site';
import { LocalHeaderSpacer } from '@/client/components/local-gov/LocalHeaderSpacer';

/**
 * 地方版（静的サイト）の 404。書き出しで 404.html になり、GitHub Pages が見つからない URL（国版の URL を含む）で返す。
 * ヘッダー・フッターはルートレイアウト（app/layout.local.tsx）が付ける。
 */
export const metadata: Metadata = {
  title: { absolute: `ページが見つかりません｜${localSiteConfig.siteName}` },
  robots: { index: false, follow: false },
};

export default function NotFound() {
  return (
    <div className="min-h-[60vh] bg-background text-mirai-text">
      <LocalHeaderSpacer />
      <main className="mx-auto max-w-3xl px-4 py-8">
        <h1 className="text-xl font-bold">ページが見つかりません</h1>
        <p className="mt-3 text-sm leading-relaxed">
          お探しのページはありません。このサイトは{localSiteConfig.prefName}の予算・決算のビューアです（国の予算のページはありません）。
        </p>
        <ul className="mt-4 space-y-2 text-sm">
          {localNavItems().map(item => (
            <li key={item.href}>
              <Link href={item.href} className="font-bold text-primary-accent underline underline-offset-4">{item.label}</Link>
            </li>
          ))}
        </ul>
      </main>
    </div>
  );
}
