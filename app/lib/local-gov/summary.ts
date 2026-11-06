/**
 * 「データについて」ページに出す要約を、正規化データから集める。純粋関数（HTTP・React なし）。
 * 設計: docs/local-gov/tasks/20261106_1327_地方版サンキー図の画面とグラフの設計.md 4.2（LocalSourcesPage）
 */
import type { LocalBudgetFile, MokuRow, NameSource, Value, ValueSource } from '@/types/local-gov';

/** 画像で確かめて直した値（値の出典が correction のもの） */
export interface CorrectionEntry {
  row: string;
  /** 目の名前（款・項・目） */
  where: string;
  /** どの値か（本年度・財源 国庫支出金・節 18 など） */
  field: string;
  value: number | null;
  note?: string;
}

/** 名前の出典ごとの件数（款・項・目は目の行ごと、事項・節・細節は1件ずつ） */
export type NameSourceCounts = Record<'kan' | 'kou' | 'moku' | 'item' | 'setsu' | 'sub', Partial<Record<NameSource, number>>>;

const FUNDING_LABEL = { national: '国庫支出金', bond: '地方債', other: 'その他', general: '一般財源' } as const;

function whereOf(r: MokuRow) {
  return `${r.kan.name} ／ ${r.kou.name} ／ ${r.moku.name}`;
}

export function valueCorrections(file: LocalBudgetFile): CorrectionEntry[] {
  const out: CorrectionEntry[] = [];
  const push = (r: MokuRow, field: string, v: Value | undefined) => {
    if (v?.src === 'correction') out.push({ row: r.id, where: whereOf(r), field, value: v.v, note: v.note });
  };
  for (const r of file.rows) {
    push(r, '本年度', r.amount);
    push(r, '前年度', r.previous);
    if (r.funding) {
      for (const k of Object.keys(FUNDING_LABEL) as (keyof typeof FUNDING_LABEL)[]) push(r, `財源 ${FUNDING_LABEL[k]}`, r.funding[k]);
    }
    r.items?.forEach(it => push(r, `事項 ${it.name}`, it.amount));
    r.setsu?.forEach(s => push(r, `節 ${s.no ?? ''} ${s.name}`.replace(/\s+/g, ' '), s.amount));
  }
  return out;
}

/** 値の出典ごとの件数（目の本年度・前年度・財源・事項・節） */
export function valueSourceCounts(file: LocalBudgetFile): Partial<Record<ValueSource, number>> {
  const c: Partial<Record<ValueSource, number>> = {};
  const add = (v: Value | undefined) => {
    if (v) c[v.src] = (c[v.src] ?? 0) + 1;
  };
  for (const r of file.rows) {
    add(r.amount);
    add(r.previous);
    if (r.funding) Object.values(r.funding).forEach(add);
    r.items?.forEach(it => add(it.amount));
    r.setsu?.forEach(s => add(s.amount));
  }
  return c;
}

export function nameSourceCounts(file: LocalBudgetFile): NameSourceCounts {
  const c: NameSourceCounts = { kan: {}, kou: {}, moku: {}, item: {}, setsu: {}, sub: {} };
  const add = (level: keyof NameSourceCounts, src: NameSource | undefined) => {
    const k = src ?? 'ocr';
    c[level][k] = (c[level][k] ?? 0) + 1;
  };
  for (const r of file.rows) {
    add('kan', r.kan.name_src);
    add('kou', r.kou.name_src);
    add('moku', r.moku.name_src);
    r.items?.forEach(it => add('item', it.name_src));
    r.setsu?.forEach(s => {
      add('setsu', s.name_src);
      s.sub?.forEach(sb => add('sub', sb.name_src));
    });
  }
  return c;
}

/** 説明欄に事項が1つだけで金額が印字されていない目の数（事項に目の額を当てたもの） */
export function noAmountPrintedCount(file: LocalBudgetFile): number {
  return file.rows.filter(r => r.items?.some(it => it.no_amount_printed)).length;
}
