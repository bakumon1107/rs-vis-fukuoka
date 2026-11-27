import type { Metadata } from 'next';
import { localPageMetadata } from '@/app/lib/local-gov/site';

// 地方版の画面（試作）。福岡県版は GitHub Pages の静的サイトとして書き出す（NEXT_PUBLIC_SITE_EDITION=local。
// 入口は layout.local.tsx・page.local.tsx。docs/local-gov/tasks/20261127_1752_サイト全体から国版を外す設計.md 10章）。
// 国版のビルドではこのファイルがそのまま使われるので、国版の description・OGP を継承しないよう地方版のものに上書きする。
export const metadata: Metadata = localPageMetadata('サンキー図');

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
