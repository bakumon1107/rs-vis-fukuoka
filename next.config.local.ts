import type { NextConfig } from 'next';
import { basePath, isLocalEdition } from './app/lib/local-gov/site-edition';

/**
 * 地方版（フォーク独自）のビルド設定。`NEXT_PUBLIC_SITE_EDITION=local` のときだけ、
 * GitHub Pages に置く静的サイトとして書き出す設定に差し替える。それ以外（国版）は設定をそのまま返す。
 * 設計: docs/local-gov/tasks/20261127_1752_サイト全体から国版を外す設計.md 10章
 *
 * - `pageExtensions` を `*.local.tsx` / `*.local.ts` だけにして、地方版のファイルだけをルートにする
 *   （国版の page.tsx・route.ts・layout.tsx はルートでなくなり、ビルドに入らない）
 * - `basePath` は GitHub Pages のプロジェクトページのパス（例 /yosan-view-fukuoka-pref。独自ドメインなら空）
 * - 書き出しは distDir（.next-local/）に出る。公開物は scripts/local-gov/assemble-pages.mjs が許可リストで組み立てる
 * - headers()（CSP）は静的書き出しでは効かないので外す
 */
export function withLocalStaticExport(config: NextConfig): NextConfig {
  if (!isLocalEdition()) return config;
  return {
    ...config,
    headers: undefined,
    output: 'export',
    pageExtensions: ['local.tsx', 'local.ts'],
    basePath: basePath(),
    trailingSlash: true,
    images: { unoptimized: true },
    distDir: '.next-local',
  };
}
