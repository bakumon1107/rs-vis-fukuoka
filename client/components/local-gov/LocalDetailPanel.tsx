'use client';

/**
 * 選んだ目の詳細（表示専用）。本年度・前年度・増減、財源内訳、説明欄の事項、節、出典（PDF のページ）、値・名前の出典の印。
 * 設計: docs/local-gov/tasks/20261106_1327_地方版サンキー図の画面とグラフの設計.md 4.2・4.4
 */
import type { LocalGovIndex, MokuRow, NameSource, Value } from '@/types/local-gov';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';
import { NAME_SRC_LABEL } from '@/client/lib/local-gov-labels';
import { ValueSourceMark } from './ValueSourceMark';
import { FUNDING_KINDS, isOcrName } from '@/app/lib/local-gov/graph';


function yen(v: Value | undefined) {
  return v && v.v !== null ? formatBudgetFromYen(v.v) : '—';
}

function Mark({ v }: { v: Value | undefined }) {
  return <ValueSourceMark src={v?.src} />;
}

function NameMark({ src }: { src?: NameSource }) {
  // 名前の出典がない名前も裏付けがないので、ocr と同じに扱う（設計書 4.4。図の印・「データについて」の件数と同じ）
  if (!isOcrName(src)) return null;
  return <span className="ml-1 text-[10px] text-amber-700" title={NAME_SRC_LABEL.ocr}>※名前は読み取り</span>;
}

/**
 * layout: side = 縦に1列（スマートフォンの下からのシート）。below = 図の下に横長で置く（広い画面。左に名前・金額・財源内訳・出典、
 * 中に説明欄の事項、右に節の3列）。横に置くと図が縮んで名前が重なったので、広い画面は図の下に出す（2026-11-14 ユーザー決定）
 */
