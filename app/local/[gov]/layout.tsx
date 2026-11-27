import type { Metadata } from 'next';
import { localPageMetadata } from '@/app/lib/local-gov/site';

// 地方版の画面（試作）。福岡県版のデプロイ（NEXT_PUBLIC_SITE_EDITION=local）では、ルートレイアウトが地方版の外枠
// （ヘッダー・フッター・配色）を付け、middleware が国版のページを隠す（docs/local-gov/tasks/20261127_1752_サイト全体から国版を外す設計.md）。
// 国版の description・OGP を継承しないよう、ここで地方版のものに上書きする。
// 数字・名前の確認が済むまで検索エンジンには載せない（noindex）
export const metadata: Metadata = localPageMetadata('サンキー図');

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
