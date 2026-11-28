'use client';

/**
 * 一般財源の中身（表示専用）。一般会計の見方で左端の「一般財源」の箱を押したときに、目の詳細と同じ場所に出す。
 * 図の帯は中身で分けない（按分の推計が要る）。中身は表だけで見せる。
 * 設計: docs/local-gov/tasks/20261114_1320_一般財源の中身の設計.md
 */
import Link from 'next/link';
import type { GeneralFund, GeneralFundBasis } from '@/types/local-gov';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';

/** 根拠の強さの短い説明（表の各行に小さく添える） */
const BASIS_LABEL: Record<GeneralFundBasis, string> = {
  revenue_kan: '歳入の款そのもの',
  matched: '説明書で確かめた（千円の位まで一致）',
  summed: '財源の名前ごとの足し上げから求めた額',
  residual: '差し引き（合計からほかの中身を引いた残り）',
};

export function GeneralFundPanel({ fund, aboutHref }: { fund: GeneralFund; aboutHref: string }) {
  return (
    <div className="space-y-3 p-4 text-sm text-mirai-text">
      <div>
        <p className="text-xs text-mirai-text-muted">一般会計 ／ 歳出の財源内訳</p>
        <h2 className="text-base font-bold">一般財源の中身</h2>
        <p className="text-xs text-mirai-text-muted">
          歳出の財源内訳の「一般財源」（使い道の決まっていないお金）が、歳入のどの収入から来ているかを並べます。
          図の帯は中身で分けていません（どの事業にどの収入を充てたかは資料に書かれていないため）。
        </p>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs text-mirai-text-muted">
            <th className="py-1 text-left font-normal">中身</th>
            <th className="py-1 text-right font-normal">額</th>
          </tr>
        </thead>
        <tbody>
          {fund.rows.map(r => (
            <tr key={r.label} className="border-t border-mirai-border align-top">
              <td className="py-1">
                {r.label}
                <span className="block text-[10px] text-mirai-text-muted">{BASIS_LABEL[r.basis]}</span>
              </td>
              <td className="whitespace-nowrap py-1 text-right">{formatBudgetFromYen(r.amount)}</td>
            </tr>
          ))}
          <tr className="border-t-2 border-mirai-border font-bold">
            <td className="py-1">計（一般財源）</td>
            <td className="whitespace-nowrap py-1 text-right">{formatBudgetFromYen(fund.total)}</td>
          </tr>
        </tbody>
      </table>
      <p className="text-xs text-mirai-text-muted">
        組み替え（歳入では別の款にあるが、財源内訳では一般財源に数えられているもの）の調べ方と根拠は{' '}
        <Link href={aboutHref} className="text-primary-accent underline">
          データについて
        </Link>
        （{fund.checked_on} に説明書で確認）。
      </p>
    </div>
  );
}
