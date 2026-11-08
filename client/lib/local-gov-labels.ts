/**
 * 地方版の画面に出す、名前の出典・値の出典の表示名（詳細パネル・「データについて」で同じ言い回しにする）。
 * 設計: docs/local-gov/tasks/20261106_1327_地方版サンキー図の画面とグラフの設計.md 4.4
 */
import { NAME_SOURCES, VALUE_SOURCES, type NameSource, type ValueSource } from '@/types/local-gov';

/** 名前の出典（NameSource）の表示名 */
export const NAME_SRC_LABEL: Record<NameSource, string> = {
  text: '資料のテキスト',
  reference: '別の資料と照合',
  search: '資料の全文検索で確認',
  readings: '複数の読み取りが一致',
  correction: '画像で確認',
  ocr: '読み取りのみ（裏付けなし）',
};

/** 値の出典（ValueSource）の表示名 */
export const VALUE_SRC_LABEL: Record<ValueSource, string> = {
  text: '資料のテキスト',
  ocr: '読み取り',
  textlayer: 'PDF の文字情報から採用',
  correction: '画像で確認して修正',
  'blank-as-zero': '空欄を 0 とみなした',
  inferred: '推定',
};

/** 値に印を付ける出典か（判定はドメイン側の summary.ts。表示名と一緒に使うのでここからも出す） */
export { isNotableValueSource } from '@/app/lib/local-gov/summary';

/** 表に並べる順（型の一覧と同じ順） */
export const NAME_SOURCE_ORDER: readonly NameSource[] = NAME_SOURCES;
export const VALUE_SOURCE_ORDER: readonly ValueSource[] = VALUE_SOURCES;
