'use client';

/**
 * 地方版の正規化データ（public/data/local-gov/<自治体>/）を読む。
 * index.json（自治体の情報・データの一覧・資料の一覧）を読み、指定の年度・基準のデータファイルを読む。
 * 年度を指定しなければ、その基準の最後の項目（index は年度の古い順に並べる）。
 * グラフはデータから画面で組み立てる（app/lib/local-gov/graph.ts。設計書 2章の案 B）。
 */
import { useEffect, useState } from 'react';
import { LOCAL_GOV_SCHEMA_VERSION, type Basis, type LocalBudgetFile, type LocalGovIndex } from '@/types/local-gov';

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

/** 自治体 ID は英小文字・数字・ハイフンだけ（URL から来るのでパスに使う前に確かめる） */
const GOV_ID = /^[a-z0-9-]+$/;

export function useLocalBudget(gov: string, year?: number, basis: Basis = 'initial'): LocalBudgetState {
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
        const candidates = index.datasets.filter(d => d.basis === basis);
        const ds = year !== undefined ? candidates.find(d => d.year === year) : candidates.at(-1);
        if (!ds) throw new Error('指定の年度のデータはありません');
        const fileRes = await fetch(`${base}/${ds.file}`);
        if (!fileRes.ok) throw new Error('データを読み込めませんでした');
        const file = (await fileRes.json()) as LocalBudgetFile;
        if (file.schema_version !== LOCAL_GOV_SCHEMA_VERSION) throw new Error(VERSION_ERROR);
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
