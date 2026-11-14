'use client';

/**
 * 地方版の正規化データ（public/data/local-gov/<自治体>/）を読む。
 * index.json（自治体の情報・データの一覧・資料の一覧）を読み、指定の年度・基準のデータファイルを読む。
 * 年度を指定しなければ、その基準で年度が最も新しい項目（pickDataset）。
 * グラフはデータから画面で組み立てる（app/lib/local-gov/graph.ts。設計書 2章の案 B）。
 */
import { useEffect, useState } from 'react';
import { composeLatest } from '@/app/lib/local-gov/supplement';
import { LOCAL_GOV_SCHEMA_VERSION, type Basis, type LocalBudgetFile, type LocalGovIndex } from '@/types/local-gov';

/** 画面で選ぶ基準。latest は 当初 + Σ補正（ファイルはなく、当初と同じ年度の補正のファイルから組み立てる） */
export type BasisChoice = Basis | 'latest';

const VERSION_ERROR = 'データの形式の版がこの画面と合いません（画面かデータの更新が必要です）';

export type LocalDataset = LocalGovIndex['datasets'][number];

export type LocalBudgetState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  /** dataset: 読んだファイルの datasets の項目（年度・基準で探し直すと、同じ年度の補正が複数回あるときに取り違える） */
  | { status: 'ready'; index: LocalGovIndex; dataset: LocalDataset; file: LocalBudgetFile };

/** URL のクエリの年度（西暦4桁）。なければ・形が違えば undefined（最新の年度を読む） */
export function yearFromQuery(v: string | null): number | undefined {
  return v && /^\d{4}$/.test(v) ? Number(v) : undefined;
}

/**
 * 読むデータの一覧の項目を選ぶ。年度の指定がなければ、その基準で年度が最も新しいもの（index.json の並び順には頼らない）
 */
export function pickDataset(index: LocalGovIndex, basis: Basis, year?: number): LocalDataset | undefined {
  const candidates = index.datasets.filter(d => d.basis === basis);
  if (year !== undefined) return candidates.find(d => d.year === year);
  return candidates.reduce<LocalDataset | undefined>((best, d) => (!best || d.year > best.year ? d : best), undefined);
}

/**
 * 補正後（latest）に使う、当初と同じ年度の補正のファイルの一覧（古い順）。回の順はファイル名の末尾の番号
 * （budget-<年度>-supplementary-<回>.json）で決める（index.json の並び順には頼らない）
 */
export function supplementDatasets(index: LocalGovIndex, year: number): LocalDataset[] {
  const no = (d: LocalDataset) => Number(/-(\d+)\.json$/.exec(d.file)?.[1] ?? 0);
  return index.datasets.filter(d => d.basis === 'supplementary' && d.year === year).sort((a, b) => no(a) - no(b));
}

/** 自治体 ID は英小文字・数字・ハイフンだけ（URL から来るのでパスに使う前に確かめる） */
const GOV_ID = /^[a-z0-9-]+$/;

export function useLocalBudget(gov: string, year?: number, basis: BasisChoice = 'initial'): LocalBudgetState {
  const [state, setState] = useState<LocalBudgetState>({ status: 'loading' });

  useEffect(() => {
    if (!GOV_ID.test(gov)) {
      setState({ status: 'error', message: '自治体の指定が正しくありません' });
      return;
    }
    let cancelled = false;
    setState({ status: 'loading' });
    (async () => {
      try {
        const base = `/data/local-gov/${gov}`;
        const indexRes = await fetch(`${base}/index.json`);
        if (!indexRes.ok) throw new Error('この自治体のデータはまだありません');
        const index = (await indexRes.json()) as LocalGovIndex;
        // 知らない版の形は読み違えるので、表示を止めて知らせる（共通 JSON 形式の設計 3章）
        if (index.schema_version !== LOCAL_GOV_SCHEMA_VERSION) throw new Error(VERSION_ERROR);
        // 補正後は当初のデータ（同じ年度）に補正を足して作る。dataset は当初の項目（年度のラベル・検算の状態）
        const ds = pickDataset(index, basis === 'latest' ? 'initial' : basis, year);
        if (!ds) throw new Error('指定の年度のデータはありません');
        const load = async (name: string) => {
          const res = await fetch(`${base}/${name}`);
          if (!res.ok) throw new Error('データを読み込めませんでした');
          const f = (await res.json()) as LocalBudgetFile;
          if (f.schema_version !== LOCAL_GOV_SCHEMA_VERSION) throw new Error(VERSION_ERROR);
          return f;
        };
        let file: LocalBudgetFile;
        if (basis === 'latest') {
          const sups = supplementDatasets(index, ds.year);
          if (sups.length === 0) throw new Error('この年度の補正予算のデータはありません');
          // 当初と補正のファイルは一覧から分かるので、まとめて読む
          const [init, ...supFiles] = await Promise.all([ds, ...sups].map(d => load(d.file)));
          file = composeLatest(init, supFiles);
        } else {
          file = await load(ds.file);
        }
        if (!cancelled) setState({ status: 'ready', index, dataset: ds, file });
      } catch (e) {
        if (!cancelled) setState({ status: 'error', message: e instanceof Error ? e.message : String(e) });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [gov, year, basis]);

  return state;
}
