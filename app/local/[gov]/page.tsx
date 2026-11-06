'use client';

/**
 * 地方版のサンキー図（/local/<自治体>。例 /local/fukuoka-pref）。
 * 設計: docs/local-gov/tasks/20261106_1327_地方版サンキー図の画面とグラフの設計.md
 *
 * ページは状態（見方・選択。URL のクエリに持つ）とデータの読み込み・レイアウトだけを持つ。
 * グラフの組み立ては app/lib/local-gov（純粋関数）、描画は client/components/local-gov。
 */
import { Suspense, useCallback, useMemo } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import LoadingSpinner from '@/client/components/LoadingSpinner';
import { AppHeader } from '@/components/navigation/AppHeader';
import { SidePanelChrome } from '@/client/components/SidePanelChrome';
import { SIDE_PANEL_WIDTH_MAX, SIDE_PANEL_WIDTH_MIN, useSidePanel } from '@/client/hooks/useSidePanel';
import { useLocalBudget } from '@/client/hooks/useLocalBudget';
import { LocalSankeyChart } from '@/client/components/local-gov/LocalSankeyChart';
import { LocalDetailPanel } from '@/client/components/local-gov/LocalDetailPanel';
import { composeDisplay } from '@/app/lib/local-gov/graph-view';
import type { LocalGraphView } from '@/app/lib/local-gov/graph';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';

const VIEWS: { key: LocalGraphView; label: string; note: string }[] = [
  { key: 'general', label: '一般会計', note: '財源 → 款 → 項 → 目 → 事項' },
  { key: 'all', label: '全会計', note: '歳入の款 → 会計 → 款 → 項 → 目（総計。会計間の繰入れの重複を含む）' },
];

export default function LocalGovPage() {
  return (
    <Suspense fallback={<LoadingSpinner fullscreen />}>
      <LocalGovContent />
    </Suspense>
  );
}

function LocalGovContent() {
  const { gov } = useParams<{ gov: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const view: LocalGraphView = searchParams.get('view') === 'all' ? 'all' : 'general';
  const selectedId = searchParams.get('sel');
  const state = useLocalBudget(gov);
  const panel = useSidePanel({ side: 'right' });

  // 見方・選択は URL のクエリに持つ（共有できる）
  const setQuery = useCallback(
    (next: { view?: LocalGraphView; sel?: string | null }) => {
      const q = new URLSearchParams(searchParams.toString());
      if (next.view !== undefined) {
        q.set('view', next.view);
        q.delete('sel');
      }
      if (next.sel !== undefined) {
        if (next.sel) q.set('sel', next.sel);
        else q.delete('sel');
      }
      router.replace(`?${q.toString()}`, { scroll: false });
    },
    [router, searchParams]
  );

  const display = useMemo(
    () => (state.status === 'ready' ? composeDisplay(state.file, view, selectedId) : null),
    [state, view, selectedId]
  );
  const row = useMemo(
    () => (state.status === 'ready' && display?.row ? state.file.rows.find(r => r.id === display.row) ?? null : null),
    [state, display]
  );

  if (state.status === 'loading') return <LoadingSpinner fullscreen />;
  if (state.status === 'error') {
    return <p className="p-8 text-sm text-destructive">{state.message}</p>;
  }
  const { index, file } = state;
  const dataset = index.datasets.find(d => d.year === file.year && d.basis === file.basis);

  return (
    <div className="min-h-screen bg-mirai-surface">
      <AppHeader current="/" />
      <main className="px-4 pb-16 pt-4" style={{ marginRight: row ? panel.effectiveWidth + 24 : 0 }}>
        <div className="mb-3 flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <h1 className="text-xl font-bold">
            {index.gov.name} {dataset?.label ?? file.year_label}
            {file.basis === 'initial' ? '当初予算' : ''}
          </h1>
          <span className="text-sm text-mirai-text-muted">
            {view === 'general' ? '一般会計の歳出' : '全会計の歳出（総計）'} {formatBudgetFromYen(display?.graph.totals.gross ?? 0)}
          </span>
          <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">試作</span>
        </div>

        <div className="mb-3 flex flex-wrap items-center gap-2">
          {VIEWS.map(v => (
            <button
              key={v.key}
              type="button"
              onClick={() => setQuery({ view: v.key })}
              className={`rounded-full border px-3 py-1 text-sm ${view === v.key ? 'border-primary-accent bg-mirai-surface-teal font-bold' : 'border-mirai-border bg-card'}`}
              title={v.note}
            >
              {v.label}
            </button>
          ))}
          <span className="text-xs text-mirai-text-muted">{VIEWS.find(v => v.key === view)?.note}</span>
        </div>

        {/* 選択中の表示と、選択の解除（全部の流れを見る）を常に出す */}
        <div className="mb-2 flex min-h-8 flex-wrap items-center gap-2 text-sm">
          {display?.selected ? (
            <>
              <span>
                選択中: <b>{display.selected.name}</b>
              </span>
              <button
                type="button"
                className="rounded-full border border-mirai-border bg-card px-3 py-0.5 text-sm"
                onClick={() => setQuery({ sel: null })}
              >
                全部の流れを見る
              </button>
            </>
          ) : (
            <span className="text-mirai-text-muted">四角を押すと、その流れだけを表示します（款・項を選ぶと、その先の目・事項が開きます）</span>
          )}
          <span className="ml-auto text-xs text-mirai-text-muted">
            <span className="text-amber-700">※</span> 名前は読み取り（資料で裏付けが取れていない）
          </span>
        </div>

        <div className="overflow-x-auto rounded-2xl bg-card p-2 shadow-soft">
          {display && <LocalSankeyChart display={display} onSelect={id => setQuery({ sel: id === selectedId ? null : id })} />}
        </div>

        <p className="mt-3 text-xs text-mirai-text-muted">
          出典: {index.sources.filter(s => s.id.startsWith('r8-setsumeisho')).map(s => s.title).join('・')}（{index.gov.name}）。
          金額は説明書に印字された数字（千円単位）を円に直したもの。帯は推計せず、印字された数字の合計で描いています。
        </p>
      </main>

      {row && (
        <SidePanelChrome
          side="right"
          width={panel.effectiveWidth}
          minWidth={SIDE_PANEL_WIDTH_MIN}
          maxWidth={SIDE_PANEL_WIDTH_MAX}
          onResizeStart={panel.onResizeStart}
          isResizing={panel.isResizing}
          onResetWidth={panel.resetWidth}
        >
          <LocalDetailPanel row={row} index={index} />
        </SidePanelChrome>
      )}
    </div>
  );
}
