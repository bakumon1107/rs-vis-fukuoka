import type { Metadata, Viewport } from "next";
import { Lexend_Giga, Noto_Sans_JP } from "next/font/google";
import { googleAnalyticsMeasurementId, isProductionAnalytics } from "@/app/lib/google-analytics";
import { SITE_URL } from "@/app/lib/site-url";
import { pageMetadata } from '@/app/lib/page-metadata';
import { SiteGoogleAnalytics } from '@/components/analytics/SiteGoogleAnalytics';
import { AppHeaderProvider } from '@/components/navigation/AppHeader';
// 地方版（フォーク独自）: NEXT_PUBLIC_SITE_EDITION=local のときだけ外枠・メタデータ・GA を切り替える
import { isLocalEdition } from '@/app/lib/local-gov/site-edition';
import { LOCAL_THEME_COLOR, localGaMeasurementId, localSiteMetadata } from '@/app/lib/local-gov/site';
import { LocalSiteShell } from '@/client/components/local-gov/LocalSiteShell';
import "./globals.css";

// 和文フォント。400（本文）/ 500（中肉）/ 700（見出し）を最低限ロード
const notoSansJP = Noto_Sans_JP({
  variable: "--font-noto-sans-jp",
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  display: "swap",
});

// 数字・ロゴ周辺のアクセント英字（デザインシステム 2.2.4）。大きい数字は 500 を使うので 500 も読む
const lexendGiga = Lexend_Giga({
  variable: "--font-lexend-giga",
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  display: "swap",
});

const LOCAL_EDITION = isLocalEdition();
// 地方版は明示した測定 ID のときだけ計測する（未設定で本家のプロパティに送らない）
const LOCAL_GA_ID = LOCAL_EDITION ? localGaMeasurementId() : null;

export const metadata: Metadata = LOCAL_EDITION ? localSiteMetadata() : {
  metadataBase: new URL(SITE_URL),
  ...pageMetadata('/'),
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: LOCAL_EDITION ? LOCAL_THEME_COLOR : "#2aa693",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja" suppressHydrationWarning>
      <body
        className={`${notoSansJP.variable} ${lexendGiga.variable} font-sans antialiased bg-background text-foreground`}
        suppressHydrationWarning
      >
        {LOCAL_EDITION ? <LocalSiteShell>{children}</LocalSiteShell> : <AppHeaderProvider>{children}</AppHeaderProvider>}
        {isProductionAnalytics() && (!LOCAL_EDITION || LOCAL_GA_ID) ? (
          <SiteGoogleAnalytics gaId={LOCAL_GA_ID ?? googleAnalyticsMeasurementId()} />
        ) : null}
      </body>
    </html>
  );
}
