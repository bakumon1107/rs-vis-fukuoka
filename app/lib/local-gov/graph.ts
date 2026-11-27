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
  type NameSource,
  type Side,
  type Yen,
} from '@/types/local-gov';

/**
 * 見方（列の組み合わせ）。列はデータの種類（予算・決算）で変わる（COLUMNS / SETTLEMENT_COLUMNS）。
 * - general: 一般会計の歳出。予算は 財源 → 款 → 項 → 目 → 事項、決算は 部局 → 款 → 項 → 目 → 節
 * - all: 全会計（総計。会計間の繰入れの重複を含む）。予算は 歳入の款 → 会計 → 款 → 項 → 目、決算は 会計 → 款 → 項 → 目 → 節
 *   （決算の歳入は図に描かない。R6 決算の設計 7章の2）
 * - enterprise: 公営企業会計（当初予算だけ）。収入の項・補填財源 → 会計・条 → 支出の項 → 目。
 *   条（収益的収支・資本的収支）ごとに入り = 出 になるよう、資本的収支の不足は補填財源の内訳（予算書の第4条）の箱から入れ、
 *   収益的収支の差は「予算上の利益」の箱へ出す（不足なら「収益的収支の不足」の箱から入れる）。
 *   設計: docs/local-gov/tasks/20261121_0100_公開前のサンキー図の足しと公営企業会計の設計.md 4.4
 */
export type LocalGraphView = 'general' | 'all' | 'enterprise';

/** 公営企業会計の条（行の enterprise_section）と予算書の条の番号 */
const SECTION_ART = { 収益的: 3, 資本的: 4 } as const;
export type EnterpriseSection = keyof typeof SECTION_ART;

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
  /**
   * 財源（一般会計の見方だけ）。各目の財源内訳のうちこの財源の額で 財源 → 款 → 項 → 目 を組み立てる
   * （財源内訳は目ごとに印字されているので按分にならない）。事項ごとの財源内訳は資料にないので、事項の列は作らない。
   * 'none' は財源内訳のない目（「財源の記載なし」の箱）
   */
  funding?: FundingKey | 'none';
  /**
   * 部局（決算の一般会計の見方だけ）。各目のこの部局の額（部局の内訳。資料の数字）で 部局 → 款 → 項 → 目 を組み立てる。
   * 節は部局ごとに分かれていないので、節の列は作らない
   */
  department?: string;
  /** 公営企業会計の条（公営企業会計の見方だけ）。款の番号は条ごとに振り直されるので、款・項を選ぶときは条も指定する */
  section?: EnterpriseSection;
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

export type FundingKey = (typeof FUNDING_KINDS)[number]['key'];

/** 公営企業会計の見方の列（予算実施計画は当初予算だけなので、決算にも同じ列を置くが見方は出さない） */
const ENTERPRISE_COLUMNS = [
  // 見出しは短く（スマートフォンの幅で隣の列の見出しに重なる）。補填財源の箱は名前に「補填財源・」が付く
  { key: 'erevenue', label: '収入' },
  { key: 'esection', label: '会計・条' },
  { key: 'ekou', label: '支出の項' },
  { key: 'moku', label: '目' },
];

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
  enterprise: ENTERPRISE_COLUMNS,
};

/** 決算の列（R6 決算の設計 4章・8章。歳入は描かない） */
const SETTLEMENT_COLUMNS: Record<LocalGraphView, { key: string; label: string }[]> = {
  general: [
    { key: 'department', label: '部局' },
    { key: 'kan', label: '款' },
    { key: 'kou', label: '項' },
    { key: 'moku', label: '目' },
    { key: 'setsu', label: '節' },
  ],
  all: [
    { key: 'account', label: '会計' },
    { key: 'kan', label: '款' },
    { key: 'kou', label: '項' },
    { key: 'moku', label: '目' },
    { key: 'setsu', label: '節' },
  ],
  enterprise: ENTERPRISE_COLUMNS,
};

/** 見方とデータの種類の列 */
export function columnsOf(view: LocalGraphView, basis: LocalBudgetFile['basis']) {
  return (basis === 'settlement' ? SETTLEMENT_COLUMNS : COLUMNS)[view];
}

