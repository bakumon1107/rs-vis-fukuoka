/**
 * 補正後予算の、当初予算からの増減（純粋関数。HTTP・React なし）。
 * 設計: docs/local-gov/tasks/20261127_2337_補正後予算の当初からの増減の表示の設計.md
 *
 * - 図の箱の当初の額: 当初のファイルから同じ見方の図を組み立て、箱の ID で対応させる（箱の ID は会計・款・項・目の番号と
 *   目の行の ID で決まるので、当初と補正後で同じ）。当初の図にない箱の当初の額は 0。
 *   「新」は当初予算のファイルのどの行も入らない箱（initialBoxIds。当初 0 円の目は新ではない）
 * - 増減の表: 補正後のファイルの目の行（before = 当初、amount = 補正後、supplements = 回ごとの補正額）を足し上げる
 * - 推計しない（資料の数字の足し算だけ）
 */
import type { LocalBudgetFile, LocalGraph, Side, Yen } from '@/types/local-gov';
import { buildLocalGraph, rowBoxIds, type LocalGraphView } from './graph';

/** 増減を出す列。財源の箱には出さない（財源内訳を足し合わせられない目があり、財源の実際の増減と合わない。2026-11-27 ユーザー決定）。
 * 事項・節は補正で並びが変わることがある（同じ ID が同じものを指すとは限らない）ので出さない */
export const DELTA_COLUMNS = new Set(['revenue', 'account', 'kan', 'kou', 'moku']);

/** 当初の図の箱の額（箱の ID → 額）。補正後の見方の箱と ID で対応させる。当初の図は全部の列まで組み立てる */
export function initialBoxValues(initial: LocalBudgetFile, view: LocalGraphView): Map<string, Yen> {
  const g = buildLocalGraph(initial, { view });
  return new Map(g.nodes.map(n => [n.id, n.value]));
}

export interface BoxDelta {
  /** 補正後 − 当初（円） */
  delta: Yen;
  /** 当初予算のファイルのどの行も入らない箱（補正で新しくできた。initialBoxIds にない） */
  added: boolean;
}

/**
 * 当初予算のファイルにある箱の ID（0 円の行も含む）。図は 0 円の行・箱を作らないので、当初の図の箱だけでは
 * 「当初 0 円だった目」と「補正で新しく設けた目」を見分けられない。行から直接集める（前年度にだけあった目は除く）
 */
export function initialBoxIds(initial: LocalBudgetFile): Set<string> {
  return new Set(initial.rows.filter(r => !r.previous_only).flatMap(rowBoxIds));
}

/**
 * 補正後の図の箱ごとの増減。増減を出さない列・「その他」にまとめた箱は入れない。
 * 「新」（added）は当初予算のファイルのどの行もその箱に入らない箱（補正で新しく設けた目・項・款・歳入の款）。
 * 当初 0 円の目とその上の箱は当初 0 からの増として扱う（新ではない）
 */
export function boxDeltas(graph: LocalGraph, before: Map<string, Yen>, initialIds: Set<string>): Map<string, BoxDelta> {
  const out = new Map<string, BoxDelta>();
  for (const n of graph.nodes) {
    if (!DELTA_COLUMNS.has(n.col) || n.flags?.includes('aggregate')) continue;
    out.set(n.id, { delta: n.value - (before.get(n.id) ?? 0), added: !initialIds.has(n.id) });
  }
  return out;
}

/**
 * 図のラベルに添える短い増減（「+12.3億」「△4.5億」「+850万」）。1万円未満の増減は出さない（''）。
 * 「円」を省き、億は小数1桁（.0 は外す）、兆は小数2桁、万は整数
 */
export function shortDelta(v: Yen): string {
  const a = Math.abs(v);
  if (a < 10_000) return '';
  const sign = v > 0 ? '+' : '△';
  const trim = (s: string) => s.replace(/\.0+$/, '');
  // 丸めてから単位を決める（丸めると次の単位に届く額が「10000万」「10000億」にならないように）
  const oku = Number((a / 1e8).toFixed(1));
  if (oku >= 10000) return `${sign}${trim((a / 1e12).toFixed(2))}兆`;
  const man = Math.round(a / 1e4);
  if (man >= 10000) return `${sign}${trim(oku.toFixed(1))}億`;
  return `${sign}${man}万`;
}

/** 増減の表の1行（会計・款・項・目）。子を開くと下の段 */
export interface DiffNode {
  key: string;
  name: string;
  level: 'account' | 'kan' | 'kou' | 'moku';
  /** 当初 */
  before: Yen;
  /** 補正後 */
  after: Yen;
  /** 回ごとの補正額（composed.rounds の順） */
  rounds: Yen[];
  children: DiffNode[];
  /** 目の行の ID（目だけ。図で選ぶ） */
  rowId?: string;
  /** 補正で新しく設けた目（その回の名前） */
  addedIn?: string;
}

