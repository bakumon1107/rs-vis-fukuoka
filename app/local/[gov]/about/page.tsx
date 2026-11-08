'use client';

/**
 * 地方版の「データについて」（/local/<自治体>/about）。説明と出典: 検算の方法と結果、画像で確かめて直した値の一覧、
 * 名前の出典ごとの件数、資料の一覧（URL・SHA256・取得日）。
 * 設計: docs/local-gov/tasks/20261106_1327_地方版サンキー図の画面とグラフの設計.md 4.2
 */
import Link from 'next/link';
import { Suspense, useMemo } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import LoadingSpinner from '@/client/components/LoadingSpinner';
import { AppHeader } from '@/components/navigation/AppHeader';
import { useLocalBudget, yearFromQuery } from '@/client/hooks/useLocalBudget';
import { PartialNotice } from '@/client/components/local-gov/PartialNotice';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';
import {
  nameSourceCounts,
  noAmountPrintedCount,
  valueNotes,
  valueSourceCounts,
  zeroAmountRows,
} from '@/app/lib/local-gov/summary';
import type { ValueSource } from '@/types/local-gov';
import {
  isNotableValueSource,
  NAME_SOURCE_ORDER,
  NAME_SRC_LABEL,
  VALUE_SOURCE_ORDER,
  VALUE_SRC_LABEL,
} from '@/client/lib/local-gov-labels';

const NAME_LEVELS = [
  ['kan', '款'],
  ['kou', '項'],
  ['moku', '目'],
  ['setsu', '節'],
  ['item', '説明欄の事項'],
  ['sub', '細節'],
] as const;


/** 確定した読み取り（text・ocr）以外の値の出典の印（詳細パネルと同じ考え方。設計書 4.4） */
function srcNote(src: ValueSource) {
  return isNotableValueSource(src) ? <span className="text-amber-700">［{VALUE_SRC_LABEL[src]}］</span> : null;
}

export default function LocalGovAboutPage() {
  return (
    <Suspense fallback={<LoadingSpinner fullscreen />}>
      <LocalGovAboutContent />
    </Suspense>
  );
}

