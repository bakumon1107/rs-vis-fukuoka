/**
 * 地方版のバブル図（/local/<自治体>/policies）の組み立て。純粋な関数だけ（画面・取得は持たない）。
 * 設計: docs/local-gov/tasks/20261120_1500_地方版バブル図の設計.md 6章
 *
 * 施策別資料の事項を「柱 → 取組 → 事項」の入れ子にする（配置は d3-hierarchy の pack。描画は client 側）。
 * 色は柱ごと（既定）か款ごと。款は数が多いので、事項の額の多い款から6つに色を当て、残りは「その他の款」にまとめる
 */
import type { LocalBudgetFile, LocalPolicies, PolicyItem } from '@/types/local-gov';

/** 色の当て方の順（検証済みの配色の 1〜7 番。dataviz の参照の配色。決まった順で当て、回さない） */
export const SERIES_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6'] as const;
/** 図に載らない経費の灰色 */
export const MUTED_COLOR = '#94a3b8';
/** 款で色分けするときの「その他の款」（載らない経費の灰色と見分けるため濃い灰色） */
export const OTHER_KAN_COLOR = '#475569';

/** 「大きな事項を外す」の境（円）。上位の義務的な負担金・給付費が大半（設計 7章の3。外した事項は一覧で示す） */
export const BIG_ITEM_YEN = 10_000_000_000;

export interface PolicyLeaf {
  kind: 'item';
  /** policies.items の添字（選択の ID） */
  index: number;
  name: string;
  value: number;
  item: PolicyItem;
}
export interface PolicyGroup {
  kind: 'pillar' | 'initiative';
  /** 柱: "p:<番号>"（柱の外は "p:none"）。取組: "i:<柱>:<取組名>" */
  key: string;
  name: string;
  pillar: number | null;
  children: (PolicyGroup | PolicyLeaf)[];
}
/** 施策の円の key（寄るときの ID） */
export const POLICIES_KEY = 'root';

export interface PolicyRoot {
  kind: 'root';
  key: typeof POLICIES_KEY;
  name: string;
  children: PolicyGroup[];
}

/** 4つの柱の外のグループの名前。取組名はデータから（年度で取組が変わっても古い名前を出さない） */
export function outsidePillarName(p: LocalPolicies): string {
  const inits = [...new Set(p.items.filter(it => it.pillar === null).map(it => it.initiative ?? '（取組なし）'))];
  return inits.length ? `4つの柱の外（${inits.join('・')}）` : '4つの柱の外';
}
const pillarKey = (p: number | null) => `p:${p ?? 'none'}`;
export const initiativeKey = (it: PolicyItem) => `i:${it.pillar ?? 'none'}:${it.initiative ?? '（取組なし）'}`;

/** 事項を柱 → 取組 → 事項の入れ子にする。hidden の事項（添字）は入れない。柱は番号順、柱の外は最後 */
export function policyTree(p: LocalPolicies, hidden: ReadonlySet<number> = new Set()): PolicyRoot {
  const pillars = new Map<string, PolicyGroup>();
  const outsideName = outsidePillarName(p);
  const pillarName = (n: number | null) => (n === null ? outsideName : p.pillars.find(x => x.no === n)?.name ?? `柱 ${n}`);
  p.items.forEach((it, index) => {
    if (hidden.has(index) || it.amount <= 0) return;
    const pk = pillarKey(it.pillar);
    let pg = pillars.get(pk);
    if (!pg) pillars.set(pk, (pg = { kind: 'pillar', key: pk, name: pillarName(it.pillar), pillar: it.pillar, children: [] }));
    const ik = initiativeKey(it);
    let ig = pg.children.find((c): c is PolicyGroup => c.kind === 'initiative' && c.key === ik);
    if (!ig) pg.children.push((ig = { kind: 'initiative', key: ik, name: it.initiative ?? '（取組なし）', pillar: it.pillar, children: [] }));
    ig.children.push({ kind: 'item', index, name: it.name, value: it.amount, item: it });
  });
  const order = (g: PolicyGroup) => (g.pillar === null ? Number.MAX_SAFE_INTEGER : g.pillar);
  return { kind: 'root', key: POLICIES_KEY, name: '施策', children: [...pillars.values()].sort((a, b) => order(a) - order(b)) };
}

/** 大きな事項（境以上）の添字 */
export function bigItems(p: LocalPolicies, threshold = BIG_ITEM_YEN): Set<number> {
  const out = new Set<number>();
  p.items.forEach((it, i) => {
    if (it.amount >= threshold) out.add(i);
  });
  return out;
}

export interface InitiativeTotal {
  key: string;
  name: string;
  pillar: number | null;
  amount: number;
  count: number;
}

/** 取組ごとの合計（多い順）。hidden の事項と額 0 の事項は数えない（policyTree と同じ。円のない取組を一覧に出さない） */
export function initiativeTotals(p: LocalPolicies, hidden: ReadonlySet<number> = new Set()): InitiativeTotal[] {
  const m = new Map<string, InitiativeTotal>();
  p.items.forEach((it, i) => {
    if (hidden.has(i) || it.amount <= 0) return;
    const k = initiativeKey(it);
    const e = m.get(k) ?? { key: k, name: it.initiative ?? '（取組なし）', pillar: it.pillar, amount: 0, count: 0 };
    e.amount += it.amount;
    e.count += 1;
    m.set(k, e);
  });
  return [...m.values()].sort((a, b) => b.amount - a.amount);
}

/**
 * 事項の款（科目の款がすべて同じならその番号、またがれば 'multi'、科目がなければ null）。
 * 資料の科目に「外」（ほかの科目にもまたがる）の印があれば、書かれていない款があるかもしれないので 'multi'
 */