/** 部局の内訳のない目（決算の一般会計で部局の表に出ない目。R6 は 0件）を流す箱の名前 */
export const DEPARTMENT_NONE = '部局の記載なし';

type Node = LocalGraph['nodes'][number];

/** 帯のキー（送り元 → 送り先）。グラフの組み立て・重ねる帯の値・描画で同じ形を使う */
export const edgeKey = (source: string, target: string) => `${source}\u0000${target}`;

/**
 * 帯を、送り元の箱の並び順・送り先の箱の並び順に並べ直す（配置計算は帯を並び順に積むので、箱の並びとずれると帯が交差する）。
 * 例: 款への財源の帯が目ごとに出てきた順だと、地方債の帯が一般財源の帯の下に入り交差していた
 */
export function orderEdges(graph: LocalGraph): LocalGraph['edges'] {
  const pos = new Map(graph.nodes.map((n, i) => [n.id, i]));
  return [...graph.edges].sort(
    (a, b) => (pos.get(a.source) ?? 0) - (pos.get(b.source) ?? 0) || (pos.get(a.target) ?? 0) - (pos.get(b.target) ?? 0)
  );
}

/** ノードと帯を足し込む入れ物（同じ ID の帯は値を足す。出てきた順を保つ）。ノードの値は最後に帯から求める */
class GraphBuilder {
  nodes = new Map<string, Node>();
  edges = new Map<string, { source: string; target: string; value: Yen }>();

  node(id: string, col: string, name: string, extra: Partial<Node> = {}): string {
    const cur = this.nodes.get(id);
    if (!cur) {
      this.nodes.set(id, { id, col, name, value: 0, ...extra });
    } else if (extra.flags?.length) {
      // 同じ箱に複数の行がまとまるとき（全会計の歳入の款は名前でまとめる）は、印を足し合わせる。
      // まとめた行のどれかの名前が読み取りのみなら、箱にも印を付ける（裏付けのない名前を裏付けありに見せない）
      cur.flags = [...new Set([...(cur.flags ?? []), ...extra.flags])];
    }
    return id;
  }

