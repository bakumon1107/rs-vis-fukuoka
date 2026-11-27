'use client';

/**
 * 1つの基金の年度末現在高の推移（表示専用）。基金の表で行を開いたときに出す大きめの棒グラフ。
 * 全体の推移（FundsTrendChart）と同じ見た目にそろえる（目盛り・年度のラベル・OCR の年度の *）。
 * 額は資料の数字そのまま（推計しない）。最初・最後・最大の年度は棒の上に額を出し、ほかの年度は棒を押すと図の上に出す
 * （ツールチップの <title> はスマートフォンで出ないため）。
 */
import { useState } from 'react';
import type { FundYearValue } from '@/types/local-gov';
import { niceStep } from '@/app/lib/local-gov/funds';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';
import { eraLabel } from './FundsTrendChart';

/** 目盛りの額の末尾の 0 を外す（「1.50億円」→「1.5億円」、「2.00億円」→「2億円」） */
function tickLabel(v: number): string {
  if (v === 0) return '0';
  return formatBudgetFromYen(v).replace(/(\.\d*?[1-9])0+(?=\D)/, '$1').replace(/\.0+(?=\D)/, '');
}

export function FundHistoryChart({ name, history }: { name: string; history: FundYearValue[] }) {
  const [picked, setPicked] = useState<number | null>(null);
  const max = Math.max(...history.map(h => h.end), 0);
  // 額のある年度がなければ描かない（全年度 0 の基金で、棒のない図と「1円」の目盛りが出る）
  if (history.length === 0 || max === 0) return null;
  // 幅 560 の図を、スマートフォンでは縮めずに横へずらして見る（縮めると 15 年分の年度のラベルが読めない大きさになる）。
  // 広い画面では 720px までに抑える（広げすぎると文字が大きくなりすぎる）
  const W = 560;
  const H = 210;
  const PAD = { l: 60, r: 8, t: 20, b: 32 };
  const step = niceStep(max);
  const top = Math.max(step, Math.ceil(max / step) * step);
  const y = (v: number) => PAD.t + (H - PAD.t - PAD.b) * (1 - v / top);
  // 棒は年度の位置に置く（配列の順に詰めると、取り込んでいない年度が抜けても続けて見える）
  const first = history[0].year;
  const slots = history[history.length - 1].year - first + 1;
  const bw = (W - PAD.l - PAD.r) / slots;
  const ticks = Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step);
  // 棒の上に額を出す年度: 最初・最後・最大。最大が最初・最後の隣なら額の文字が重なるので出さない（押せば出る）
  const last = history.length - 1;
  const maxIndex = history.findIndex(h => h.end === max);
  const slotOf = (i: number) => history[i].year - first;
  const nearEnd = maxIndex !== 0 && maxIndex !== last && (slotOf(maxIndex) - slotOf(0) <= 1 || slotOf(last) - slotOf(maxIndex) <= 1);
  const labeled = new Set([0, last, ...(nearEnd ? [] : [maxIndex])]);
  const pickedValue = picked !== null ? history[picked] : null;
  return (
    <figure className="space-y-1">
      <p className="min-h-4 text-[11px] text-mirai-text" aria-live="polite">
        {pickedValue
          ? `${eraLabel(pickedValue.year)}年度末 ${formatBudgetFromYen(pickedValue.end)}${pickedValue.src === 'ocr' ? '（画像の調書を OCR で読んだ年度）' : ''}`
          : ''}
      </p>
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full min-w-[560px] max-w-[720px]" role="img" aria-label={`${name}の年度末現在高の推移（年度ごとの棒）`}>
          {ticks.map(t => (
            <g key={t}>
              <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} className="stroke-mirai-border" strokeWidth={1} />
              <text x={PAD.l - 6} y={y(t) + 4} textAnchor="end" className="fill-mirai-text-muted text-[11px]">
                {tickLabel(t)}
              </text>
            </g>
          ))}
          {history.map((h, i) => {
            const x = PAD.l + slotOf(i) * bw + bw * 0.15;
            const y0 = y(h.end);
            const isPicked = picked === i;
            return (
              <g key={h.year} onClick={() => setPicked(isPicked ? null : i)} className="cursor-pointer">
                <title>{`${eraLabel(h.year)}年度末 ${formatBudgetFromYen(h.end)}${h.src === 'ocr' ? '（画像の調書を OCR で読んだ年度）' : ''}`}</title>
                {/* 押しやすいよう、棒の列全体を押せる範囲にする（透明） */}
                <rect x={PAD.l + slotOf(i) * bw} y={PAD.t} width={bw} height={H - PAD.t - PAD.b} fill="transparent" />
                <rect x={x} y={y0} width={bw * 0.7} height={Math.max(0, y(0) - y0)} className="fill-primary-accent" opacity={isPicked ? 1 : 0.8} />
                {labeled.has(i) && h.end > 0 && (
                  // 端の年度は棒の端にそろえる（真ん中にそろえると、最初は目盛りの文字に重なり、最後は図の右端で切れる）
                  <text
                    x={i === 0 ? x : i === last ? x + bw * 0.7 : x + bw * 0.35}
                    y={y0 - 4}
                    textAnchor={i === 0 ? 'start' : i === last ? 'end' : 'middle'}
                    className="fill-mirai-text text-[11px]"
                  >
                    {formatBudgetFromYen(h.end)}
                  </text>
                )}
                <text x={x + bw * 0.35} y={H - PAD.b + 14} textAnchor="middle" className={`text-[11px] ${isPicked ? 'fill-mirai-text font-bold' : 'fill-mirai-text-muted'}`}>
                  {eraLabel(h.year)}
                  {h.src === 'ocr' ? '*' : ''}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <figcaption className="text-[11px] text-mirai-text-muted">
        年度末（3月31日）の現在高。棒を押すとその年度の額を上に出します。* は画像の調書を OCR で読んだ年度
      </figcaption>
    </figure>
  );
}
