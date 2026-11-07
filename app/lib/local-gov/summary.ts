/**
 * 「データについて」ページに出す要約を、正規化データから集める。純粋関数（HTTP・React なし）。
 * 設計: docs/local-gov/tasks/20261106_1327_地方版サンキー図の画面とグラフの設計.md 4.2（app/local/[gov]/about/page.tsx が使う）
 */
import type { LocalBudgetFile, MokuRow, NameSource, Value, ValueSource } from '@/types/local-gov';
import { FUNDING_KINDS } from './graph';

/** 確定した読み取り（ocr・text）以外の出典の値（画像で確認・文字層・空欄を 0 とみなした・推定） */
export interface ValueNoteEntry {
  row: string;
  /** 会計・歳入出・款・項・目 */
  where: string;
  /** どの値か（本年度・財源 国庫支出金・節 18・細節 普通旅費 など） */
  field: string;
  value: number | null;
  src: ValueSource;
  note?: string;
}

/** 名前の出典ごとの件数（款・項・目は目の行ごと、事項・節・細節は1件ずつ） */
export type NameSourceCounts = Record<'kan' | 'kou' | 'moku' | 'item' | 'setsu' | 'sub', Partial<Record<NameSource, number>>>;


function whereOf(file: LocalBudgetFile, r: MokuRow) {
  const acc = file.accounts.find(a => a.id === r.account)?.name ?? r.account;
  return `${acc} ／ ${r.side === 'revenue' ? '歳入' : '歳出'} ／ ${r.kan.name} ／ ${r.kou.name} ／ ${r.moku.name}`;
}

/**
 * 確定した読み取り以外の出典の値をすべて集める（設計書 4.4）。歳入の目の値のように、図からも詳細パネルからも見られない値があるので、
 * 「データについて」で一覧にして、どの値が画像で確認・空欄を 0 とみなした などかを示す
 */
export function valueNotes(file: LocalBudgetFile): ValueNoteEntry[] {
  const out: ValueNoteEntry[] = [];
  const push = (r: MokuRow, field: string, v: Value | undefined) => {
    if (v && v.src !== 'ocr' && v.src !== 'text') {
      out.push({ row: r.id, where: whereOf(file, r), field, value: v.v, src: v.src, note: v.note });
    }
  };
  for (const r of file.rows) {
    push(r, '本年度', r.amount);
    push(r, '前年度', r.previous);
    if (r.funding) {
      for (const f of FUNDING_KINDS) push(r, `財源 ${f.label}`, r.funding[f.key]);
    }
    r.items?.forEach(it => push(r, `事項 ${it.name}`, it.amount));
    r.setsu?.forEach(s => {
      push(r, `節 ${s.no ?? ''} ${s.name}`.replace(/\s+/g, ' '), s.amount);
      s.sub?.forEach(sb => push(r, `細節 ${sb.name}`, sb.amount));
    });
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

/** 本年度の計上がない目（0 円・空欄）。図には箱を出さないので、「データについて」に一覧で出す（設計書 3.2） */
export function zeroAmountRows(file: LocalBudgetFile): MokuRow[] {
  return file.rows.filter(r => (r.amount.v ?? 0) === 0);
}

/** 目の行の出典（pages[].source）に出てくる資料の id（出てきた順）。画面の「出典」に出す資料を、年度に依らず決める */
export function sourcesUsed(file: LocalBudgetFile): string[] {
  return [...new Set(file.rows.flatMap(r => r.pages.map(p => p.source)))];
}

/** 説明欄に事項が1つだけで金額が印字されていない目の数（事項に目の額を当てたもの） */
export function noAmountPrintedCount(file: LocalBudgetFile): number {
  return file.rows.filter(r => r.items?.some(it => it.no_amount_printed)).length;
}
