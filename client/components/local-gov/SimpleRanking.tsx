'use client';

/**
 * かんたんの図の下の一覧（表示専用）。図の右の列の箱（一般会計なら歳出の款）を金額の大きい順に、帯の長さつきで並べる。
 * 押すとくわしくの図でその箱を選ぶ。
 * 設計: docs/local-gov/tasks/20261128_0905_スマートフォンのサンキー図と簡易表示の設計.md 2.3
 */
import type { BoxDelta } from '@/app/lib/local-gov/supplement-diff';
import type { LocalGraph, Yen } from '@/types/local-gov';
import { PREVIOUS_NOTE, RankedList } from './RankedList';

interface Props {
  graph: LocalGraph;
  /** 補正後の見方の、箱ごとの当初からの増減 */
  deltas?: Map<string, BoxDelta>;
  /** 箱ごとの前年度の額（当初予算の見方だけ。ほかは undefined） */
  previous?: Map<string, Yen>;
  onSelect: (id: string) => void;
}

export function SimpleRanking({ graph, deltas, previous, onSelect }: Props) {
  const col = graph.columns.filter(c => graph.nodes.some(n => n.col === c.key)).at(-1);
  if (!col) return null;
  const items = graph.nodes
    .filter(n => n.col === col.key && !n.flags?.includes('aggregate'))
    .sort((a, b) => b.value - a.value)
    .map(n => ({
      id: n.id,
      name: n.name,
      value: n.value,
      ocr: n.flags?.includes('name-ocr'),
      delta: deltas?.get(n.id),
      previous: previous?.get(n.id),
    }));
  return (
    <section aria-label={`${col.label}の金額の大きい順`} className="rounded-2xl bg-card p-3 shadow-soft">
      <h2 className="mb-1 text-sm font-bold">{col.label}の金額の大きい順</h2>
      <p className="mb-2 text-[11px] text-mirai-text-muted">
        名前を押すと、くわしい図でその流れを見られます。{previous && PREVIOUS_NOTE}
      </p>
      <RankedList items={items} onSelect={onSelect} />
    </section>
  );
}