export interface DiffTreeOptions {
  side: Side;
  /** 会計を一番上の段にするか（全会計の見方）。しないときは一般会計だけ */
  byAccount: boolean;
}

/**
 * 補正後のファイルから増減の表を作る（会計 → 款 → 項 → 目）。公営企業会計は入れない（補正後の見方に出さない）。
 * 当初・補正後・回ごとの額は、目の値を足し上げたもの
 */
export function supplementDiffTree(file: LocalBudgetFile, opts: DiffTreeOptions): DiffNode[] {
  const rounds = file.composed?.rounds.map(r => r.round) ?? [];
  const accountOf = new Map(file.accounts.map(a => [a.id, a]));
  const rows = file.rows.filter(r => {
    const acc = accountOf.get(r.account);
    if (acc?.kind === 'enterprise' || r.side !== opts.side) return false;
    return opts.byAccount || r.account === 'general';
  });
  const top: DiffNode[] = [];
  const index = new Map<string, DiffNode>();
  const child = (parent: DiffNode[], key: string, name: string, level: DiffNode['level']): DiffNode => {
    let n = index.get(key);
    if (!n) {
      n = { key, name, level, before: 0, after: 0, rounds: rounds.map(() => 0), children: [] };
      index.set(key, n);
      parent.push(n);
    }
    return n;
  };
  for (const r of rows) {
    const path: DiffNode[] = [];
    let siblings = top;
    if (opts.byAccount) {
      const acc = child(siblings, `account:${r.account}`, accountOf.get(r.account)?.name ?? r.account, 'account');
      path.push(acc);
      siblings = acc.children;
    }
    const kan = child(siblings, `kan:${r.account}:${r.side}:${r.kan.no}`, r.kan.name, 'kan');
    path.push(kan);
    const kou = child(kan.children, `kou:${r.account}:${r.side}:${r.kan.no}-${r.kou.no}`, r.kou.name, 'kou');
    path.push(kou);
    const moku = child(kou.children, `moku:${r.id}`, r.moku.name, 'moku');
    moku.rowId = r.id;
    if (r.added_in) moku.addedIn = r.added_in;
    path.push(moku);
    const before = r.before?.v ?? 0;
    const after = r.amount.v ?? 0;
    const perRound = rounds.map(name => (r.supplements ?? []).filter(s => s.round === name).reduce((t, s) => t + (s.amount.v ?? 0), 0));
    for (const n of path) {
      n.before += before;
      n.after += after;
      perRound.forEach((v, i) => (n.rounds[i] += v));
    }
  }
  return top;
}

/**
 * 並べ替えの大きさ: 自分の増減の絶対値。自分が 0 なら子の大きさの合計（同じ項の中で目の間で付け替えた項を、
 * 動いた額の分だけ上に出す。0 のままだと「増減の大きい順」で一番下に回る）
 */
function activity(n: DiffNode): number {
  const own = Math.abs(n.after - n.before);
  return own !== 0 ? own : n.children.reduce((t, c) => t + activity(c), 0);
}

/** 表の並べ替え（各段の中で）。delta: 増減の大きい順（activity。同じなら元の順）。order: 款・項・目の順（データの順） */
export function sortDiff(nodes: DiffNode[], by: 'delta' | 'order'): DiffNode[] {
  const sorted = by === 'delta'
    ? nodes.map((n, i) => ({ n, i, a: activity(n) })).sort((x, y) => y.a - x.a || x.i - y.i).map(x => x.n)
    : nodes;
  return sorted.map(n => ({ ...n, children: sortDiff(n.children, by) }));
}

/**
 * 増減のない行を外す。子を先に絞り、自分の増減が 0 でも増減のある子が残る行は残す
 * （同じ項の中で目の間で付け替えた補正は、項の増減が 0 でも目は動いている）
 */
export function withoutZero(nodes: DiffNode[]): DiffNode[] {
  return nodes
    .map(n => ({ ...n, children: withoutZero(n.children) }))
    .filter(n => n.after !== n.before || n.children.length > 0);
}

/** 行の当初・補正後の合計（表の合計の行） */
export function diffTotal(nodes: DiffNode[]): { before: Yen; after: Yen } {
  return nodes.reduce((t, n) => ({ before: t.before + n.before, after: t.after + n.after }), { before: 0, after: 0 });
}

/** 当初の図の総計（見出しの「補正 +○○」の元。見方ごとに一度だけ求める） */
export function initialGross(initial: LocalBudgetFile, view: LocalGraphView): Yen {
  return buildLocalGraph(initial, { view, depth: 1 }).totals.gross;
}

/** 図の総計の増減（見出しの「補正 +○○」）。当初の図の総計との差 */
export function grossDelta(initial: LocalBudgetFile, view: LocalGraphView, composedGross: Yen): Yen {
  return composedGross - initialGross(initial, view);
}

