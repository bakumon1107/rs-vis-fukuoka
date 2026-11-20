/**
 * 地方版の基金（/local/<自治体>/funds）の組み立て。純粋な関数だけ（画面・取得は持たない）。
 * 設計: docs/local-gov/tasks/20261120_1200_地方版の基金の設計.md
 *
 * 予算の積み立て・取り崩しを、名前で基金に結ぶ:
 * - 取り崩し: 一般会計の歳入の目「〇〇基金繰入金」（12款2項）・「〇〇基金特別会計繰入金」（会計としての基金。市町村振興基金）
 * - 積み立て: 一般会計の歳出の事項「〇〇基金積立金」・目「〇〇基金特別会計繰出金」（財政調整基金特別会計）
 * 一般会計との境目だけで数える（特別会計の中のやり取りは数えない。設計 7章の3）
 */
import type { FundItem, LocalBudgetFile, LocalFunds, Yen } from '@/types/local-gov';

export interface FundFlowRef {
  /** 目の行の ID */
  row: string;
  /** 予算の目・事項の名前 */
  label: string;
  amount: Yen;
}

export interface FundFlows {
  /** 基金の名前（「福岡県」を除く）→ 積み立て・取り崩し */
  byFund: Map<string, { deposit: FundFlowRef[]; withdraw: FundFlowRef[] }>;
}

const WITHDRAW_RE = /^(.+基金)(?:特別会計)?繰入金$/;
const DEPOSIT_ITEM_RE = /^(.+基金)積立金$/;
const DEPOSIT_MOKU_RE = /^(.+基金)特別会計繰出金$/;

/** 予算のファイル（一般会計）から、基金ごとの積み立て・取り崩しを集める。金額が読めない（null）ものは入れない */
export function fundFlows(file: LocalBudgetFile): FundFlows {
  const byFund: FundFlows['byFund'] = new Map();
  const at = (name: string) => {
    let e = byFund.get(name);
    if (!e) byFund.set(name, (e = { deposit: [], withdraw: [] }));
    return e;
  };
  for (const r of file.rows) {
    if (r.account !== 'general') continue;
    if (r.side === 'revenue') {
      const m = WITHDRAW_RE.exec(r.moku.name);
      if (m && r.amount.v != null) at(m[1]).withdraw.push({ row: r.id, label: r.moku.name, amount: r.amount.v });
      continue;
    }
    // 目そのものが「〇〇基金積立金」「〇〇基金特別会計繰出金」なら目の額で数える（額が読めた目だけ。事項はその内訳なので重ねない）
    const mm = DEPOSIT_ITEM_RE.exec(r.moku.name) ?? DEPOSIT_MOKU_RE.exec(r.moku.name);
    if (mm && r.amount.v != null) {
      at(mm[1]).deposit.push({ row: r.id, label: r.moku.name, amount: r.amount.v });
      continue;
    }
    // 事項: 数えた事項の内訳（parent が数えた事項）は重ねない。親が基金の名前でない事項（「基金積立金」）なら内訳を数える
    const counted = new Set<number>();
    (r.items ?? []).forEach((it, i) => {
      if (it.parent !== undefined && counted.has(it.parent)) return;
      const m = DEPOSIT_ITEM_RE.exec(it.name) ?? DEPOSIT_MOKU_RE.exec(it.name);
      if (m && it.amount.v != null) {
        at(m[1]).deposit.push({ row: r.id, label: it.name, amount: it.amount.v });
        counted.add(i);
      }
    });
  }
  return { byFund };
}

export interface FundRow {
  name: string;
  /** 決算の基金（なければ予算にだけある、決算の年度より後に設けた基金） */
  fund: FundItem | null;
  deposit: Yen;
  withdraw: Yen;
  refs: FundFlowRef[];
}

/** 決算の基金と予算の積み立て・取り崩しを並べる。決算の年度末現在高の多い順、予算にだけある基金は最後 */
export function fundRows(funds: LocalFunds, flows: FundFlows | null): FundRow[] {
  const sum = (xs: FundFlowRef[]) => xs.reduce((s, x) => s + x.amount, 0);
  const rows: FundRow[] = funds.items.map(f => {
    const fl = flows?.byFund.get(f.name);
    return { name: f.name, fund: f, deposit: fl ? sum(fl.deposit) : 0, withdraw: fl ? sum(fl.withdraw) : 0,
      refs: fl ? [...fl.deposit, ...fl.withdraw] : [] };
  });
  rows.sort((a, b) => (b.fund?.end ?? 0) - (a.fund?.end ?? 0));
  const known = new Set(funds.items.map(f => f.name));
  for (const [name, fl] of flows?.byFund ?? []) {
    if (known.has(name)) continue;
    rows.push({ name, fund: null, deposit: sum(fl.deposit), withdraw: sum(fl.withdraw), refs: [...fl.deposit, ...fl.withdraw] });
  }
  return rows;
}
