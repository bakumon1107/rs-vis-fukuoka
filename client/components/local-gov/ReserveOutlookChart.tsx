'use client';

/**
 * 三基金（財源調整分）の年度末残高の推移と、県の公式の見込み（点線）・財政改革プランの目標の帯（表示専用）。
 * 設計: docs/local-gov/tasks/20261128_1646_基金と財政の指標のタブの設計.md 2.2
 * 縦軸は億円の1本だけ。実績は実線と点、見込みは点線と白抜きの点。点を指す・押す・フォーカスすると内訳を出す
 */
import { useState } from 'react';
import type { LocalFiscalFile } from '@/types/local-gov';
import { niceScale, reservePoints } from '@/app/lib/local-gov/fiscal';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';
import { useElementWidth } from '@/client/hooks/useElementWidth';
import { tipStyle } from '@/client/lib/local-gov-tooltip';
import { eraLabel } from '@/client/components/local-gov/FundsTrendChart';

/** 地方版の主色（ラベンダー。app/lib/local-gov/site.ts と同じ） */
const LINE = '#7a6cc0';
const H = 260;
const PAD = { l: 56, r: 20, t: 16, b: 40 };
/** ツールチップの幅（px）。点と反対の側に出す（点の近くの線を隠さないように） */
const TIP_W = 224;

