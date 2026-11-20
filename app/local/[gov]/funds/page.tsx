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

function LocalFundsContent() {
  const { gov } = useParams<{ gov: string }>();
  const settlement = useLocalBudget(gov, undefined, 'settlement');
  const initial = useLocalBudget(gov, undefined, 'initial');
  const funds = settlement.status === 'ready' ? settlement.file.funds ?? null : null;
  const flows = useMemo(() => (initial.status === 'ready' ? fundFlows(initial.file) : null), [initial]);
  const rows = useMemo(() => (funds ? fundRows(funds, flows) : []), [funds, flows]);

  if (settlement.status === 'loading') return <LoadingSpinner fullscreen />;
  if (settlement.status === 'error') return <p className="p-4 text-sm">読み込めませんでした: {settlement.message}</p>;
  if (!funds) return <p className="p-4 text-sm">この自治体の基金のデータはまだありません。</p>;

  const { index } = settlement;
  const budgetLabel = initial.status === 'ready' ? `${initial.dataset.label}当初予算` : '当初予算';
  const latest = funds.totals[funds.totals.length - 1];
  const total = latest.fiscal_adjustment + latest.debt_reduction + latest.other;
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
          基金は、特定の目的のために県が積み立てているお金です。{funds.as_of.label}の現在高は {funds.items.length} 基金で
          計 <b>{formatBudgetFromYen(total)}</b>。うち県債（借金）の返済に備える減債基金が {formatBudgetFromYen(latest.debt_reduction)}、
          年度間の財源の調整に使う財政調整基金が {formatBudgetFromYen(latest.fiscal_adjustment)} です。
        </p>

        <section className="space-y-2">
          <h2 className="text-base font-bold">年度末の現在高の推移（決算）</h2>
          <FundsTrendChart totals={funds.totals} />
        </section>

        <section className="space-y-2">
          <h2 className="text-base font-bold">基金ごとの現在高（{funds.as_of.label}）と{budgetLabel}の予定</h2>
          <p className="text-xs text-mirai-text-muted">
            現在高は{funds.as_of.label}（決算）、積み立て・取り崩しは{budgetLabel}の予定で、時点が違います
            （{budgetLabel}の積み立て 計 {formatBudgetFromYen(deposit)}・取り崩し 計 {formatBudgetFromYen(withdraw)}）。
            取り崩しは一般会計の歳入「〇〇基金繰入金」、積み立ては歳出の「〇〇基金積立金」を名前で結んだもの。基金の名前を押すと内訳を開きます。
          </p>
          <FundsTable rows={rows} asOfLabel={funds.as_of.label} budgetLabel={budgetLabel} gov={gov} />
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
                    {s.src === 'ocr' ? '（画像・OCR）' : ''}
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
