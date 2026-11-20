'use client';

/**
 * 施策の事項の詳細（表示専用）。額・前年度・柱と取組・課・科目（予算の目。サンキー図へのリンク）・説明・出典のページ。
 * 設計: docs/local-gov/tasks/20261120_1500_地方版バブル図の設計.md 6章
 */
import Link from 'next/link';
import type { LocalBudgetFile, PolicyItem, SourceDocument } from '@/types/local-gov';
import { OUTSIDE_PILLAR_NAME } from '@/app/lib/local-gov/policies';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';

interface Props {
  item: PolicyItem;
  gov: string;
  kanNames: Map<number, string>;
  file: LocalBudgetFile;
  source: SourceDocument | undefined;
  onClose: () => void;
}

export function PolicyDetail({ item, gov, kanNames, file, source, onClose }: Props) {
  const diff = item.previous === null ? null : item.amount - item.previous;
  const pillar = item.pillar === null ? OUTSIDE_PILLAR_NAME : `${item.pillar}. ${file.policies?.pillars.find(p => p.no === item.pillar)?.name ?? ''}`;
  return (
    <section className="space-y-2 rounded-2xl bg-card p-3 text-sm shadow-soft" aria-label="選んだ事項の詳細">
      <div className="flex items-start gap-2">
        <h2 className="flex-1 font-bold">
          {item.name}
          {item.is_new && <span className="ml-1 rounded bg-amber-100 px-1 text-xs font-normal text-amber-800">新規</span>}
        </h2>
        <button type="button" onClick={onClose} className="text-xs text-primary-accent underline">
          閉じる
        </button>
      </div>
      <p>
        <b>{formatBudgetFromYen(item.amount)}</b>
        {item.previous !== null && (
          <span className="text-mirai-text-muted">
            （前年度 {formatBudgetFromYen(item.previous)}
            {diff !== null && diff !== 0 && `、${diff > 0 ? '+' : '−'}${formatBudgetFromYen(Math.abs(diff))}`}）
          </span>
        )}
      </p>
      <dl className="grid grid-cols-[4.5rem_1fr] gap-x-2 gap-y-1 text-xs">
        <dt className="text-mirai-text-muted">柱</dt>
        <dd>{pillar}</dd>
        <dt className="text-mirai-text-muted">取組</dt>
        <dd>{item.initiative ?? '（なし）'}</dd>
        <dt className="text-mirai-text-muted">課</dt>
        <dd>{item.division}</dd>
        <dt className="text-mirai-text-muted">科目</dt>
        <dd>
          <ul className="space-y-0.5">
            {item.kamoku.map((k, i) => {
              const row = k.row ? file.rows.find(r => r.id === k.row) : null;
              const label = row
                ? `${row.kan.name} › ${row.kou.name} › ${row.moku.name}`
                : `${kanNames.get(k.kan) ?? `${k.kan}款`} ${k.kou ?? '?'}項 ${k.moku}目`;
              return (
                <li key={i}>
                  {row ? (
                    <Link href={`/local/${gov}?view=general&sel=${encodeURIComponent(`moku:${row.id}`)}`} className="text-primary-accent underline">
                      {label}
                    </Link>
                  ) : (
                    label
                  )}
                  {k.unmatched && <span className="text-mirai-text-muted">（資料の科目が予算の目にない。資料の印字のまま）</span>}
                  {k.kou_unresolved && <span className="text-mirai-text-muted">（資料の項が読み分けられない）</span>}
                </li>
              );
            })}
            {item.other_kamoku && <li className="text-mirai-text-muted">ほかの科目にもまたがる（資料に「外」）</li>}
          </ul>
          {item.kamoku.length > 1 && <p className="text-mirai-text-muted">額は科目ごとに分かれていません（資料は事項の合計だけ）。</p>}
        </dd>
      </dl>
      {item.notes.length > 0 && (
        <div className="text-xs">
          <p className="text-mirai-text-muted">説明（資料の内訳）</p>
          <ul className="list-disc pl-4">
            {item.notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="text-xs text-mirai-text-muted">
        出典:{' '}
        {source ? (
          <a href={`${source.url}#page=${item.source.page}`} className="text-primary-accent underline" target="_blank" rel="noreferrer">
            {source.title} {item.source.page}ページ
          </a>
        ) : (
          `${item.source.doc} ${item.source.page}ページ`
        )}
      </p>
    </section>
  );
}
