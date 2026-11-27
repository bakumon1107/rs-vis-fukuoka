/**
 * 地方版の静的サイト（GitHub Pages）に載せるファイルの許可リスト。
 * Next.js の書き出しは public/ を丸ごとコピーする（国のデータ 120MB 超・国版の OGP 等）ので、
 * 書き出しから許可したものだけを公開物にする。本家が public/ に何を足しても公開物に入らない。
 * 設計: docs/local-gov/tasks/20261127_1752_サイト全体から国版を外す設計.md 10.8
 */

/**
 * 丸ごと載せるフォルダ（書き出しの中の相対パス。末尾は /）。自治体のデータは公開する自治体の分だけ（下の isPublishedPath）。
 * ほかの自治体のデータ（確認中の下書きなど）を public/data/local-gov/ に置いても、この自治体のサイトには載せない
 */
export const ALLOWED_DIRS = ['_next/', 'local/', 'terms/', 'privacy/', 'local-site/'];

/** 自治体 ID の形（app/lib/local-gov/site-edition.ts の GOV_ID_PATTERN と同じ） */
export const GOV_ID_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
export const DEFAULT_LOCAL_GOV_ID = 'fukuoka-pref';

/** 環境変数の自治体 ID を、ビルド（site-edition.ts の localGovId）と同じ決め方で決める。形が違えば null（呼ぶ側で止める） */
export function resolveGovId(value) {
  const trimmed = (value ?? '').trim();
  if (!trimmed) return DEFAULT_LOCAL_GOV_ID;
  return GOV_ID_PATTERN.test(trimmed) ? trimmed : null;
}

/** 載せるファイル（書き出しの直下） */
export const ALLOWED_FILES = ['index.html', 'index.txt', '404.html'];

/** 公開物に必ずあるはずのファイル（なければ書き出しの失敗とみなす） */
export function requiredFiles(gov) {
  return ['index.html', '404.html', `local/${gov}/index.html`, `local/${gov}/funds/index.html`, `local/${gov}/about/index.html`, 'terms/index.html', 'privacy/index.html', `data/local-gov/${gov}/index.json`];
}

/** 書き出しの中の相対パス（/ 区切り）を公開物に載せるか。gov は公開する自治体の ID */
export function isPublishedPath(rel, gov = DEFAULT_LOCAL_GOV_ID) {
  if (!rel || rel.startsWith('/') || rel.split('/').includes('..')) return false;
  return ALLOWED_FILES.includes(rel) || ALLOWED_DIRS.some(dir => rel.startsWith(dir)) || rel.startsWith(`data/local-gov/${gov}/`);
}
