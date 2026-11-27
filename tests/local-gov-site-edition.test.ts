import test, { after, before } from 'node:test';
import assert from 'node:assert/strict';
import {
  basePath, DEFAULT_LOCAL_GOV_ID, GOV_ID_PATTERN, isLocalEdition, localGovId, siteEdition, withBasePath,
} from '../app/lib/local-gov/site-edition';
import { LOCAL_PAGE_PATHS, localGaMeasurementId, localPageMetadata } from '../app/lib/local-gov/site';
import { SITE_URL } from '../app/lib/site-url';
import { withLocalStaticExport } from '../next.config.local';
import * as allowlist from '../scripts/local-gov/pages-allowlist.mjs';

// 「未設定」を確かめるテストは、関数の既定の引数が読む環境変数に左右される（福岡県版の環境変数を付けて npm test すると落ちる）。
// このファイルのテストの間だけ外し、終わったら元に戻す
const ENV_KEYS = ['NEXT_PUBLIC_SITE_EDITION', 'NEXT_PUBLIC_LOCAL_GOV_ID', 'NEXT_PUBLIC_BASE_PATH', 'NEXT_PUBLIC_GA_MEASUREMENT_ID'];
const savedEnv = new Map<string, string | undefined>();
before(() => {
  for (const k of ENV_KEYS) {
    savedEnv.set(k, process.env[k]);
    delete process.env[k];
  }
});
after(() => {
  for (const [k, v] of savedEnv) {
    if (v === undefined) delete process.env[k];
    else process.env[k] = v;
  }
});

test('公開物の組み立て（pages-allowlist.mjs）の自治体 ID の決め方は、ビルド（site-edition.ts）と同じ', () => {
  // .mjs は TypeScript を読めないので写しを持っている。食い違うと、書き出しと組み立てが別の自治体を見る
  assert.equal(allowlist.GOV_ID_PATTERN.source, GOV_ID_PATTERN.source);
  assert.equal(allowlist.GOV_ID_PATTERN.flags, GOV_ID_PATTERN.flags);
  assert.equal(allowlist.DEFAULT_LOCAL_GOV_ID, DEFAULT_LOCAL_GOV_ID);
  // 同じ入力で同じ自治体になる（組み立ては形の違う ID で止める＝null、ビルドは既定に落とす）
  for (const v of [undefined, '', '  ', ' fukuoka-city ', 'fukuoka-pref', 'Fukuoka-Pref', 'a_b', 'kita-kyushu-2']) {
    const r = allowlist.resolveGovId(v);
    if (r === null) assert.equal(localGovId(v), DEFAULT_LOCAL_GOV_ID, String(v));
    else assert.equal(r, localGovId(v), String(v));
  }
});

test('画面のメタデータ: 地方版は canonical・og:url をこの画面の絶対 URL、国版のビルドでは noindex で canonical なし', () => {
  // 期待値は自治体 ID を文字で書く（パスを作る関数と同じ関数で期待値を作ると、ID の誤りを見逃す）
  const path = '/local/fukuoka-pref/funds/';
  const local = localPageMetadata('基金', path, { local: true });
  const url = `${SITE_URL.replace(/\/$/, '')}/local/fukuoka-pref/funds/`;
  assert.equal(local.alternates?.canonical, url);
  assert.equal((local.openGraph as { url?: string }).url, url);
  assert.equal(local.robots, undefined);
  assert.equal(LOCAL_PAGE_PATHS.funds(), `/local/${localGovId()}/funds/`);
  const national = localPageMetadata('基金', path, { local: false });
  // canonical は null（ルートレイアウトの国版トップの canonical を継承させない）
  assert.equal(national.alternates?.canonical, null);
  assert.deepEqual(national.robots, { index: false, follow: false });
  assert.equal((national.openGraph as { url?: string }).url, undefined);
  // 画面ごとの説明は description・OGP・twitter のすべてに入る
  const terms = localPageMetadata('利用規約', LOCAL_PAGE_PATHS.terms(), { local: true, description: '規約の説明' });
  assert.equal(terms.description, '規約の説明');
  assert.equal((terms.openGraph as { description?: string }).description, '規約の説明');
  assert.equal((terms.twitter as { description?: string }).description, '規約の説明');
});

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

test('basePath: 先頭に / を付け、末尾の / は外す。未設定・空・/ だけなら空', () => {
  assert.equal(basePath('/yosan-view-fukuoka-pref'), '/yosan-view-fukuoka-pref');
  assert.equal(basePath('yosan-view-fukuoka-pref/'), '/yosan-view-fukuoka-pref');
  assert.equal(basePath(' /yosan-view-fukuoka-pref// '), '/yosan-view-fukuoka-pref');
  assert.equal(basePath(undefined), '');
  assert.equal(basePath(''), '');
  assert.equal(basePath('/'), '');
  assert.equal(withBasePath('/data/local-gov/fukuoka-pref', '/yosan-view-fukuoka-pref'), '/yosan-view-fukuoka-pref/data/local-gov/fukuoka-pref');
  assert.equal(withBasePath('/data/local-gov/fukuoka-pref', ''), '/data/local-gov/fukuoka-pref');
});

test('地方版の GA: G- 形式の ID を明示したときだけ', () => {
  assert.equal(localGaMeasurementId(undefined), null);
  assert.equal(localGaMeasurementId(''), null);
  assert.equal(localGaMeasurementId('UA-123'), null);
  assert.equal(localGaMeasurementId(' G-ABC123 '), 'G-ABC123');
});

test('ビルド設定: 国版（版の指定なし）では設定をそのまま返す', () => {
  const saved = process.env.NEXT_PUBLIC_SITE_EDITION;
  delete process.env.NEXT_PUBLIC_SITE_EDITION;
  try {
    const config = { reactStrictMode: true };
    assert.equal(withLocalStaticExport(config), config);
  } finally {
    if (saved !== undefined) process.env.NEXT_PUBLIC_SITE_EDITION = saved;
  }
});

test('ビルド設定: 地方版では静的書き出し・*.local.tsx だけ・basePath・headers なし', () => {
  const saved = { edition: process.env.NEXT_PUBLIC_SITE_EDITION, base: process.env.NEXT_PUBLIC_BASE_PATH };
  process.env.NEXT_PUBLIC_SITE_EDITION = 'local';
  process.env.NEXT_PUBLIC_BASE_PATH = '/yosan-view-fukuoka-pref/';
  try {
    const config = withLocalStaticExport({ reactStrictMode: true, headers: async () => [] });
    assert.equal(config.output, 'export');
    assert.deepEqual(config.pageExtensions, ['local.tsx', 'local.ts']);
    assert.equal(config.basePath, '/yosan-view-fukuoka-pref');
    assert.equal(config.trailingSlash, true);
    assert.equal(config.headers, undefined);
    assert.equal(config.reactStrictMode, true);
  } finally {
    for (const [key, value] of [['NEXT_PUBLIC_SITE_EDITION', saved.edition], ['NEXT_PUBLIC_BASE_PATH', saved.base]] as const) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
});
