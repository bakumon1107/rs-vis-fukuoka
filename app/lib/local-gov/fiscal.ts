/**
 * 三基金の推移と見込み・財政の指標のグラフの組み立て（純粋関数。HTTP・React なし）。
 * 設計: docs/local-gov/tasks/20261128_1646_基金と財政の指標のタブの設計.md 2・4章
 */
import type { FiscalIndicator, LocalFiscalFile } from '@/types/local-gov';

export interface ReservePoint {
  year: number;
  total: number;
  /** 実績（基金積立状況）か、県の公式の見込みか */
  kind: 'actual' | 'outlook';
  /** 実績の内訳（RESERVE の parts の並び）。見込みにはない */
  parts?: number[];
}

/** 三基金のグラフの点: 実績を年度順に、最後に見込み（あれば）。見込みは最後の実績の次の年度のときだけ */
export function reservePoints(file: LocalFiscalFile): ReservePoint[] {
  const hist = [...file.reserve.history].sort((a, b) => a.year - b.year);
  const pts: ReservePoint[] = hist.map(h => ({ year: h.year, total: h.total, kind: 'actual', parts: h.parts }));
  const o = file.reserve.outlook;
  const last = hist.at(-1)?.year;
  if (o && last !== undefined && o.year === last + 1) pts.push({ year: o.year, total: o.total, kind: 'outlook' });
  return pts;
}

/** 目盛りの上端と刻み（1・2・5 × 10^n の刻みで、最大値を含む4〜6本） */
export function niceScale(max: number, ticks = 5): { top: number; step: number } {
  if (!(max > 0)) return { top: 1, step: 1 };
  const raw = max / ticks;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map(m => m * mag).find(s => s >= raw) ?? 10 * mag;
  return { top: Math.ceil(max / step) * step, step };
}

/** 指標の最新の年度と、その前の年度からの向き（良くなった・悪くなった・同じ） */
export function latestChange(ind: FiscalIndicator): {
  latest: FiscalIndicator['values'][number];
  previous?: FiscalIndicator['values'][number];
  direction: 'better' | 'worse' | 'same' | null;
} | null {
  const vs = [...ind.values].sort((a, b) => a.year - b.year);
  const latest = vs.at(-1);
  if (!latest) return null;
  const previous = vs.at(-2);
  if (!previous) return { latest, direction: null };
  const d = latest.value - previous.value;
  // 表示の桁（財政力指数は小数第2位・比率は小数第1位）で同じなら「同じ」
  const eps = ind.unit === '' ? 0.005 : 0.05;
  const direction = Math.abs(d) < eps ? 'same' : (d > 0) === (ind.good === 'high') ? 'better' : 'worse';
  return { latest, previous, direction };
}

/** 指標の値の表示（財政力指数は小数第2位、比率は小数第1位と %） */
export function formatIndicator(ind: Pick<FiscalIndicator, 'unit'>, v: number): string {
  return ind.unit === '' ? v.toFixed(2) : `${v.toFixed(1)}%`;
}