  edge(source: string, target: string, value: Yen) {
    // 0 円の帯は作らない。負の値（財源内訳の △・補正の減額）は想定していない: サンキー図は負の太さを描けないので、
    // 補正後（latest）を組み立てるときに扱い（減額は別の列にする など）を決める。実データのテストで負の帯がないことを確かめている
    if (value === 0) return;
    const k = edgeKey(source, target);
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
  if (f.section !== undefined && row.enterprise_section !== f.section) return false;
  return true;
}

/**
 * 名前に裏付けがないか（読み取りのみ）。名前の出典がない名前（name_src は省略できる）も ocr と同じに扱う（設計書 4.4）。
 * 図の印・詳細パネルの印・「データについて」の件数はすべてこの関数で決める
 */
export function isOcrName(src: NameSource | undefined): boolean {
  return src === undefined || src === 'ocr';
}

/** 名前の確からしさの印（画面で「名前は読み取り」を付ける） */
function nameFlags(src: NameSource | undefined): string[] | undefined {
  return isOcrName(src) ? ['name-ocr'] : undefined;
}

const amountOf = (row: MokuRow): Yen => row.amount.v ?? 0;

/** 款・項・目のノード ID（会計ごとに別。全会計の見方で同じ名前の款が会計をまたいで混ざらないように） */
const kanId = (r: MokuRow) => `kan:${r.account}:${r.side}:${r.kan.no}`;
const kouId = (r: MokuRow) => `kou:${r.account}:${r.side}:${r.kan.no}-${r.kou.no}`;
const mokuId = (r: MokuRow) => `moku:${r.id}`;

/**
 * 款 → 項 → 目（→ 事項）の帯を足す。cols は作る列の key の一覧。
 * from: 款へ流し込む左の列のノード（全会計の見方の会計）。null なら款への帯は足さない（一般会計の見方は財源の帯が担う）
 * value: 款 → 項 → 目 に流す額（省略時は目の本年度）。財源で絞り込んだときはその財源の額で、事項は作らない
 */
function addHierarchy(b: GraphBuilder, r: MokuRow, cols: Set<string>, from: string | null, value?: Yen) {
  const v = value ?? amountOf(r);
  if (!cols.has('kan')) return;
  const kan = b.node(kanId(r), 'kan', r.kan.name, { flags: nameFlags(r.kan.name_src) });
  if (from) b.edge(from, kan, v);
  if (!cols.has('kou')) return;
  const kou = b.node(kouId(r), 'kou', r.kou.name, { flags: nameFlags(r.kou.name_src) });
  b.edge(kan, kou, v);
  if (!cols.has('moku')) return;
  const moku = b.node(mokuId(r), 'moku', r.moku.name, { row: r.id, flags: nameFlags(r.moku.name_src) });
  b.edge(kou, moku, v);
  // 節（決算）。名前は節番号で決まる節名。同じ目の節は配列の位置で区別する
  if (cols.has('setsu') && r.setsu && value === undefined) {
    r.setsu.forEach((s, i) => {
      if (!s.amount.v) return;
      const setsu = b.node(`setsu:${r.id}:${i}`, 'setsu', s.name, { row: r.id, flags: nameFlags(s.name_src) });
      b.edge(moku, setsu, s.amount.v);
    });
  }
  if (!cols.has('item') || !r.items || value !== undefined) return;
  // 事項は親の事項だけ（入れ子の内訳は親に含まれる）。事項のない目（R8 の一般会計で水防費・予備費など4つ）は目で止まる。
  // ID は items の配列の位置（入れ子も数える）。名前で決めると、別の目の「職員費」などが1つの箱に混ざる
  r.items.forEach((it, i) => {
    if (it.parent !== undefined || it.amount.v === null) return;
    const item = b.node(`item:${r.id}:${i}`, 'item', it.name, { row: r.id, flags: nameFlags(it.name_src) });
    b.edge(moku, item, it.amount.v);
  });
}

/**
 * 複数の会計に出てくる歳出の款の名前。ファイル全体で数える（絞り込んだグラフでも、最初の画面と同じラベルにするため）
 */
function duplicatedExpenseKanNames(file: LocalBudgetFile): Set<string> {
  const accountsOf = new Map<string, Set<string>>();
  const enterprise = new Set(file.accounts.filter(a => a.kind === 'enterprise').map(a => a.id));
  for (const r of file.rows) {
    // 図に出る行（0 円でない行）だけで数える（設計書 3.2・4.4: ラベル・印は図に出る行だけから決める）
    if (r.side !== 'expense' || enterprise.has(r.account) || amountOf(r) === 0) continue;
    const s = accountsOf.get(r.kan.name) ?? new Set<string>();
    s.add(r.account);
    accountsOf.set(r.kan.name, s);
  }
  return new Set([...accountsOf].filter(([, s]) => s.size > 1).map(([name]) => name));
}

/** 公営企業会計の短い名前（「病院事業会計」→「病院」）。会計・条の箱と差の箱のラベルに使う */
export const enterpriseShortName = (name: string) => name.replace(/事業会計$/, '');

/** 公営企業会計の見方の箱の ID（graph-view.ts の選択の読み取りと同じ形） */
export const enterpriseIds = {
  section: (account: string, s: EnterpriseSection) => `esection:${account}:${SECTION_ART[s]}`,
  kou: (r: MokuRow) => `ekou:${r.account}:${SECTION_ART[r.enterprise_section!]}:${r.kan.no}-${r.kou.no}`,
  revenue: (name: string) => `erevenue:${name}`,
  fill: (name: string) => `efill:${name}`,
  shortfall: (account: string, s: EnterpriseSection) => `eshort:${account}:${SECTION_ART[s]}`,
  surplus: (account: string, s: EnterpriseSection) => `esurplus:${account}:${SECTION_ART[s]}`,
};

/**
 * 公営企業会計の見方（設計 4.4）。返り値は支出の合計（第3条 + 第4条）。
 * - 収入は項の名前でまとめる（「企業債」など会計をまたいで同じ名前の項は1つの箱。全会計の見方の歳入の款と同じ考え方）
 * - 会計・条の箱の入り = 出 にする箱（補填財源・収益的収支の差・不足）は、会計・条を丸ごと描くときだけ足す。
 *   支出の項・目で絞ったときは収入を描かないので足さない（足すと、支出だけの箱に「不足」が出てしまう）
 */
function addEnterprise(b: GraphBuilder, file: LocalBudgetFile, rows: MokuRow[], cols: Set<string>, filter: LocalGraphFilter | undefined): Yen {
  const accountOf = new Map(file.accounts.map(a => [a.id, a]));
  const whole = filter?.side === undefined && filter?.kan === undefined && filter?.kou === undefined && filter?.moku === undefined;
  // 支出の項の名前が複数の会計・条にあるとき（R8: 予備費 6・建設改良費 4 など）は、ラベルに会計・条を添える。
  // ファイル全体で数える（絞り込んだグラフでも最初の画面と同じラベルにする。全会計の見方の duplicatedExpenseKanNames と同じ考え方）
  // 同じ会計・条の中で同じ名前の項が別の款にあれば、款の名前も添える
  const idsOfKou = new Map<string, Set<string>>();
  const add = (k: string, id: string) => idsOfKou.set(k, (idsOfKou.get(k) ?? new Set<string>()).add(id));
  for (const r of file.rows) {
    if (accountOf.get(r.account)?.kind !== 'enterprise' || r.side !== 'expense' || !r.enterprise_section || amountOf(r) === 0) continue;
    add(r.kou.name, enterpriseIds.kou(r));
    add(`${r.kou.name}\u0000${r.account}:${r.enterprise_section}`, enterpriseIds.kou(r));
  }
  const kouLabel = (r: MokuRow, accName: string) => {
    if ((idsOfKou.get(r.kou.name)?.size ?? 0) < 2) return r.kou.name;
    const inSection = idsOfKou.get(`${r.kou.name}\u0000${r.account}:${r.enterprise_section}`)?.size ?? 0;
    return `${r.kou.name}（${enterpriseShortName(accName)}・${r.enterprise_section}${inSection > 1 ? `・${r.kan.name}` : ''}）`;
  };
  // 会計・条ごとの収入・支出の合計（差の箱を決める）
  const sums = new Map<string, { account: string; section: EnterpriseSection; revenue: Yen; expense: Yen }>();
  let gross = 0;
  for (const r of rows) {
    const acc = accountOf.get(r.account);
    if (acc?.kind !== 'enterprise' || !r.enterprise_section) continue;
    const v = amountOf(r);
    const secId = enterpriseIds.section(r.account, r.enterprise_section);
    const s = sums.get(secId) ?? { account: r.account, section: r.enterprise_section, revenue: 0, expense: 0 };
    s[r.side] += v;
    sums.set(secId, s);
    if (v === 0) continue;
    const sec = b.node(secId, 'esection', `${enterpriseShortName(acc.name)}・${r.enterprise_section}収支`);
    if (r.side === 'revenue') {
      b.edge(b.node(enterpriseIds.revenue(r.kou.name), 'erevenue', r.kou.name, { flags: nameFlags(r.kou.name_src) }), sec, v);
      continue;
    }
    gross += v;
    if (!cols.has('ekou')) continue;
    const kou = b.node(enterpriseIds.kou(r), 'ekou', kouLabel(r, acc.name), { flags: nameFlags(r.kou.name_src) });
    b.edge(sec, kou, v);
    if (cols.has('moku')) b.edge(kou, b.node(mokuId(r), 'moku', r.moku.name, { row: r.id, flags: nameFlags(r.moku.name_src) }), v);
  }
  if (!whole) return gross;
  for (const [secId, s] of sums) {
    const acc = accountOf.get(s.account)!;
    const short = enterpriseShortName(acc.name);
    let gap = s.expense - s.revenue; // 正なら不足（左から入れる）、負なら差（右へ出す）
    // 資本的収支の不足は、予算書の第4条の補填財源の内訳から入れる（内訳の合計 = 不足額 は書き出しと validate で確かめている）
    // 内訳の合計が不足額より多いデータ（validate を通っていない）では補填財源を描かず、「補填財源の記載なし」の不足の箱にする
    // （多すぎる内訳を引くと、ありもしない「収入の残り」の箱ができる）。少なければ内訳を描き、残りを「記載なし」にする
    const cs = acc.enterprise?.capital_shortfall;
    const filled = cs ? cs.items.reduce((t, it) => t + it.amount, 0) : 0;
    if (s.section === '資本的' && cs && gap > 0 && filled <= gap) {
      for (const it of cs.items) b.edge(b.node(enterpriseIds.fill(it.name), 'erevenue', `補填財源・${it.name}`), secId, it.amount);
      gap -= filled;
    }
    if (gap > 0) {
      const label = s.section === '収益的' ? `${short}・収益的収支の不足` : `${short}・資本的収支の不足（補填財源の記載なし）`;
      b.edge(b.node(enterpriseIds.shortfall(s.account, s.section), 'erevenue', label), secId, gap);
    } else if (gap < 0 && cols.has('ekou')) {
      const label = s.section === '収益的' ? `${short}・収益的収支の差（予算上の利益）` : `${short}・資本的収支の差（収入の残り）`;
      const id = b.node(enterpriseIds.surplus(s.account, s.section), 'ekou', label);
      b.edge(secId, id, -gap);
      // 差の箱は、同じ会計・条の支出の項のすぐ下に置く（列の最後に置くと、帯が図を縦に横切る）
      const keys = [...b.nodes.keys()].filter(k => k !== id);
      const prefix = `ekou:${s.account}:${SECTION_ART[s.section]}:`;
      const at = keys.findLastIndex(k => k.startsWith(prefix));
      if (at >= 0) {
        keys.splice(at + 1, 0, id);
        b.nodes = new Map(keys.map(k => [k, b.nodes.get(k)!] as const));
      }
    }
  }
  return gross;
}

export function buildLocalGraph(file: LocalBudgetFile, opts: LocalGraphOptions): LocalGraph {
  // 補正のファイルは差分（増減）なので、そのまま描くと補正後の額に見える（減額は負の帯にもなる）。
  // 当初 + Σ補正（basis: latest）を組み立てる処理は補正の取り込みのときに作る（共通 JSON 形式の設計 5章）。それまでは受け付けない
  if (file.basis === 'supplementary') {
    throw new Error('補正（差分）のファイルからはグラフを組み立てません（当初 + 補正 の組み立ては未実装）');
  }
  const columns = columnsOf(opts.view, file.basis).slice(0, opts.depth ?? undefined);
  const cols = new Set(columns.map(c => c.key));
  const b = new GraphBuilder();
  const rows = file.rows.filter(r => matches(r, opts.filter));
  let gross = 0;

  if (opts.view === 'enterprise') {
    gross = addEnterprise(b, file, rows, cols, opts.filter);
  } else if (file.basis === 'settlement' && opts.view === 'general') {
    // 決算の一般会計: 部局 → 款 → 項 → 目 → 節。部局 → 款 は目ごとの部局の内訳（資料の数字）をそのまま流す（按分しない）
    const only = opts.filter?.department;
    for (const r of rows) {
      if (r.account !== 'general' || r.side !== 'expense' || amountOf(r) === 0) continue;
      const deps: [string, Yen][] = r.by_department && r.by_department.length > 0
        ? r.by_department.map(d => [d.name, d.amount.v ?? 0])
        : [[DEPARTMENT_NONE, amountOf(r)]];
      const picked = only !== undefined ? deps.filter(([n]) => n === only) : deps;
      const v = only !== undefined ? picked.reduce((s, [, x]) => s + x, 0) : amountOf(r);
      if (v === 0) continue;
      gross += v;
      if (cols.has('kan')) {
        const kan = b.node(kanId(r), 'kan', r.kan.name, { flags: nameFlags(r.kan.name_src) });
        for (const [n, x] of picked) if (x) b.edge(b.node(`department:${n}`, 'department', n), kan, x);
      }
      addHierarchy(b, r, cols, null, only !== undefined ? v : undefined);
    }
  } else if (file.basis === 'settlement') {
    // 決算の全会計: 会計 → 款 → 項 → 目 → 節（歳入は描かない）
    const dupKan = duplicatedExpenseKanNames(file);
    const accountOf = new Map(file.accounts.map(a => [a.id, a]));
    for (const r of rows) {
      const acc = accountOf.get(r.account);
      if (acc?.kind === 'enterprise' || r.side !== 'expense' || amountOf(r) === 0) continue;
      gross += amountOf(r);
      const accName = acc?.name ?? r.account;
      addHierarchy(b, r, cols, b.node(`account:${r.account}`, 'account', accName));
      const kn = b.nodes.get(kanId(r));
      if (kn && dupKan.has(r.kan.name)) kn.name = `${r.kan.name}（${accName}）`;
    }
  } else if (opts.view === 'general') {
    const only = opts.filter?.funding;
    for (const r of rows) {
      if (r.account !== 'general' || r.side !== 'expense') continue;
      // この目から流す財源の帯 [財源の箱の key, 額]。財源内訳のない目（R8 は 0件）は「財源の記載なし」（none）から目の本年度を流す
      // （目を図から落とさず、財源の列の合計も歳出の総額のまま。設計書 3.2）
      const flows: [FundingKey | 'none', Yen][] = r.funding
        ? FUNDING_KINDS.map(f => [f.key, r.funding![f.key].v ?? 0])
        : [['none', amountOf(r)]];
      const picked = only ? flows.filter(([k]) => k === only) : flows;
      // 款から先に流す額: 財源で絞り込んだらその財源の額（事項は作らない）、絞り込まなければ目の本年度
      const v = only ? picked.reduce((s, [, x]) => s + x, 0) : amountOf(r);
      // 図に出ない行（0 円の目、財源で絞ったときにその財源が 0 円の目）は箱も作らない。箱を作ると、その行の名前の印が
      // ほかの行の箱に混ざる（設計書 3.2: 印は図に出る行だけから決める）
      if (amountOf(r) === 0 || v === 0) continue;
      gross += v;
      // 財源 → 款: その目の財源内訳（印字された数字）をそのまま款へ流す。款の財源は、含まれる目の財源の合計になる
      if (cols.has('kan')) {
        const kan = b.node(kanId(r), 'kan', r.kan.name, { flags: nameFlags(r.kan.name_src) });
        for (const [k, x] of picked) {
          const label = k === 'none' ? '財源の記載なし' : FUNDING_KINDS.find(f => f.key === k)!.label;
          b.edge(b.node(`funding:${k}`, 'funding', label), kan, x);
        }
      }
      // 款から先（款 → 項 → 目 → 事項）。款への入りは上の財源の帯
      addHierarchy(b, r, cols, null, only ? v : undefined);
    }
  } else {
    const dupKan = duplicatedExpenseKanNames(file);
    const accountOf = new Map(file.accounts.map(a => [a.id, a]));
    for (const r of rows) {
      const acc = accountOf.get(r.account);
      // 公営企業会計は描かない（収益的・資本的収支に分かれ歳入と歳出が一致しない。設計書 3.2）
      if (acc?.kind === 'enterprise') continue;
      // 0 円の目は図に出ないので箱も作らない（名前でまとめる歳入の款に、図に出ない行の印を混ぜない）
      if (amountOf(r) === 0) continue;
      const accName = acc?.name ?? r.account;
      const accNode = b.node(`account:${r.account}`, 'account', accName);
      if (r.side === 'revenue') {
        // 歳入の款 → 会計。歳入の款は名前でまとめる（会計をまたいで同じ名前の款は1つの箱）
        const rev = b.node(`revenue:${r.kan.name}`, 'revenue', r.kan.name, { flags: nameFlags(r.kan.name_src) });
        b.edge(rev, accNode, amountOf(r));
      } else {
        gross += amountOf(r);
        addHierarchy(b, r, cols, accNode);
        // 同じ名前の歳出の款が複数の会計にあるときは、ラベルに会計の名前を添える（R8: 公債費 4・予備費 3 など。添えないと見分けられない）
        const kn = b.nodes.get(kanId(r));
        if (kn && dupKan.has(r.kan.name)) kn.name = `${r.kan.name}（${accName}）`;
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
    basis: file.basis,
    columns,
    nodes,
    edges,
    // 純計（会計間の繰入れの重複を除いた額）はグラフには持たず、画面が totals.ts の netTotal で計算して見出しに出す（net は省く）
    totals: { gross },
  };
}
