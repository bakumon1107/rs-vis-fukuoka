/**
 * データの一覧（index.json）で status が partial（検算が一致しない箇所がある）のデータを開いたときの注意。表示専用。
 * 設計: docs/local-gov/tasks/20261106_1327_地方版サンキー図の画面とグラフの設計.md 4.4、共通 JSON 形式の設計 3.1
 * linkToAbout: 「データについて」へのリンクを出すか（そのページ自体に出すときは出さない）
 */
import Link from 'next/link';
import type { Basis } from '@/types/local-gov';

export function PartialNotice({
  govId,
  year,
  basis = 'initial',
  linkToAbout = true,
}: {
  govId: string;
  year: number;
  /** 予算か決算か（「データについて」へのリンクで同じデータを開く） */
  basis?: Basis;
  linkToAbout?: boolean;
}) {
  return (
    <p role="note" className="mb-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
      このデータには、検算が一致しない箇所や推定した値があります。数字は確定したものではありません。
      {linkToAbout && (
        <>
          {' '}
          <Link href={`/local/${govId}/about?year=${year}${basis === 'settlement' ? '&basis=settlement' : ''}`} className="underline">
            データについて
          </Link>
          で検算の結果を確かめられます。
        </>
      )}
    </p>
  );
}
