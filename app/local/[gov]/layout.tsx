import type { Metadata } from 'next';

// 地方版の画面（試作）。国版と地方版の切り替え（ナビ・トップ）は全体計画のフェーズ2。それまでは URL を直接開いて確認する。
// 数字・名前の確認が済むまで検索エンジンには載せない
export const metadata: Metadata = {
  title: '地方版予算ビュー（試作）',
  robots: { index: false, follow: false },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
