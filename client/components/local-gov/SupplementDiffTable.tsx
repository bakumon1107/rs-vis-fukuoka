'use client';

/**
 * 補正後予算の、当初からの増減の表（表示専用）。図の下に折りたたみで置く（2026-11-27 ユーザー決定）。
 * 会計（全会計の見方）／款 → 項 → 目。押すと下の段を開く。広い画面は回ごとの補正額の列も、スマートフォンは 当初・増減・補正後 だけ。
 * 表の中身は app/lib/local-gov/supplement-diff.ts の supplementDiffTree（目の値の足し上げ。推計しない）。
 * 設計: docs/local-gov/tasks/20261127_2337_補正後予算の当初からの増減の表示の設計.md 4.2
 */
import Link from 'next/link';
import { Fragment, useMemo, useState } from 'react';
import { diffTotal, sortDiff, supplementDiffTree, withoutZero, type DiffNode } from '@/app/lib/local-gov/supplement-diff';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';
import type { LocalBudgetFile, Side } from '@/types/local-gov';

const yen = (v: number) => (v === 0 ? '—' : formatBudgetFromYen(v));
const signed = (v: number) => (v === 0 ? '—' : `${v > 0 ? '+' : '△'}${formatBudgetFromYen(Math.abs(v))}`);
const deltaClass = (v: number) => (v > 0 ? 'text-emerald-700' : v < 0 ? 'text-red-700' : 'text-mirai-text-muted');
/** 回の名前の短い形（「6月補正（第1号）」→「6月」、「9月補正（第4号・追加提案）」→「9月追加」） */
const shortRound = (r: string) => `${r.replace(/補正.*$/, '').replace(/専決$/, '専決')}${r.includes('追加') ? '追加' : ''}`;

interface Props {
  file: LocalBudgetFile;
  /** 全会計の見方なら会計の段から。一般会計の見方なら一般会計の款から */
  byAccount: boolean;
  gov: string;
}

