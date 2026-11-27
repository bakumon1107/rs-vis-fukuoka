import test from 'node:test';
import assert from 'node:assert/strict';
import { fundFlows, fundRows, niceStep } from '../app/lib/local-gov/funds';
import type { LocalBudgetFile, LocalFunds, MokuRow, Value } from '../types/local-gov';

test('基金ごとのグラフの目盛りの間隔は 1・2・5 × 10^k で、最大値を 4 本前後で区切る', () => {
  assert.equal(niceStep(749_256_000_000), 200_000_000_000); // 減債基金 7492.56億円 → 2000億円ごと
  assert.equal(niceStep(56_427_000), 10_000_000); // 5642.7万円 → 1000万円ごと（6 本）
  assert.equal(niceStep(4_000), 1_000);
  assert.equal(niceStep(0), 1);
  // 1円より細かくしない（円の表示で「0円・0円・1円」と並んでしまう）
  assert.equal(niceStep(1), 1);
  assert.equal(niceStep(3), 1);
  for (const max of [37, 999, 1_234_567, 9_999_999_999]) {
    const s = niceStep(max);
    const lead = s / 10 ** Math.floor(Math.log10(s));
    assert.ok([1, 2, 5].includes(Math.round(lead)), `${max} → ${s}`);
    assert.ok(max / s >= 2.4 && max / s <= 7, `${max} → ${s} は ${max / s} 本`);
  }
});

const v = (n: number | null): Value => ({ v: n, src: 'ocr' });

function row(id: string, side: 'revenue' | 'expense', moku: string, amount: number | null, items: MokuRow['items'] = undefined): MokuRow {
  const [kan, kou, no] = id.split('/')[2].split('-').map(Number);
  return { id, account: 'general', side, kan: { no: kan, name: '' }, kou: { no: kou, name: '' }, moku: { no, name: moku },
    amount: v(amount), pages: [], ...(items ? { items } : {}) } as MokuRow;
}

const budget = {
  rows: [
    row('general/revenue/12-2-1', 'revenue', '財政調整基金繰入金', 21_899_939_000),
    row('general/revenue/12-1-3', 'revenue', '市町村振興基金特別会計繰入金', 52_018_000),
    row('general/revenue/12-2-9', 'revenue', '県債管理基金繰入金', null),
    row('general/expense/2-1-1', 'expense', '一般管理費', 1, [
      { name: '減債基金積立金', amount: v(259_215_000) },
      { name: '減債基金積立金', amount: v(1_000), parent: 0 },
      { name: '地方公務員災害補償基金負担金', amount: v(5) },
    ]),
    row('general/expense/2-4-4', 'expense', '地域振興費', 1, [{ name: '文化芸術振興基金積立金', amount: v(4_841_361_000) }]),
    // 特別会計としての基金への繰出しは、目でも事項でも積み立てに数える（目のときは事項を重ねて数えない）
    row('general/expense/13-2-1', 'expense', '財政調整基金特別会計繰出金', 100, [{ name: '財政調整基金特別会計繰出金', amount: v(100) }]),
    row('general/expense/13-2-2', 'expense', '特別会計繰出金', 7, [{ name: '市町村振興基金特別会計繰出金', amount: v(7) }]),
    // 親が基金の名前でない事項（「基金積立金」）の内訳は数える
    row('general/expense/2-1-9', 'expense', '財産管理費', 30, [
      { name: '基金積立金', amount: v(30) },
      { name: '公共施設整備基金積立金', amount: v(30), parent: 0 },
      // 数えた事項の内訳の内訳は重ねない（3段）
      { name: '内訳', amount: v(30), parent: 1 },
      { name: '公共施設整備基金積立金', amount: v(30), parent: 2 },
    ]),
    // 子が親より前に並んでいても重ねない
    row('general/expense/2-1-8', 'expense', '財産管理費', 40, [
      { name: '共助社会づくり基金積立金', amount: v(40), parent: 1 },
      { name: '共助社会づくり基金積立金', amount: v(40) },
    ]),
  ],
} as unknown as LocalBudgetFile;

test('fundFlows: 繰入金・特別会計繰入金・積立金を名前で基金に結ぶ。負担金・内訳・読めない額は入れない', () => {
  const { byFund } = fundFlows(budget);
  assert.deepEqual(byFund.get('財政調整基金')?.withdraw.map(x => x.amount), [21_899_939_000]);
  assert.deepEqual(byFund.get('市町村振興基金')?.withdraw.map(x => x.amount), [52_018_000]);
  assert.deepEqual(byFund.get('減債基金')?.deposit.map(x => x.amount), [259_215_000]);
  assert.deepEqual(byFund.get('財政調整基金')?.deposit.map(x => x.amount), [100]);
  assert.deepEqual(byFund.get('市町村振興基金')?.deposit.map(x => x.amount), [7]);
  assert.deepEqual(byFund.get('公共施設整備基金')?.deposit.map(x => x.amount), [30]);
  assert.deepEqual(byFund.get('共助社会づくり基金')?.deposit.map(x => x.amount), [40]);
  assert.equal(byFund.has('地方公務員災害補償基金'), false);
  assert.equal(byFund.has('県債管理基金'), false);
});

test('fundRows: 年度末現在高の多い順。予算にだけある基金は最後', () => {
  const fund = (name: string, end: number) => ({ name, kind: 'stock', no: 1, holdings: [], end, after_closing: end, history: [] });
  const funds = { items: [fund('財政調整基金', 66_716_408_000), fund('減債基金', 749_255_770_000)] } as unknown as LocalFunds;
  const rows = fundRows(funds, fundFlows(budget));
  assert.deepEqual(rows.slice(0, 2).map(r => r.name), ['減債基金', '財政調整基金']);
  assert.deepEqual(rows.slice(2).map(r => r.name).sort(), ['公共施設整備基金', '共助社会づくり基金', '市町村振興基金', '文化芸術振興基金']);
  assert.equal(rows[1].withdraw, 21_899_939_000);
  const culture = rows.find(r => r.name === '文化芸術振興基金');
  assert.equal(culture?.fund, null);
  assert.equal(culture?.deposit, 4_841_361_000);
});
