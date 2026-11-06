'use client';

/**
 * 地方版の正規化データ（public/data/local-gov/<自治体>/）を読む。
 * index.json（自治体の情報・データの一覧・資料の一覧）を読み、指定の年度・基準のデータファイルを読む。
 * グラフはデータから画面で組み立てる（app/lib/local-gov/graph.ts。設計書 2章の案 B）。
 */
import { useEffect, useState } from 'react';
import type { Basis, LocalBudgetFile, LocalGovIndex } from '@/types/local-gov';

export type LocalBudgetState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; index: LocalGovIndex; file: LocalBudgetFile };

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
        const candidates = index.datasets.filter(d => d.basis === basis);
        const ds = year !== undefined ? candidates.find(d => d.year === year) : candidates.at(-1);
        if (!ds) throw new Error('指定の年度のデータはありません');
        const fileRes = await fetch(`${base}/${ds.file}`);
        if (!fileRes.ok) throw new Error('データを読み込めませんでした');
        const file = (await fileRes.json()) as LocalBudgetFile;
        if (!cancelled) setState({ status: 'ready', index, file });
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
