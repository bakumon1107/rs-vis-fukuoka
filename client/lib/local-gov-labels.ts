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

/**
 * 歳出の財源内訳と歳入の款の区分の違いのうち、説明書を読んで確かめたもの（自治体・年度・予算の種類ごと。「データについて」に出す）。
 * 根拠: docs/local-gov/fukuoka/20261114_0005_財源内訳と歳入の款の差の調査.md。
 * 自治体ごとの説明文なので、2件目の自治体を載せるときに index.json に移す（画面とグラフの設計 4.2）
 */
const FUNDING_RECLASS_NOTES: Record<string, string[]> = {
  'fukuoka-pref/2026/initial': [
    '国の「物価高騰対応重点支援地方創生臨時交付金」約67億円は、歳入では国庫支出金ですが、歳出の財源内訳では一般財源に数えられています（差の額が千円の位まで一致）。',
    '県債のうち「調整債」約133億円は、歳入では県債ですが、歳出の財源内訳では一般財源に数えられています（差の額が千円の位まで一致）。',
    '繰入金のうち財政調整基金繰入金・減債基金繰入金・特別会計繰入金（ほかの会計からの繰入金。この図に描いていない公営企業会計からの分を含む）の合わせて約325億円は、歳出の財源内訳では一般財源に数えられています（財源内訳の欄の読み取りから財源の名前ごとに足し上げた差が、この3つの合計と千円の位まで一致）。',
    '寄附金（一般寄附金）のうち約11億円も、一般財源に数えられています（同じく財源の名前ごとの足し上げから求めた額）。',
    'このほか、諸収入・財産収入・使用料及び手数料の一部（合わせて約157億円）も一般財源に数えられています。この額は財源の名前ごとの足し上げから求めた概算で、どの収入かは説明書に書かれていません。',
  ],
};

/** 財源内訳と歳入の款の違いのうち確かめたもの（なければ undefined） */
export function fundingReclassNotes(govId: string, file: { year: number; basis: string }): string[] | undefined {
  return FUNDING_RECLASS_NOTES[`${govId}/${file.year}/${file.basis}`];
}

/** 表に並べる順（型の一覧と同じ順） */
export const NAME_SOURCE_ORDER: readonly NameSource[] = NAME_SOURCES;
export const VALUE_SOURCE_ORDER: readonly ValueSource[] = VALUE_SOURCES;
