/**
 * 地方版の正規化データ（LocalBudgetFile）の検証。純粋関数（HTTP・React なし）。
 * 設計: docs/local-gov/tasks/20261106_0841_共通JSON形式の設計.md 6章
 *
 * 自治体のパイプラインが書き出したファイルを、共通の規則で確かめる。
 * どの自治体でも成り立つべき規則（型・ID・参照・行の中の合計）だけを置く。
 * 自治体固有の照合（予算書・計上額調との一致など）はパイプライン側（scripts/local-gov/<自治体>/）で行う。
 */
import {
  LOCAL_GOV_SCHEMA_VERSION,
  NAME_SOURCES,
  SETSU_NO_SOURCES,
  VALUE_SOURCES,
  type LocalBudgetFile,
  type MokuRow,
  type NameWithSource,
  type Value,
} from '@/types/local-gov';

export interface ValidationResult {
  errors: string[];
  /** 推定（src: inferred）の値の数。1つでもあれば index の status は partial でなければならない */
  inferredCount: number;
}

const BASES = ['initial', 'supplementary', 'settlement'];
const SIDES = ['revenue', 'expense'];

function vOf(x: Value | undefined): number | null {
  return x === undefined ? null : x.v;
}

function sumKnown(values: (Value | undefined)[]): number | null {
  let s = 0;
  for (const x of values) {
    const v = vOf(x);
    if (v === null) return null;
    s += v;
  }
  return s;
}

export function expectedRowId(row: Pick<MokuRow, 'account' | 'side' | 'kan' | 'kou' | 'moku'>): string {
  return `${row.account}/${row.side}/${row.kan.no}-${row.kou.no}-${row.moku.no}`;
}

