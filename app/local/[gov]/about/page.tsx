'use client';

/**
 * 地方版の「データについて」（/local/<自治体>/about）。説明と出典: 検算の方法と結果、画像で確かめて直した値の一覧、
 * 名前の出典ごとの件数、資料の一覧（URL・SHA256・取得日）。
 * 設計: docs/local-gov/tasks/20261106_1327_地方版サンキー図の画面とグラフの設計.md 4.2
 */
import Link from 'next/link';
import { Suspense, useEffect, useMemo, useRef } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import LoadingSpinner from '@/client/components/LoadingSpinner';
import { AppHeader } from '@/components/navigation/AppHeader';
import { useLocalBudget, yearFromQuery } from '@/client/hooks/useLocalBudget';
import { PartialNotice } from '@/client/components/local-gov/PartialNotice';
import { ValueSourceMark } from '@/client/components/local-gov/ValueSourceMark';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';
import {
  nameSourceCounts,
  noAmountPrintedCount,
  valueNotes,
  unreadAmountRows,
  valueSourceCounts,
  zeroAmountRows,
} from '@/app/lib/local-gov/summary';
import type { Basis, ValueSource } from '@/types/local-gov';
import {
  fundingReclassNotes,
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
/** 金額。欠測（null・ない）は 0 円と区別して「—」 */
function amountOrDash(v: number | null | undefined) {
  return v != null ? formatBudgetFromYen(v) : '—';
}

function srcNote(src: ValueSource) {
  return <ValueSourceMark src={src} className="text-amber-700" />;
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
  // 予算か決算か（basis）と年度はサンキー図のページと同じクエリで受け取る。なければ当初予算の最新の年度
  const params = useSearchParams();
  const basis: Basis = params.get('basis') === 'settlement' ? 'settlement' : 'initial';
  const year = yearFromQuery(params.get('year'));
  // 来たときのサンキー図のクエリ（見方・選択）。クエリとして解釈し直してから使う（パスや「#」は付けさせない）
  const back = params.get('back');
  const state = useLocalBudget(gov, year, basis);
  const summary = useMemo(() => {
    if (state.status !== 'ready') return null;
    const f = state.file;
    return {
      notes: valueNotes(f),
      names: nameSourceCounts(f),
      values: valueSourceCounts(f),
      zero: zeroAmountRows(f),
      unread: unreadAmountRows(f),
      noAmount: noAmountPrintedCount(f),
    };
  }, [state]);

  // データを読み終えるまで節がないので、ブラウザの「#…」へのスクロールが効かない。読み終えてから該当の節へ動かす
  // （一般会計・全会計の見方の「調べた内訳はデータについて」は #funding へ案内する）
  // 最初に読み終えたときだけ動かす（年度を変えて読み直したときに、読んでいた場所から「#…」へ戻さない）
  const ready = state.status === 'ready';
  const scrolledToHash = useRef(false);
  useEffect(() => {
    if (!ready || scrolledToHash.current || !window.location.hash) return;
    scrolledToHash.current = true;
    let id: string;
    try {
      id = decodeURIComponent(window.location.hash.slice(1));
    } catch {
      return; // 壊れた「#…」（%E0 など）は無視する
    }
    // 読み上げの位置も移すため、フォーカスも移す（移動先の節は tabIndex={-1}。タブ順には入れない）
    const el = document.getElementById(id);
    el?.scrollIntoView();
    el?.focus({ preventScroll: true });
  }, [ready]);

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
  const fundingNotes = fundingReclassNotes(gov, file);
  const isSettlement = file.basis === 'settlement';
  const basisQuery = isSettlement ? '&basis=settlement' : '';

  return (
    <div className="min-h-screen bg-mirai-surface">
      <AppHeader current="/" />
      <main className="mx-auto max-w-4xl space-y-6 px-4 pb-16 pt-4 text-sm text-mirai-text">
        <div>
          <Link
            href={back ? `/local/${gov}?${new URLSearchParams(back).toString()}` : `/local/${gov}?year=${file.year}${basisQuery}`}
            className="text-xs text-primary-accent underline"
          >
            ← サンキー図に戻る
          </Link>
          <h1 className="mt-1 text-xl font-bold">
            {index.gov.name} {dataset.label}
            {isSettlement ? '決算' : '当初予算'} データについて
          </h1>
        </div>

        {dataset.status === 'partial' && <PartialNotice govId={gov} year={file.year} basis={file.basis} linkToAbout={false} />}

        {isSettlement ? (
          <section className="space-y-2 rounded-2xl bg-card p-4 shadow-soft">
            <h2 className="font-bold">数字の作り方</h2>
            {/* 決算の資料の説明は福岡県の資料に合わせたもの。2件目の自治体を載せるときに、資料の説明を index.json に移す */}
            <p>
              {index.gov.name}が公開している「歳入歳出決算概要説明書」と「歳入歳出決算事項別明細書」（どちらも文字の入った PDF）から、
              目（もく）ごとの予算現額・支出済額・翌年度繰越額・不用額、部局ごとの内訳、節（報酬・給料・委託料などの性質）、
              「決算の内容」「不用額の内容」を取り出しています。金額は資料に印字された円単位の数字そのままで、推計や按分はしていません。
              図の帯は支出済額（実際に使った額）です。
            </p>
            <p>取り出した数字は、次の検算で確かめています（1円でも違えば止める）。</p>
            <ul className="list-disc space-y-0.5 pl-5">
              <li>目ごとに: 予算現額 = 支出済額 + 翌年度繰越額 + 不用額、節の支出済額の合計 = 目の支出済額、部局ごとの内訳の合計 = 目</li>
              <li>目の合計 = 項 = 款（款項目別明細表）。部局別の表の合計 = 款項目別明細表の目</li>
              <li>特別会計は会計ごとの合計を「特別会計歳入歳出決算一覧表」と突き合わせる</li>
            </ul>
          </section>
        ) : (
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
        )}

        {file.revenue_by_kan && file.revenue_by_kan.length > 0 && (
          <section id="revenue" className="scroll-mt-24 space-y-2 rounded-2xl bg-card p-4 shadow-soft">
            <h2 className="font-bold">歳入（会計・款ごと）</h2>
            <p className="text-xs text-mirai-text-muted">
              決算の図には歳入を描いていません（どの収入をどの歳出に使ったかは資料にないため）。歳入は款ごとの額をここに載せます。
              調定額 = 収入済額 − 過誤納金 + 不納欠損額 + 収入未済額。
            </p>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-xs">
                <thead>
                  <tr className="text-mirai-text-muted">
                    <th className="py-1 text-left font-normal">会計・款</th>
                    <th className="py-1 text-right font-normal">収入済額</th>
                    <th className="py-1 text-right font-normal">予算現額</th>
                    <th className="py-1 text-right font-normal">調定額</th>
                    <th className="py-1 text-right font-normal">不納欠損額</th>
                    <th className="py-1 text-right font-normal">収入未済額</th>
                    <th className="py-1 text-right font-normal">過誤納金（内数）</th>
                  </tr>
                </thead>
                <tbody>
                  {file.revenue_by_kan.map(r => (
                    <tr key={`${r.account}-${r.kan.no}`} className="border-t border-mirai-border">
                      <td className="py-1">
                        <span className="text-mirai-text-muted">{accountName.get(r.account) ?? r.account} ／ </span>
                        {r.kan.name}
                      </td>
                      {/* 欠測（v が null）は 0 円と区別して「—」 */}
                      <td className="py-1 text-right font-bold">{amountOrDash(r.amount.v)}</td>
                      <td className="py-1 text-right">{amountOrDash(r.budget_current.v)}</td>
                      <td className="py-1 text-right">{amountOrDash(r.assessed.v)}</td>
                      <td className="py-1 text-right">{amountOrDash(r.deficit_loss.v)}</td>
                      <td className="py-1 text-right">{amountOrDash(r.uncollected.v)}</td>
                      {/* 過誤納金は行がないとき 0 円（印字がない＝過誤納金なし）。差額から求めた値は出典の印を付ける */}
                      <td className="py-1 text-right" title={r.overpaid?.note}>
                        {r.overpaid ? amountOrDash(r.overpaid.v) : formatBudgetFromYen(0)}
                        {r.overpaid && <ValueSourceMark src={r.overpaid.src} className="text-amber-700" />}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {fundingNotes && (
          <section
            id="funding"
            tabIndex={-1}
            className="scroll-mt-24 space-y-2 rounded-2xl bg-card p-4 shadow-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-accent"
          >
            <h2 className="font-bold">財源内訳と歳入の款の違い</h2>
            <p>
              一般会計の見方の左端は歳出の財源内訳（国庫支出金・地方債・その他・一般財源）、全会計の見方の左端は歳入の款（県税・国庫支出金・県債・繰入金など）です。
              国庫支出金や県債の額が2つの見方で違うのは、主に全会計の見方が特別会計の分も含むためです。
              一般会計だけで比べても、歳入では国庫支出金・県債・繰入金などに入っているお金の一部を、歳出の財源内訳では一般財源として数えているため、額が合いません。
              一般会計について説明書を読んで調べた結果は次のとおりです。どこまで確かめられたかは、それぞれの括弧の中に書いています（{index.gov.name}の資料。なぜ一般財源に数えるのかは説明書に書かれていません）。
            </p>
            <ul className="list-disc space-y-0.5 pl-5">
              {fundingNotes.map(n => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </section>
        )}

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
                {/* 数えている値は種類で違う（決算は支出済額と節。予算現額・繰越額・不用額・歳入の款は数えていない） */}
                {file.basis === 'settlement' ? '値の出典（目の支出済額・節）' : '値の出典（目の本年度・前年度・財源内訳・事項・節・細節）'}:{' '}
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

        {/* 決算はテキスト PDF から取るので、読み取りの食い違いを直した値はない（0 件のときは節ごと出さない） */}
        {summary && !(file.basis === 'settlement' && summary.notes.length === 0) && (
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
                  <ValueSourceMark src={x.src} className="text-amber-700" />
                  {x.note && <span className="text-mirai-text-muted">（{x.note}）</span>}
                </li>
              ))}
            </ul>
          </section>
        )}

        {summary && summary.unread.length > 0 && (
          <section className="space-y-2 rounded-2xl bg-card p-4 shadow-soft">
            <h2 className="font-bold">額が読めない目（{summary.unread.length} 件）</h2>
            <p>
              {isSettlement ? '支出済額' : '本年度の額'}を資料から読めなかった目です（0 円とは限りません）。サンキー図には箱を出していません。
            </p>
            <ul className="space-y-1 text-xs">
              {summary.unread.map(r => (
                <li key={r.id}>
                  <span className="text-mirai-text-muted">
                    {accountName.get(r.account) ?? r.account} ／ {r.side === 'revenue' ? '歳入' : '歳出'} ／ {r.kan.name} ／ {r.kou.name} ／
                  </span>{' '}
                  {r.moku.name}
                </li>
              ))}
            </ul>
          </section>
        )}

        {summary && summary.zero.length > 0 && (
          <section className="space-y-2 rounded-2xl bg-card p-4 shadow-soft">
            <h2 className="font-bold">
              {isSettlement ? '支出のなかった目' : '本年度の計上がない目'}（{summary.zero.length} 件）
            </h2>
            <p>
              {isSettlement
                ? '支出済額が 0 円の目は、サンキー図には箱を出していません（高さのない箱になるため）。予算現額・不用額とあわせて、ここに並べます。'
                : '本年度が 0 円の目は、サンキー図には箱を出していません（高さのない箱になるため）。前年度の額とあわせて、ここに並べます。'}
            </p>
            <ul className="space-y-1 text-xs">
              {summary.zero.map(r => (
                <li key={r.id}>
                  <span className="text-mirai-text-muted">
                    {accountName.get(r.account) ?? r.account} ／ {r.side === 'revenue' ? '歳入' : '歳出'} ／ {r.kan.name} ／ {r.kou.name} ／
                  </span>{' '}
                  {isSettlement ? (
                    <>
                      {r.moku.name}（支出済額 0円・予算現額{' '}
                      {amountOrDash(r.budget_current?.v)}・不用額 {amountOrDash(r.unused?.v)}）
                      {/* 図に箱がないので、決算の内容・不用額の内容はここで読めるようにする（部局ごとの説明も） */}
                      {[r.explanation, ...(r.by_department ?? []).map(d => d.explanation)]
                        .filter((e): e is NonNullable<typeof e> => !!e && !!(e.content || e.unused))
                        .map((e, i) => (
                          <span key={i} className="block pl-3 text-mirai-text-muted">
                            {e.content && <>決算の内容: {e.content}</>}
                            {e.content && e.unused && '／'}
                            {e.unused && <>不用額の内容: {e.unused}</>}
                          </span>
                        ))}
                    </>
                  ) : (
                    <>
                      {r.moku.name}（本年度 {r.amount.v != null ? formatBudgetFromYen(r.amount.v) : '読めない'}
                      {srcNote(r.amount.src)}・前年度 {r.previous?.v != null ? formatBudgetFromYen(r.previous.v) : '—'}
                      {r.previous && srcNote(r.previous.src)}）
                    </>
                  )}
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
