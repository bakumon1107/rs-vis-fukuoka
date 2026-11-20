/**
 * 地方版（local-gov）の共通 JSON 形式の型。
 * 設計: docs/local-gov/tasks/20261106_0841_共通JSON形式の設計.md
 *
 * 自治体ごとのデータパイプライン（scripts/local-gov/<自治体>/）が export で書き出し、
 * 共通のグラフ生成と画面がこれを読む。金額はすべて円の整数。
 */

/** 円の整数（千円の資料は ×1000 して持つ） */
export type Yen = number;

export const LOCAL_GOV_SCHEMA_VERSION = 1 as const;

/** 値の出典。画面で推計・修正の印を出すために値ごとに持つ */
export type ValueSource =
  | 'text' // テキスト PDF から抽出
  | 'ocr' // スキャン画像の OCR
  | 'textlayer' // 発行元が付けた文字層（OCR との突き合わせで採用）
  | 'correction' // 画像で確かめて修正表で直した
  | 'blank-as-zero' // 空欄を 0 とみなした（|本年度 − 前年度| = |比較| が成り立つときだけ）
  | 'inferred'; // 検算の式から逆算（裏付けのない推定。原則使わない）

export const VALUE_SOURCES: readonly ValueSource[] = ['text', 'ocr', 'textlayer', 'correction', 'blank-as-zero', 'inferred'];

export interface Value {
  v: Yen | null;
  src: ValueSource;
  /** 同じ値を出した読み取りの数（OCR の資料だけ。多数決） */
  agree?: number;
  /** 修正表の根拠など */
  note?: string;
}

export type AccountKind = 'general' | 'special' | 'enterprise';

export interface Account {
  /** 'general' / 'special:<slug>' / 'enterprise:<slug>' */
  id: string;
  kind: AccountKind;
  name: string;
}

export type Side = 'revenue' | 'expense';
export type Basis = 'initial' | 'supplementary' | 'settlement';

export interface NumberedName {
  no: number;
  name: string;
  /** 名前の出典（NameSource）。金額と違って名前は検算で確かめられないので、どこから取ったかを残す */
  name_src?: NameSource;
  /** name_src が search のとき、名前が見つかった資料の id（index.json の sources の id） */
  name_evidence?: string[];
}

/**
 * 名前の出典。強い順に
 * text: テキスト PDF の資料そのもの（計上額調など）/ reference: 別資料・別年度のテキスト（R6 決算・節番号の正式な節名）と照合 /
 * search: 手元のテキスト資料の全文に同じ名前がある（name_evidence に資料）/ readings: 独立した読み取りの2つ以上が一致 /
 * correction: 画像で確かめて修正表に記録 / ocr: 裏付けなし（画面で印を付ける）
 */
export type NameSource = 'text' | 'reference' | 'search' | 'readings' | 'correction' | 'ocr';
export const NAME_SOURCES: readonly NameSource[] = ['text', 'reference', 'search', 'readings', 'correction', 'ocr'];

/**
 * 節番号の出典。ocr: 説明書の OCR（旧 OCR を含む）/ textlayer: 発行元の文字層 / correction: 画像で確かめて修正表に記録 /
 * text: テキスト PDF の説明書（R8 の補正予算のうちテキストの回）
 */
export type SetsuNoSource = 'ocr' | 'textlayer' | 'correction' | 'text';
export const SETSU_NO_SOURCES: readonly SetsuNoSource[] = ['ocr', 'textlayer', 'correction', 'text'];

/** 名前とその出典（事項・節・細節） */
export interface NameWithSource {
  name: string;
  name_src?: NameSource;
  name_evidence?: string[];
}

/** 説明欄の ○事項 */
export interface Item extends NameWithSource {
  amount: Value;
  /** 入れ子の内訳は親の添字（items 配列の中の位置） */
  parent?: number;
  /** 「職員費 293人」の人数 */
  headcount?: number;
  /** 1事項で金額の記載なし（目の額を当てた） */
  no_amount_printed?: boolean;
  links?: { kind: '施策別資料' | '行政評価'; id: string; match: 'amount+name' | 'name' }[];
  /** 補正後（当初 + Σ補正）で、当初になく補正で加わった事項（その回の名前。例「9月補正（第3号）」） */
  added_in?: string;
}

export interface Setsu extends NameWithSource {
  /** 節の番号。読めなかったときは null（並び順の番号をこしらえない） */
  no: number | null;
  /** no の出典（no が null のときはない） */
  no_src?: SetsuNoSource;
  amount: Value;
  sub?: (NameWithSource & { amount: Value })[];
  /** 補正後で、当初になく補正で加わった節 */
  added_in?: string;
}

