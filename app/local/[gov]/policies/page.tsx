'use client';

/**
 * 地方版の施策のバブル図（/local/<自治体>/policies）。当初予算の施策別資料の事項を、県の総合計画の柱・取組で入れ子の円にする。
 * 設計: docs/local-gov/tasks/20261120_1500_地方版バブル図の設計.md 6章
 *
 * ページは読み込み・状態（色・外す・寄る・選ぶ）・レイアウトだけを持つ。組み立ては app/lib/local-gov/policies.ts、
 * 描画は client/components/local-gov。施策別資料は当初予算だけなので、当初予算の最新の年度を読む（補正後・決算では出さない。設計 3章）
 */
import Link from 'next/link';
import { Suspense, useMemo, useState } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import LoadingSpinner from '@/client/components/LoadingSpinner';
import { AppHeader } from '@/components/navigation/AppHeader';
import { useLocalBudget, yearFromQuery } from '@/client/hooks/useLocalBudget';
import { PolicyBubbleChart } from '@/client/components/local-gov/PolicyBubbleChart';
import { PolicyDetail } from '@/client/components/local-gov/PolicyDetail';
import {
  BIG_ITEM_YEN,
  OUTSIDE_PILLAR_NAME,
  POLICIES_KEY,
  bigItems,
  colorScheme,
  focusPath,
  initiativeLeaves,
  initiativeTotals,
  kanNames,
  policyTree,
  sourceForDoc,
} from '@/app/lib/local-gov/policies';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';

export default function LocalPoliciesPage() {
  return (
    <Suspense fallback={<LoadingSpinner fullscreen />}>
      <LocalPoliciesContent />
    </Suspense>
  );
}

type ColorMode = 'pillar' | 'kan';

