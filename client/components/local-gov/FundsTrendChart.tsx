'use client';

/**
 * 基金の年度末現在高の推移（表示専用）。年度ごとに、財政調整基金・減債基金・その他の基金を積み上げた棒。
 * 設計: docs/local-gov/tasks/20261120_1200_地方版の基金の設計.md 4章
 */
import type { FundTotals } from '@/types/local-gov';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';

const SERIES = [
  { key: 'debt_reduction', label: '減債基金（県債の返済の備え）', className: 'fill-teal-700' },
  { key: 'fiscal_adjustment', label: '財政調整基金（年度間の財源の調整）', className: 'fill-amber-500' },
  { key: 'other', label: 'その他の基金（特定の目的）', className: 'fill-slate-400' },
] as const;

/** 年度の短い和暦（2024 → R6、2018 → H30）。基金ごとの推移のグラフ（FundHistoryChart）でも使う */
export function eraLabel(year: number): string {
  return year >= 2019 ? `R${year - 2018}` : `H${year - 1988}`;
}

export function FundsTrendChart({ totals }: { totals: FundTotals[] }) {
  const W = 720;
  const H = 260;
  const PAD = { l: 64, r: 8, t: 12, b: 36 };
  const max = Math.max(...totals.map(t => t.fiscal_adjustment + t.debt_reduction + t.other), 1);
  // 目盛りは 2,000億円ごと（1兆円に届かない額）。最大に合わせて切り上げる
  const step = 200_000_000_000;
  const top = Math.ceil(max / step) * step;
  const y = (v: number) => PAD.t + (H - PAD.t - PAD.b) * (1 - v / top);
  const bw = (W - PAD.l - PAD.r) / totals.length;
  const ticks = Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step);
  return (
    <figure className="space-y-2">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="基金の年度末現在高の推移（年度ごとの積み上げ棒）">
        {ticks.map(t => (
          <g key={t}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} className="stroke-mirai-border" strokeWidth={1} />
            <text x={PAD.l - 6} y={y(t) + 4} textAnchor="end" className="fill-mirai-text-muted text-[11px]">
              {t === 0 ? '0' : formatBudgetFromYen(t).replace('.00', '')}
            </text>
          </g>
        ))}
        {totals.map((t, i) => {
          let acc = 0;
          const x = PAD.l + i * bw + bw * 0.15;
          const total = t.fiscal_adjustment + t.debt_reduction + t.other;
          return (
            <g key={t.year}>
              <title>
                {`${eraLabel(t.year)}年度末 計 ${formatBudgetFromYen(total)}（減債 ${formatBudgetFromYen(t.debt_reduction)}・財政調整 ${formatBudgetFromYen(t.fiscal_adjustment)}・その他 ${formatBudgetFromYen(t.other)}）${t.src === 'ocr' ? '。画像の調書を OCR で読んだ年度' : ''}`}
              </title>
              {SERIES.map(s => {
                const v = t[s.key];
                const y0 = y(acc + v);
                const h = y(acc) - y0;
                acc += v;
                return <rect key={s.key} x={x} y={y0} width={bw * 0.7} height={Math.max(0, h)} className={s.className} />;
              })}
              <text x={x + bw * 0.35} y={H - PAD.b + 14} textAnchor="middle" className="fill-mirai-text-muted text-[11px]">
                {eraLabel(t.year)}
                {t.src === 'ocr' ? '*' : ''}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-mirai-text-muted">
        {SERIES.map(s => (
          <span key={s.key} className="inline-flex items-center gap-1">
            <svg width="10" height="10" aria-hidden="true">
              <rect width="10" height="10" className={s.className} />
            </svg>
            {s.label}
          </span>
        ))}
        <span>年度末（3月31日）の現在高。* は画像の調書を OCR で読んだ年度（前後の年度との一致で確かめた）</span>
      </figcaption>
    </figure>
  );
}