export function ReserveOutlookChart({ file }: { file: LocalFiscalFile }) {
  const { ref, width } = useElementWidth<HTMLDivElement>(640);
  const [active, setActive] = useState<number | null>(null);
  const pts = reservePoints(file);
  const target = file.reserve.target;
  if (pts.length === 0) return null;
  // 枠の幅で描く（下限を付けると、幅 320px の画面で枠からはみ出して横スクロールが出る）
  const W = width;
  const { top, step } = niceScale(Math.max(...pts.map(p => p.total), target?.max ?? 0));
  const x = (i: number) => PAD.l + ((W - PAD.l - PAD.r) * (i + 0.5)) / pts.length;
  const y = (v: number) => PAD.t + (H - PAD.t - PAD.b) * (1 - v / top);
  const ticks = Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step);
  const actual = pts.filter(p => p.kind === 'actual');
  const lastActual = actual.length - 1;
  const outlookIdx = pts.findIndex(p => p.kind === 'outlook');
  // 年度のラベル: 狭い画面は1つおき（最後の実績と見込みは必ず出す）
  const every = W < 520 ? 2 : 1;
  const showYear = (i: number) => i >= lastActual || (lastActual - i) % every === 0;
  const oku = (v: number) => formatBudgetFromYen(v).replace('.00', '');
  const tip = active === null ? null : pts[active];

  return (
    <figure className="space-y-2">
      {/* 測る枠は中身で広がらないようにする（広がると、その幅を測って図を描き、また広がる） */}
      <div ref={ref} className="relative w-full min-w-0 overflow-hidden">
        {/* role="img" だと中の点（ボタン）が支援技術から隠れるので group にする */}
        <svg width={W} height={H} role="group" aria-label={`${file.reserve.label}の年度末残高の推移と見込み`} className="block">
          {ticks.map(t => (
            <g key={t}>
              <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} className="stroke-mirai-border" strokeWidth={1} />
              <text x={PAD.l - 6} y={y(t) + 4} textAnchor="end" className="fill-mirai-text-muted text-[11px]">
                {t === 0 ? '0' : oku(t)}
              </text>
            </g>
          ))}
          {/* 目標の帯（財政改革プラン。下限〜上限） */}
          {target && (
            <g>
              <rect x={PAD.l} y={y(target.max)} width={W - PAD.l - PAD.r} height={y(target.min) - y(target.max)} fill={LINE} opacity={0.12} />
              <text x={PAD.l + 6} y={y(target.max) + 13} className="fill-mirai-text-muted text-[11px]">
                目標（{eraLabel(target.year)}年度末 {oku(target.min)}〜{oku(target.max)}）
              </text>
            </g>
          )}
          {/* 実績の線 */}
          <polyline
            points={actual.map((p, i) => `${x(i)},${y(p.total)}`).join(' ')}
            fill="none"
            stroke={LINE}
            strokeWidth={2}
            strokeLinejoin="round"
          />
          {/* 見込み: 最後の実績から点線 */}
          {outlookIdx >= 0 && (
            <line
              x1={x(lastActual)}
              y1={y(actual[lastActual].total)}
              x2={x(outlookIdx)}
              y2={y(pts[outlookIdx].total)}
              stroke={LINE}
              strokeWidth={2}
              strokeDasharray="5 4"
            />
          )}
          {pts.map((p, i) => (
            <g key={p.year}>
              <circle
                cx={x(i)}
                cy={y(p.total)}
                r={active === i ? 6 : 4.5}
                fill={p.kind === 'outlook' ? 'var(--card, #fff)' : LINE}
                stroke={LINE}
                strokeWidth={2}
              />
              {showYear(i) && (
                <text x={x(i)} y={H - PAD.b + 16} textAnchor="middle" className="fill-mirai-text-muted text-[11px]">
                  {eraLabel(p.year)}
                  {/* 見込みは2行目に（隣の年度のラベルと詰まらないように） */}
                  {p.kind === 'outlook' && (
                    <tspan x={x(i)} dy={12}>
                      見込
                    </tspan>
                  )}
                </text>
              )}
            </g>
          ))}
          {/* 直接のラベル: 最後の実績と見込み */}
          <text x={x(lastActual)} y={y(actual[lastActual].total) - 10} textAnchor="middle" className="fill-mirai-text text-[11px] font-bold">
            {oku(actual[lastActual].total)}
          </text>
          {outlookIdx >= 0 && (
            <text x={x(outlookIdx)} y={y(pts[outlookIdx].total) + 20} textAnchor="end" className="fill-mirai-text text-[11px] font-bold">
              見込み {oku(pts[outlookIdx].total)}
            </text>
          )}
          {/* 当たり判定（点より広い縦の帯）。指す・押す・フォーカスで内訳 */}
          {pts.map((p, i) => (
            <rect
              key={`hit-${p.year}`}
              x={x(i) - (W - PAD.l - PAD.r) / pts.length / 2}
              y={PAD.t}
              width={(W - PAD.l - PAD.r) / pts.length}
              height={H - PAD.t - PAD.b}
              fill="transparent"
              tabIndex={0}
              role="button"
              aria-label={`${eraLabel(p.year)}年度末${p.kind === 'outlook' ? 'の見込み' : ''} ${oku(p.total)}`}
              onMouseEnter={() => setActive(i)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(i)}
              onBlur={() => setActive(null)}
              // 押したら出す（指したときに出た内訳を、押して消さない）。消すのは指を離す・フォーカスを外すとき
              onClick={() => setActive(i)}
              className="cursor-pointer outline-none"
            />
          ))}
        </svg>
        {tip && active !== null && (
          <div
            className="pointer-events-none absolute z-10 rounded-lg border border-mirai-border bg-card p-2 text-xs shadow-soft"
            style={tipStyle(x(active), W, Math.min(TIP_W, W), PAD.l + 4, PAD.r, 4)}
            role="status"
          >
            <div className="font-bold">
              {eraLabel(tip.year)}年度末{tip.kind === 'outlook' ? 'の見込み' : ''} {oku(tip.total)}
            </div>
            {tip.kind === 'actual' && tip.parts ? (
              <ul className="mt-1 space-y-0.5 text-mirai-text-muted">
                {file.reserve.parts.map((name, j) => (
                  <li key={name} className="flex justify-between gap-2">
                    <span>{name}</span>
                    <span>{oku(tip.parts![j])}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-mirai-text-muted">{file.reserve.outlook?.as_of}の県の見込み。補正予算や決算で変わります</p>
            )}
          </div>
        )}
      </div>
      <figcaption className="text-xs text-mirai-text-muted">
        実線が年度末の残高（実績）、点線が県の見込み、帯が目標。点を指す・押すと内訳を出します
      </figcaption>
      <details className="text-xs">
        <summary className="cursor-pointer text-primary-accent">数字の表で見る</summary>
        <table className="mt-2 w-full max-w-xl">
          <thead>
            <tr className="text-mirai-text-muted">
              <th className="py-1 text-left font-normal">年度末</th>
              <th className="py-1 text-right font-normal">計</th>
              {file.reserve.parts.map(n => (
                <th key={n} className="hidden py-1 text-right font-normal sm:table-cell">
                  {n}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pts.map(p => (
              <tr key={p.year} className="border-t border-mirai-border">
                <td className="py-1">
                  {eraLabel(p.year)}
                  {p.kind === 'outlook' ? '（見込み）' : ''}
                </td>
                <td className="py-1 text-right">{oku(p.total)}</td>
                {file.reserve.parts.map((n, j) => (
                  <td key={n} className="hidden py-1 text-right sm:table-cell">
                    {p.parts ? oku(p.parts[j]) : '—'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