function LocalPoliciesContent() {
  const { gov } = useParams<{ gov: string }>();
  // 年度は URL の year（サンキー図から渡す）。なければ当初予算の最新の年度
  const searchParams = useSearchParams();
  const state = useLocalBudget(gov, yearFromQuery(searchParams.get('year')), 'initial');
  const [colorMode, setColorMode] = useState<ColorMode>('pillar');
  const [hideBig, setHideBig] = useState(false);
  const [focus, setFocus] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [selectedOutside, setSelectedOutside] = useState<string | null>(null);

  const file = state.status === 'ready' ? state.file : null;
  const policies = file?.policies ?? null;
  const big = useMemo(() => (policies ? bigItems(policies) : new Set<number>()), [policies]);
  const hidden = hideBig ? big : null;
  const tree = useMemo(() => (policies ? policyTree(policies, hidden ?? undefined) : null), [policies, hidden]);
  const kans = useMemo(() => (file ? kanNames(file) : new Map<number, string>()), [file]);
  const scheme = useMemo(() => (policies ? colorScheme(policies, colorMode, kans) : null), [policies, colorMode, kans]);
  const totals = useMemo(() => (policies ? initiativeTotals(policies, hidden ?? undefined) : []), [policies, hidden]);

  if (state.status === 'loading') return <LoadingSpinner fullscreen />;
  if (state.status === 'error') {
    // ヘッダーは固定で重なるので、エラーのときも AppHeader を置いて下の余白を作る（ないと文言がヘッダーに隠れる。サンキー図のページと同じ）
    return (
      <div className="min-h-screen bg-mirai-surface">
        <AppHeader current="/" />
        <p className="px-4 pt-4 text-sm text-destructive">読み込めませんでした: {state.message}</p>
      </div>
    );
  }
  if (!policies || !tree || !scheme || !file) {
    return (
      <div className="min-h-screen bg-mirai-surface">
        <AppHeader current="/" />
        <p className="px-4 pt-4 text-sm">この自治体・年度の施策のデータはまだありません。</p>
      </div>
    );
  }

  const { index, dataset } = state;
  const inPolicies = policies.items.reduce((s, i) => s + i.amount, 0);
  const outsideTotal = policies.outside.reduce((s, o) => s + o.amount, 0);
  const bigTotal = [...big].reduce((s, i) => s + policies.items[i].amount, 0);
  const item = selected !== null ? policies.items[selected] ?? null : null;
  const outsideItem = selectedOutside ? policies.outside.find(o => o.key === selectedOutside) ?? null : null;

  // 寄っている円の道すじ（全体 › 施策 › 柱 › 取組）。寄り先が木にない（外した事項だけの取組など）ときは全体として扱う（図も全体に戻る）
  const path = focus ? focusPath(tree, focus) : null;
  const crumbs: { key: string | null; label: string }[] = [{ key: null, label: '全体' }, ...(path ?? [])];
  const focusedInitiative = path && focus?.startsWith('i:') ? focus : null;
  const initiativeItems = focusedInitiative ? initiativeLeaves(tree, focusedInitiative) : [];

  const select = (i: number, ik: string) => {
    setSelected(i === selected ? null : i);
    setSelectedOutside(null);
    // 取組の外から押したら、その取組に寄る（中の事項の名前が読める大きさにする）
    if (ik && focus !== ik) setFocus(ik);
  };
  const sourceOf = (doc: string) => sourceForDoc(index.sources, doc);
  // サンキー図へ戻るときは同じ年度の当初予算を開く
  const sankeyHref = `/local/${gov}?year=${file.year}`;

  return (
    <div className="min-h-screen bg-mirai-surface">
      <AppHeader current="/" />
      <main className="mx-auto max-w-6xl space-y-4 px-4 pb-16 pt-4 text-mirai-text">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <h1 className="text-xl font-bold">
            {index.gov.name} {dataset.label}当初予算 施策のバブル図
          </h1>
          <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">試作</span>
          <Link href={sankeyHref} className="text-sm text-primary-accent underline">
            予算・決算の流れ（サンキー図）へ
          </Link>
        </div>
        <p className="text-sm">
          一般会計の歳出 {formatBudgetFromYen(policies.expense_total)} のうち、編成概要の施策別資料に載る事項 {policies.items.length} 件
          （計 <b>{formatBudgetFromYen(inPolicies)}</b>）を、県の総合計画の柱と取組で分けて円にしました。円の面積が予算額です。
          施策別資料に載らない経費 {formatBudgetFromYen(outsideTotal)} は灰色の円です（同じ縮尺）。
          円を押すとその円に寄り、事項を押すと内容を出します。
        </p>

        <div className="flex flex-wrap items-center gap-2 text-sm">
          <div role="group" aria-label="色の分け方" className="flex overflow-hidden rounded-full border border-mirai-border">
            {(['pillar', 'kan'] as const).map(m => (
              <button
                key={m}
                type="button"
                aria-pressed={colorMode === m}
                onClick={() => setColorMode(m)}
                className={`px-3 py-1 ${colorMode === m ? 'bg-primary-accent font-bold text-white' : 'bg-card'}`}
              >
                {m === 'pillar' ? '柱で色分け' : '款で色分け'}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-1 rounded-full border border-mirai-border bg-card px-3 py-1">
            <input
              type="checkbox"
              checked={hideBig}
              onChange={e => {
                setHideBig(e.target.checked);
                if (selected !== null && e.target.checked && big.has(selected)) setSelected(null);
                // 外すと施策の円が灰色の円に比べて小さくなるので、施策の円に寄って小さな事項を見やすくする
                // 寄っていた円（取組など）が外した後になくなるときも、施策の円に寄り直す（寄り先を残すと、外すのをやめたときに前の円へ跳ぶ）
                if (e.target.checked && (focus === null || !focusPath(policyTree(policies, big), focus))) setFocus(POLICIES_KEY);
              }}
            />
            {BIG_ITEM_YEN / 100_000_000}億円以上の事項（{big.size} 件・計 {formatBudgetFromYen(bigTotal)}）を外す
          </label>
        </div>

        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs" aria-label="色の凡例">
          {scheme.legend.map(l => (
            <li key={l.key} className="flex items-center gap-1">
              <span className="inline-block h-3 w-3 rounded-full" style={{ background: l.color }} aria-hidden />
              {l.label}
            </li>
          ))}
          <li className="flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded-full bg-slate-400/60" aria-hidden />
            施策別資料に載らない経費
          </li>
        </ul>

        {hideBig && (
          <p className="text-xs text-mirai-text-muted">
            外した事項: {[...big].map(i => `${policies.items[i].name} ${formatBudgetFromYen(policies.items[i].amount)}`).join('・')}
          </p>
        )}

        <nav aria-label="寄っている円" className="flex flex-wrap items-center gap-1 text-sm">
          {crumbs.map((c, i) => (
            <span key={c.key ?? 'all'} className="flex items-center gap-1">
              {i > 0 && <span className="text-mirai-text-muted">›</span>}
              {i === crumbs.length - 1 ? (
                <b>{c.label}</b>
              ) : (
                <button type="button" className="text-primary-accent underline" onClick={() => setFocus(c.key)}>
                  {c.label}
                </button>
              )}
            </span>
          ))}
        </nav>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <div className="rounded-2xl bg-card p-2 shadow-soft">
            <PolicyBubbleChart
              tree={tree}
              outside={policies.outside}
              colorOf={scheme.colorOf}
              focus={focus}
              onFocus={setFocus}
              selected={selected}
              onSelect={select}
              selectedOutside={selectedOutside}
              onOutside={k => {
                setSelectedOutside(k === selectedOutside ? null : k);
                setSelected(null);
              }}
            />
          </div>

          <aside className="space-y-3">
            {item && selected !== null && (
              <PolicyDetail item={item} gov={gov} kanNames={kans} file={file} source={sourceOf(item.source.doc)} onClose={() => setSelected(null)} />
            )}
            {outsideItem && (
              <section className="space-y-1 rounded-2xl bg-card p-3 text-sm shadow-soft">
                <h2 className="font-bold">{outsideItem.label}</h2>
                <p>{formatBudgetFromYen(outsideItem.amount)}（施策別資料に載らない経費）</p>
                <p className="text-xs text-mirai-text-muted">
                  {outsideItem.key === 'other'
                    ? '一般会計の歳出から、施策別資料の事項と、ほかの4つの灰色の円を引いた残り。人件費と施策の事項が重なる分は、ここが小さくなる形で差し引かれています。'
                    : '説明書の款・節・事項から数えた額。施策別資料に事項として載らない、決まった出費です。'}
                </p>
              </section>
            )}

            {focusedInitiative ? (
              <section className="rounded-2xl bg-card p-3 shadow-soft">
                <h2 className="mb-2 text-sm font-bold">この取組の事項（{initiativeItems.length} 件・多い順）</h2>
                <ul className="max-h-[32rem] space-y-0.5 overflow-y-auto text-sm">
                  {initiativeItems.map(({ item: it, index: i }) => (
                    <li key={i}>
                      <button
                        type="button"
                        aria-pressed={selected === i}
                        onClick={() => select(i, focusedInitiative)}
                        className={`flex w-full items-baseline gap-2 rounded px-1 text-left hover:bg-mirai-surface ${selected === i ? 'bg-mirai-surface-teal font-bold' : ''}`}
                      >
                        <span className="inline-block h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: scheme.colorOf(it) }} aria-hidden />
                        <span className="min-w-0 flex-1">
                          {it.name}
                          {it.is_new && <span className="ml-1 text-xs text-amber-700">新規</span>}
                        </span>
                        <span className="shrink-0 tabular-nums text-mirai-text-muted">{formatBudgetFromYen(it.amount)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            ) : (
              <section className="rounded-2xl bg-card p-3 shadow-soft">
                <h2 className="mb-2 text-sm font-bold">取組の一覧（{totals.length}。合計の多い順。押すと寄ります）</h2>
                <ul className="max-h-[32rem] space-y-0.5 overflow-y-auto text-sm">
                  {totals.map(t => (
                    <li key={t.key}>
                      <button
                        type="button"
                        onClick={() => setFocus(t.key)}
                        className="flex w-full items-baseline gap-2 rounded px-1 text-left hover:bg-mirai-surface"
                      >
                        <span className="w-5 shrink-0 text-xs text-mirai-text-muted">{t.pillar ?? '外'}</span>
                        <span className="min-w-0 flex-1">{t.name}</span>
                        <span className="shrink-0 tabular-nums text-mirai-text-muted">
                          {formatBudgetFromYen(t.amount)}・{t.count}件
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </aside>
        </div>

        <section className="space-y-1 text-xs text-mirai-text-muted">
          <p>
            範囲: 一般会計の事項だけ。施策別資料のうち、特別会計・公営企業会計の事項 {policies.excluded.special.count} 件
            （{formatBudgetFromYen(policies.excluded.special.amount)}）は除いています。債務負担行為のある一般会計の事項 {policies.excluded.debt_burden.count} 件は、
            この年度の額を円にし（この年度の額が 0 で限度額だけのものは円なし）、限度額（計 {formatBudgetFromYen(policies.excluded.debt_burden.amount)}。
            後年度にわたる額で、この年度の歳出ではない）は含めていません。
            中小企業の制度融資の貸付金（中小企業振興資金融資費）は、施策別資料の事項ですが灰色の円で見せています（金融機関に預けて年度内に戻るお金）。
            補正予算は入っていません（施策別資料は当初予算だけ）。
          </p>
          <p>
            1つの事項が複数の款・目にまたがるときも、円は1つです（款で色分けするときは「款をまたぐ事項」の色）。
            柱の外の「{OUTSIDE_PILLAR_NAME}」は、施策別資料で4つの柱の後に載る計画推進の基盤づくりの事項です。
          </p>
          <p>
            出典:{' '}
            {policies.source_docs.map((d, i) => {
              const s = sourceOf(d);
              return (
                <span key={d}>
                  {i > 0 && '・'}
                  {s ? (
                    <a href={s.url} className="text-primary-accent underline" target="_blank" rel="noreferrer">
                      {s.title}
                    </a>
                  ) : (
                    d
                  )}
                </span>
              );
            })}
            （{index.gov.name}）。金額は資料に印字された数字（千円単位）を円に直したもの。
          </p>
        </section>
      </main>
    </div>
  );
}
