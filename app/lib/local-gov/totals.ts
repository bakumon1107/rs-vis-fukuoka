/**
 * 全会計の純計と、人件費の割合（純粋関数。HTTP・React なし）。
 * 設計: docs/local-gov/tasks/20261121_0100_公開前のサンキー図の足しと公営企業会計の設計.md 2章・3章
 */
import type { LocalBudgetFile, MokuRow, Yen } from '@/types/local-gov';
import type { LocalGraphFilter } from './graph';

export interface NetTotal {
  /** 全会計（一般会計・特別会計。公営企業会計は除く）の歳出の総計 */
  gross: Yen;
  /** 会計間の繰入れ（歳入の目の transfer の印。受け手の額） */
  transfers: Yen;
  /** 繰入れの目の数（額が 0 の目は数えない。R8 当初で 0 円の繰入れの目が1つある） */
  count: number;
  net: Yen;
}

/**
 * 全会計の純計 = 総計 − 会計間の繰入れ（設計 2章）。繰入れの印がないファイル（決算）は null。
 * 公営企業会計は全会計の見方に入れないので、総計にも繰入れにも入れない（公営企業会計からの繰入れの印は付けていない）
 */
export function netTotal(file: LocalBudgetFile): NetTotal | null {
  const enterprise = new Set(file.accounts.filter(a => a.kind === 'enterprise').map(a => a.id));
  const rows = file.rows.filter(r => !enterprise.has(r.account));
  const marked = rows.filter(r => r.side === 'revenue' && r.transfer);
  if (marked.length === 0) return null;
  const gross = rows.filter(r => r.side === 'expense').reduce((s, r) => s + (r.amount.v ?? 0), 0);
  const transfers = marked.reduce((s, r) => s + (r.amount.v ?? 0), 0);
  return { gross, transfers, count: marked.filter(r => (r.amount.v ?? 0) !== 0).length, net: gross - transfers };
}

/** 公営企業会計の支出の合計（第3条 = 収益的支出・第4条 = 資本的支出。設計 4.4 の見出し）。公営企業会計がなければ null */
export function enterpriseExpense(file: LocalBudgetFile): { accounts: number; revenueSection: Yen; capitalSection: Yen } | null {
  const enterprise = new Set(file.accounts.filter(a => a.kind === 'enterprise').map(a => a.id));
  if (enterprise.size === 0) return null;
  const sum = (s: '収益的' | '資本的') => file.rows
    .filter(r => enterprise.has(r.account) && r.side === 'expense' && r.enterprise_section === s)
    .reduce((t, r) => t + (r.amount.v ?? 0), 0);
  return { accounts: enterprise.size, revenueSection: sum('収益的'), capitalSection: sum('資本的') };
}

/** 割合の表示（小数1桁の %）。0 より大きく 0.05% 未満は「0.1%未満」（0.0% と出すと 0 に見える） */
export function formatRatio(ratio: number): string {
  if (ratio > 0 && ratio < 0.0005) return '0.1%未満';
  return `${(ratio * 100).toFixed(1)}%`;
}

/** 人件費に数える節（節 1〜4。番号は年度で変わりうるので名前で見る） */
export const PERSONNEL_SETSU = ['報酬', '給料', '職員手当等', '共済費'] as const;

export interface PersonnelShare {
  /** 選んだ範囲の目の額の合計 */
  total: Yen;
  /** そのうち人件費の節の合計 */
  personnel: Yen;
  /** 割合（0〜1） */
  ratio: number;
}

function matchesFilter(r: MokuRow, f: LocalGraphFilter): boolean {
  return (f.account === undefined || r.account === f.account)
    && (f.side === undefined || r.side === f.side)
    && (f.kan === undefined || r.kan.no === f.kan)
    && (f.kou === undefined || r.kou.no === f.kou)
    && (f.moku === undefined || r.moku.no === f.moku)
    && (f.section === undefined || r.enterprise_section === f.section);
}

/**
 * 選んだ款・項・目（の絞り込み）の歳出のうち、人件費の節の額と割合（設計 3章）。節の額を足すだけで推計しない。
 * 出さないとき（null）: 財源・部局で選んだとき（節は財源・部局ごとに分かれていない）、歳出の目がないとき、
 * 節のない目を含むとき（補正で節がなくなった目など。割合が実際より小さく見えるので出さない。予備費の目は節を持たないので人件費 0 として数える）
 */
export function personnelShare(file: LocalBudgetFile, filter: LocalGraphFilter): PersonnelShare | null {
  if (filter.funding !== undefined || filter.department !== undefined) return null;
  const rows = file.rows.filter(r => r.side === 'expense' && matchesFilter(r, filter) && (r.amount.v ?? 0) !== 0);
  // 予備費の目は節を持たない（使い道が決まっていない）ので、人件費 0 として数える。ほかの節のない目があれば出さない
  const noSetsu = (r: MokuRow) => (!r.setsu || r.setsu.length === 0) && r.moku.name !== '予備費';
  if (rows.length === 0 || rows.some(noSetsu)) return null;
  const names = new Set<string>(PERSONNEL_SETSU);
  const total = rows.reduce((s, r) => s + (r.amount.v ?? 0), 0);
  const personnel = rows.reduce(
    (s, r) => s + (r.setsu ?? []).filter(x => names.has(x.name)).reduce((t, x) => t + (x.amount.v ?? 0), 0), 0);
  if (total <= 0) return null;
  return { total, personnel, ratio: personnel / total };
}
