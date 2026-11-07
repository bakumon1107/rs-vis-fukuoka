'use client';

/**
 * 選んだ目の詳細（表示専用）。本年度・前年度・増減、財源内訳、説明欄の事項、節、出典（PDF のページ）、値・名前の出典の印。
 * 設計: docs/local-gov/tasks/20261106_1327_地方版サンキー図の画面とグラフの設計.md 4.2・4.4
 */
import type { LocalGovIndex, MokuRow, NameSource, Value, ValueSource } from '@/types/local-gov';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';
import { FUNDING_KINDS } from '@/app/lib/local-gov/graph';

const NAME_SRC_LABEL: Record<NameSource, string> = {
  text: '資料のテキスト',
  reference: '別の資料と照合',
  search: '資料の全文検索で確認',
  readings: '複数の読み取りが一致',
  correction: '画像で確認',
  ocr: '読み取り（裏付けなし）',
};

const VALUE_SRC_NOTE: Partial<Record<ValueSource, string>> = {
  correction: '画像で確認して修正',
  textlayer: 'PDF の文字情報から採用',
  'blank-as-zero': '空欄を 0 とみなした',
  inferred: '推定',
};


function yen(v: Value | undefined) {
  return v && v.v !== null ? formatBudgetFromYen(v.v) : '—';
}

function Mark({ v }: { v: Value | undefined }) {
  const note = v ? VALUE_SRC_NOTE[v.src] : undefined;
  return note ? <span className="ml-1 text-[10px] text-amber-700">（{note}）</span> : null;
}

function NameMark({ src }: { src?: NameSource }) {
  // 名前の出典がない名前も裏付けがないので、ocr と同じに扱う（設計書 4.4。図の印・「データについて」の件数と同じ）
  if (src !== undefined && src !== 'ocr') return null;
  return <span className="ml-1 text-[10px] text-amber-700" title={NAME_SRC_LABEL.ocr}>※名前は読み取り</span>;
}

export function LocalDetailPanel({ row, index, accountName }: { row: MokuRow; index: LocalGovIndex; accountName: string }) {
  const diff = row.amount.v !== null && row.previous?.v != null ? row.amount.v - row.previous.v : null;
  const sources = new Map(index.sources.map(s => [s.id, s]));
  // 説明欄の事項は、親の事項の下に内訳（入れ子の事項）を字下げして並べる。
  // 内訳にも見ておきたいものがある（議会費の「各種負担金等」の内訳の「議員連盟補助金」「政務活動費交付金」など）
  const items = row.items ?? [];
  const topItems = items.map((it, i) => ({ it, i })).filter(({ it }) => it.parent === undefined);
  const childrenOf = (i: number) => items.map((it, j) => ({ it, j })).filter(({ it }) => it.parent === i);

  return (
    // パネルの枠（SidePanelChrome）は中身を切り取るだけなので、中身の側でスクロールする
    <div className="h-full space-y-4 overflow-y-auto overscroll-contain p-4 text-sm text-mirai-text">
      <div>
        <p className="text-xs text-mirai-text-muted">
          {/* 全会計の見方では同じ名前の款（公債費・予備費など）が複数の会計にあるので、会計の名前も出す */}
          {accountName} ／ {row.kan.name} ／ {row.kou.name}
        </p>
        <h2 className="text-base font-bold">
          {row.moku.name}
          <NameMark src={row.moku.name_src} />
        </h2>
        <p className="text-[11px] text-mirai-text-muted">名前の出典: {NAME_SRC_LABEL[row.moku.name_src ?? 'ocr']}</p>
      </div>

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

      {row.funding && (
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
      )}

      {topItems.length > 0 && (
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
      )}

      {row.setsu && row.setsu.length > 0 && (
        <section>
          <h3 className="mb-1 text-xs font-bold text-mirai-text-muted">節（{row.side === 'expense' ? '性質' : '内訳'}）</h3>
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
      )}

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
    </div>
  );
}
