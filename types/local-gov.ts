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
}

/** 説明欄の ○事項 */
export interface Item {
  name: string;
  amount: Value;
  /** 入れ子の内訳は親の添字（items 配列の中の位置） */
  parent?: number;
  /** 「職員費 293人」の人数 */
  headcount?: number;
  /** 1事項で金額の記載なし（目の額を当てた） */
  no_amount_printed?: boolean;
  links?: { kind: '施策別資料' | '行政評価'; id: string; match: 'amount+name' | 'name' }[];
}

export interface Setsu {
  no: number;
  name: string;
  amount: Value;
  sub?: { name: string; amount: Value }[];
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
  moku: NumberedName;
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
  /** 会計間の繰出し・繰入れ（純計で重複を除くための印） */
  transfer?: { to_account?: string; from_account?: string };
  /** 「○○課所管」「事業費支弁職員 2人」などの注記 */
  notes?: string[];
  pages: { source: string; page: number }[];
}

export interface CheckSummary {
  rows: number;
  all_ok: number;
  rules: Record<string, number>;
  external?: Record<string, string>;
  readings?: { agree_2plus: number };
  corrections?: number;
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
  checks: CheckSummary;
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
  datasets: { year: number; label: string; basis: Basis | 'latest'; file: string; status: 'verified' | 'partial' }[];
  sources: SourceDocument[];
}

/** 画面用のグラフ（graph-<年度>-<基準>.json） */
export interface LocalGraph {
  schema_version: typeof LOCAL_GOV_SCHEMA_VERSION;
  gov_id: string;
  year: number;
  basis: 'initial' | 'latest' | 'settlement';
  /** 列はデータ側で定義する（例: 財源 / 会計 / 款 / 項 / 目 / 事項） */
  columns: { key: string; label: string }[];
  nodes: { id: string; col: string; name: string; value: Yen; row?: string; flags?: string[] }[];
  edges: { source: string; target: string; value: Yen }[];
  totals: { gross: Yen; net: Yen };
}
