import type { Metadata } from 'next';
import { SITE_URL } from '@/app/lib/site-url';
import { isLocalEdition, localGovId, withBasePath } from './site-edition';

/**
 * 地方版のブランド設定（福岡市版「みらい議会＠福岡市」の site.config.ts と同じ形）。
 * ヘッダー・フッター・利用規約・プライバシーポリシー・メタデータは、名前や運営者をここから読む。
 * 本家の app/lib/product.ts（政府予算ビュー）は変えない。
 */
export const localSiteConfig = {
  siteName: '予算ビュー＠福岡県',
  /** テキストロゴの上段・下段 */
  logo: { main: '予算ビュー', sub: '＠福岡県' },
  siteDescription: '福岡県の予算・決算を、会計・款・項・目のサンキー図と基金の推移でたどる非公式のビューアです。',
  prefName: '福岡県',
  /**
   * ソースコード（AGPL-3.0）。改変版の利用者にソースを示すため、本家ではなくこのフォークを指す。
   * リポジトリを yosan-view-fukuoka-pref に改名したら https://github.com/bakumon1107/yosan-view-fukuoka-pref に直す
   * （GitHub は旧 URL を転送するが、リンクは直す）
   */
  repositoryUrl: 'https://github.com/bakumon1107/yosan-view-fukuoka-pref',
  /** 本家（もとにしたソフトウェア） */
  upstream: { name: '政府予算ビュー', repositoryUrl: 'https://github.com/team-mirai-volunteer/rs-vis' },
  /** フッターに常に出す免責 */
  disclaimer: 'このサービスは政党チームみらいが運営しているものではありません',
  /** サービス運営者情報（利用規約・問い合わせ先） */
  operator: {
    name: 'バクモン',
    contactUrl: 'https://x.com/bakumon0907',
    /** 利用規約の準拠法・管轄裁判所（第一審の専属的合意管轄） */
    jurisdiction: '福岡地方裁判所',
  },
} as const;

/** 地方版の配色（ソフトラベンダー。福岡市版・安芸高田市版と同じ値）。本家の globals.css は変えず、CSS 変数を上書きする */
export const LOCAL_THEME_VARS: Record<string, string> = {
  '--primary': '#a495d6',
  '--primary-rgb': '164 149 214',
  '--primary-accent': '#7a6cc0',
  '--primary-accent-rgb': '122 108 192',
  '--ring': '#a495d6',
  '--mirai-gradient-start': '#dbd3f9',
  '--mirai-gradient-end': '#ede9fd',
  '--mirai-surface-teal': '#ede9fd',
  '--mirai-surface-teal-rgb': '237 233 253',
  '--status-good': '#7a6cc0',
};

export const LOCAL_THEME_COLOR = '#a495d6';

/** 地方版のナビ（ヘッダーの主要ナビ・メニュー）。名前は短く */
export function localNavItems(gov: string = localGovId()) {
  return [
    { href: `/local/${gov}`, label: 'サンキー図' },
    { href: `/local/${gov}/funds`, label: '基金' },
    { href: `/local/${gov}/about`, label: 'データについて' },
  ] as const;
}

/** 規約などの並び（フッター・メニュー） */
export const LOCAL_POLICY_LINKS = [
  { href: '/terms', label: '利用規約', external: false },
  { href: '/privacy', label: 'プライバシーポリシー', external: false },
  { href: localSiteConfig.repositoryUrl, label: 'ソースコード（GitHub）', external: true },
] as const;

/**
 * 地方版の既定のメタデータ（ルートレイアウト app/layout.local.tsx）。
 * 検索エンジンに載せる（2026-11-27 ユーザー決定で noindex を外した）。
 * OGP 画像は地方版のものを作るまで付けない（国版の画像は出さない）。
 * アイコンは basePath を付けて地方版のものを指す（本家の app/icon.* は書き出し後に公開物から外す）。
 */
export function localSiteMetadata(): Metadata {
  const { siteName, siteDescription } = localSiteConfig;
  return {
    metadataBase: new URL(SITE_URL),
    title: { default: siteName, template: `%s｜${siteName}` },
    description: siteDescription,
    applicationName: siteName,
    icons: { icon: withBasePath('/local-site/icon.svg'), apple: withBasePath('/local-site/icon.svg') },
    openGraph: { title: siteName, description: siteDescription, siteName, locale: 'ja_JP', type: 'website' },
    twitter: { card: 'summary', title: siteName, description: siteDescription },
  };
}

/** 地方版の各画面のパス（basePath を除く。trailingSlash に合わせて末尾は「/」） */
export const LOCAL_PAGE_PATHS = {
  sankey: () => `/local/${localGovId()}/`,
  funds: () => `/local/${localGovId()}/funds/`,
  about: () => `/local/${localGovId()}/about/`,
  terms: () => '/terms/',
  privacy: () => '/privacy/',
} as const;

/**
 * 地方版の各画面のメタデータ。title は「<画面名>｜予算ビュー＠福岡県」を absolute で付ける
 * （国版の版で開いたときも国版の名前が付かないように、テンプレートに頼らない）。
 * description・OGP も地方版で上書きする（国版のものを継承させない）。
 * - 福岡県版（静的サイト）: og:url と canonical をこの画面の絶対 URL にする。SITE_URL は basePath を含む
 *   （Pages の base_url）ので、metadataBase からの相対ではなく文字列でつなぐ（相対だと basePath が落ちる）。
 *   リポジトリの改名で旧 URL から転送されても、canonical で新しい URL を示せる
 * - 国版のビルド（/local/* は試作のまま）: noindex にし、ルートレイアウトの canonical（国版のトップ）を継承させない
 */
export function localPageMetadata(
  pageName: string,
  path: string,
  options: {
    /** 画面ごとの説明（規約など）。省略時はサイトの説明。description・OGP・twitter のすべてに使う */
    description?: string;
    /** 福岡県版（静的サイト）か。省略時は環境変数から（テストで切り替える） */
    local?: boolean;
  } = {},
): Metadata {
  const { siteName } = localSiteConfig;
  const description = options.description ?? localSiteConfig.siteDescription;
  const local = options.local ?? isLocalEdition();
  const title = `${pageName}｜${siteName}`;
  const url = `${SITE_URL.replace(/\/$/, '')}${path}`;
  return {
    title: { absolute: title },
    description,
    alternates: { canonical: local ? url : null },
    ...(local ? {} : { robots: { index: false, follow: false } }),
    openGraph: { title, description, siteName, locale: 'ja_JP', type: 'website', images: [], ...(local ? { url } : {}) },
    twitter: { card: 'summary', title, description, images: [] },
  };
}

/**
 * 地方版で GA を読み込む測定 ID。`NEXT_PUBLIC_GA_MEASUREMENT_ID` が明示されたときだけ返す
 * （本家の google-analytics.ts は未設定だと本家の本番プロパティに落ちるため、地方版はそれを使わない）。
 */
export function localGaMeasurementId(value: string | undefined = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID): string | null {
  const trimmed = value?.trim();
  return trimmed && /^G-[A-Z0-9]+$/.test(trimmed) ? trimmed : null;
}
