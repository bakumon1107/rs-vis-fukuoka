import type { Metadata, Viewport } from 'next';
import { Lexend_Giga, Noto_Sans_JP } from 'next/font/google';
import { SiteGoogleAnalytics } from '@/components/analytics/SiteGoogleAnalytics';
import { LOCAL_THEME_COLOR, localGaMeasurementId, localSiteMetadata } from '@/app/lib/local-gov/site';
import { LocalSiteShell } from '@/client/components/local-gov/LocalSiteShell';
import './globals.css';

/**
 * 地方版（静的サイト）のルートレイアウト。地方版のビルド（next.config.local.ts の pageExtensions）では
 * 本家の app/layout.tsx の代わりにこれが使われる。国版のビルドではルートにならない。
 * 国版のヘッダー・AI ナビは置かず、地方版の外枠（ヘッダー・フッター・配色）で包む。
 */

// 和文フォント・アクセント英字（本家の app/layout.tsx と同じ）
const notoSansJP = Noto_Sans_JP({ variable: '--font-noto-sans-jp', subsets: ['latin'], weight: ['400', '500', '700'], display: 'swap' });
const lexendGiga = Lexend_Giga({ variable: '--font-lexend-giga', subsets: ['latin'], weight: ['400', '500', '700'], display: 'swap' });

export const metadata: Metadata = localSiteMetadata();

export const viewport: Viewport = { width: 'device-width', initialScale: 1, themeColor: LOCAL_THEME_COLOR };

/** GA は測定 ID を明示したときだけ読み込む（既定は読み込まない。プライバシーポリシーの GA の段落も同じ条件） */
const GA_ID = localGaMeasurementId();

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ja" suppressHydrationWarning>
      <body
        className={`${notoSansJP.variable} ${lexendGiga.variable} font-sans antialiased bg-background text-foreground`}
        suppressHydrationWarning
      >
        <LocalSiteShell>{children}</LocalSiteShell>
        {GA_ID ? <SiteGoogleAnalytics gaId={GA_ID} /> : null}
      </body>
    </html>
  );
}