function LocalGovAboutContent() {
  const { gov } = useParams<{ gov: string }>();
  // 年度はサンキー図のページと同じクエリ（year）で受け取る。なければ最新の年度
  const year = yearFromQuery(useSearchParams().get('year'));
  const state = useLocalBudget(gov, year);
  const summary = useMemo(() => {
    if (state.status !== 'ready') return null;
    const f = state.file;
    return {
      notes: valueNotes(f),
      names: nameSourceCounts(f),
      values: valueSourceCounts(f),
      zero: zeroAmountRows(f),
      noAmount: noAmountPrintedCount(f),
    };
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
  // 同じ名前の款が複数の会計にあるので、0 円の目の一覧には会計の名前を添える
  const accountName = new Map(file.accounts.map(a => [a.id, a.name]));
  const c = file.checks;

  return (
    <div className="min-h-screen bg-mirai-surface">
      <AppHeader current="/" />
      <main className="mx-auto max-w-4xl space-y-6 px-4 pb-16 pt-4 text-sm text-mirai-text">
        <div>
          <Link href={`/local/${gov}?year=${file.year}`} className="text-xs text-primary-accent underline">
            ← サンキー図に戻る
          </Link>
          <h1 className="mt-1 text-xl font-bold">
            {index.gov.name} {dataset.label} データについて
          </h1>
        </div>

        {dataset.status === 'partial' && <PartialNotice govId={gov} year={file.year} linkToAbout={false} />}

        <section className="space-y-2 rounded-2xl bg-card p-4 shadow-soft">
          <h2 className="font-bold">数字の作り方</h2>
          {/* 説明書・予算書の本体・計上額調などの説明は福岡県の資料に合わせたもの。2件目の自治体を載せるときに、資料の説明を index.json に移す */}
          <p>
            {index.gov.name}が公開している「予算に関する説明書」（スキャン画像の PDF）を文字認識（OCR）で読み取り、目（もく）ごとの本年度・前年度・財源内訳・節・説明欄の事項を取り出しています。
            金額は説明書に印字された千円単位の数字を円に直したもので、推計や按分はしていません。
          </p>
          <p>読み取った数字は、次の検算で確かめています。</p>
          <ul className="list-disc space-y-0.5 pl-5">
            <li>目ごとに: 説明欄の事項の合計・財源内訳の合計・節の合計がそれぞれ本年度と一致し、本年度 − 前年度 = 比較</li>
            <li>
              目を足し上げた合計を、予算書の本体（議案）の項の額と、当初予算計上額調（テキスト PDF）の款・会計の額と突き合わせる
              （どの単位で突き合わせたかと結果は、下の「検算の結果」）
            </li>
            <li>複数の読み取り（OCR 2種類と PDF の文字情報）で同じ値になるかを数える</li>
          </ul>
        </section>

        <section className="space-y-2 rounded-2xl bg-card p-4 shadow-soft">
          <h2 className="font-bold">検算の結果</h2>
          <ul className="list-disc space-y-0.5 pl-5">
            <li>
              目 {c.rows} 件のうち、すべての検算が一致したもの <b>{c.all_ok} 件</b>
            </li>
            {c.external &&
              Object.entries(c.external).map(([k, v]) => (
                <li key={k}>
                  {k.replace(/_/g, ' と ')}: {v}
                </li>
              ))}
            {c.readings && (
              <li>
                2通り以上の読み取りで同じ値: {(c.readings.agree_2plus * 100).toFixed(2)}%（1通り以下で画像で確認した値{' '}
                {c.readings.confirmed_by_image ?? 0} 件）
              </li>
            )}
            {summary && (
              <li>
                値の出典（目の本年度・前年度・財源内訳・事項・節・細節）:{' '}
                {VALUE_SOURCE_ORDER.filter(k => summary.values[k]).map(k => `${VALUE_SRC_LABEL[k]} ${summary.values[k]}`).join('、')}
              </li>
            )}
            {summary && summary.noAmount > 0 && (
              <li>
                説明欄に事項が1つだけで金額が印字されていない目 {summary.noAmount} 件は、その事項に目の額を当てています（事項の額としては検算していません。画面に「金額の記載なし」と表示）
              </li>
            )}
          </ul>
        </section>

        {summary && (
          <section className="space-y-2 rounded-2xl bg-card p-4 shadow-soft">
            <h2 className="font-bold">名前の確かめ方</h2>
            <p>名前は検算では確かめられないため、名前ごとに裏付けの種類を持たせています。「読み取りのみ」の名前には画面で ※ を付けています。</p>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-mirai-text-muted">
                    <th className="py-1 text-left font-normal">名前</th>
                    {NAME_SOURCE_ORDER.map(k => (
                      <th key={k} className="px-1 text-right font-normal">
                        {NAME_SRC_LABEL[k]}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {NAME_LEVELS.map(([level, label]) => (
                    <tr key={level} className="border-t border-mirai-border">
                      <th className="py-1 text-left font-normal">{label}</th>
                      {NAME_SOURCE_ORDER.map(k => (
                        <td key={k} className={`px-1 text-right ${k === 'ocr' && summary.names[level][k] ? 'text-amber-700' : ''}`}>
                          {summary.names[level][k] ?? '—'}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-mirai-text-muted">款・項・目は目の行ごとの件数。</p>
          </section>
        )}

        {summary && (
          <section className="space-y-2 rounded-2xl bg-card p-4 shadow-soft">
            <h2 className="font-bold">読み取り以外の方法で決めた値（{summary.notes.length} 件）</h2>
            <p>
              読み取りで食い違った・読めなかった数字は、PDF の画像を見て確かめた値を使っています。空欄を 0 とみなした値（本年度・前年度・比較の関係が
              成り立つときだけ）もここに並べます。図や詳細パネルで見られない値（歳入の目など）も含みます。
            </p>
            <ul className="space-y-1 text-xs">
              {summary.notes.map((x, i) => (
                <li key={i}>
                  <span className="text-mirai-text-muted">{x.where}</span> {x.field}:{' '}
                  <b>{x.value === null ? '—' : formatBudgetFromYen(x.value)}</b>
                  <span className="text-amber-700">［{VALUE_SRC_LABEL[x.src]}］</span>
                  {x.note && <span className="text-mirai-text-muted">（{x.note}）</span>}
                </li>
              ))}
            </ul>
          </section>
        )}

        {summary && summary.zero.length > 0 && (
          <section className="space-y-2 rounded-2xl bg-card p-4 shadow-soft">
            <h2 className="font-bold">本年度の計上がない目（{summary.zero.length} 件）</h2>
            <p>本年度が 0 円の目は、サンキー図には箱を出していません（高さのない箱になるため）。前年度の額とあわせて、ここに並べます。</p>
            <ul className="space-y-1 text-xs">
              {summary.zero.map(r => (
                <li key={r.id}>
                  <span className="text-mirai-text-muted">
                    {accountName.get(r.account) ?? r.account} ／ {r.side === 'revenue' ? '歳入' : '歳出'} ／ {r.kan.name} ／ {r.kou.name} ／
                  </span>{' '}
                  {r.moku.name}（本年度 {r.amount.v != null ? formatBudgetFromYen(r.amount.v) : '読めない'}
                  {srcNote(r.amount.src)}・前年度 {r.previous?.v != null ? formatBudgetFromYen(r.previous.v) : '—'}
                  {r.previous && srcNote(r.previous.src)}）
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="space-y-2 rounded-2xl bg-card p-4 shadow-soft">
          <h2 className="font-bold">資料（{index.sources.length} 点）</h2>
          <p className="text-xs text-mirai-text-muted">
            {index.gov.name}のデータの作成と確認に使った資料です（名前の裏付けに別の年度の資料も使うため、年度で絞っていません）。
            SHA256 は取得した PDF のハッシュ値です。{index.gov.name}が資料を差し替えた場合は、この値で気づけるようにしています。
          </p>
          <ul className="space-y-1 text-xs">
            {index.sources.map(s => (
              <li key={s.id}>
                <a href={s.url} target="_blank" rel="noreferrer" className="text-primary-accent underline">
                  {s.title}
                </a>
                <span className="ml-2 text-mirai-text-muted">
                  取得 {s.retrieved}・SHA256 <span className="break-all font-mono">{s.sha256}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      </main>
    </div>
  );
}
