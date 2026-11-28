'use client';

/**
 * 選んだ箱（財源・款・項・歳入の款・会計など）の内訳の表（表示専用）。その箱から右へ出る帯の行き先を、金額の大きい順に並べる。
 * 押すとその箱を選ぶ（款 → 項 → 目と下りていける）。
 * 設計: docs/local-gov/tasks/20261128_1130_選んだ箱の内訳の表と前年度比の設計.md
 */
import type { Breakdown } from '@/app/lib/local-gov/breakdown';
import { DELTA_COLUMNS, type BoxDelta } from '@/app/lib/local-gov/supplement-diff';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';
import type { Yen } from '@/types/local-gov';
import { PREVIOUS_NOTE, PreviousLine, RankedList } from './RankedList';

interface Props {
  breakdown: Breakdown;
  /** 行ごとの補正の増減（補正後の見方） */
  deltas?: Map<string, BoxDelta>;
  /** 箱ごとの前年度の額（当初予算の見方だけ） */
  previous?: Map<string, Yen>;
  onSelect: (id: string) => void;
}

export function BoxBreakdown({ breakdown: b, deltas, previous, onSelect }: Props) {
  // 前年度の額は、箱の全部が選んだ箱に入る行だけ（財源 → 款のように一部だけの行は、款全体の前年度と比べることになる）
  const items = b.items.map(it => ({
    ...it,
    delta: deltas?.get(it.id),
    previous: previous && it.whole ? previous.get(it.id) : undefined,
  }));
  const parentPrevious = previous?.get(b.parent.id);
  const someShown = items.some(it => it.previous !== undefined);
  // 一部だけ入るために前年度比・補正の増減を外した行があるか（その断り書きを出す）
  const partialRows = b.items.filter(it => !it.whole);
  const prevHidden = !!previous && partialRows.some(it => previous.has(it.id));
  const deltaHidden = !!deltas && DELTA_COLUMNS.has(b.childCol) && partialRows.length > 0;
  const hidden = [prevHidden && '前年度比', deltaHidden && '当初からの増減'].filter(Boolean).join('・');
  // 財源の箱は前年度の額がない（目ごとの財源内訳は本年度だけ）
  const fundingNoPrevious = !!previous && b.parent.id.startsWith('funding:');
  return (
    <section aria-label={`${b.parent.name}の内訳`} className="p-3">
      <h2 className="text-sm font-bold">
        {b.parent.name}の内訳（{b.childLabel}ごと）
      </h2>
      <p className="mb-2 mt-0.5 flex flex-wrap items-baseline gap-x-2 text-sm tabular-nums">
        <span>計 {formatBudgetFromYen(b.parent.value)}</span>
        {parentPrevious !== undefined && <PreviousLine value={b.parent.value} previous={parentPrevious} />}
      </p>
      <p className="mb-2 text-[11px] text-mirai-text-muted">
        名前を押すと、その{b.childLabel}を選びます。{(someShown || parentPrevious !== undefined) && PREVIOUS_NOTE}
        {fundingNoPrevious && '財源ごとの前年度の額は資料にないため、計には前年度比を出していません。'}
        {hidden && `${b.parent.name}から一部だけが入る行は、その分の額なので${hidden}を付けていません。`}
      </p>
      <RankedList items={items} onSelect={onSelect} />
    </section>
  );
}
