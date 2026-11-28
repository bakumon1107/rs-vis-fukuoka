'use client';

/**
 * 金額の大きい順の一覧の行（表示専用）。名前・額・補正の増減・帯の長さ・前年度比。押すとその箱を選ぶ。
 * かんたんの図の下の一覧（SimpleRanking）と、選んだ箱の内訳（BoxBreakdown）で使う
 */
import { previousRatio } from '@/app/lib/local-gov/breakdown';
import { shortDelta, type BoxDelta } from '@/app/lib/local-gov/supplement-diff';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';
import type { Yen } from '@/types/local-gov';

export interface RankedItem {
  id: string;
  name: string;
  value: Yen;
  /** 名前が読み取りだけ（※を付ける） */
  ocr?: boolean;
  /** 補正後の見方の、当初からの増減 */
  delta?: BoxDelta;
  /** 前年度の額（出さないときは undefined） */
  previous?: Yen;
}

/** 前年度の額の断り書き（一覧・内訳の表の上に出す） */
export const PREVIOUS_NOTE = '前年度は、説明書の「前年度予算額」（前の年度の当初予算）。';

const deltaColor =(v: number) => (v > 0 ? 'text-emerald-700' : v < 0 ? 'text-red-700' : 'text-mirai-text-muted');

/** 前年度の額と増減（「前年度 845.7億円 → +16.6億（+2.0%）」の形。前年度が 0 なら「前年度は計上なし」） */
export function PreviousLine({ value, previous }: { value: Yen; previous: Yen }) {
  const ratio = previousRatio(value, previous);
  const diff = value - previous;
  return (
    <span className="text-[11px] text-mirai-text-muted tabular-nums">
      {ratio === null ? (
        '前年度は計上なし'
      ) : (
        <>
          前年度 {formatBudgetFromYen(previous)}
          <span className={`ml-1 font-bold ${deltaColor(diff)}`}>
            {shortDelta(diff) || '±0'}（{ratio}）
          </span>
        </>
      )}
    </span>
  );
}

export function RankedList({ items, onSelect }: { items: RankedItem[]; onSelect: (id: string) => void }) {
  const max = Math.max(0, ...items.map(i => i.value));
  return (
    <ul>
      {items.map(n => {
        const d = n.delta;
        const dt = d ? (d.added ? '新' : shortDelta(d.delta)) : '';
        return (
          <li key={n.id} className="border-t border-mirai-border first:border-t-0">
            <button type="button" onClick={() => onSelect(n.id)} className="block w-full py-1.5 text-left">
              <span className="flex items-baseline justify-between gap-2 text-sm">
                <span className="min-w-0 truncate text-primary-accent">
                  {n.name}
                  {/* 図と同じく、読み取りの名前には印（凡例は図の上） */}
                  {n.ocr && <span className="text-amber-700">※</span>}
                </span>
                <span className="shrink-0 tabular-nums">
                  {formatBudgetFromYen(n.value)}
                  {dt && <span className={`ml-1 text-xs font-bold ${d?.added ? 'text-amber-700' : deltaColor(d?.delta ?? 0)}`}>{dt}</span>}
                </span>
              </span>
              <span aria-hidden="true" className="mt-1 block h-1.5 rounded-full bg-mirai-border">
                <span className="block h-full rounded-full bg-primary-accent opacity-60" style={{ width: `${max > 0 ? (n.value / max) * 100 : 0}%` }} />
              </span>
              {n.previous !== undefined && (
                <span className="mt-0.5 block text-right">
                  <PreviousLine value={n.value} previous={n.previous} />
                </span>
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
