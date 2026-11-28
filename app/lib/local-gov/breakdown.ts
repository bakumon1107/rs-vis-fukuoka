/**
 * 選んだ箱の内訳の表（その箱から右へ出る帯の行き先ごとの額）と、箱ごとの前年度の額。純粋関数（HTTP・React なし）。
 * 設計: docs/local-gov/tasks/20261128_1130_選んだ箱の内訳の表と前年度比の設計.md
 */
import type { LocalBudgetFile, Yen } from '@/types/local-gov';
import { columnsOf, rowBoxIds, type LocalGraphView } from './graph';
import { fullGraph } from './graph-view';
import { DELTA_COLUMNS, type BoxDelta } from './supplement-diff';

export interface BreakdownItem {
  id: string;
  name: string;
  /** 選んだ箱からこの箱へ流れる額（図の帯の額） */
  value: Yen;
  /** 箱の名前が読み取りだけのもの（図の ※ と同じ） */
  ocr: boolean;
  /**
   * この箱の全部が選んだ箱に入っているか（帯の額 = 箱の額。款 → 項、項 → 目、会計 → 款）。
   * 財源 → 款・歳入の款 → 会計のように一部だけのときは、箱の前年度比・補正の増減を出さない（箱全体の数字なので帯の額と合わない）
   */
  whole: boolean;
}

export interface Breakdown {
  parent: { id: string; name: string; value: Yen };
  /** 行の列（key）と名前（「項」「目」など） */
  childCol: string;
  childLabel: string;
  /** 額の大きい順 */
  items: BreakdownItem[];
}

/**
 * 選んだ箱の内訳。絞り込まない全体のグラフ（選んだ箱の右の列まで）から、その箱から出る帯を集める。
 * 図を3列に絞ったとき・右端の列を「その他」にまとめたときも、全部の行を出す。右へ帯の出ない箱は null
 */
export function boxBreakdown(file: LocalBudgetFile, view: LocalGraphView, id: string, col: string): Breakdown | null {
  const cols = columnsOf(view, file.basis);
  const idx = cols.findIndex(c => c.key === col);
  if (idx < 0 || idx + 1 >= cols.length) return null;
  const g = fullGraph(file, view, idx + 2);
  const parent = g.nodes.find(n => n.id === id);
  if (!parent) return null;
  const nodeOf = new Map(g.nodes.map(n => [n.id, n]));
  const items: BreakdownItem[] = [];
  for (const e of g.edges) {
    if (e.source !== id) continue;
    const n = nodeOf.get(e.target);
    if (!n || e.value === 0) continue;
    items.push({ id: n.id, name: n.name, value: e.value, ocr: !!n.flags?.includes('name-ocr'), whole: e.value === n.value });
  }
  if (items.length === 0) return null;
  items.sort((a, b) => b.value - a.value);
  const childCol = nodeOf.get(items[0].id)!.col;
  return {
    parent: { id: parent.id, name: parent.name, value: parent.value },
    childCol,
    childLabel: cols.find(c => c.key === childCol)?.label ?? '',
    items,
  };
}

/**
 * 内訳の行ごとの補正の増減（補正後の見方）。図の箱の増減（boxDeltas）と同じ決め方で、箱の全部が選んだ箱に入る行だけ
 * （一部だけの行に箱全体の増減を添えると、帯の額の増減に見えてしまう）
 */
export function breakdownDeltas(b: Breakdown, before: Map<string, Yen>, initialIds: Set<string>): Map<string, BoxDelta> {
  const out = new Map<string, BoxDelta>();
  if (!DELTA_COLUMNS.has(b.childCol)) return out;
  for (const it of b.items) {
    if (!it.whole) continue;
    out.set(it.id, { delta: it.value - (before.get(it.id) ?? 0), added: !initialIds.has(it.id) });
  }
  return out;
}

/**
 * 箱ごとの前年度の額（箱の ID → 額）。説明書の目の「前年度予算額」を、目の入る箱（会計・款・項・目・歳入の款）へ足す。
 * 前年度にだけあった目も足す（款・項の前年度の額に入る）。前年度にだけあった款（previous_only_kan）も足す。
 * 会計の箱は歳出の目だけで足す（歳入も足すと二重になる）。
 * 財源の箱は目ごとの財源内訳に前年度がないので入らない。前年度の額のある目が1つもないデータ（補正・決算・公営企業会計）は空
 */
export function previousBoxValues(file: LocalBudgetFile): Map<string, Yen> {
  const out = new Map<string, Yen>();
  // 公営企業会計の行は全会計の見方の歳入の款・会計に入らない（graph.ts と同じ）ので足さない
  const enterprise = new Set(file.accounts.filter(a => a.kind === 'enterprise').map(a => a.id));
  // 前年度の額が読めなかった目（null）を含む箱は、足りない額で前年度比を出さないよう外す
  const incomplete = new Set<string>();
  for (const r of file.rows) {
    if (enterprise.has(r.account)) continue;
    const p = r.previous?.v;
    for (const id of rowBoxIds(r)) {
      if (id.startsWith('account:') && r.side !== 'expense') continue;
      if (p === null || p === undefined) incomplete.add(id);
      else out.set(id, (out.get(id) ?? 0) + p);
    }
  }
  // 前年度にだけあった款（行がない。総括表にだけ載る）。番号がなく款の箱には入らないので、歳入は歳入の款の箱、歳出は会計の箱に足す
  for (const k of previousOnlyKanBoxes(file)) {
    for (const id of k.boxIds) {
      if (k.previous === null) incomplete.add(id);
      else out.set(id, (out.get(id) ?? 0) + k.previous);
    }
  }
  for (const id of incomplete) out.delete(id);
  return out;
}

/** 前年度にだけあった款と、その前年度の額が入る箱（previousBoxValues と同じ決め方） */
function previousOnlyKanBoxes(file: LocalBudgetFile) {
  const enterprise = new Set(file.accounts.filter(a => a.kind === 'enterprise').map(a => a.id));
  return (file.previous_only_kan ?? [])
    .filter(k => !enterprise.has(k.account))
    .map(k => ({
      account: k.account,
      name: k.kan.name,
      previous: k.previous.v,
      boxIds: k.side === 'revenue' ? [`revenue:${k.kan.name}`] : [`account:${k.account}`],
    }));
}

/**
 * 選んだ箱の前年度に入っている、前年度にだけあった款（会計の名前・款の名前・前年度の額）。内訳の表の断り書き用
 * （本年度の行がないので、表の行の前年度の合計と計の前年度が合わない）
 */
export function previousOnlyKanIn(file: LocalBudgetFile, boxId: string): { account: string; kan: string; previous: Yen }[] {
  const nameOf = new Map(file.accounts.map(a => [a.id, a.name]));
  return previousOnlyKanBoxes(file)
    .filter(k => k.previous !== null && k.boxIds.includes(boxId))
    .map(k => ({ account: nameOf.get(k.account) ?? k.account, kan: k.name, previous: k.previous! }));
}

/** 前年度からの増減の割合（「+5.1%」「△2.3%」）。前年度が 0 なら null */
export function previousRatio(value: Yen, previous: Yen): string | null {
  if (previous === 0) return null;
  const r = ((value - previous) / previous) * 100;
  const s = Math.abs(r).toFixed(1);
  if (s === '0.0') return '±0.0%';
  return `${r > 0 ? '+' : '△'}${s}%`;
}
