/**
 * 地方版の正規化データ（LocalBudgetFile）の検証。純粋関数（HTTP・React なし）。
 * 設計: docs/local-gov/tasks/20261106_0841_共通JSON形式の設計.md 6章
 *
 * 自治体のパイプラインが書き出したファイルを、共通の規則で確かめる。
 * どの自治体でも成り立つべき規則（型・ID・参照・行の中の合計）だけを置く。
 * 自治体固有の照合（予算書・計上額調との一致など）はパイプライン側（scripts/local-gov/<自治体>/）で行う。
 */
import {
  GENERAL_FUND_BASES,
  LOCAL_GOV_SCHEMA_VERSION,
  NAME_SOURCES,
  SETSU_NO_SOURCES,
  VALUE_SOURCES,
  type LocalBudgetFile,
  type LocalGovIndex,
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

export function expectedRowId(row: Pick<MokuRow, 'account' | 'side' | 'kan' | 'kou' | 'moku' | 'enterprise_section'>): string {
  // 公営企業会計は款の番号が条（第3条 収益的・第4条 資本的）ごとに振り直されるので、条を ID に入れる
  if (row.enterprise_section) {
    const art = row.enterprise_section === '収益的' ? 3 : 4;
    return `${row.account}/${row.side}/${art}-${row.kan.no}-${row.kou.no}-${row.moku.no}`;
  }
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
    if (row.previous_only) {
      // 前年度にだけあった目は番号がない（ID は …-<款>-<項>-p<n>）
      const prefix = `${row.account}/${row.side}/${row.kan.no}-${row.kou.no}-p`;
      if (row.moku.no !== null || !row.id.startsWith(prefix) || !/^\d+$/.test(row.id.slice(prefix.length)))
        err(`${where}: 前年度のみの目の ID・番号が合わない（期待 ${prefix}<n>・番号 null）`);
      if (row.amount.v !== 0) err(`${where}: 前年度のみの目の本年度が 0 でない`);
    } else if (row.id !== expectedRowId(row)) err(`${where}: ID が款・項・目の番号と合わない（期待 ${expectedRowId(row)}）`);
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
        // 入れ子は1段まで、親は子より前（画面の詳細パネルは「親の事項 → 内訳」の1段で表示する）
        // 整数かを先に確かめる（小数の parent で配列を引くと undefined になり、検証そのものが例外で止まる）
        if (it.parent !== undefined && (!Number.isInteger(it.parent) || it.parent < 0 || it.parent >= i
            || row.items![it.parent].parent !== undefined)) {
          err(`${where} items[${i}]: parent が不正（${it.parent}。前にある親の事項（入れ子は1段まで）を指すこと）`);
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
        // 細節があるなら、その合計は節の額と一致する（細節の欠け・別の節への付け違いを見つける。R8 で実例）
        if (st.sub && st.sub.length > 0) {
          const ss = sumKnown(st.sub.map(sb => sb.amount));
          const sv = vOf(st.amount);
          if (ss !== null && sv !== null && ss !== sv) err(`${where} setsu[${i}]: 細節の合計 ${ss} ≠ 節の額 ${sv}`);
        }
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
    // 予算現額 = 支出済額 + 翌年度繰越額 + 不用額 は歳出だけ（歳入は収入済額と予算現額の差が増減額で、繰越・不用額がない）
    if (file.basis === 'settlement' && row.side === 'expense') {
      const s = sumKnown([row.amount, row.carried_over, row.unused]);
      const bc = vOf(row.budget_current);
      if (s !== null && bc !== null && s !== bc) err(`${where}: 支出済 + 繰越 + 不用 ${s} ≠ 予算現額 ${bc}`);
    }
    if (row.by_department && row.by_department.length > 0) {
      row.by_department.forEach((d, i) => {
        if (!d.name) err(`${where} by_department[${i}]: 部局の名前がない`);
        for (const k of ['amount', 'budget_current', 'carried_over', 'unused'] as const) {
          checkValue(`${where} by_department[${i}].${k}`, d[k], true);
        }
      });
      for (const k of ['amount', 'budget_current', 'carried_over', 'unused'] as const) {
        const s = sumKnown(row.by_department.map(d => d[k]));
        const want = vOf(row[k]);
        if (s !== null && want !== null && s !== want) err(`${where}: 部局の内訳の ${k} の合計 ${s} ≠ 目の値 ${want}`);
      }
    }
    if (row.transfer?.to_account && !accountIds.has(row.transfer.to_account)) {
      err(`${where}: 繰出し先の会計 ${row.transfer.to_account} が accounts にない`);
    }
  }

  (file.revenue_by_kan ?? []).forEach((r, i) => {
    const where = `revenue_by_kan[${i}] ${r.account} ${r.kan?.no}款`;
    if (!accountIds.has(r.account)) err(`${where}: 会計 ${r.account} が accounts にない`);
    checkName(`${where} kan`, r.kan, true);
    for (const k of ['amount', 'budget_current', 'assessed', 'deficit_loss', 'uncollected'] as const) checkValue(`${where} ${k}`, r[k], true);
    checkValue(`${where} overpaid`, r.overpaid, false);
    // 調定額 = 収入済額 − 過誤納金 + 不納欠損額 + 収入未済額
    const a = vOf(r.amount), d = vOf(r.deficit_loss), u = vOf(r.uncollected), s = vOf(r.assessed);
    const o = r.overpaid ? vOf(r.overpaid) : 0;
    if (a !== null && d !== null && u !== null && s !== null && o !== null && a - o + d + u !== s) {
      err(`${where}: 収入済 − 過誤納 + 不納欠損 + 収入未済 ${a - o + d + u} ≠ 調定額 ${s}`);
    }
  });
  if (file.revenue_by_kan && file.basis !== 'settlement') err('revenue_by_kan は決算のファイルだけ');

  // 一般財源の中身: 当初予算だけ。行の合計 = total = 一般会計の歳出の目の財源内訳の一般財源の合計。額は 0 以上の整数（円）
  const gf = file.general_fund;
  if (gf) {
    if (file.basis !== 'initial') err('general_fund は当初予算のファイルだけ');
    if (!Array.isArray(gf.notes) || gf.notes.some(n => typeof n !== 'string')) err('general_fund.notes が文字列の配列でない');
    gf.rows.forEach((r, i) => {
      if (!GENERAL_FUND_BASES.includes(r.basis)) err(`general_fund.rows[${i}]: basis が不正（${r.basis}）`);
      if (!Number.isInteger(r.amount) || r.amount < 0) err(`general_fund.rows[${i}] ${r.label}: 額が 0 以上の整数でない（${r.amount}）`);
      for (const id of r.refs ?? []) if (!rowIds.has(id)) err(`general_fund.rows[${i}] ${r.label}: 組み替えの元の目 ${id} がない`);
    });
    const sum = gf.rows.reduce((s, r) => s + r.amount, 0);
    if (sum !== gf.total) err(`general_fund: 行の合計 ${sum} ≠ total ${gf.total}`);
    // 一般財源の読めない（財源内訳がない・null の）一般会計の歳出の目は 0 円にせず誤りにする（足りない合計と照合して通さない）
    const expense = file.rows.filter(r => r.account === 'general' && r.side === 'expense');
    for (const r of expense) {
      if (r.funding?.general.v == null) err(`general_fund: ${r.id} の財源内訳の一般財源が読めない（一般財源の合計と照合できない）`);
    }
    const general = expense.reduce((s, r) => s + (r.funding?.general.v ?? 0), 0);
    if (gf.total !== general) err(`general_fund: total ${gf.total} ≠ 一般会計の歳出の財源内訳の一般財源の合計 ${general}`);
  }

  // 基金: 決算のファイルだけ。区分ごとに 前年度末 + 増減 = 年度末、年度末 + 出納整理 = 出納閉鎖日。基金の額 = 区分の合計。
  // 推移の決算年度の値 = 年度末。年度ごとの合計 = その年度の基金の推移の合計（今ある基金の分を含む。廃止した基金があるので ≧）
  const funds = file.funds;
  if (funds) {
    if (file.basis !== 'settlement') err('funds は決算のファイルだけ');
    const isYen = (n: unknown) => Number.isInteger(n);
    for (const f of funds.items) {
      for (const h of f.holdings) {
        if (![h.start, h.change, h.end, h.closing_change, h.after_closing].every(isYen)) err(`funds ${f.name} ${h.kind}: 額が整数でない`);
        if (h.start + h.change !== h.end) err(`funds ${f.name} ${h.kind}: 前年度末 + 増減 ≠ 年度末`);
        if (h.end + h.closing_change !== h.after_closing) err(`funds ${f.name} ${h.kind}: 年度末 + 出納整理 ≠ 出納閉鎖日`);
      }
      if (f.holdings.reduce((s, h) => s + h.end, 0) !== f.end) err(`funds ${f.name}: 区分の年度末の合計 ≠ end`);
      if (f.holdings.reduce((s, h) => s + h.after_closing, 0) !== f.after_closing) err(`funds ${f.name}: 区分の出納閉鎖日の合計 ≠ after_closing`);
      const last = f.history.find(h => h.year === funds.as_of.year);
      if (!last || last.end !== f.end) err(`funds ${f.name}: 推移の ${funds.as_of.year} 年度の値が年度末現在高と違う`);
      // 過年度の推移も1円単位の整数（合計の比較は ≧ なので、端数があっても通ってしまう）
      for (const h of f.history) if (!isYen(h.end) || h.end < 0) err(`funds ${f.name} ${h.year}: 推移の額が 0 以上の整数でない`);
    }
    for (const t of funds.totals) {
      if (![t.fiscal_adjustment, t.debt_reduction, t.other].every(n => isYen(n) && n >= 0)) {
        err(`funds.totals ${t.year}: 額が 0 以上の整数でない`);
      }
      const current = funds.items.reduce((s, f) => s + (f.history.find(h => h.year === t.year)?.end ?? 0), 0);
      if (t.fiscal_adjustment + t.debt_reduction + t.other < current) err(`funds.totals ${t.year}: 合計が今ある基金の推移の合計より小さい`);
    }
  }

  // 公営企業会計: 行には条（enterprise_section）がある。補填財源の内訳の合計 = 不足額 = 資本的支出 − 資本的収入
  for (const a of file.accounts) {
    const isEnterprise = a.kind === 'enterprise';
    if (!isEnterprise && a.enterprise) err(`会計 ${a.id}: 公営企業会計でないのに enterprise がある`);
    if (!isEnterprise) continue;
    const own = file.rows.filter(r => r.account === a.id);
    if (own.some(r => !r.enterprise_section)) err(`会計 ${a.id}: 条（enterprise_section）のない行がある`);
    const capital = (side: 'revenue' | 'expense') =>
      own.filter(r => r.enterprise_section === '資本的' && r.side === side).reduce((s, r) => s + (r.amount.v ?? 0), 0);
    const gap = capital('expense') - capital('revenue');
    const cs = a.enterprise?.capital_shortfall;
    if (gap > 0 && !cs) err(`会計 ${a.id}: 資本的収支の不足 ${gap} の補填財源がない`);
    if (cs) {
      const nonNeg = (v: number) => Number.isSafeInteger(v) && v >= 0;
      if (!nonNeg(cs.amount)) err(`会計 ${a.id}: 補填財源の不足額が 0 以上の整数でない（${cs.amount}）`);
      if (!cs.source?.source) err(`会計 ${a.id}: 補填財源の出典がない`);
      // JSON は型で守られないので、内訳がなくても落ちずに失敗として返す
      const items = Array.isArray(cs.items) ? cs.items : [];
      if (!Array.isArray(cs.items)) err(`会計 ${a.id}: 補填財源の内訳がない`);
      items.forEach((x, i) => {
        if (!x.name) err(`会計 ${a.id}: 補填財源の内訳 ${i} の名前がない`);
        if (!nonNeg(x.amount)) err(`会計 ${a.id}: 補填財源の内訳「${x.name}」の額が 0 以上の整数でない（${x.amount}）`);
      });
      const sum = items.reduce((s, x) => s + x.amount, 0);
      if (sum !== cs.amount || cs.amount !== gap) err(`会計 ${a.id}: 補填財源の内訳の合計 ${sum} / 不足額 ${cs.amount} / 資本的支出 − 収入 ${gap}`);
    }
  }
  for (const r of file.rows) {
    // 型は2つの値だけだが、JSON は型で守られない。ほかの値は ID の確かめで第4条に数えられて見逃されるので、ここで止める
    if (r.enterprise_section !== undefined && r.enterprise_section !== '収益的' && r.enterprise_section !== '資本的') {
      err(`${r.id}: 条（enterprise_section）が 収益的・資本的 のどちらでもない（${String(r.enterprise_section)}）`);
    }
    if (r.enterprise_section && !file.accounts.some(a => a.id === r.account && a.kind === 'enterprise')) {
      err(`${r.id}: 公営企業会計でない会計の行に条（enterprise_section）がある`);
    }
  }

  if (file.checks.rows !== file.rows.length) err(`checks.rows ${file.checks.rows} ≠ 目の行数 ${file.rows.length}`);
  if (file.checks.all_ok > file.checks.rows) err(`checks.all_ok ${file.checks.all_ok} が rows を超える`);

  return { errors, inferredCount };
}

/**
 * 予算のファイルと、自治体の index（資料の一覧・データの一覧）の突き合わせ。
 * 出典のページ（pages[].source）と、全文検索で確かめた名前の資料（name_evidence）が、資料の一覧にあること。
 * 画面は資料の一覧から PDF の URL を引くので、ない id があるとリンクが切れる。
 * fileName（ファイルの名前）で datasets の項目を特定する。同じ年度に補正が複数回あると、年度・基準だけでは決まらない
 */
export function validateAgainstIndex(file: LocalBudgetFile, index: LocalGovIndex, fileName: string): string[] {
  const errors: string[] = [];
  const ids = new Set(index.sources.map(s => s.id));
  if (file.gov_id !== index.gov.id) errors.push(`gov_id ${file.gov_id} が index の ${index.gov.id} と違う`);
  const ds = index.datasets.find(d => d.file === fileName);
  if (!ds) {
    errors.push(`index の datasets に ${fileName} がない`);
  } else if (ds.year !== file.year || ds.basis !== file.basis) {
    errors.push(`index の datasets の ${fileName} は ${ds.year}・${ds.basis} だが、ファイルは ${file.year}・${file.basis}`);
  } else if (ds.status === 'verified') {
    // verified と書けるのは、推定の値がなく、全検算が一致したときだけ（共通 JSON 形式の設計 3.1）
    const { inferredCount } = validateBudgetFile(file);
    if (inferredCount > 0) errors.push(`推定の値が ${inferredCount} 件あるのに、datasets の status が verified`);
    if (file.checks.all_ok < file.checks.rows) {
      errors.push(`全検算が一致しない目が ${file.checks.rows - file.checks.all_ok} 件あるのに、datasets の status が verified`);
    }
  }
  const checkEvidence = (where: string, ev: string[] | undefined) => {
    for (const id of ev ?? []) if (!ids.has(id)) errors.push(`${where}: 名前の資料 ${id} が index の sources にない`);
  };
  for (const a of file.accounts) {
    const src = a.enterprise?.capital_shortfall?.source?.source;
    if (src && !ids.has(src)) errors.push(`会計 ${a.id}: 補填財源の出典 ${src} が index の sources にない`);
  }
  for (const row of file.rows) {
    for (const p of row.pages) if (!ids.has(p.source)) errors.push(`${row.id}: 出典 ${p.source} が index の sources にない`);
    for (const level of ['kan', 'kou', 'moku'] as const) checkEvidence(`${row.id} ${level}`, row[level].name_evidence);
    row.items?.forEach((it, i) => checkEvidence(`${row.id} items[${i}]`, it.name_evidence));
    row.setsu?.forEach((s, i) => {
      checkEvidence(`${row.id} setsu[${i}]`, s.name_evidence);
      s.sub?.forEach((sb, j) => checkEvidence(`${row.id} setsu[${i}].sub[${j}]`, sb.name_evidence));
    });
  }
  for (const st of file.funds?.statements ?? []) {
    if (!ids.has(st.source)) errors.push(`funds: ${st.label} の調書 ${st.source} が index の sources にない`);
  }
  return errors;
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