export function SupplementDiffTable({ file, byAccount, gov }: Props) {
  const [side, setSide] = useState<Side>('expense');
  const [sortBy, setSortBy] = useState<'delta' | 'order'>('delta');
  const [showZero, setShowZero] = useState(false);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const rounds = file.composed?.rounds.map(r => r.round) ?? [];
  const tree = useMemo(() => supplementDiffTree(file, { side, byAccount }), [file, side, byAccount]);
  const nodes = useMemo(() => sortDiff(showZero ? tree : withoutZero(tree), sortBy), [tree, showZero, sortBy]);
  // 合計は増減のない行も含めた全体（見出しの総計と同じ額。見えている行だけを足すと、当初・補正後が全体より小さく出る）
  const total = diffTotal(tree);
  const toggle = (key: string) =>
    setOpen(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const indent = { account: 0, kan: 0, kou: 1, moku: 2 } as const;
  const renderRows = (ns: DiffNode[], depth: number): React.ReactNode =>
    ns.map(n => {
      const isOpen = open.has(n.key);
      const d = n.after - n.before;
      const pad = (byAccount ? depth : indent[n.level]) * 12;
      return (
        <Fragment key={n.key}>
          <tr className="border-t border-mirai-border align-top">
            <td className="break-words py-1.5 pr-1" style={{ paddingLeft: pad }}>
              {n.children.length > 0 ? (
                <button type="button" aria-expanded={isOpen} onClick={() => toggle(n.key)} className="text-left text-primary-accent hover:underline">
                  <span aria-hidden="true" className="mr-0.5 inline-block w-3 text-[10px] text-mirai-text-muted">{isOpen ? '▼' : '▶'}</span>
                  {n.name}
                </button>
              ) : n.rowId && n.rowId.includes('/expense/') ? (
                // 目は図でその目を選んだ状態にする（補正後の見方のまま）
                <Link href={`/local/${gov}?basis=latest&view=${byAccount ? 'all' : 'general'}&sel=${encodeURIComponent(`moku:${n.rowId}`)}`} className="text-primary-accent underline-offset-2 hover:underline">
                  {n.name}
                </Link>
              ) : (
                n.name
              )}
              {n.addedIn && <span className="ml-1 text-[10px] font-bold text-amber-700">新</span>}
            </td>
            <td className="whitespace-nowrap px-1 py-1.5 text-right tabular-nums">{yen(n.before)}</td>
            {rounds.map((r, i) => (
              <td key={r} className={`overflow-hidden whitespace-nowrap p-0 py-1.5 text-right tabular-nums md:px-1 ${deltaClass(n.rounds[i])}`}>
                <span className="hidden md:inline">{signed(n.rounds[i])}</span>
              </td>
            ))}
            <td className={`whitespace-nowrap px-1 py-1.5 text-right font-bold tabular-nums ${deltaClass(d)}`}>{signed(d)}</td>
            <td className="whitespace-nowrap px-1 py-1.5 text-right tabular-nums">{yen(n.after)}</td>
          </tr>
          {isOpen && renderRows(n.children, depth + 1)}
        </Fragment>
      );
    });

  const button = (active: boolean) =>
    `rounded-full border px-3 py-0.5 text-xs ${active ? 'border-primary-accent bg-mirai-surface-teal font-bold' : 'border-mirai-border bg-card'}`;
  return (
    <details className="rounded-2xl bg-card p-3 shadow-soft">
      <summary className="cursor-pointer text-sm font-bold">補正の増減の表</summary>
      <div className="mt-2 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <div role="group" aria-label="歳出と歳入" className="flex gap-1">
            <button type="button" aria-pressed={side === 'expense'} onClick={() => setSide('expense')} className={button(side === 'expense')}>歳出</button>
            <button type="button" aria-pressed={side === 'revenue'} onClick={() => setSide('revenue')} className={button(side === 'revenue')}>歳入</button>
          </div>
          <div role="group" aria-label="並べ方" className="flex gap-1">
            <button type="button" aria-pressed={sortBy === 'delta'} onClick={() => setSortBy('delta')} className={button(sortBy === 'delta')}>増減の大きい順</button>
            <button type="button" aria-pressed={sortBy === 'order'} onClick={() => setSortBy('order')} className={button(sortBy === 'order')}>款の順</button>
          </div>
          <label className="flex items-center gap-1 text-xs">
            <input type="checkbox" checked={showZero} onChange={e => setShowZero(e.target.checked)} />
            増減のない項目も表示
          </label>
        </div>
        <p className="text-[11px] text-mirai-text-muted">
          {byAccount ? '全会計（公営企業会計を除く）' : '一般会計'}の{side === 'expense' ? '歳出' : '歳入'}。当初予算に、{file.composed?.through}までの補正を足した額。
          行を押すと下の段を開きます。{side === 'expense' ? '目の名前を押すと図でその目を選びます。' : ''}
        </p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[340px] table-fixed text-[11px] sm:text-sm">
            <colgroup>
              <col className="w-[34%] md:w-[26%]" />
              <col className="w-[22%] md:w-[13%]" />
              {rounds.map(r => <col key={r} className="w-0 md:w-[9%]" />)}
              <col className="w-[22%] md:w-[13%]" />
              <col className="w-[22%] md:w-[13%]" />
            </colgroup>
            <thead>
              <tr className="text-xs text-mirai-text-muted">
                <th className="py-1 text-left align-bottom font-normal">{byAccount ? '会計・款・項・目' : '款・項・目'}</th>
                <th className="px-1 py-1 text-right align-bottom font-normal">当初</th>
                {/* 回ごとの列はスマートフォンで幅 0 の col。セルは隠さず中身だけ隠す（display:none にすると table-fixed で
                    後ろのセルが前の col に当たり、増減・補正後の列が幅 0 になって重なる） */}
                {rounds.map(r => (
                  <th key={r} title={r} className="overflow-hidden p-0 py-1 text-right align-bottom font-normal md:px-1">
                    <span className="hidden md:inline">{shortRound(r)}</span>
                  </th>
                ))}
                <th className="px-1 py-1 text-right align-bottom font-bold text-mirai-text">増減</th>
                <th className="px-1 py-1 text-right align-bottom font-normal">補正後</th>
              </tr>
            </thead>
            <tbody>
              {renderRows(nodes, 0)}
              <tr className="border-t-2 border-mirai-border font-bold">
                <td className="py-1.5">合計</td>
                <td className="whitespace-nowrap px-1 py-1.5 text-right tabular-nums">{yen(total.before)}</td>
                {rounds.map((r, i) => {
                  const v = tree.reduce((t, n) => t + n.rounds[i], 0);
                  return (
                    <td key={r} className={`overflow-hidden whitespace-nowrap p-0 py-1.5 text-right tabular-nums md:px-1 ${deltaClass(v)}`}>
                      <span className="hidden md:inline">{signed(v)}</span>
                    </td>
                  );
                })}
                <td className={`whitespace-nowrap px-1 py-1.5 text-right tabular-nums ${deltaClass(total.after - total.before)}`}>{signed(total.after - total.before)}</td>
                <td className="whitespace-nowrap px-1 py-1.5 text-right tabular-nums">{yen(total.after)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </details>
  );
}