export function LocalDetailPanel({
  row,
  index,
  accountName,
  layout = 'side',
}: {
  row: MokuRow;
  index: LocalGovIndex;
  accountName: string;
  layout?: 'side' | 'below';
}) {
  const diff = row.amount.v !== null && row.previous?.v != null ? row.amount.v - row.previous.v : null;
  const sources = new Map(index.sources.map(s => [s.id, s]));
  // 説明欄の事項は、親の事項の下に内訳（入れ子の事項）を字下げして並べる。
  // 内訳にも見ておきたいものがある（議会費の「各種負担金等」の内訳の「議員連盟補助金」「政務活動費交付金」など）
  const items = row.items ?? [];
  const topItems = items.map((it, i) => ({ it, i })).filter(({ it }) => it.parent === undefined);
  // 親の事項ごとの内訳を一度だけまとめる（親ごとに全件をなめ直さない）
  const children = new Map<number, { it: (typeof items)[number]; j: number }[]>();
  items.forEach((it, j) => {
    if (it.parent !== undefined) children.set(it.parent, [...(children.get(it.parent) ?? []), { it, j }]);
  });
  const childrenOf = (i: number) => children.get(i) ?? [];

  const head = (
      <div>
        <p className="text-xs text-mirai-text-muted">
          {/* 全会計の見方では同じ名前の款（公債費・予備費など）が複数の会計にあるので、会計の名前も出す */}
          {accountName} ／ {row.kan.name} ／ {row.kou.name}
        </p>
        <h2 className="text-base font-bold">
          {row.moku.name}
          <NameMark src={row.moku.name_src} />
        </h2>
        <p className="text-[11px] text-mirai-text-muted">名前の出典: {NAME_SRC_LABEL[isOcrName(row.moku.name_src) ? 'ocr' : row.moku.name_src!]}</p>
      </div>
  );

  // 決算の目（予算現額がある）: 支出済額・予算現額・翌年度繰越額・不用額と執行率（支出済額 ÷ 予算現額）
  const settlement = row.budget_current !== undefined;
  const rate = settlement && row.budget_current?.v ? (row.amount.v ?? 0) / row.budget_current.v : null;
  const settlementAmounts = settlement && (
      <table className="w-full text-sm">
        <tbody>
          <tr>
            <th className="py-0.5 text-left font-normal text-mirai-text-muted">支出済額</th>
            <td className="text-right font-bold">{yen(row.amount)}<Mark v={row.amount} /></td>
          </tr>
          <tr>
            <th className="py-0.5 text-left font-normal text-mirai-text-muted">予算現額</th>
            <td className="text-right">{yen(row.budget_current)}<Mark v={row.budget_current} /></td>
          </tr>
          <tr>
            <th className="py-0.5 text-left font-normal text-mirai-text-muted">翌年度繰越額</th>
            <td className="text-right">{yen(row.carried_over)}<Mark v={row.carried_over} /></td>
          </tr>
          <tr>
            <th className="py-0.5 text-left font-normal text-mirai-text-muted">不用額</th>
            <td className="text-right">{yen(row.unused)}<Mark v={row.unused} /></td>
          </tr>
          {rate !== null && (
            <tr>
              <th className="py-0.5 text-left font-normal text-mirai-text-muted" title="支出済額 ÷ 予算現額">執行率</th>
              <td className="text-right">{(rate * 100).toFixed(1)}%</td>
            </tr>
          )}
        </tbody>
      </table>
  );

  // 決算の内容・不用額の内容（概要説明書の文）。部局をまたぐ目は部局ごとに文がある
  const explainLines = (e: { content?: string; unused?: string } | undefined) =>
    e && (
      <dl className="space-y-1 text-xs">
        {e.content && (
          <div>
            <dt className="text-mirai-text-muted">決算の内容（主な使い道）</dt>
            <dd>{e.content}</dd>
          </div>
        )}
        {e.unused && (
          <div>
            <dt className="text-mirai-text-muted">不用額の内容（主に余ったもの）</dt>
            <dd>{e.unused}</dd>
          </div>
        )}
      </dl>
    );
  const departments = row.by_department ?? [];
  const settlementExplain = settlement && (row.explanation || departments.length > 0) && (
        <section>
          <h3 className="mb-1 text-xs font-bold text-mirai-text-muted">{departments.length > 0 ? '部局ごとの決算' : '決算の内容'}</h3>
          {explainLines(row.explanation)}
          {departments.length > 0 && (
            <ul className="space-y-2">
              {departments.map(d => (
                <li key={d.name}>
                  <div className="flex justify-between gap-2">
                    <span className="font-bold">{d.name}</span>
                    <span className="shrink-0">{yen(d.amount)}<Mark v={d.amount} /></span>
                  </div>
                  {departments.length > 1 && (
                    <p className="text-[11px] text-mirai-text-muted">
                      予算現額 {yen(d.budget_current)}・繰越 {yen(d.carried_over)}・不用額 {yen(d.unused)}
                    </p>
                  )}
                  {explainLines(d.explanation)}
                </li>
              ))}
            </ul>
          )}
        </section>
  );

  const amounts = settlementAmounts || (
      <table className="w-full text-sm">
        <tbody>
          <tr>
            <th className="py-0.5 text-left font-normal text-mirai-text-muted">本年度</th>
            <td className="text-right font-bold">{yen(row.amount)}<Mark v={row.amount} /></td>
          </tr>
          <tr>
            <th className="py-0.5 text-left font-normal text-mirai-text-muted">前年度</th>
            <td className="text-right">{yen(row.previous)}<Mark v={row.previous} /></td>
          </tr>
          {diff !== null && (
            <tr>
              <th className="py-0.5 text-left font-normal text-mirai-text-muted">増減</th>
              <td className="text-right">{diff >= 0 ? '+' : '△'}{formatBudgetFromYen(Math.abs(diff))}</td>
            </tr>
          )}
        </tbody>
      </table>
  );

  const funding = row.funding && (
        <section>
          <h3 className="mb-1 text-xs font-bold text-mirai-text-muted">財源内訳</h3>
          <table className="w-full">
            <tbody>
              {FUNDING_KINDS.map(({ key, label }) => (
                <tr key={key}>
                  <th className="py-0.5 text-left font-normal">{label}</th>
                  <td className="text-right">{yen(row.funding![key])}<Mark v={row.funding![key]} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
  );

  const itemList = topItems.length > 0 && (
        <section>
          <h3 className="mb-1 text-xs font-bold text-mirai-text-muted">説明欄の事項</h3>
          <ul className="space-y-0.5">
            {topItems.map(({ it, i }) => (
              <li key={i}>
                <div className="flex justify-between gap-2">
                  <span>
                    {it.name}
                    {it.headcount !== undefined && <span className="text-mirai-text-muted">（{it.headcount}人）</span>}
                    <NameMark src={it.name_src} />
                    {it.no_amount_printed && (
                      <span className="ml-1 text-[10px] text-amber-700" title="説明欄に事項が1つだけで金額が印字されていないため、目の額を当てています（事項の額としては検算していません）">
                        ※金額の記載なし（目の額）
                      </span>
                    )}
                  </span>
                  <span className="shrink-0">{yen(it.amount)}<Mark v={it.amount} /></span>
                </div>
                {childrenOf(i).length > 0 && (
                  <ul className="mt-0.5 space-y-0.5 border-l border-mirai-border pl-3 text-xs text-mirai-text-secondary">
                    {childrenOf(i).map(({ it: c, j }) => (
                      <li key={j} className="flex justify-between gap-2">
                        <span>
                          {c.name}
                          {c.headcount !== undefined && <span className="text-mirai-text-muted">（{c.headcount}人）</span>}
                          <NameMark src={c.name_src} />
                        </span>
                        <span className="shrink-0">{yen(c.amount)}<Mark v={c.amount} /></span>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </section>
  );

  const setsuList = row.setsu && row.setsu.length > 0 && (
        <section>
          <h3 className="mb-1 text-xs font-bold text-mirai-text-muted">
            節（{row.side === 'expense' ? '性質' : '内訳'}{settlement ? '。支出済額' : ''}）
          </h3>
          <ul className="space-y-0.5">
            {row.setsu.map((s, i) => (
              <li key={i}>
                <div className="flex justify-between gap-2">
                  <span>
                    {s.no !== null ? `${s.no} ` : ''}
                    {s.name}
                    <NameMark src={s.name_src} />
                  </span>
                  <span className="shrink-0">{yen(s.amount)}<Mark v={s.amount} /></span>
                </div>
                {/* 細節（節の内訳。旅費の「普通旅費」「費用弁償」など） */}
                {s.sub && s.sub.length > 0 && (
                  <ul className="mt-0.5 space-y-0.5 border-l border-mirai-border pl-3 text-xs text-mirai-text-secondary">
                    {s.sub.map((sb, j) => (
                      <li key={j} className="flex justify-between gap-2">
                        <span>
                          {sb.name}
                          <NameMark src={sb.name_src} />
                        </span>
                        <span className="shrink-0">{yen(sb.amount)}<Mark v={sb.amount} /></span>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </section>
  );

  const sourceList = (
      <section>
        <h3 className="mb-1 text-xs font-bold text-mirai-text-muted">出典</h3>
        <ul className="space-y-0.5 text-xs">
          {row.pages.map(p => {
            const s = sources.get(p.source);
            return (
              <li key={`${p.source}-${p.page}`}>
                {s ? (
                  <a className="text-primary-accent underline" href={`${s.url}#page=${p.page}`} target="_blank" rel="noreferrer">
                    {s.title} p.{p.page}
                  </a>
                ) : (
                  `${p.source} p.${p.page}`
                )}
              </li>
            );
          })}
        </ul>
      </section>
  );

  if (layout === 'below') {
    // 図の下に横長で置く。左に名前・金額・財源内訳・出典、中に説明欄の事項（決算は部局ごとの決算・決算の内容）、右に節。
    // 事項・節のない目（歳入の目など）は列を作らず、残りの列で幅を分ける
    const cols = [settlementExplain || itemList, setsuList].filter(Boolean);
    return (
      <div className={`grid gap-x-8 gap-y-4 p-4 text-sm text-mirai-text ${cols.length === 2 ? 'md:grid-cols-3' : cols.length === 1 ? 'md:grid-cols-2' : ''}`}>
        <div className="space-y-4">
          {head}
          {amounts}
          {funding}
          {sourceList}
        </div>
        {cols.map((c, i) => (
          <div key={i}>{c}</div>
        ))}
      </div>
    );
  }
  return (
    // パネルの枠（SidePanelChrome）は中身を切り取るだけなので、中身の側でスクロールする
    <div className="h-full space-y-4 overflow-y-auto overscroll-contain p-4 text-sm text-mirai-text">
      {head}
      {amounts}
      {funding}
      {settlementExplain}
      {itemList}
      {setsuList}
      {sourceList}
    </div>
  );
}