export interface Funding {
  national: Value; // 国庫支出金
  bond: Value; // 地方債
  other: Value; // その他
  general: Value; // 一般財源
}

/** 目の行（正規化データの1行）。階層は入れ子でなく項目として持つ */
export interface MokuRow {
  /** `<会計ID>/<歳入歳出>/<款>-<項>-<目>`。その年度の番号（年度をまたぐ対応は crosswalk で持つ） */
  id: string;
  account: string;
  side: Side;
  /** 公営企業会計だけ */
  enterprise_section?: '収益的' | '資本的';
  kan: NumberedName;
  kou: NumberedName;
  /** 目。前年度にだけあった目（previous_only）は番号が印字されないので no は null（ID は `…-p<項の中の順>`） */
  moku: Omit<NumberedName, 'no'> & { no: number | null };
  /**
   * 前年度にだけあった目（当初予算。本年度が空欄で番号の印字がない。R8 の知事選挙費など）。
   * 番号をこしらえると、補正で新しく設けた目と同じ番号になる（R8 8月専決「3 県議会議員補欠選挙費」）ので、ID を p<n> にする
   */
  previous_only?: true;
  /** 本年度（予算）／補正額（補正）／支出済額（決算） */
  amount: Value;
  previous?: Value; // 前年度（当初予算）
  before?: Value; // 補正前の額（補正）
  after?: Value; // 計（補正）
  budget_current?: Value; // 予算現額（決算）
  carried_over?: Value; // 翌年度繰越額（決算）
  unused?: Value; // 不用額（決算）
  funding?: Funding; // 財源内訳（歳出）
  items?: Item[];
  setsu?: Setsu[];
  department?: { name: string; via: string };
  /**
   * 部局ごとの内訳（決算。1つの目が複数の部局にまたがる。R6 で 234目のうち 6目）。4列の合計は目の値と一致する。
   * 決算の内容・不用額の内容は部局ごとに資料にあるので、ここに持つ
   */
  by_department?: {
    name: string;
    amount: Value;
    budget_current: Value;
    carried_over: Value;
    unused: Value;
    explanation?: Explanation;
  }[];
  /** 決算の内容・不用額の内容（決算。部局の内訳がない目＝特別会計はここに持つ） */
  explanation?: Explanation;
  /** 会計間の繰出し・繰入れ（純計で重複を除くための印） */
  transfer?: { to_account?: string; from_account?: string };
  /** 「○○課所管」「事業費支弁職員 2人」などの注記 */
  notes?: string[];
  pages: { source: string; page: number }[];
  /** 補正後（当初 + Σ補正）で、当初になく補正で新しく設けた目（その回の名前） */
  added_in?: string;
  /** 補正後で、この目を動かした補正の回と補正額（古い順） */
  supplements?: { round: string; amount: Value }[];
}

/** 決算の目の説明（概要説明書の「決算の内容」「不用額の内容」の文） */
export interface Explanation {
  /** 決算の内容（主な使い道。例「人件費 運営費 財産管理費」） */
  content?: string;
  /** 不用額の内容（主に何が余ったか。例「人件費 （120,825千円）」） */
  unused?: string;
}

/** 決算の歳入（会計 × 款）。特別会計の歳入は資料に款までしかないので、一般会計もそろえて款の単位で持つ */
export interface RevenueByKan {
  account: string;
  kan: NumberedName;
  amount: Value; // 収入済額
  budget_current: Value; // 予算現額
  assessed: Value; // 調定額
  deficit_loss: Value; // 不納欠損額
  uncollected: Value; // 収入未済額
  /** 過誤納金（収入済額の内数）。調定額 = 収入済額 − 過誤納金 + 不納欠損額 + 収入未済額 */
  overpaid?: Value;
}

export interface CheckSummary {
  rows: number;
  all_ok: number;
  rules: Record<string, number>;
  external?: Record<string, string>;
  /**
   * agree_2plus: 多数決（OCR の資料の3つの読み取り）で、2通り以上が同じ値だった値の割合。
   * confirmed_by_image: 裏付けが1通り以下だったが、画像で確かめて修正表に記録した値の数
   */
  /**
   * name_engines: 名前の候補に使った読み取り（「データについて」で使った OCR と帰属の表示を出す。NDLOCR-Lite は CC BY 4.0）
   */
  readings?: { agree_2plus: number; confirmed_by_image?: number; name_engines?: string[] };
  corrections?: number;
}

