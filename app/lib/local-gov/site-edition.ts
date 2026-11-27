/**
 * サイトの版（国版 / 地方版）の判定と、地方版のときの URL の振り分け。
 *
 * 地方版は環境変数 `NEXT_PUBLIC_SITE_EDITION=local` を立てたデプロイだけ。未設定なら本家と同じ国版のまま
 * （CI・本家の e2e はそのまま通る）。`NEXT_PUBLIC_` なのでビルド時に埋め込まれる（版を変えたら再ビルド）。
 * 設計: docs/local-gov/tasks/20261127_1752_サイト全体から国版を外す設計.md
 *
 * 振り分けは許可リスト方式。本家が新しいページや API を足しても、地方版では自動で隠れる。
 * middleware.ts はこのファイルの routeForLocalEdition を呼ぶだけにする（本家との衝突を小さく保つ）。
 */

export type SiteEdition = 'national' | 'local';

/** 既定の自治体（`NEXT_PUBLIC_LOCAL_GOV_ID` が未設定・不正なとき） */
export const DEFAULT_LOCAL_GOV_ID = 'fukuoka-pref';

const GOV_ID_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export function siteEdition(value: string | undefined = process.env.NEXT_PUBLIC_SITE_EDITION): SiteEdition {
  return value?.trim() === 'local' ? 'local' : 'national';
}

export function isLocalEdition(value: string | undefined = process.env.NEXT_PUBLIC_SITE_EDITION): boolean {
  return siteEdition(value) === 'local';
}

export function localGovId(value: string | undefined = process.env.NEXT_PUBLIC_LOCAL_GOV_ID): string {
  const trimmed = value?.trim();
  return trimmed && GOV_ID_PATTERN.test(trimmed) ? trimmed : DEFAULT_LOCAL_GOV_ID;
}

export type LocalRoute =
  | { kind: 'pass' }
  | { kind: 'rewrite'; to: string }
  | { kind: 'redirect'; to: string }
  | { kind: 'notFound' };

/** 地方版の書き換え先（URL は変えずに地方版の中身を出す） */
const REWRITES: Record<string, string> = {
  '/terms': '/local-site/terms',
  '/privacy': '/local-site/privacy',
  '/sitemap.xml': '/local-site/sitemap.xml',
  '/robots.txt': '/local-site/robots.txt',
  // アイコンは本家の app/icon.* 等を変えずに、地方版のアイコンへ差し替える
  '/favicon.ico': '/local-site/icon.svg',
  '/icon.svg': '/local-site/icon.svg',
  '/icon.png': '/local-site/icon.svg',
  '/apple-icon.png': '/local-site/icon.svg',
};

/** そのまま通すパスの接頭辞 */
const PASS_PREFIXES = ['/local/', '/local-site/', '/data/local-gov/', '/og/local/'];

/** Next.js の内部パス（静的アセット・開発時の HMR 等）。版に関係なく通す */
export function isFrameworkPath(pathname: string): boolean {
  return pathname.startsWith('/_next/') || pathname.startsWith('/__next');
}

/** 拡張子のある最後のセグメント（静的ファイル）か */
function looksLikeFile(pathname: string): boolean {
  const last = pathname.slice(pathname.lastIndexOf('/') + 1);
  return /\.[A-Za-z0-9]+$/.test(last);
}

/**
 * 地方版のときの振り分け。
 * - `/`・`/local` → 自治体のサンキー図へリダイレクト
 * - `/local/**`・`/local-site/**`・地方版のデータ・地方版の OGP → そのまま
 * - 規約・プライバシー・サイトマップ・robots・アイコン → 地方版の中身へ書き換え
 * - `/api/**`・それ以外の静的ファイル（国のデータ・国版の OGP 等） → 404
 * - それ以外のページ（国版） → `/` へリダイレクト
 */
export function routeForLocalEdition(pathname: string, govId: string = localGovId()): LocalRoute {
  // 末尾のスラッシュは外して扱う（`/` 自体は残す）
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, '') || '/' : pathname;
  if (isFrameworkPath(path)) return { kind: 'pass' };
  if (path === '/' || path === '/local') return { kind: 'redirect', to: `/local/${govId}` };
  const rewrite = REWRITES[path];
  if (rewrite) return { kind: 'rewrite', to: rewrite };
  if (PASS_PREFIXES.some(prefix => path.startsWith(prefix))) return { kind: 'pass' };
  if (path === '/api' || path.startsWith('/api/')) return { kind: 'notFound' };
  if (looksLikeFile(path)) return { kind: 'notFound' };
  return { kind: 'redirect', to: '/' };
}
