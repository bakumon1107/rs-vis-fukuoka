'use client';

/**
 * かんたんの図の下の一覧（表示専用）。図の右の列の箱（一般会計なら歳出の款）を金額の大きい順に、帯の長さつきで並べる。
 * 押すとくわしくの図でその箱を選ぶ。
 * 設計: docs/local-gov/tasks/20261128_0905_スマートフォンのサンキー図と簡易表示の設計.md 2.3
 */
import { shortDelta, type BoxDelta } from '@/app/lib/local-gov/supplement-diff';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';
import type { LocalGraph } from '@/types/local-gov';

interface Props {
  graph: LocalGraph;
  /** 補正後の見方の、箱ごとの当初からの増減 */
  deltas?: Map<string, BoxDelta>;
  onSelect: (id: string) => void;
}

export function SimpleRanking({ graph, deltas, onSelect }: Props) {
  const col = graph.columns.filter(c => graph.nodes.some(n => n.col === c.key)).at(-1);
  if (!col) return null;
  const nodes = graph.nodes.filter(n => n.col === col.key && !n.flags?.includes('aggregate')).sort((a, b) => b.value - a.value);
  const max = nodes[0]?.value ?? 0;
  return (
    <section aria-label={`${col.label}の金額の大きい順`} className="rounded-2xl bg-card p-3 shadow-soft">
      <h2 className="mb-1 text-sm font-bold">{col.label}の金額の大きい順</h2>
      <p className="mb-2 text-[11px] text-mirai-text-muted">名前を押すと、くわしい図でその流れを見られます。</p>
      <ul>
        {nodes.map(n => {
          const d = deltas?.get(n.id);
          const dt = d ? (d.added ? '新' : shortDelta(d.delta)) : '';
          return (
            <li key={n.id} className="border-t border-mirai-border first:border-t-0">
              <button type="button" onClick={() => onSelect(n.id)} className="block w-full py-1.5 text-left">
                <span className="flex items-baseline justify-between gap-2 text-sm">
                  <span className="min-w-0 truncate text-primary-accent">
                    {n.name}
                    {/* 図と同じく、読み取りの名前には印（凡例は図の上） */}
                    {n.flags?.includes('name-ocr') && <span className="text-amber-700">※</span>}
                  </span>
                  <span className="shrink-0 tabular-nums">
                    {formatBudgetFromYen(n.value)}
                    {dt && (
                      <span className={`ml-1 text-xs font-bold ${d?.added ? 'text-amber-700' : (d?.delta ?? 0) > 0 ? 'text-emerald-700' : 'text-red-700'}`}>
                        {dt}
                      </span>
                    )}
                  </span>
                </span>
                <span aria-hidden="true" className="mt-1 block h-1.5 rounded-full bg-mirai-border">
                  <span className="block h-full rounded-full bg-primary-accent opacity-60" style={{ width: `${max > 0 ? (n.value / max) * 100 : 0}%` }} />
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
