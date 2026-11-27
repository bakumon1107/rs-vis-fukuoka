import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { netTotal, personnelShare } from '../app/lib/local-gov/totals';
import type { LocalBudgetFile, MokuRow, Value } from '../types/local-gov';

const v = (n: number | null): Value => ({ v: n, src: 'ocr' });

function row(id: string, amount: number, over: Partial<MokuRow> = {}): MokuRow {
  const [account, side, nums] = id.split('/');
  const [kan, kou, moku] = nums.split('-').map(Number);
  return {
    id, account, side: side as MokuRow['side'], kan: { no: kan, name: '款' }, kou: { no: kou, name: '項' }, moku: { no: moku, name: '目' },
    amount: v(amount), pages: [], ...over,
  } as MokuRow;
}

const setsu = (pairs: [string, number][]) => pairs.map(([name, n], i) => ({ no: i + 1, name, amount: v(n) }));

const file = (rows: MokuRow[], over: Partial<LocalBudgetFile> = {}) => ({
  schema_version: 1, gov_id: 'x', year: 2026, year_label: '令和8年度', basis: 'initial', unit_source: '千円',
  accounts: [
    { id: 'general', kind: 'general', name: '一般会計' },
    { id: 'special:debt', kind: 'special', name: '公債管理特別会計' },
    { id: 'enterprise:water', kind: 'enterprise', name: '流域下水道事業会計' },
  ],
  rows, checks: { rows: rows.length, all_ok: rows.length, rules: {} }, ...over,
}) as LocalBudgetFile;

test('netTotal: 全会計の総計から会計間の繰入れ（受け手の印）を除く。公営企業会計は入れない。印がなければ null', () => {
  const rows = [
    row('general/expense/12-1-1', 1_000),
    row('special:debt/expense/1-1-1', 600),
    row('special:debt/revenue/2-1-1', 600, { transfer: { from_account: 'general' } }),
    row('enterprise:water/expense/1-1-1', 99_999),
  ];
  assert.deepEqual(netTotal(file(rows)), { gross: 1_600, transfers: 600, count: 1, net: 1_000 });
  assert.equal(netTotal(file(rows.filter(r => !r.transfer))), null);
});

test('personnelShare: 選んだ範囲の人件費の節（報酬・給料・職員手当等・共済費）の割合。財源・部局・節のない目では出さない', () => {
  const rows = [
    row('general/expense/9-1-1', 1_000, { setsu: setsu([['給料', 500], ['職員手当等', 200], ['需用費', 300]]) }),
    row('general/expense/9-1-2', 1_000, { setsu: setsu([['共済費', 100], ['委託料', 900]]) }),
    row('general/expense/10-1-1', 500),
  ];
  const f = file(rows);
  assert.deepEqual(personnelShare(f, { account: 'general', side: 'expense', kan: 9 }), { total: 2_000, personnel: 800, ratio: 0.4 });
  assert.deepEqual(personnelShare(f, { account: 'general', side: 'expense', kan: 9, kou: 1, moku: 1 }), { total: 1_000, personnel: 700, ratio: 0.7 });
  assert.equal(personnelShare(f, { account: 'general', side: 'expense', kan: 10 }), null); // 節のない目
  // 予備費の目は節を持たないので人件費 0 として数える（会計を選んでも割合が出る）
  const withReserve = file([...rows.slice(0, 2), row('general/expense/14-1-1', 1_000, { moku: { no: 1, name: '予備費' } })]);
  assert.deepEqual(personnelShare(withReserve, { account: 'general', side: 'expense' }), { total: 3_000, personnel: 800, ratio: 800 / 3_000 });
  assert.equal(personnelShare(f, { funding: 'general' }), null);
  assert.equal(personnelShare(f, { department: '総務部' }), null);
});

// 公開データ: R8 当初の純計は下調べの値（総計 3,317,938,658 千円 − 繰入れ 295,508,530 千円）
const budgetPath = path.join(__dirname, '..', 'public/data/local-gov/fukuoka-pref/budget-2026-initial.json');
test('公開データの純計と人件費（R8 当初）', { skip: !fs.existsSync(budgetPath) }, () => {
  const data = JSON.parse(fs.readFileSync(budgetPath, 'utf-8')) as LocalBudgetFile;
  const n = netTotal(data);
  assert.deepEqual(n && { count: n.count, transfers: n.transfers, net: n.net }, { count: 15, transfers: 295_508_530_000, net: 3_022_430_128_000 });
  const police = personnelShare(data, { account: 'general', side: 'expense', kan: 9 });
  assert.ok(police && police.ratio > 0.83 && police.ratio < 0.85);
});
