/**
 * 地方版の静的サイト（GitHub Pages）に載せるファイルの許可リスト。
 * Next.js の書き出しは public/ を丸ごとコピーする（国のデータ 120MB 超・国版の OGP 等）ので、
 * 書き出しから許可したものだけを公開物にする。本家が public/ に何を足しても公開物に入らない。
 * 設計: docs/local-gov/tasks/20261127_1752_サイト全体から国版を外す設計.md 10.8
 */

/** 丸ごと載せるフォルダ（書き出しの中の相対パス。末尾は /） */
export const ALLOWED_DIRS = ['_next/', 'local/', 'terms/', 'privacy/', 'data/local-gov/', 'local-site/'];

/** 載せるファイル（書き出しの直下） */
export const ALLOWED_FILES = ['index.html', 'index.txt', '404.html'];

/** 公開物に必ずあるはずのファイル（なければ書き出しの失敗とみなす） */
export function requiredFiles(gov) {
  return ['index.html', '404.html', `local/${gov}/index.html`, `local/${gov}/funds/index.html`, `local/${gov}/about/index.html`, 'terms/index.html', 'privacy/index.html', `data/local-gov/${gov}/index.json`];
}

/** 書き出しの中の相対パス（/ 区切り）を公開物に載せるか */
export function isPublishedPath(rel) {
  if (!rel || rel.startsWith('/') || rel.split('/').includes('..')) return false;
  return ALLOWED_FILES.includes(rel) || ALLOWED_DIRS.some(dir => rel.startsWith(dir));
}
