'use client';

/**
 * 三基金の推移と見込み・財政の指標のファイル（index.json の fiscal が指す fiscal-indicators.json）を読む。
 * ファイルのない自治体は none（画面はその区画を出さない）。
 * 設計: docs/local-gov/tasks/20261128_1646_基金と財政の指標のタブの設計.md
 */
import { useEffect, useState } from 'react';
import { withBasePath } from '@/app/lib/local-gov/site-edition';
import { LOCAL_GOV_SCHEMA_VERSION, type LocalFiscalFile, type LocalGovIndex } from '@/types/local-gov';

export type LocalFiscalState =
  | { status: 'loading' }
  | { status: 'none' }
  | { status: 'error'; message: string }
  | { status: 'ready'; file: LocalFiscalFile; index: LocalGovIndex };

const GOV_ID = /^[a-z0-9-]+$/;
const FILE_NAME = /^[a-z0-9-]+\.json$/;

export function useLocalFiscal(gov: string): LocalFiscalState {
  const [state, setState] = useState<LocalFiscalState>({ status: 'loading' });
  useEffect(() => {
    if (!GOV_ID.test(gov)) {
      setState({ status: 'error', message: '自治体の指定が正しくありません' });
      return;
    }
    let cancelled = false;
    setState({ status: 'loading' });
    (async () => {
      try {
        const base = withBasePath(`/data/local-gov/${gov}`);
        const indexRes = await fetch(`${base}/index.json`);
        if (!indexRes.ok) throw new Error('この自治体のデータはまだありません');
        const index = (await indexRes.json()) as LocalGovIndex;
        // ファイルの名前は index から来るので、形を確かめてから URL に使う
        if (!index.fiscal || !FILE_NAME.test(index.fiscal)) {
          if (!cancelled) setState({ status: 'none' });
          return;
        }
        const res = await fetch(`${base}/${index.fiscal}`);
        if (!res.ok) throw new Error('財政の指標のデータを読み込めませんでした');
        const file = (await res.json()) as LocalFiscalFile;
        if (file.schema_version !== LOCAL_GOV_SCHEMA_VERSION) throw new Error('データの形式の版がこの画面と合いません');
        if (!cancelled) setState({ status: 'ready', file, index });
      } catch (e) {
        if (!cancelled) setState({ status: 'error', message: e instanceof Error ? e.message : String(e) });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [gov]);
  return state;
}
