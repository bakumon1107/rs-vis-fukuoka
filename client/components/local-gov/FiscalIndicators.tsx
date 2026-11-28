'use client';

/**
 * 財政の指標（財政力指数・経常収支比率・実質公債費比率・将来負担比率）の推移を、指標ごとの小さな線グラフで並べる（表示専用）。
 * 設計: docs/local-gov/tasks/20261128_1646_基金と財政の指標のタブの設計.md 4章
 * 縦軸は指標ごとに1本（2つの量を1つのグラフに重ねない）。比べる線は47都道府県の中央値（灰色の点線）
 */
import { useState } from 'react';
import type { FiscalIndicator, LocalFiscalFile } from '@/types/local-gov';
import { formatIndicator, latestChange } from '@/app/lib/local-gov/fiscal';
import { useElementWidth } from '@/client/hooks/useElementWidth';
import { eraLabel } from '@/client/components/local-gov/FundsTrendChart';

const LINE = '#7a6cc0';
const MEDIAN = '#9ca3af';
const H = 150;
const PAD = { l: 44, r: 52, t: 12, b: 24 };

/** 画面の一言の説明（設計 4.1） */
const ABOUT: Record<FiscalIndicator['key'], string> = {
  fiscal_capacity: '標準的な行政に要るお金のうち、県の税などでまかなえる割合（3年平均）。1 に近いほど自前でまかなえます',
  current_balance:
    '毎年入るお金のうち、人件費・社会保障・借金の返済など毎年決まって出ていくお金に回る割合。高いほど自由に使える分が少なくなります',
  debt_service: '収入に対する借金の返済の重さ（3年平均）。25% を超えると早期健全化の対象になります',
  future_burden: '収入に対する、県債の残高など将来払う負担の重さ。400% を超えると早期健全化の対象になります',
};

const DIRECTION_LABEL = { better: '前の年度より良くなった', worse: '前の年度より悪くなった', same: '前の年度と同じ' } as const;

function MiniChart({ ind }: { ind: FiscalIndicator }) {
  const { ref, width } = useElementWidth<HTMLDivElement>(320);
  const [active, setActive] = useState<number | null>(null);
  const vs = [...ind.values].sort((a, b) => a.year - b.year);
  if (vs.length === 0) return null;
  const W = Math.max(260, width);
  const all = vs.flatMap(v => [v.value, v.median]);
  const lo = Math.min(...all);
  const hi = Math.max(...all);
  // 上下に少し余白（値の幅の 15%）。0 からにはしない（推移を読むため。目盛りに値を書く）
  const pad = (hi - lo) * 0.15 || Math.abs(hi) * 0.05 || 1;
  const y0 = lo - pad;
  const y1 = hi + pad;
  const x = (i: number) => PAD.l + ((W - PAD.l - PAD.r) * i) / Math.max(1, vs.length - 1);
  const y = (v: number) => PAD.t + (H - PAD.t - PAD.b) * (1 - (v - y0) / (y1 - y0));
  const line = (get: (v: (typeof vs)[number]) => number) => vs.map((v, i) => `${x(i)},${y(get(v))}`).join(' ');
  const last = vs.length - 1;
  const tip = active === null ? null : vs[active];
  const fmt = (v: number) => formatIndicator(ind, v);
  return (
    <div ref={ref} className="relative w-full">
      <svg width={W} height={H} role="img" aria-label={`${ind.label}の推移（福岡県と47都道府県の中央値）`} className="block">
        {[lo, hi].map((t, i) => (
          <g key={i}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} className="stroke-mirai-border" strokeWidth={1} />
            <text x={PAD.l - 6} y={y(t) + 4} textAnchor="end" className="fill-mirai-text-muted text-[11px]">
              {fmt(t)}
            </text>
          </g>
        ))}
        <polyline points={line(v => v.median)} fill="none" stroke={MEDIAN} strokeWidth={2} strokeDasharray="4 3" />
        <polyline points={line(v => v.value)} fill="none" stroke={LINE} strokeWidth={2} strokeLinejoin="round" />
        {vs.map((v, i) => (
          <circle key={v.year} cx={x(i)} cy={y(v.value)} r={active === i ? 5 : 3} fill={LINE} />
        ))}
        {/* 線の端に最新の値 */}
        <text x={x(last) + 6} y={y(vs[last].value) + 4} className="fill-mirai-text text-[11px] font-bold">
          {fmt(vs[last].value)}
        </text>
        <text x={x(last) + 6} y={y(vs[last].median) + 4} className="fill-mirai-text-muted text-[11px]">
          {fmt(vs[last].median)}
        </text>
        {[0, last].map(i => (
          <text key={i} x={x(i)} y={H - 6} textAnchor={i === 0 ? 'start' : 'end'} className="fill-mirai-text-muted text-[11px]">
            {eraLabel(vs[i].year)}
          </text>
        ))}
        {vs.map((v, i) => (
          <rect
            key={`hit-${v.year}`}
            x={x(i) - (W - PAD.l - PAD.r) / Math.max(1, vs.length - 1) / 2}
            y={PAD.t}
            width={(W - PAD.l - PAD.r) / Math.max(1, vs.length - 1)}
            height={H - PAD.t - PAD.b}
            fill="transparent"
            tabIndex={0}
            role="button"
            aria-label={`${eraLabel(v.year)} ${ind.label} ${fmt(v.value)}（中央値 ${fmt(v.median)}・${v.of}団体中 ${v.rank}位）`}
            onMouseEnter={() => setActive(i)}
            onMouseLeave={() => setActive(null)}
            onFocus={() => setActive(i)}
            onBlur={() => setActive(null)}
            onClick={() => setActive(active === i ? null : i)}
            className="cursor-pointer outline-none"
          />
        ))}
      </svg>
      {tip && active !== null && (
        <div
          className="pointer-events-none absolute z-10 w-44 rounded-lg border border-mirai-border bg-card p-2 text-xs shadow-soft"
          // 点と反対の側に出す（点の近くの線を隠さないように）
          style={{ left: x(active) > W / 2 ? PAD.l : W - PAD.r - 176, top: 0 }}
          role="status"
        >
          <div className="font-bold">
            {eraLabel(tip.year)}年度 {fmt(tip.value)}
          </div>
          <div className="text-mirai-text-muted">
            中央値 {fmt(tip.median)}・{tip.of}団体中 {tip.rank}位
          </div>
        </div>
      )}
    </div>
  );
}

