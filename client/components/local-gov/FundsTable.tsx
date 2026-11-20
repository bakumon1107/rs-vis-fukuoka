'use client';

/**
 * 基金ごとの表（表示専用）: 決算の年度末現在高と、予算の積み立て・取り崩しの予定。行を開くと区分（現金・有価証券・
 * 一般会計への貸付など）と、積み立て・取り崩しの元の予算の目。
 * 設計: docs/local-gov/tasks/20261120_1200_地方版の基金の設計.md 4章
 */
import Link from 'next/link';
import { Fragment, useState } from 'react';
import type { FundRow } from '@/app/lib/local-gov/funds';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';

const yen = (v: number) => (v === 0 ? '—' : formatBudgetFromYen(v));

function Spark({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const max = Math.max(...values, 1);
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * 60},${18 - (v / max) * 16}`).join(' ');
  return (
    <svg width="60" height="20" aria-hidden="true" className="inline-block align-middle">
      <polyline points={pts} fill="none" className="stroke-primary-accent" strokeWidth={1.5} />
    </svg>
  );
}

interface Props {
  rows: FundRow[];
  asOfLabel: string;
  budgetLabel: string;
  gov: string;
  /** 当初予算の読み込みの状態。ready のときだけ予定の額を出す（読み込み中・失敗を「予定なし」と見せない） */
  plan: 'loading' | 'error' | 'ready';
}

export function FundsTable({ rows, asOfLabel, budgetLabel, gov, plan }: Props) {
  const [open, setOpen] = useState<string | null>(null);
  const planCell = (v: number) => (plan === 'ready' ? yen(v) : plan === 'loading' ? '…' : '?');
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-sm">
        <thead>
          <tr className="text-xs text-mirai-text-muted">
            <th className="py-1 text-left font-normal">基金</th>
            <th className="py-1 text-right font-normal">{asOfLabel}の現在高</th>
            <th className="py-1 text-center font-normal">推移</th>
            <th className="py-1 text-right font-normal">{budgetLabel}の積み立て</th>
            <th className="py-1 text-right font-normal">{budgetLabel}の取り崩し</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => {
            const isOpen = open === r.name;
            return (
              <Fragment key={r.name}>
                <tr className="border-t border-mirai-border align-top">
                  <td className="py-1">
                    <button
                      type="button"
                      aria-expanded={isOpen}
                      onClick={() => setOpen(isOpen ? null : r.name)}
                      className="text-left text-primary-accent underline-offset-2 hover:underline"
                    >
                      {r.name}
                    </button>
                    {r.fund?.kind === 'operating' && <span className="ml-1 text-[10px] text-mirai-text-muted">運用基金</span>}
                    {!r.fund && (
                      <span className="block text-[10px] text-mirai-text-muted">
                        {asOfLabel}の調書に同じ名前の基金がない（その後に設けたか、名前が違う）
                      </span>
                    )}
                    {r.fund?.renamed_from && (
                      <span className="block text-[10px] text-mirai-text-muted">旧 {r.fund.renamed_from.join('・')}</span>
                    )}
                  </td>
                  <td className="whitespace-nowrap py-1 text-right">{r.fund ? (r.fund.no_figures ? '記載なし' : yen(r.fund.end)) : '—'}</td>
                  <td className="py-1 text-center">{r.fund && <Spark values={r.fund.history.map(h => h.end)} />}</td>
                  <td className="whitespace-nowrap py-1 text-right">{planCell(r.deposit)}</td>
                  <td className="whitespace-nowrap py-1 text-right">{planCell(r.withdraw)}</td>
                </tr>
                {isOpen && (
                  <tr className="bg-mirai-surface">
                    <td colSpan={5} className="space-y-2 px-2 py-2 text-xs">
                      {r.fund && (
                        <table className="w-full">
                          <thead>
                            <tr className="text-mirai-text-muted">
                              <th className="text-left font-normal">区分</th>
                              <th className="text-right font-normal">前年度末</th>
                              <th className="text-right font-normal">年度中の増減</th>
                              <th className="text-right font-normal">年度末</th>
                              <th className="text-right font-normal">出納閉鎖日（5月31日）</th>
                            </tr>
                          </thead>
                          <tbody>
                            {r.fund.holdings.map(h => (
                              <tr key={h.kind}>
                                <td>{h.kind}</td>
                                <td className="text-right">{yen(h.start)}</td>
                                <td className="text-right">{h.change < 0 ? `△${formatBudgetFromYen(-h.change)}` : yen(h.change)}</td>
                                <td className="text-right">{yen(h.end)}</td>
                                <td className="text-right">{yen(h.after_closing)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                      {plan !== 'ready' ? (
                        <p className="text-mirai-text-muted">
                          {plan === 'loading' ? '当初予算を読み込み中です' : '当初予算を読み込めなかったので、予定は分かりません'}
                        </p>
                      ) : r.refs.length > 0 ? (
                        <ul className="list-disc pl-4">
                          {r.refs.map(x => (
                            <li key={`${x.row}-${x.label}`}>
                              {x.row.includes('/expense/') ? (
                                <Link href={`/local/${gov}?sel=${encodeURIComponent(`moku:${x.row}`)}`} className="text-primary-accent underline">
                                  {x.label}
                                </Link>
                              ) : (
                                x.label
                              )}{' '}
                              {formatBudgetFromYen(x.amount)}
                              <span className="text-mirai-text-muted">（{x.row.includes('/expense/') ? '歳出' : '歳入'}の目 {x.row.split('/').pop()}）</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-mirai-text-muted">{budgetLabel}に積み立て・取り崩しの予定はありません</p>
                      )}
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
