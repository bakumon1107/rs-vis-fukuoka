'use client';

/**
 * 基金ごとの表（表示専用）: 決算の年度末現在高と、予算の積み立て・取り崩しの予定。行を開くと、その基金の年度末現在高の
 * 推移の大きめのグラフ、区分（現金・有価証券・一般会計への貸付など）、積み立て・取り崩しの元の予算の目。
 * 設計: docs/local-gov/tasks/20261120_1200_地方版の基金の設計.md 4章
 */
import Link from 'next/link';
import { Fragment, useState } from 'react';
import type { FundRow } from '@/app/lib/local-gov/funds';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';
import { FundHistoryChart } from './FundHistoryChart';

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

/** 額の列の見出し（「現在高」＋2行目に時点）。長い見出しが変なところで折り返さないよう、行を分けて小さく出す */
function AmountHead({ label, when }: { label: string; when: string }) {
  return (
    <th className="px-1 py-1 text-right align-bottom font-normal">
      <span className="block font-bold text-mirai-text">{label}</span>
      <span className="block text-[10px] leading-tight">{when}</span>
    </th>
  );
}

export function FundsTable({ rows, asOfLabel, budgetLabel, gov, plan }: Props) {
  const [open, setOpen] = useState<string | null>(null);
  const planCell = (v: number) => (plan === 'ready' ? yen(v) : plan === 'loading' ? '…' : '?');
  // 額の列: 小さい画面でも横にはみ出さないよう、表の幅は画面に合わせ（最小幅を付けない）、基金の名前の列を早めに折り返す。
  // 推移の小さい折れ線はスマートフォンの幅では出さない（行を開くと大きいグラフが出る）
  // とても狭い画面（320px 前後）では額が列に収まらないので、表に最小幅を付けて横にずらせるようにする（390px 前後なら収まる）。
  // 推移の列はスマートフォンの幅では幅 0（col を display:none にすると、ブラウザによって列の幅の割り当てがずれる）
  const num = 'whitespace-nowrap px-1 py-1.5 text-right tabular-nums';
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[340px] table-fixed text-[11px] sm:text-sm">
        <colgroup>
          <col className="w-[35%] sm:w-[34%]" />
          <col className="w-[22%] sm:w-[17%]" />
          <col className="w-0 sm:w-[13%]" />
          <col className="w-[21.5%] sm:w-[18%]" />
          <col className="w-[21.5%] sm:w-[18%]" />
        </colgroup>
        <thead>
          <tr className="text-xs text-mirai-text-muted">
            <th className="py-1 text-left align-bottom font-normal">基金</th>
            <AmountHead label="現在高" when={`${asOfLabel}`} />
            <th className="hidden py-1 text-center align-bottom font-normal sm:table-cell">推移</th>
            <AmountHead label="積み立て" when={`${budgetLabel}`} />
            <AmountHead label="取り崩し" when={`${budgetLabel}`} />
          </tr>
        </thead>
        <tbody>
          {rows.map(r => {
            const isOpen = open === r.name;
            return (
              <Fragment key={r.name}>
                <tr className="border-t border-mirai-border align-top">
                  <td className="break-words py-1.5 pr-1">
                    <button
                      type="button"
                      aria-expanded={isOpen}
                      onClick={() => setOpen(isOpen ? null : r.name)}
                      className="text-left text-primary-accent underline-offset-2 hover:underline"
                    >
                      <span aria-hidden="true" className="mr-0.5 inline-block w-3 text-[10px] text-mirai-text-muted">{isOpen ? '▼' : '▶'}</span>
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
                  <td className={`${num} font-bold`}>{r.fund ? (r.fund.no_figures ? '記載なし' : yen(r.fund.end)) : '—'}</td>
                  <td className="hidden py-1.5 text-center sm:table-cell">{r.fund && <Spark values={r.fund.history.map(h => h.end)} />}</td>
                  <td className={num}>{planCell(r.deposit)}</td>
                  <td className={num}>{planCell(r.withdraw)}</td>
                </tr>
                {isOpen && (
                  <tr className="bg-mirai-surface">
                    <td colSpan={5} className="space-y-3 px-2 py-3 text-xs">
                      {/* その基金の年度末現在高の推移（大きめの棒グラフ） */}
                      {r.fund && !r.fund.no_figures && r.fund.history.length > 1 && r.fund.history.some(h => h.end > 0) && (
                        <div className="rounded-xl bg-card p-2">
                          <FundHistoryChart name={r.name} history={r.fund.history} />
                        </div>
                      )}
                      {r.fund && (
                        <div className="overflow-x-auto">
                        <table className="w-full min-w-[420px]">
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
                        </div>
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