export function FiscalIndicators({ file }: { file: LocalFiscalFile }) {
  const years = [...new Set(file.indicators.flatMap(i => i.values.map(v => v.year)))].sort((a, b) => a - b);
  return (
    <div className="space-y-3">
      {/* 凡例（系列は2本。どのカードも同じ） */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-mirai-text-muted">
        <span className="inline-flex items-center gap-1">
          <svg width="18" height="8" aria-hidden="true">
            <line x1="0" y1="4" x2="18" y2="4" stroke={LINE} strokeWidth="2" />
          </svg>
          福岡県
        </span>
        <span className="inline-flex items-center gap-1">
          <svg width="18" height="8" aria-hidden="true">
            <line x1="0" y1="4" x2="18" y2="4" stroke={MEDIAN} strokeWidth="2" strokeDasharray="4 3" />
          </svg>
          47都道府県の中央値
        </span>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {file.indicators.map(ind => {
          const c = latestChange(ind);
          return (
            <section key={ind.key} className="space-y-1 rounded-2xl bg-card p-3 shadow-soft">
              <div className="flex flex-wrap items-baseline justify-between gap-x-2">
                <h3 className="text-sm font-bold">{ind.label}</h3>
                {ind.threshold !== null && (
                  <span className="text-[11px] text-mirai-text-muted">早期健全化基準 {formatIndicator(ind, ind.threshold)}</span>
                )}
              </div>
              {c && (
                <p className="text-sm">
                  <b className="text-lg">{formatIndicator(ind, c.latest.value)}</b>
                  <span className="ml-1 text-xs text-mirai-text-muted">
                    （{eraLabel(c.latest.year)}年度。47都道府県中 {c.latest.rank}位・{ind.good === 'high' ? '高い' : '低い'}方から
                    {c.latest.of < 47 ? `。値のある ${c.latest.of} 団体で数えた` : ''}
                    {c.direction ? `。${DIRECTION_LABEL[c.direction]}` : ''}）
                  </span>
                </p>
              )}
              <p className="text-xs text-mirai-text-muted">{ABOUT[ind.key]}</p>
              <MiniChart ind={ind} />
            </section>
          );
        })}
      </div>
      <details className="text-xs">
        <summary className="cursor-pointer text-primary-accent">数字の表で見る</summary>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[480px]">
            <thead>
              <tr className="text-mirai-text-muted">
                <th className="py-1 text-left font-normal">年度</th>
                {file.indicators.map(ind => (
                  <th key={ind.key} className="py-1 text-right font-normal">
                    {ind.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {years.map(yr => (
                <tr key={yr} className="border-t border-mirai-border">
                  <td className="py-1">{eraLabel(yr)}</td>
                  {file.indicators.map(ind => {
                    const v = ind.values.find(x => x.year === yr);
                    return (
                      <td key={ind.key} className="py-1 text-right">
                        {v ? `${formatIndicator(ind, v.value)}（${v.rank}位）` : '—'}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
