'use client';

/**
 * 地方版のサンキー図（/local/<自治体>。例 /local/fukuoka-pref）。
 * 設計: docs/local-gov/tasks/20261106_1327_地方版サンキー図の画面とグラフの設計.md
 *
 * ページは状態（年度・見方・選択。URL のクエリに持つ）とデータの読み込み・レイアウトだけを持つ。
 * グラフの組み立ては app/lib/local-gov（純粋関数）、描画は client/components/local-gov。
 */
import Link from 'next/link';
import { Suspense, useCallback, useMemo } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import LoadingSpinner from '@/client/components/LoadingSpinner';
import { AppHeader } from '@/components/navigation/AppHeader';
import { SidePanelChrome } from '@/client/components/SidePanelChrome';
import { SIDE_PANEL_WIDTH_MAX, SIDE_PANEL_WIDTH_MIN, useSidePanel } from '@/client/hooks/useSidePanel';
import { useLocalBudget, yearFromQuery } from '@/client/hooks/useLocalBudget';
import { useIsNarrow } from '@/client/hooks/useMediaQuery';
import { LocalSankeyChart } from '@/client/components/local-gov/LocalSankeyChart';
import { LocalDetailPanel } from '@/client/components/local-gov/LocalDetailPanel';
import { composeDisplay } from '@/app/lib/local-gov/graph-view';
import { sourcesUsed } from '@/app/lib/local-gov/summary';
import type { LocalGraphView } from '@/app/lib/local-gov/graph';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';

// opens: 選んだときに開く列の案内（graph-view.ts の selectionToFilter の深さ。設計書 4.3）
const VIEWS: { key: LocalGraphView; label: string; note: string; opens: string }[] = [
  { key: 'general', label: '一般会計', note: '財源 → 款 → 項 → 目 → 事項', opens: '財源・款を選ぶと目、項・目・事項を選ぶと事項まで開きます' },
  {
    key: 'all',
    label: '全会計',
    note: '歳入の款 → 会計 → 款 → 項 → 目（総計。会計間の繰入れの重複を含む）',
    opens: '会計を選ぶと項、款・項・目を選ぶと目まで開きます',
  },
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
  // 年度（西暦）。なければ最新の年度
  const year = yearFromQuery(searchParams.get('year'));
  const state = useLocalBudget(gov, year);
  const panel = useSidePanel({ side: 'right' });
  const isNarrow = useIsNarrow();

  // 年度・見方・選択は URL のクエリに持つ（共有できる）
  const setQuery = useCallback(
    (next: { year?: number; view?: LocalGraphView; sel?: string | null }) => {
      const q = new URLSearchParams(searchParams.toString());
      if (next.year !== undefined) {
        q.set('year', String(next.year));
        q.delete('sel');
      }
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
  // 出典は、この年度のデータの目が参照している資料（年度ごとに資料が違う）。全目をなめるので、データが変わったときだけ求める
  // （パネルの幅を変えている間はページが描き直され続ける）
  const sourceTitles = useMemo(() => {
    if (state.status !== 'ready') return '';
    const used = new Set(sourcesUsed(state.file));
    return state.index.sources.filter(s => used.has(s.id)).map(s => s.title).join('・');
  }, [state]);

  if (state.status === 'loading') return <LoadingSpinner fullscreen />;
  if (state.status === 'error') {
    // ヘッダーは固定で重なるので、エラーのときも AppHeader を置いて下の余白を作る（ないと文言がヘッダーに隠れる）
    return (
      <div className="min-h-screen bg-mirai-surface">
        <AppHeader current="/" />
        <p className="px-4 pt-4 text-sm text-destructive">{state.message}</p>
      </div>
    );
  }
  const { index, dataset, file } = state;
  // 年度の切り替え（同じ基準のデータが2年度以上あるときだけ出す）
  const years = [...new Set(index.datasets.filter(d => d.basis === dataset.basis).map(d => d.year))];

  return (
    <div className="min-h-screen bg-mirai-surface">
      <AppHeader current="/" />
      {/* 横のパネルの分だけ右を空ける。狭い幅ではパネルは画面の下から出るので空けない（空けると本文の幅がなくなり、見出しが縦に1字ずつになる） */}
      <main className="px-4 pb-16 pt-4" style={{ marginRight: row && !isNarrow ? panel.effectiveWidth + 24 : 0 }}>
        <div className="mb-3 flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <h1 className="text-xl font-bold">
            {index.gov.name} {dataset.label}
            {file.basis === 'initial' ? '当初予算' : ''}
          </h1>
          <span className="text-sm text-mirai-text-muted">
            {/* 公営企業会計は全会計の見方に描かない（歳入と歳出が一致しない様式。設計書 3.2）ので、いつも「除く」と示す */}
            {view === 'general' ? '一般会計の歳出' : '全会計の歳出（総計・公営企業会計を除く）'}{' '}
            {formatBudgetFromYen(display?.graph.totals.gross ?? 0)}
          </span>
          <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">試作</span>
        </div>

        <div className="mb-3 flex flex-wrap items-center gap-2">
          {years.length > 1 && (
            <select
              aria-label="年度"
              value={file.year}
              onChange={e => setQuery({ year: Number(e.target.value) })}
              className="rounded-full border border-mirai-border bg-card px-3 py-1 text-sm"
            >
              {years.map(y => (
                <option key={y} value={y}>
                  {index.datasets.find(d => d.year === y && d.basis === dataset.basis)?.label ?? y}
                </option>
              ))}
            </select>
          )}
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
          <span className="text-xs text-mirai-text-muted">
            {VIEWS.find(v => v.key === view)?.note}
            {view === 'all' && '。公営企業会計は含みません'}
          </span>
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
              {display.note && <span className="text-xs text-mirai-text-muted">{display.note}</span>}
            </>
          ) : (
            <span className="text-mirai-text-muted">四角を押すと、その流れだけを表示します（{VIEWS.find(v => v.key === view)?.opens}）</span>
          )}
          <span className="ml-auto text-xs text-mirai-text-muted">
            <span className="text-amber-700">※</span> 名前は読み取り（資料で裏付けが取れていない）
          </span>
        </div>

        <div className="overflow-x-auto rounded-2xl bg-card p-2 shadow-soft">
          {display && <LocalSankeyChart display={display} onSelect={id => setQuery({ sel: id === selectedId ? null : id })} />}
        </div>

        <p className="mt-3 text-xs text-mirai-text-muted">
          出典: {sourceTitles}（{index.gov.name}）。
          {file.unit_source === '千円' ? '金額は資料に印字された数字（千円単位）を円に直したもの。' : '金額は資料に印字された数字（円単位）。'}帯は推計せず、印字された数字の合計で描いています。{' '}
          <Link href={`/local/${gov}/about?year=${file.year}`}className="text-primary-accent underline">
            データについて（検算の方法と結果・資料の一覧）
          </Link>
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
          <LocalDetailPanel
            row={row}
            index={index}
            accountName={file.accounts.find(a => a.id === row.account)?.name ?? row.account}
          />
        </SidePanelChrome>
      )}
    </div>
  );
}
