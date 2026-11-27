'use client';

/**
 * 1つの基金の年度末現在高の推移（表示専用）。基金の表で行を開いたときに出す大きめの棒グラフ。
 * 全体の推移（FundsTrendChart）と同じ見た目にそろえる（目盛り・年度のラベル・OCR の年度の *）。
 * 額は資料の数字そのまま（推計しない）。各年度の額は棒のツールチップ、最初と最後と最大の年度は棒の上に出す。
 */
import type { FundYearValue } from '@/types/local-gov';
import { niceStep } from '@/app/lib/local-gov/funds';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';
import { eraLabel } from './FundsTrendChart';

export function FundHistoryChart({ name, history }: { name: string; history: FundYearValue[] }) {
  if (history.length === 0) return null;
  // 幅 560 の図を、スマートフォンでは縮めずに横へずらして見る（縮めると 15 年分の年度のラベルが読めない大きさになる）。
  // 広い画面では 720px までに抑える（広げすぎると文字が大きくなりすぎる）
  const W = 560;
  const H = 210;
  const PAD = { l: 60, r: 8, t: 20, b: 32 };
  const max = Math.max(...history.map(h => h.end), 0);
  const step = niceStep(max);
  const top = Math.max(step, Math.ceil(max / step) * step);
  const y = (v: number) => PAD.t + (H - PAD.t - PAD.b) * (1 - v / top);
  const bw = (W - PAD.l - PAD.r) / history.length;
  const ticks = Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step);
  // 棒の上に額を出す年度（全部に出すと重なる）: 最初・最後・最大
  const maxIndex = history.findIndex(h => h.end === max);
  const labeled = new Set([0, history.length - 1, maxIndex]);
  return (
    <figure className="space-y-1">
      <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full min-w-[560px] max-w-[720px]" role="img" aria-label={`${name}の年度末現在高の推移（年度ごとの棒）`}>
        {ticks.map(t => (
          <g key={t}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} className="stroke-mirai-border" strokeWidth={1} />
            <text x={PAD.l - 6} y={y(t) + 4} textAnchor="end" className="fill-mirai-text-muted text-[11px]">
              {t === 0 ? '0' : formatBudgetFromYen(t).replace('.00', '')}
            </text>
          </g>
        ))}
        {history.map((h, i) => {
          const x = PAD.l + i * bw + bw * 0.15;
          const y0 = y(h.end);
          return (
            <g key={h.year}>
              <title>{`${eraLabel(h.year)}年度末 ${formatBudgetFromYen(h.end)}${h.src === 'ocr' ? '（画像の調書を OCR で読んだ年度）' : ''}`}</title>
              <rect x={x} y={y0} width={bw * 0.7} height={Math.max(0, y(0) - y0)} className="fill-primary-accent" opacity={0.8} />
              {labeled.has(i) && h.end > 0 && (
                // 端の年度は棒の端にそろえる（真ん中にそろえると、最初は目盛りの文字に重なり、最後は図の右端で切れる）
                <text
                  x={i === 0 ? x : i === history.length - 1 ? x + bw * 0.7 : x + bw * 0.35}
                  y={y0 - 4}
                  textAnchor={i === 0 ? 'start' : i === history.length - 1 ? 'end' : 'middle'}
                  className="fill-mirai-text text-[11px]"
                >
                  {formatBudgetFromYen(h.end)}
                </text>
              )}
              <text x={x + bw * 0.35} y={H - PAD.b + 14} textAnchor="middle" className="fill-mirai-text-muted text-[11px]">
                {eraLabel(h.year)}
                {h.src === 'ocr' ? '*' : ''}
              </text>
            </g>
          );
        })}
      </svg>
      </div>
      <figcaption className="text-[11px] text-mirai-text-muted">
        年度末（3月31日）の現在高。棒に触れると各年度の額。* は画像の調書を OCR で読んだ年度
      </figcaption>
    </figure>
  );
}
