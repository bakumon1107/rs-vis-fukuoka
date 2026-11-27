/**
 * サイトの版（国版 / 地方版）と自治体 ID の判定。
 *
 * 地方版は環境変数 `NEXT_PUBLIC_SITE_EDITION=local` を立てたビルドだけ（GitHub Pages の静的サイト。next.config.local.ts）。
 * 未設定なら本家と同じ国版のまま（CI・本家の e2e はそのまま通る）。`NEXT_PUBLIC_` なのでビルド時に埋め込まれる。
 * 設計: docs/local-gov/tasks/20261127_1752_サイト全体から国版を外す設計.md 10章
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

/**
 * basePath（GitHub Pages のプロジェクトページのパス。例 /yosan-view-fukuoka-pref）。
 * next/link・router は Next.js が自動で付けるが、fetch・メタデータの URL・meta refresh は自分で付ける。
 * 先頭に / を付け、末尾の / は外す。未設定・空なら ''。
 */
export function basePath(value: string | undefined = process.env.NEXT_PUBLIC_BASE_PATH): string {
  const trimmed = value?.trim().replace(/\/+$/, '') ?? '';
  if (!trimmed) return '';
  return trimmed.startsWith('/') ? trimmed : `/${trimmed}`;
}

/** basePath を前に付けたパス（`path` は / から始める） */
export function withBasePath(path: string, base: string = basePath()): string {
  return `${base}${path}`;
}
