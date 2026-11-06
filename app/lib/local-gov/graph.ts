/**
 * 地方版のサンキー図のグラフを、正規化データ（LocalBudgetFile）から組み立てる。純粋関数（HTTP・React なし）。
 * 設計: docs/local-gov/tasks/20261106_1327_地方版サンキー図の画面とグラフの設計.md 3章
 *
 * - 推計を入れない: 帯の値はすべて説明書に印字された数字の合計。按分しない
 * - 選んだとき（絞り込み）は、選んだものに含まれる目の数字だけから組み立て直す。
 *   財源 → 款 の帯も、選んだ目の財源内訳だけの合計になる（款全体の割合で按分しない。国版の focusSankey と違う点）
 * - 金額は円の整数のまま
 */
import {
  LOCAL_GOV_SCHEMA_VERSION,
  type LocalBudgetFile,
  type LocalGraph,
  type MokuRow,
  type Side,
  type Yen,
} from '@/types/local-gov';

/**
 * 見方（列の組み合わせ）。
 * - general: 一般会計の歳出。財源 → 款 → 項 → 目 → 事項
 * - all: 全会計。歳入の款 → 会計 → 款 → 項 → 目（総計。会計間の繰入れの重複を含む）
 */
export type LocalGraphView = 'general' | 'all';

/**
 * 絞り込み。指定したものに含まれる目だけで組み立てる（番号は款・項・目の番号）。
 * 款の番号は歳入と歳出で別なので、全会計の見方で款・項・目を選ぶときは side も指定する
 */
export interface LocalGraphFilter {
  account?: string;
  side?: Side;
  kan?: number;
  kou?: number;
  moku?: number;
}

export interface LocalGraphOptions {
  view: LocalGraphView;
  filter?: LocalGraphFilter;
  /** 左から何列まで作るか（深い列は選んだときだけ開く）。省略時は全部 */
  depth?: number;
}

/** 財源の区分（歳出の目の財源内訳。説明書の列の順） */
export const FUNDING_KINDS = [
  { key: 'national', label: '国庫支出金' },
  { key: 'bond', label: '地方債' },
  { key: 'other', label: 'その他' },
  { key: 'general', label: '一般財源' },
] as const;

const COLUMNS: Record<LocalGraphView, { key: string; label: string }[]> = {
  general: [
    { key: 'funding', label: '財源' },
    { key: 'kan', label: '款' },
    { key: 'kou', label: '項' },
    { key: 'moku', label: '目' },
    { key: 'item', label: '事項' },
  ],
  all: [
    { key: 'revenue', label: '歳入の款' },
    { key: 'account', label: '会計' },
    { key: 'kan', label: '款' },
    { key: 'kou', label: '項' },
    { key: 'moku', label: '目' },
  ],
};

type Node = LocalGraph['nodes'][number];

/** ノードと帯を足し込む入れ物（同じ ID の帯は値を足す。出てきた順を保つ）。ノードの値は最後に帯から求める */
class GraphBuilder {
  nodes = new Map<string, Node>();
  edges = new Map<string, { source: string; target: string; value: Yen }>();

  node(id: string, col: string, name: string, extra: Partial<Node> = {}): string {
    if (!this.nodes.has(id)) this.nodes.set(id, { id, col, name, value: 0, ...extra });
    return id;
  }

  edge(source: string, target: string, value: Yen) {
    if (value === 0) return;
    const k = `${source}\u0000${target}`;
    const e = this.edges.get(k);
    if (e) e.value += value;
    else this.edges.set(k, { source, target, value });
  }
}

function matches(row: MokuRow, f: LocalGraphFilter | undefined): boolean {
  if (!f) return true;
  if (f.account !== undefined && row.account !== f.account) return false;
  if (f.side !== undefined && row.side !== f.side) return false;
  if (f.kan !== undefined && row.kan.no !== f.kan) return false;
  if (f.kou !== undefined && row.kou.no !== f.kou) return false;
  if (f.moku !== undefined && row.moku.no !== f.moku) return false;
  return true;
}

/** 名前の確からしさの印（画面で「名前は読み取り」を付ける） */
function nameFlags(src: string | undefined): string[] | undefined {
  return src === 'ocr' ? ['name-ocr'] : undefined;
}

const amountOf = (row: MokuRow): Yen => row.amount.v ?? 0;

/** 款・項・目のノード ID（会計ごとに別。全会計の見方で同じ名前の款が会計をまたいで混ざらないように） */
const kanId = (r: MokuRow) => `kan:${r.account}:${r.side}:${r.kan.no}`;
const kouId = (r: MokuRow) => `kou:${r.account}:${r.side}:${r.kan.no}-${r.kou.no}`;
const mokuId = (r: MokuRow) => `moku:${r.id}`;

