import test from 'node:test';
import assert from 'node:assert/strict';
import { basePath, DEFAULT_LOCAL_GOV_ID, isLocalEdition, localGovId, siteEdition, withBasePath } from '../app/lib/local-gov/site-edition';
import { LOCAL_PAGE_PATHS, localGaMeasurementId, localPageMetadata } from '../app/lib/local-gov/site';
import { SITE_URL } from '../app/lib/site-url';

test('画面のメタデータ: 地方版は canonical・og:url をこの画面の絶対 URL、国版のビルドでは noindex で canonical なし', () => {
  const local = localPageMetadata('基金', LOCAL_PAGE_PATHS.funds(), true);
  const url = `${SITE_URL.replace(/\/$/, '')}/local/fukuoka-pref/funds/`;
  assert.equal(local.alternates?.canonical, url);
  assert.equal((local.openGraph as { url?: string }).url, url);
  assert.equal(local.robots, undefined);
  const national = localPageMetadata('基金', LOCAL_PAGE_PATHS.funds(), false);
  // canonical は null（ルートレイアウトの国版トップの canonical を継承させない）
  assert.equal(national.alternates?.canonical, null);
  assert.deepEqual(national.robots, { index: false, follow: false });
  assert.equal((national.openGraph as { url?: string }).url, undefined);
});
import { withLocalStaticExport } from '../next.config.local';

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
