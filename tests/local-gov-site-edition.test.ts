import test from 'node:test';
import assert from 'node:assert/strict';
import {
  DEFAULT_LOCAL_GOV_ID,
  isLocalEdition,
  localGovId,
  routeForLocalEdition,
  siteEdition,
} from '../app/lib/local-gov/site-edition';
import { localGaMeasurementId } from '../app/lib/local-gov/site';

const GOV = 'fukuoka-pref';
const route = (path: string) => routeForLocalEdition(path, GOV);

test('版の判定: local のときだけ地方版。未設定・その他は国版', () => {
  assert.equal(siteEdition('local'), 'local');
  assert.equal(siteEdition(' local '), 'local');
  assert.equal(siteEdition(undefined), 'national');
  assert.equal(siteEdition(''), 'national');
  assert.equal(siteEdition('national'), 'national');
  assert.equal(siteEdition('Local'), 'national');
  assert.equal(isLocalEdition('local'), true);
  assert.equal(isLocalEdition(undefined), false);
});

test('自治体 ID: 未設定・不正なら既定（福岡県）', () => {
  assert.equal(localGovId('fukuoka-city'), 'fukuoka-city');
  assert.equal(localGovId(undefined), DEFAULT_LOCAL_GOV_ID);
  assert.equal(localGovId(''), DEFAULT_LOCAL_GOV_ID);
  assert.equal(localGovId('../etc'), DEFAULT_LOCAL_GOV_ID);
  assert.equal(localGovId('Fukuoka'), DEFAULT_LOCAL_GOV_ID);
});

test('トップと /local は自治体のサンキー図へリダイレクト', () => {
  assert.deepEqual(route('/'), { kind: 'redirect', to: '/local/fukuoka-pref' });
  assert.deepEqual(route('/local'), { kind: 'redirect', to: '/local/fukuoka-pref' });
  assert.deepEqual(route('/local/'), { kind: 'redirect', to: '/local/fukuoka-pref' });
  assert.deepEqual(routeForLocalEdition('/', 'fukuoka-city'), { kind: 'redirect', to: '/local/fukuoka-city' });
});

test('地方版の画面・データ・書き換え先はそのまま通す', () => {
  for (const path of [
    '/local/fukuoka-pref',
    '/local/fukuoka-pref/',
    '/local/fukuoka-pref/funds',
    '/local/fukuoka-pref/about',
    '/local-site/terms',
    '/local-site/icon.svg',
    '/data/local-gov/fukuoka-pref/index.json',
    '/og/local/fukuoka-pref.png',
    '/_next/static/chunks/main.js',
    '/__nextjs_original-stack-frame',
  ]) {
    assert.deepEqual(route(path), { kind: 'pass' }, path);
  }
});

test('規約・プライバシー・サイトマップ・robots・アイコンは地方版の中身へ書き換え', () => {
  assert.deepEqual(route('/terms'), { kind: 'rewrite', to: '/local-site/terms' });
  assert.deepEqual(route('/terms/'), { kind: 'rewrite', to: '/local-site/terms' });
  assert.deepEqual(route('/privacy'), { kind: 'rewrite', to: '/local-site/privacy' });
  assert.deepEqual(route('/sitemap.xml'), { kind: 'rewrite', to: '/local-site/sitemap.xml' });
  assert.deepEqual(route('/robots.txt'), { kind: 'rewrite', to: '/local-site/robots.txt' });
  for (const icon of ['/favicon.ico', '/icon.svg', '/icon.png', '/apple-icon.png']) {
    assert.deepEqual(route(icon), { kind: 'rewrite', to: '/local-site/icon.svg' }, icon);
  }
});

test('国版のページはトップへリダイレクト（本家が足した未知のページも）', () => {
  for (const path of [
    '/budget-sankey',
    '/sankey-svg',
    '/project-bubble',
    '/quality',
    '/subcontracts/123',
    '/vendors',
    '/funds',
    '/mof-kou/1',
    '/mof-budget-overview/transfer-detail',
    '/lp',
    '/some-new-upstream-page',
    '/localx',
  ]) {
    assert.deepEqual(route(path), { kind: 'redirect', to: '/' }, path);
  }
});

test('API と国の静的ファイルは 404', () => {
  for (const path of [
    '/api',
    '/api/funds',
    '/api/mcp',
    '/api/ai/sankey-chat',
    '/api/projects/1/comments',
    '/data/funds.json.gz',
    '/data/local-gov.json',
    '/og/home.png',
    '/lp/hero.png',
  ]) {
    assert.deepEqual(route(path), { kind: 'notFound' }, path);
  }
});

test('地方版の GA: G- 形式の ID を明示したときだけ', () => {
  assert.equal(localGaMeasurementId(undefined), null);
  assert.equal(localGaMeasurementId(''), null);
  assert.equal(localGaMeasurementId('UA-123'), null);
  assert.equal(localGaMeasurementId(' G-ABC123 '), 'G-ABC123');
});
