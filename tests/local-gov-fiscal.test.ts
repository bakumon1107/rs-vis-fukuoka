import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { formatIndicator, latestChange, niceScale, reservePoints } from '../app/lib/local-gov/fiscal';
import { validateFiscalFile } from '../app/lib/local-gov/validate';
import { tipStyle } from '../client/lib/local-gov-tooltip';
import type { FiscalIndicator, LocalFiscalFile, LocalGovIndex } from '../types/local-gov';

const ind = (key: FiscalIndicator['key'], over: Partial<FiscalIndicator> = {}): FiscalIndicator => ({
  key,
  label: key,
  unit: key === 'fiscal_capacity' ? '' : '%',
  good: key === 'fiscal_capacity' ? 'high' : 'low',
  threshold: key === 'debt_service' ? 25 : key === 'future_burden' ? 400 : null,
  values: [
    { year: 2023, value: 10, median: 9, rank: 5, of: 47, source: 'r5-shihyo' },
    { year: 2024, value: 11, median: 9, rank: 6, of: 47, source: 'r6-shihyo' },
  ],
  ...over,
});

const fiscal = (over: Partial<LocalFiscalFile> = {}): LocalFiscalFile => ({
  schema_version: 1,
  gov_id: 'fukuoka-pref',
  reserve: {
    label: '三基金',
    parts: ['a', 'b'],
    history: [
      { year: 2024, total: 30, parts: [10, 20], source: 'r6-kikin', page: 2 },
      { year: 2025, total: 40, parts: [15, 25], source: 'r7-kikin', page: 2 },
    ],
    outlook: { year: 2026, total: 35, as_of: 'R8当初予算の時点', source: 'r8-gaiyou', page: 2 },
    target: { year: 2026, min: 20, max: 30, plan: 'プラン', source: 'r8-gaiyou', page: 2 },
  },
  indicators: [ind('fiscal_capacity'), ind('current_balance'), ind('debt_service'), ind('future_burden')],
  ...over,
});

const index: LocalGovIndex = {
  schema_version: 1,
  gov: { id: 'fukuoka-pref', name: '福岡県', kind: 'prefecture' },
  datasets: [],
  fiscal: 'fiscal-indicators.json',
  sources: ['r6-kikin', 'r7-kikin', 'r8-gaiyou', 'r5-shihyo', 'r6-shihyo'].map(id => ({
    id, title: id, url: 'https://example.invalid/x', sha256: 'x', retrieved: '2026-11-28',
  })),
};

test('三基金の点: 実績を年度順に、見込みは最後の実績の次の年度のときだけ足す', () => {
  const pts = reservePoints(fiscal());
  assert.deepEqual(pts.map(p => [p.year, p.kind]), [[2024, 'actual'], [2025, 'actual'], [2026, 'outlook']]);
  const gap = fiscal();
  gap.reserve.outlook = { ...gap.reserve.outlook!, year: 2027 };
  assert.equal(reservePoints(gap).length, 2);
});

test('ツールチップの位置: 点と反対の側に寄せ、図の幅に収める', () => {
  // 右半分の点 → 左寄せ。左半分の点 → 右寄せ
  assert.deepEqual(tipStyle(500, 640, 224, 60, 20, 4), { width: 224, left: 60, top: 4 });
  assert.deepEqual(tipStyle(100, 640, 224, 60, 20, 4), { width: 224, left: 396, top: 4 });
  // 狭い図: 右端からはみ出さない・左端は 0 より左にしない
  assert.equal(tipStyle(200, 270, 224, 60, 20, 4).left, 46);
  assert.equal(tipStyle(50, 200, 200, 60, 20, 4).left, 0);
});

test('目盛り: 1・2・5 の刻みで最大を含む', () => {
  assert.deepEqual(niceScale(83_500_000_000), { top: 100_000_000_000, step: 20_000_000_000 });
  assert.deepEqual(niceScale(0), { top: 1, step: 1 });
});

