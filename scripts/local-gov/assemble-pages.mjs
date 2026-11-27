#!/usr/bin/env node
/**
 * 地方版の静的書き出し（.next-local/）から、GitHub Pages に載せる公開物（out/）を組み立てる。
 * 許可リスト（pages-allowlist.mjs）にあるものだけをコピーし、.nojekyll を置き、大きさと中身を確かめて出力する。
 *
 * 使い方（リポジトリの直下で）:
 *   NEXT_PUBLIC_SITE_EDITION=local NEXT_PUBLIC_BASE_PATH=/yosan-view-fukuoka-pref npx next build
 *   node scripts/local-gov/assemble-pages.mjs [書き出し=.next-local] [公開物=out]
 * 公開物のフォルダは毎回作り直す（このスクリプトの出力専用。.gitignore の /out/ に当たる）。
 */
import fs from 'node:fs';
import path from 'node:path';
import { isPublishedPath, requiredFiles, resolveGovId } from './pages-allowlist.mjs';

const [src = '.next-local', dest = 'out'] = process.argv.slice(2);
// ビルドと同じ決め方（形の違う ID はビルドが既定の自治体に落とすので、ここでは食い違いを避けて止める）
const gov = resolveGovId(process.env.NEXT_PUBLIC_LOCAL_GOV_ID);
if (gov === null) {
  console.error(`NEXT_PUBLIC_LOCAL_GOV_ID の形が正しくありません（英小文字・数字・ハイフン）: ${process.env.NEXT_PUBLIC_LOCAL_GOV_ID}`);
  process.exit(1);
}

if (!fs.existsSync(path.join(src, 'index.html'))) {
  console.error(`書き出しが見つかりません: ${src}/index.html（地方版のビルドを先に実行してください）`);
  process.exit(1);
}
// 作り直すときに消すので、ビルドの出力用の名前（.gitignore の /out/・/.next-*/）だけを受け付ける
const destName = path.basename(path.resolve(dest));
if (destName !== 'out' && !destName.startsWith('.next-')) {
  console.error(`公開物のフォルダは out か .next- で始まる名前にしてください（作り直すときに消すため）: ${dest}`);
  process.exit(1);
}
// 書き出しと同じフォルダ・どちらかがもう一方の中にあると、作り直しで書き出しを消してしまう
// シンボリックリンク（out → .next-local など）も実体で比べる。まだない公開物のフォルダは親の実体からたどる
const real = (p) => (fs.existsSync(p) ? fs.realpathSync(p) : path.join(fs.realpathSync(path.dirname(path.resolve(p))), path.basename(p)));
const srcAbs = real(src);
const destAbs = real(dest);
const inside = (a, b) => a === b || a.startsWith(b + path.sep);
if (inside(destAbs, srcAbs) || inside(srcAbs, destAbs)) {
  console.error(`公開物のフォルダは書き出しのフォルダと別にしてください: 書き出し ${src} / 公開物 ${dest}`);
  process.exit(1);
}
fs.rmSync(dest, { recursive: true, force: true });

/** フォルダの中のファイルを相対パス（/ 区切り）で列挙する */
function walk(dir, base = '') {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const rel = base ? `${base}/${entry.name}` : entry.name;
    if (entry.isDirectory()) out.push(...walk(path.join(dir, entry.name), rel));
    else if (entry.isFile()) out.push(rel);
  }
  return out;
}

const all = walk(src);
let bytes = 0;
let copied = 0;
const skippedTop = new Map();
for (const rel of all) {
  if (!isPublishedPath(rel, gov)) {
    const top = rel.split('/')[0];
    skippedTop.set(top, (skippedTop.get(top) ?? 0) + 1);
    continue;
  }
  const to = path.join(dest, rel);
  fs.mkdirSync(path.dirname(to), { recursive: true });
  fs.copyFileSync(path.join(src, rel), to);
  bytes += fs.statSync(to).size;
  copied += 1;
}
// GitHub Pages の Jekyll に _next/ を無視させない
fs.writeFileSync(path.join(dest, '.nojekyll'), '');

const missing = requiredFiles(gov).filter(rel => !fs.existsSync(path.join(dest, rel)));
const mb = (n) => `${(n / 1024 / 1024).toFixed(1)}MB`;
console.log(`公開物: ${dest}（${copied} ファイル、${mb(bytes)}）`);
const byTop = new Map();
for (const rel of walk(dest)) {
  const top = rel.includes('/') ? `${rel.split('/')[0]}/` : rel;
  byTop.set(top, (byTop.get(top) ?? 0) + fs.statSync(path.join(dest, rel)).size);
}
for (const [top, size] of [...byTop].sort((a, b) => b[1] - a[1])) console.log(`  ${top.padEnd(16)} ${mb(size)}`);
console.log(`載せなかったもの（書き出しの直下ごとの件数）: ${[...skippedTop].map(([k, v]) => `${k} ${v}`).join('、') || 'なし'}`);
if (missing.length > 0) {
  console.error(`公開物に必要なファイルがありません: ${missing.join('、')}`);
  process.exit(1);
}