export function itemKan(it: PolicyItem): number | 'multi' | null {
  const kans = new Set(it.kamoku.map(k => k.kan));
  if (it.other_kamoku) return 'multi';
  if (kans.size === 0) return null;
  return kans.size === 1 ? [...kans][0] : 'multi';
}

/** 寄る円の key（施策の円・柱・取組）が木にあれば、全体からの道すじを返す（ないとき = 外した事項だけの取組などは null） */
export function focusPath(tree: PolicyRoot, focus: string): { key: string; label: string }[] | null {
  if (focus === tree.key) return [{ key: tree.key, label: '施策別資料の事項' }];
  for (const p of tree.children) {
    const plabel = p.pillar === null ? p.name : `${p.pillar}. ${p.name}`;
    if (p.key === focus) return [{ key: tree.key, label: '施策別資料の事項' }, { key: p.key, label: plabel }];
    for (const c of p.children) {
      if (c.kind === 'initiative' && c.key === focus) {
        return [{ key: tree.key, label: '施策別資料の事項' }, { key: p.key, label: plabel }, { key: c.key, label: c.name }];
      }
    }
  }
  return null;
}

/** 取組の事項（添字つき。額の多い順）。木から取るので、外した事項は入らない */
export function initiativeLeaves(tree: PolicyRoot, key: string): PolicyLeaf[] {
  for (const p of tree.children) {
    for (const c of p.children) {
      if (c.kind === 'initiative' && c.key === key) {
        return (c.children.filter(x => x.kind === 'item') as PolicyLeaf[]).sort((a, b) => b.value - a.value);
      }
    }
  }
  return [];
}

/** 施策別資料の PDF のファイル名から出典の資料を探す。名前の「。名前の検索に使用」はサンキー図での使い道の注記なので外す */
export function sourceForDoc<T extends { url: string; title: string }>(sources: T[], doc: string): T | undefined {
  const s = sources.find(x => x.url.endsWith(`/${doc}`));
  return s ? { ...s, title: s.title.replace('。名前の検索に使用', '') } : undefined;
}

export interface ColorLegend {
  key: string;
  label: string;
  color: string;
}

/** 一般会計の歳出の款の番号 → 名前（予算のファイルの目の行から） */
export function kanNames(file: LocalBudgetFile): Map<number, string> {
  const m = new Map<number, string>();
  for (const r of file.rows) if (r.account === 'general' && r.side === 'expense') m.set(r.kan.no, r.kan.name);
  return m;
}

/**
 * 色の当て方。柱ごと: 柱 1〜4 と柱の外に 1〜5 番。款ごと: 事項の額の多い款から 1〜6 番、款をまたぐ事項に 7 番、残りの款は濃い灰色。
 * 色は事項の持ち物（柱・款）で決め、外す・絞るで変わらない（全事項の額の順で当てる）
 */
export function colorScheme(p: LocalPolicies, mode: 'pillar' | 'kan', kanName: Map<number, string>):
  { colorOf: (it: PolicyItem) => string; legend: ColorLegend[] } {
  if (mode === 'pillar') {
    const legend: ColorLegend[] = p.pillars.map((x, i) => ({ key: pillarKey(x.no), label: `${x.no}. ${x.name}`, color: SERIES_COLORS[i] ?? MUTED_COLOR }));
    if (p.items.some(it => it.pillar === null)) legend.push({ key: pillarKey(null), label: outsidePillarName(p), color: SERIES_COLORS[p.pillars.length] ?? MUTED_COLOR });
    const by = new Map(legend.map(l => [l.key, l.color]));
    return { colorOf: it => by.get(pillarKey(it.pillar)) ?? MUTED_COLOR, legend };
  }
  const sums = new Map<number, number>();
  for (const it of p.items) {
    const k = itemKan(it);
    if (typeof k === 'number') sums.set(k, (sums.get(k) ?? 0) + it.amount);
  }
  const top = [...sums.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6).map(([k]) => k);
  const by = new Map(top.map((k, i) => [k, SERIES_COLORS[i]]));
  const legend: ColorLegend[] = top.map(k => ({ key: `k:${k}`, label: kanName.get(k) ?? `${k}款`, color: by.get(k)! }));
  legend.push({ key: 'k:multi', label: '款をまたぐ事項', color: SERIES_COLORS[6] });
  legend.push({ key: 'k:other', label: 'その他の款', color: OTHER_KAN_COLOR });
  return {
    colorOf: it => {
      const k = itemKan(it);
      if (k === 'multi') return SERIES_COLORS[6];
      return (typeof k === 'number' && by.get(k)) || OTHER_KAN_COLOR;
    },
    legend,
  };
}

/** 幅 widthPx に収まるように名前を切る（1文字の幅を fontPx とみなす。3文字に満たなければ空） */
export function fitWidth(name: string, widthPx: number, fontPx: number): string {
  const max = Math.floor(widthPx / fontPx);
  if (max < 3) return '';
  return name.length <= max ? name : `${name.slice(0, max - 1)}…`;
}

/** 円の真ん中に置く名前（円の中ほどの幅 1.6r に収める） */
export function fitLabel(name: string, radiusPx: number, fontPx: number): string {
  return fitWidth(name, radiusPx * 1.6, fontPx);
}

/** 半径 r の円の、上端から depth の高さでの幅（弦の長さ）。depth が r を超えれば直径 */
export function chordPx(radiusPx: number, depthPx: number): number {
  const h = Math.min(Math.max(depthPx, 0), radiusPx);
  return 2 * Math.sqrt(2 * radiusPx * h - h * h);
}