test('指標の向き: 財政力指数は上がると良い、比率は下がると良い。表示の桁で同じなら同じ', () => {
  assert.equal(latestChange(ind('fiscal_capacity'))!.direction, 'better');
  assert.equal(latestChange(ind('current_balance'))!.direction, 'worse');
  const same = ind('current_balance', {
    values: [
      { year: 2023, value: 95.61, median: 90, rank: 1, of: 47, source: 's' },
      { year: 2024, value: 95.63, median: 90, rank: 1, of: 47, source: 's' },
    ],
  });
  assert.equal(latestChange(same)!.direction, 'same');
  assert.equal(formatIndicator({ unit: '' }, 0.63618), '0.64');
  assert.equal(formatIndicator({ unit: '%' }, 95.6), '95.6%');
});

test('財政の指標のファイルの検証: 正しいものは誤りなし。各条件の誤りを見つける', () => {
  assert.deepEqual(validateFiscalFile(fiscal(), index), []);
  const errs = (f: LocalFiscalFile) => validateFiscalFile(f, index);
  const bad = fiscal();
  bad.reserve.history[1] = { ...bad.reserve.history[1], parts: [15, 24] };
  assert.ok(errs(bad).some(e => e.includes('parts の合計')));
  const gap = fiscal();
  gap.reserve.history[1] = { ...gap.reserve.history[1], year: 2026 };
  assert.ok(errs(gap).some(e => e.includes('年度が続いていない')));
  const outlook = fiscal();
  outlook.reserve.outlook = { ...outlook.reserve.outlook!, year: 2027 };
  assert.ok(errs(outlook).some(e => e.includes('最後の実績')));
  const target = fiscal();
  target.reserve.target = { ...target.reserve.target!, min: 40 };
  assert.ok(errs(target).some(e => e.includes('min ≦ max')));
  assert.ok(errs(fiscal({ indicators: [ind('fiscal_capacity')] })).some(e => e.includes('種類がそろわない')));
  assert.ok(errs(fiscal({ indicators: [ind('fiscal_capacity', { threshold: 1 }), ind('current_balance'), ind('debt_service'), ind('future_burden')] }))
    .some(e => e.includes('threshold')));
  const rank = ind('debt_service', { values: [{ year: 2024, value: 1, median: 1, rank: 48, of: 47, source: 'r6-shihyo' }] });
  assert.ok(errs(fiscal({ indicators: [ind('fiscal_capacity'), ind('current_balance'), rank, ind('future_burden')] })).some(e => e.includes('順位')));
  const src = fiscal();
  src.reserve.history[0] = { ...src.reserve.history[0], source: 'r9-unknown' };
  assert.ok(errs(src).some(e => e.includes('出典 r9-unknown')));
  assert.ok(validateFiscalFile(fiscal({ gov_id: 'other' }), index).some(e => e.includes('gov_id')));
});

// 書き出した実データ（index.json の fiscal が指すファイル）を検証する。まだなければ飛ばす
const DATA_DIR = path.join(process.cwd(), 'public', 'data', 'local-gov');
const fiscalFiles = fs.existsSync(DATA_DIR)
  ? fs.readdirSync(DATA_DIR).flatMap(gov => {
      const p = path.join(DATA_DIR, gov, 'index.json');
      if (!fs.existsSync(p)) return [];
      const idx = JSON.parse(fs.readFileSync(p, 'utf-8')) as LocalGovIndex;
      return idx.fiscal ? [{ idx, file: path.join(DATA_DIR, gov, idx.fiscal) }] : [];
    })
  : [];

test('書き出した財政の指標のファイルが検証を通る', { skip: fiscalFiles.length === 0 ? '書き出したデータがまだない' : false }, () => {
  for (const { idx, file } of fiscalFiles) {
    const f = JSON.parse(fs.readFileSync(file, 'utf-8')) as LocalFiscalFile;
    assert.deepEqual(validateFiscalFile(f, idx), [], path.relative(process.cwd(), file));
  }
});