export function validateBudgetFile(file: LocalBudgetFile): ValidationResult {
  const errors: string[] = [];
  let inferredCount = 0;
  const err = (msg: string) => errors.push(msg);

  if (file.schema_version !== LOCAL_GOV_SCHEMA_VERSION) {
    err(`schema_version が ${LOCAL_GOV_SCHEMA_VERSION} でない（${String(file.schema_version)}）`);
    return { errors, inferredCount };
  }
  if (!Number.isInteger(file.year)) err(`year が整数でない（${file.year}）`);
  if (!BASES.includes(file.basis)) err(`basis が不正（${file.basis}）`);
  if (file.basis === 'supplementary' && !file.supplementary) err('補正のファイルに supplementary（回・種別）がない');

  const accountIds = new Set<string>();
  for (const a of file.accounts) {
    if (accountIds.has(a.id)) err(`会計の ID が重複: ${a.id}`);
    accountIds.add(a.id);
  }

  const checkValue = (where: string, x: Value | undefined, required: boolean) => {
    if (x === undefined) {
      if (required) err(`${where}: 値がない`);
      return;
    }
    if (!VALUE_SOURCES.includes(x.src)) err(`${where}: 出典が不正（${String(x.src)}）`);
    if (x.src === 'inferred') inferredCount += 1;
    if (x.agree !== undefined && (!Number.isInteger(x.agree) || x.agree < 0)) {
      err(`${where}: 読み取りの一致の数が不正（${x.agree}）`);
    }
    if (x.v === null) {
      if (required) err(`${where}: 金額が不明（null）`);
      return;
    }
    if (!Number.isSafeInteger(x.v)) err(`${where}: 金額が整数でない（${x.v}）`);
  };

  // 名前の出典: 値が決まった中にあること。search（全文検索）なら見つかった資料（name_evidence）があること
  const checkName = (where: string, x: NameWithSource, required: boolean) => {
    if (required && !x.name) err(`${where}: 名前がない`);
    const ns = x.name_src;
    if (ns !== undefined && !NAME_SOURCES.includes(ns)) err(`${where}: 名前の出典が不正（${String(ns)}）`);
    if (ns === 'search' && !(x.name_evidence && x.name_evidence.length > 0 && x.name_evidence.every(s => !!s))) {
      err(`${where}: 全文検索で確かめた名前に、見つかった資料（name_evidence）がない`);
    }
  };

  const rowIds = new Set<string>();
  for (const row of file.rows) {
    const where = row.id;
    if (rowIds.has(row.id)) err(`目の ID が重複: ${row.id}`);
    rowIds.add(row.id);
    if (row.id !== expectedRowId(row)) err(`${where}: ID が款・項・目の番号と合わない（期待 ${expectedRowId(row)}）`);
    if (!accountIds.has(row.account)) err(`${where}: 会計 ${row.account} が accounts にない`);
    if (!SIDES.includes(row.side)) err(`${where}: side が不正（${row.side}）`);
    for (const level of ['kan', 'kou', 'moku'] as const) checkName(`${where} ${level}`, row[level], true);
    if (row.pages.length === 0) err(`${where}: 出典のページがない`);

    checkValue(`${where} amount`, row.amount, true);
    for (const k of ['previous', 'before', 'after', 'budget_current', 'carried_over', 'unused'] as const) {
      checkValue(`${where} ${k}`, row[k], false);
    }
    const amount = vOf(row.amount);

    if (row.funding) {
      const f = row.funding;
      for (const k of ['national', 'bond', 'other', 'general'] as const) checkValue(`${where} funding.${k}`, f[k], true);
      const s = sumKnown([f.national, f.bond, f.other, f.general]);
      if (s !== null && amount !== null && s !== amount) err(`${where}: 財源内訳の合計 ${s} ≠ 金額 ${amount}`);
    }
    if (row.items && row.items.length > 0) {
      row.items.forEach((it, i) => {
        checkValue(`${where} items[${i}]`, it.amount, true);
        checkName(`${where} items[${i}]`, it, false);
        if (it.parent !== undefined && (it.parent < 0 || it.parent >= row.items!.length || it.parent === i)) {
          err(`${where} items[${i}]: parent が不正（${it.parent}）`);
        }
      });
      const s = sumKnown(row.items.filter(it => it.parent === undefined).map(it => it.amount));
      if (s !== null && amount !== null && s !== amount) err(`${where}: 説明欄の事項の合計 ${s} ≠ 金額 ${amount}`);
    }
    if (row.setsu && row.setsu.length > 0) {
      row.setsu.forEach((st, i) => {
        checkValue(`${where} setsu[${i}]`, st.amount, true);
        checkName(`${where} setsu[${i}]`, st, false);
        if (st.no_src !== undefined && !SETSU_NO_SOURCES.includes(st.no_src)) {
          err(`${where} setsu[${i}]: 節番号の出典が不正（${String(st.no_src)}）`);
        }
        if (st.no === null && st.no_src !== undefined) err(`${where} setsu[${i}]: 番号がないのに番号の出典がある`);
        st.sub?.forEach((sb, j) => checkName(`${where} setsu[${i}].sub[${j}]`, sb, false));
      });
      const s = sumKnown(row.setsu.map(st => st.amount));
      if (s !== null && amount !== null && s !== amount) err(`${where}: 節の合計 ${s} ≠ 金額 ${amount}`);
    }
    if (file.basis === 'supplementary') {
      const b = vOf(row.before);
      const a = vOf(row.after);
      if (b === null || a === null) err(`${where}: 補正前の額・計がない`);
      else if (amount !== null && b + amount !== a) err(`${where}: 補正前 ${b} + 補正額 ${amount} ≠ 計 ${a}`);
    }
    if (file.basis === 'settlement') {
      const s = sumKnown([row.amount, row.carried_over, row.unused]);
      const bc = vOf(row.budget_current);
      if (s !== null && bc !== null && s !== bc) err(`${where}: 支出済 + 繰越 + 不用 ${s} ≠ 予算現額 ${bc}`);
    }
    if (row.transfer?.to_account && !accountIds.has(row.transfer.to_account)) {
      err(`${where}: 繰出し先の会計 ${row.transfer.to_account} が accounts にない`);
    }
  }

  if (file.checks.rows !== file.rows.length) err(`checks.rows ${file.checks.rows} ≠ 目の行数 ${file.rows.length}`);
  if (file.checks.all_ok > file.checks.rows) err(`checks.all_ok ${file.checks.all_ok} が rows を超える`);

  return { errors, inferredCount };
}

/** 会計・歳入歳出ごとの金額の合計（自治体のパイプライン側の照合や、グラフの生成で使う） */
export function totalsByAccount(file: LocalBudgetFile): Map<string, number> {
  const out = new Map<string, number>();
  for (const row of file.rows) {
    const k = `${row.account}/${row.side}`;
    out.set(k, (out.get(k) ?? 0) + (row.amount.v ?? 0));
  }
  return out;
}
