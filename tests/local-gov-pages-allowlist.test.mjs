import test from 'node:test';
import assert from 'node:assert/strict';
import { isPublishedPath, requiredFiles } from '../scripts/local-gov/pages-allowlist.mjs';

test('公開物に載せる: 地方版の画面・データ・Next.js の資産・トップと 404', () => {
  for (const rel of [
    'index.html',
    'index.txt',
    '404.html',
    '_next/static/chunks/main.js',
    'local/fukuoka-pref/index.html',
    'local/fukuoka-pref/index.txt',
    'local/fukuoka-pref/funds/index.html',
    'terms/index.html',
    'privacy/index.txt',
    'data/local-gov/fukuoka-pref/index.json',
    'local-site/icon.svg',
  ]) {
    assert.equal(isPublishedPath(rel), true, rel);
  }
});

test('公開物に載せない: 国のデータ・国版の画像・本家のアイコン・未知のもの', () => {
  for (const rel of [
    'data/funds.json.gz',
    'data/mof-budget-overview-2023.json',
    'data/dictionaries/x.json',
    'data/local-gov.json',
    'og/home.png',
    'lp/hero.png',
    'logos/x.svg',
    'policy-evaluation/a.json',
    'tax-expenditures/a.json',
    'favicon.ico',
    'icon.png',
    'icon.svg',
    'apple-icon.png',
    '404/index.html',
    'new-upstream-dir/file.json',
    '',
    '/etc/passwd',
    'local/../data/funds.json.gz',
  ]) {
    assert.equal(isPublishedPath(rel), false, rel);
  }
});

test('必要なファイルの一覧は自治体ごと', () => {
  const files = requiredFiles('fukuoka-pref');
  assert.ok(files.includes('local/fukuoka-pref/index.html'));
  assert.ok(files.includes('data/local-gov/fukuoka-pref/index.json'));
  assert.ok(files.includes('404.html'));
  assert.ok(files.every(rel => isPublishedPath(rel)));
});
