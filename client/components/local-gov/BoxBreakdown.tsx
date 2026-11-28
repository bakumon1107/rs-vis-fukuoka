'use client';

/**
 * 選んだ箱（財源・款・項・歳入の款・会計など）の内訳の表（表示専用）。その箱から右へ出る帯の行き先を、金額の大きい順に並べる。
 * 押すとその箱を選ぶ（款 → 項 → 目と下りていける）。
 * 設計: docs/local-gov/tasks/20261128_1130_選んだ箱の内訳の表と前年度比の設計.md
 */
import { useEffect, useRef } from 'react';
import type { Breakdown } from '@/app/lib/local-gov/breakdown';
import { DELTA_COLUMNS, shortDelta, type BoxDelta } from '@/app/lib/local-gov/supplement-diff';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';
import type { Yen } from '@/types/local-gov';
import { PREVIOUS_NOTE, PreviousLine, RankedList, deltaColor } from './RankedList';

interface Props {
  breakdown: Breakdown;
  /** 行ごとの補正の増減（補正後の見方） */
  deltas?: Map<string, BoxDelta>;
  /** 選んだ箱の補正の増減（補正後の見方。図の箱のラベルと同じもの） */
  parentDelta?: BoxDelta;
  /** 箱ごとの前年度の額（当初予算の見方だけ） */
  previous?: Map<string, Yen>;
  /** 選んだ箱の前年度に入っている、前年度にだけあった款（previousOnlyKanIn。本年度の行がないので表の行には出ない） */
  previousOnly?: { account: string; kan: string; previous: Yen }[];
  onSelect: (id: string) => void;
}

export function BoxBreakdown({ breakdown: b, deltas, parentDelta, previous, previousOnly = [], onSelect }: Props) {
  // 行を押して次の箱の内訳に替わったら、見出しにフォーカスを移す（キーボード・読み上げで使う人が場所を見失わないように）
  const headingRef = useRef<HTMLHeadingElement>(null);
  const pendingFocus = useRef(false);
  useEffect(() => {
    if (!pendingFocus.current) return;
    pendingFocus.current = false;
    headingRef.current?.focus({ preventScroll: true });
  }, [b.parent.id]);

  // 前年度の額は、箱の全部が選んだ箱に入る行だけ（財源 → 款のように一部だけの行は、款全体の前年度と比べることになる）
  const items = b.items.map(it => ({
    ...it,
    delta: deltas?.get(it.id),
    previous: previous && it.whole ? previous.get(it.id) : undefined,
  }));
  // 計は行の合計（右へ出る帯の合計）。会計の箱は入り（歳入）と出（歳出）が合わないデータもあるので、表の行と合う方を出す
  const total = b.items.reduce((s, it) => s + it.value, 0);
  const parentPrevious = previous?.get(b.parent.id);
  const someShown = items.some(it => it.previous !== undefined);
  // 一部だけ入るために前年度比・補正の増減を外した行があるか（その断り書きを出す）
  const partialRows = b.items.filter(it => !it.whole);
  const prevHidden = !!previous && partialRows.some(it => previous.has(it.id));
  const deltaHidden = !!deltas && DELTA_COLUMNS.has(b.childCol) && partialRows.length > 0;
  const hidden = [prevHidden && '前年度比', deltaHidden && '当初からの増減'].filter(Boolean).join('・');
  // 財源の箱は前年度の額がない（目ごとの財源内訳は本年度だけ）
  const fundingNoPrevious = !!previous && b.parent.id.startsWith('funding:');
  // 前年度にだけあった款は本年度の行がないので、表の行の前年度を足しても計の前年度にならない。その分を書く
  const onlyNote =
    parentPrevious !== undefined && previousOnly.length > 0
      ? `前年度には、本年度はない${previousOnly.map(k => `${k.account}の${k.kan}（${formatBudgetFromYen(k.previous)}）`).join('・')}を含みます。`
      : '';
  const pd = parentDelta && (parentDelta.added ? '新' : shortDelta(parentDelta.delta));
  return (
    <div className="p-3">
      <h2 ref={headingRef} tabIndex={-1} className="text-sm font-bold focus:outline-none">
        {b.parent.name}の内訳（{b.childLabel}ごと）
      </h2>
      <p className="mb-2 mt-0.5 flex flex-wrap items-baseline gap-x-2 text-sm tabular-nums">
        <span>
          計 {formatBudgetFromYen(total)}
          {pd && (
            <span className={`ml-1 text-xs font-bold ${parentDelta?.added ? 'text-amber-700' : deltaColor(parentDelta?.delta ?? 0)}`}>{pd}</span>
          )}
        </span>
        {parentPrevious !== undefined && <PreviousLine value={total} previous={parentPrevious} />}
      </p>
      <p className="mb-2 text-[11px] text-mirai-text-muted">
        名前を押すと、その{b.childLabel}を選びます。{(someShown || parentPrevious !== undefined) && PREVIOUS_NOTE}
        {fundingNoPrevious && '財源ごとの前年度の額は資料にないため、計には前年度比を出していません。'}
        {hidden && `${b.parent.name}から一部だけが入る行は、その分の額なので${hidden}を付けていません。`}
        {onlyNote}
      </p>
      <RankedList
        items={items}
        onSelect={id => {
          pendingFocus.current = true;
          onSelect(id);
        }}
      />
    </div>
  );
}