/**
 * 一般財源の中身の行の根拠の強さ。revenue_kan: 歳入の款そのもの（データの歳入の目から足す）/
 * matched: 財源内訳の差と歳入の目・節が千円の位まで一致 / summed: 財源の名前ごとの足し上げから求めた額 / residual: 合計からの差し引き
 */
export type GeneralFundBasis = 'revenue_kan' | 'matched' | 'summed' | 'residual';
export const GENERAL_FUND_BASES: readonly GeneralFundBasis[] = ['revenue_kan', 'matched', 'summed', 'residual'];

export interface GeneralFundRow {
  label: string;
  /** 円 */
  amount: number;
  basis: GeneralFundBasis;
  /** revenue_kan の款の番号 */
  kan?: number;
  /** 組み替えの元の歳入の目の ID */
  refs?: string[];
}

export interface GeneralFund {
  rows: GeneralFundRow[];
  /** 円。一般会計の歳出の目の財源内訳の一般財源の合計と一致する */
  total: number;
  /** 組み替えの説明（「データについて」に出す） */
  notes: string[];
  /** 説明書で確かめた日 */
  checked_on: string;
}

/** 施策別資料の事項の科目（予算の目）。row は予算の目の行の ID（予算にないときは null） */
export interface PolicyKamoku {
  kan: number;
  kou: number | null;
  moku: number;
  row: string | null;
  /** 資料の科目が予算の目にない（資料の印字のまま。項が読み分けられず、予算にその款・目の目がないときは kou が null） */
  unmatched?: true;
  /** 根拠を確かめて直した・決めた科目の、資料の読み（「10 7 2」。項が読み分けられないときは「9 ? 1」）。そのままならない */
  printed?: string;
  /** printed の科目の決め方。fix: 根拠を確かめた直しの表（額・内訳・節）。budget: 項が読み分けられず、予算にその款・目の目が1つだけ */
  resolved?: 'fix' | 'budget';
}

export interface PolicyItem {
  name: string;
  /** 柱の番号（4つの柱の外のグループ「計画推進の基盤づくり」（取組は地方分権の推進・行政改革の推進）は null） */
  pillar: number | null;
  /** 取組（施策別資料の区分） */
  initiative: string | null;
  /** 課名 */
  division: string;
  kamoku: PolicyKamoku[];
  /** 科目に「外」の印（ほかの科目にもまたがる） */
  other_kamoku?: true;
  /** 事項の額が科目の目の予算額を超える（資料の科目は1つだが、ほかの目にもまたがるとみられる。書き出しの OVER_MOKU_OK） */
  exceeds_moku?: true;
  /** 円 */
  amount: Yen;
  previous: Yen | null;
  is_new: boolean;
  notes: string[];
  source: { doc: string; page: number };
}

export interface LocalPolicies {
  pillars: { no: number; name: string }[];
  items: PolicyItem[];
  /**
   * special: 範囲から除いた事項（特別会計・公営企業会計）の件数と額。
   * debt_burden: 債務負担行為のある一般会計の事項（制度融資を除く）の件数と限度額の合計（事項の今年度の額は items に入る。
   * 今年度の額が 0 の事項は items に入らない。限度額は後年度にわたる額で入れない）
   */
  excluded: { special: { count: number; amount: Yen }; debt_burden: { count: number; amount: Yen } };
  /** 図に載らない経費（一般会計の歳出 − 施策の事項。最後の other は差し引き） */
  outside: { key: string; label: string; amount: Yen }[];
  /** 一般会計の歳出の合計（円） */
  expense_total: Yen;
  /** 施策別資料の PDF のファイル名 */
  source_docs: string[];
}

/** 基金の区分（財産に関する調書の行。現金・有価証券・一般会計貸付金・美術作品・備蓄物資など）。円 */
export interface FundHolding {
  kind: string;
  /** 前年度末現在高 */
  start: Yen;
  /** 決算年度中増減高 */
  change: Yen;
  /** 決算年度末現在高（3月31日） */
  end: Yen;
  /** 出納整理期間中増高（4〜5月） */
  closing_change: Yen;
  /** 出納閉鎖日現在高（5月31日） */
  after_closing: Yen;
}

export interface FundYearValue {
  /** 年度（西暦。2024 = 令和6年度） */
  year: number;
  /** 年度末現在高（円） */
  end: Yen;
  src: 'text' | 'ocr';
}