/**
 * 款 → 項 → 目（→ 事項）の帯を足す。cols は作る列の key の一覧。
 * from: 款へ流し込む左の列のノード（全会計の見方の会計）。null なら款への帯は足さない（一般会計の見方は財源の帯が担う）
 */
function addHierarchy(b: GraphBuilder, r: MokuRow, cols: Set<string>, from: string | null) {
  const v = amountOf(r);
  if (!cols.has('kan')) return;
  const kan = b.node(kanId(r), 'kan', r.kan.name, { flags: nameFlags(r.kan.name_src) });
  if (from) b.edge(from, kan, v);
  if (!cols.has('kou')) return;
  const kou = b.node(kouId(r), 'kou', r.kou.name, { flags: nameFlags(r.kou.name_src) });
  b.edge(kan, kou, v);
  if (!cols.has('moku')) return;
  const moku = b.node(mokuId(r), 'moku', r.moku.name, { row: r.id, flags: nameFlags(r.moku.name_src) });
  b.edge(kou, moku, v);
  if (!cols.has('item') || !r.items) return;
  // 事項は親の事項だけ（入れ子の内訳は親に含まれる）。事項のない目（税交付金・公債費の元金など）は目で止まる
  r.items.forEach((it, i) => {
    if (it.parent !== undefined || it.amount.v === null) return;
    const item = b.node(`item:${r.id}:${i}`, 'item', it.name, { row: r.id, flags: nameFlags(it.name_src) });
    b.edge(moku, item, it.amount.v);
  });
}

export function buildLocalGraph(file: LocalBudgetFile, opts: LocalGraphOptions): LocalGraph {
  const columns = COLUMNS[opts.view].slice(0, opts.depth ?? undefined);
  const cols = new Set(columns.map(c => c.key));
  const b = new GraphBuilder();
  const rows = file.rows.filter(r => matches(r, opts.filter));
  let gross = 0;

  if (opts.view === 'general') {
    for (const r of rows) {
      if (r.account !== 'general' || r.side !== 'expense') continue;
      gross += amountOf(r);
      if (!r.funding) continue;
      // 財源 → 款: その目の財源内訳（印字された数字）をそのまま款へ流す。款の財源は、含まれる目の財源の合計になる
      const kan = cols.has('kan') ? b.node(kanId(r), 'kan', r.kan.name, { flags: nameFlags(r.kan.name_src) }) : null;
      for (const f of FUNDING_KINDS) {
        const fv = r.funding[f.key].v ?? 0;
        const fund = b.node(`funding:${f.key}`, 'funding', f.label);
        if (kan) b.edge(fund, kan, fv);
      }
      // 款から先（款 → 項 → 目 → 事項）。款への入りは上の財源の帯
      addHierarchy(b, r, cols, null);
    }
  } else {
    for (const r of rows) {
      const acc = file.accounts.find(a => a.id === r.account);
      const accNode = b.node(`account:${r.account}`, 'account', acc?.name ?? r.account);
      if (r.side === 'revenue') {
        // 歳入の款 → 会計。歳入の款は名前でまとめる（会計をまたいで同じ名前の款は1つの箱）
        const rev = b.node(`revenue:${r.kan.name}`, 'revenue', r.kan.name, { flags: nameFlags(r.kan.name_src) });
        b.edge(rev, accNode, amountOf(r));
      } else {
        gross += amountOf(r);
        addHierarchy(b, r, cols, accNode);
      }
    }
  }

  // ノードの値: 入ってくる帯の合計（左端の列は出ていく帯の合計）
  const inflow = new Map<string, Yen>();
  const outflow = new Map<string, Yen>();
  for (const e of b.edges.values()) {
    inflow.set(e.target, (inflow.get(e.target) ?? 0) + e.value);
    outflow.set(e.source, (outflow.get(e.source) ?? 0) + e.value);
  }
  // 列の順に並べる（同じ列の中は出てきた順＝データの款・項・目の順。配置計算は列の中を生成順に積む）
  const colIndex = new Map(columns.map((c, i) => [c.key, i]));
  const nodes = [...b.nodes.values()]
    .map(n => ({ ...n, value: inflow.get(n.id) ?? outflow.get(n.id) ?? 0 }))
    .filter(n => n.value !== 0 && cols.has(n.col))
    .sort((a, b2) => colIndex.get(a.col)! - colIndex.get(b2.col)!);
  const keep = new Set(nodes.map(n => n.id));
  const edges = [...b.edges.values()].filter(e => keep.has(e.source) && keep.has(e.target));

  return {
    schema_version: LOCAL_GOV_SCHEMA_VERSION,
    gov_id: file.gov_id,
    year: file.year,
    basis: file.basis === 'supplementary' ? 'latest' : file.basis,
    columns,
    nodes,
    edges,
    // 純計（会計間の繰入れの重複を除いた額）は MVP の後。今は総計と同じ値を入れ、画面では総計だけを出す
    totals: { gross, net: gross },
  };
}
