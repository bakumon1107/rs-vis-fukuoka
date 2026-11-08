/**
 * 値の出典の印（画像で確認して修正・空欄を 0 とみなした など）。確定した読み取り（text・ocr）には付けない。表示専用。
 * 詳細パネルと「データについて」で同じ条件・同じ表示名にする（設計書 4.4）
 */
import type { ValueSource } from '@/types/local-gov';
import { isNotableValueSource, VALUE_SRC_LABEL } from '@/client/lib/local-gov-labels';

export function ValueSourceMark({ src, className = 'ml-1 text-[10px] text-amber-700' }: { src: ValueSource | undefined; className?: string }) {
  if (!src || !isNotableValueSource(src)) return null;
  return <span className={className}>（{VALUE_SRC_LABEL[src]}）</span>;
}