export interface FundItem {
  /** 「福岡県」を除いた名前（「財政調整基金」） */
  name: string;
  /** stock: 積立基金 / operating: 定額の資金を運用する基金 */
  kind: 'stock' | 'operating';
  /** 調書の番号（積立・運用それぞれの中の順） */
  no: number;
  holdings: FundHolding[];
  /** 区分の合計（年度末・出納閉鎖日） */
  end: Yen;
  after_closing: Yen;
  history: FundYearValue[];
  /** 改称前の名前（推移はつないである） */
  renamed_from?: string[];
  /** 調書の額がすべて「－」（OCR の年度は額の行がない） */
  no_figures?: true;
}

export interface FundTotals {
  year: number;
  fiscal_adjustment: Yen;
  debt_reduction: Yen;
  other: Yen;
  src: 'text' | 'ocr';
}

/** 基金の現在高（決算のファイルだけ。財産に関する調書。地方版の基金の設計） */
export interface LocalFunds {
  as_of: { year: number; label: string };
  items: FundItem[];
  /** 年度ごとの全基金の年度末現在高の合計（廃止した基金を含む） */
  totals: FundTotals[];
  /** 取り込んだ調書（年度・sources.json の id・テキストか OCR か） */
  /** partial: その年度の間に廃止した基金だけを取り込んだ調書（ほかの基金は次の年度の調書の前年度末） */
  statements: { year: number; label: string; source: string; src: 'text' | 'ocr'; partial?: true }[];
  notes: string[];
  checks: { signs_fixed: number; names_fixed: number };
}

export interface LocalBudgetFile {
  schema_version: typeof LOCAL_GOV_SCHEMA_VERSION;
  gov_id: string;
  year: number;
  year_label: string;
  basis: Basis;
  supplementary?: { round: string; kind: '定例' | '追加提案' | '専決'; bill_no?: string; date?: string };
  unit_source: '千円' | '円';
  accounts: Account[];
  rows: MokuRow[];
  /** 決算の歳入（会計 × 款）。決算の行は歳出の目だけなので、歳入はここに持つ */
  revenue_by_kan?: RevenueByKan[];
  checks: CheckSummary;
  /**
   * 一般会計の歳出の財源内訳の「一般財源」の中身（当初予算。組み替えを調べた年度だけ。一般財源の中身の設計）。
   * 補正後（composed）では外す（一般財源の額が変わる）。説明文だけ composed.funding_notes に残る
   */
  general_fund?: GeneralFund;
  /** 施策別資料の事項（当初予算だけ。バブル図）。補正後（composed）では外す */
  policies?: LocalPolicies;
  /** 基金の現在高と推移（決算のファイルだけ） */
  funds?: LocalFunds;
  /**
   * 補正後（当初 + Σ補正）として画面で組み立てたデータだけに付く（ファイルには書かない。app/lib/local-gov/supplement.ts）。
   * basis は 'initial' のまま（図の組み立ては当初と同じ）。rows の amount は補正後の額、before は当初の額
   */
  composed?: {
    through: string;
    rounds: { round: string; kind: string }[];
    /** 当初の general_fund.notes（財源内訳と歳入の款の違いの説明。補正後でも当てはまる。general_fund 自体は外す） */
    funding_notes?: string[];
  };
}

export interface SourceDocument {
  id: string;
  title: string;
  url: string;
  sha256: string;
  retrieved: string;
}

export interface LocalGovIndex {
  schema_version: typeof LOCAL_GOV_SCHEMA_VERSION;
  gov: {
    id: string;
    name: string;
    kind: 'prefecture' | 'municipality';
    population?: { value: number; as_of: string; source: string }[];
  };
  /** ファイルがあるデータだけ（latest = 当初 + Σ補正 は画面で組み立てるので書かない。共通 JSON 形式の設計 3.1・5章） */
  datasets: { year: number; label: string; basis: Basis; file: string; status: 'verified' | 'partial' }[];
  sources: SourceDocument[];
}

/** 画面用のグラフ。正規化データから画面で組み立てる（app/lib/local-gov/graph.ts。ファイルにはしない） */
export interface LocalGraph {
  schema_version: typeof LOCAL_GOV_SCHEMA_VERSION;
  gov_id: string;
  year: number;
  basis: 'initial' | 'latest' | 'settlement';
  /** 列の一覧。見方ごとに app/lib/local-gov/graph.ts が決める（例: 財源 / 款 / 項 / 目 / 事項） */
  columns: { key: string; label: string }[];
  nodes: { id: string; col: string; name: string; value: Yen; row?: string; flags?: string[] }[];
  edges: { source: string; target: string; value: Yen }[];
  /** gross: 総計。net: 純計（会計間の繰入れの重複を除いた額）。純計を計算しない間は省く */
  totals: { gross: Yen; net?: Yen };
}
