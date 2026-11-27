'use client';

/**
 * 地方版の基金（/local/<自治体>/funds）。決算の基金の現在高と推移、当初予算の積み立て・取り崩しの予定。
 * 設計: docs/local-gov/tasks/20261120_1200_地方版の基金の設計.md
 *
 * ページは読み込みとレイアウトだけを持つ。組み立ては app/lib/local-gov/funds.ts（純粋関数）、描画は client/components/local-gov。
 * 残高（決算）と予定（当初予算）は時点が違うので、見出しで分けて示す。決算の後の年度末の残高の見込みは作らない（推計しない）
 */
import Link from 'next/link';
import { Suspense, useMemo } from 'react';
import { useParams } from 'next/navigation';
import LoadingSpinner from '@/client/components/LoadingSpinner';
import { AppHeader } from '@/components/navigation/AppHeader';
import { useLocalBudget } from '@/client/hooks/useLocalBudget';
import { FundsTrendChart } from '@/client/components/local-gov/FundsTrendChart';
import { FundsTable } from '@/client/components/local-gov/FundsTable';
import { fundFlows, fundRows } from '@/app/lib/local-gov/funds';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';

export default function LocalFundsPage() {
  return (
    <Suspense fallback={<LoadingSpinner fullscreen />}>
      <LocalFundsContent />
    </Suspense>
  );
}

/** 決算の年度（西暦）の次の年度の和暦の名前（2024 → 令和7年度）。残高を更新する予定の年度の注記に使う */
function nextYearLabel(year: number): string {
  const y = year + 1;
  return y >= 2019 ? (y === 2019 ? '令和元年度' : `令和${y - 2018}年度`) : `平成${y - 1988}年度`;
}

function LocalFundsContent() {
  const { gov } = useParams<{ gov: string }>();
  const settlement = useLocalBudget(gov, undefined, 'settlement');
  const initial = useLocalBudget(gov, undefined, 'initial');
  const funds = settlement.status === 'ready' ? settlement.file.funds ?? null : null;
  const flows = useMemo(() => (initial.status === 'ready' ? fundFlows(initial.file) : null), [initial]);
  const rows = useMemo(() => (funds ? fundRows(funds, flows) : []), [funds, flows]);

  if (settlement.status === 'loading') return <LoadingSpinner fullscreen />;
  // ヘッダーは固定で重なるので、エラー・データなしのときも AppHeader を置いて下の余白を作る（ないと文言がヘッダーに隠れる）
  if (settlement.status === 'error' || !funds) {
    return (
      <div className="min-h-screen bg-mirai-surface">
        <AppHeader current="/" />
        <p className={`px-4 pt-4 text-sm ${settlement.status === 'error' ? 'text-destructive' : ''}`}>
          {settlement.status === 'error' ? `読み込めませんでした: ${settlement.message}` : 'この自治体の基金のデータはまだありません。'}
        </p>
      </div>
    );
  }

  const { index } = settlement;
  const budgetLabel = initial.status === 'ready' ? `${initial.dataset.label}当初予算` : '当初予算';
  // 予算の予定は、当初予算を読めたときだけ額を出す（読み込み中・失敗を「予定なし（0円）」と見せない）
  const plan = initial.status;
  const latest = funds.totals[funds.totals.length - 1];
  const total = latest.fiscal_adjustment + latest.debt_reduction + latest.other;
  // 残高のある基金の数（調書に載るが額が「－」・0 の基金は数えない）
  const holding = funds.items.filter(f => f.end > 0).length;
  const deposit = rows.reduce((s, r) => s + r.deposit, 0);
  const withdraw = rows.reduce((s, r) => s + r.withdraw, 0);

  return (
    <div className="min-h-screen bg-mirai-surface">
      <AppHeader current="/" />
      <main className="mx-auto max-w-4xl space-y-6 px-4 pb-16 pt-4 text-mirai-text">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <h1 className="text-xl font-bold">{index.gov.name} 基金</h1>
          <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">試作</span>
          <Link href={`/local/${gov}`} className="text-sm text-primary-accent underline">
            予算・決算の流れ（サンキー図）へ
          </Link>
        </div>
        <p className="text-sm">
          基金は、特定の目的のために県が積み立てているお金です。{funds.as_of.label}の現在高は、調書に載る {funds.items.length} 基金
          （うち残高のあるもの {holding}）の計 <b>{formatBudgetFromYen(total)}</b>。うち県債（借金）の返済に備える減債基金が {formatBudgetFromYen(latest.debt_reduction)}、
          年度間の財源の調整に使う財政調整基金が {formatBudgetFromYen(latest.fiscal_adjustment)} です。
        </p>
        {/* 残高（決算）と予定（当初予算）は時点が違う。間の年度は残高も予定もないことを先に示す（設計: 公開前のサンキー図の足し 3章） */}
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          時点に注意: 残高は{funds.as_of.label}（決算。財産に関する調書）、積み立て・取り崩しは{budgetLabel}の予定です。
          {nextYearLabel(funds.as_of.year)}末の残高は、{nextYearLabel(funds.as_of.year)}決算の調書が公表されたら（例年12月ごろ）更新します。
        </p>

        <section className="space-y-2">
          <h2 className="text-base font-bold">年度末の現在高の推移（決算）</h2>
          <FundsTrendChart totals={funds.totals} />
        </section>

        <section className="space-y-2">
          <h2 className="text-base font-bold">基金ごとの現在高（{funds.as_of.label}）と{budgetLabel}の予定</h2>
          <p className="text-xs text-mirai-text-muted">
            現在高は{funds.as_of.label}（決算）、積み立て・取り崩しは{budgetLabel}の予定で、時点が違います
            {plan === 'ready'
              ? `（${budgetLabel}の積み立て 計 ${formatBudgetFromYen(deposit)}・取り崩し 計 ${formatBudgetFromYen(withdraw)}）`
              : plan === 'loading'
                ? '（当初予算を読み込み中）'
                : `（当初予算を読み込めませんでした: ${initial.status === 'error' ? initial.message : ''}）`}
            。
            取り崩しは一般会計の歳入「〇〇基金繰入金」、積み立ては歳出の「〇〇基金積立金」を名前で結んだもの。基金の名前を押すと内訳を開きます。
          </p>
          <FundsTable rows={rows} asOfLabel={funds.as_of.label} budgetLabel={budgetLabel} gov={gov} plan={plan} />
        </section>

        <section className="space-y-1 text-xs text-mirai-text-muted">
          <h2 className="text-sm font-bold text-mirai-text">資料と注意</h2>
          <ul className="list-disc space-y-1 pl-4">
            {funds.notes.map(n => (
              <li key={n}>{n}</li>
            ))}
            <li>
              財産に関する調書（決算）:{' '}
              {funds.statements.map((s, i) => {
                const src = index.sources.find(x => x.id === s.source);
                return (
                  <span key={s.source}>
                    {i > 0 && '・'}
                    {src ? (
                      <a href={src.url} className="text-primary-accent underline" target="_blank" rel="noreferrer">
                        {s.label}
                      </a>
                    ) : (
                      s.label
                    )}
                    {(s.src === 'ocr' || s.partial) &&
                      `（${[s.src === 'ocr' ? '画像・OCR' : '', s.partial ? 'その年度に廃止した基金だけ' : ''].filter(Boolean).join('・')}）`}
                  </span>
                );
              })}
            </li>
          </ul>
        </section>
      </main>
    </div>
  );
}
