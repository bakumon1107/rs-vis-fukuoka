/**
 * 選んだ箱の内訳の表と前年度の額（app/lib/local-gov/breakdown.ts）のテスト。R8 の実データで確かめる。
 * 設計: docs/local-gov/tasks/20261128_1130_選んだ箱の内訳の表と前年度比の設計.md
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { buildLocalGraph } from '../app/lib/local-gov/graph';
import { boxBreakdown, breakdownDeltas, previousBoxValues, previousRatio, previousRevenueGap } from '../app/lib/local-gov/breakdown';
import { composeLatest } from '../app/lib/local-gov/supplement';
import { initialBoxIds, initialBoxValues } from '../app/lib/local-gov/supplement-diff';
import type { LocalBudgetFile } from '../types/local-gov';

const DIR = path.join(process.cwd(), 'public', 'data', 'local-gov', 'fukuoka-pref');
const has = fs.existsSync(path.join(DIR, 'budget-2026-supplementary-4.json'));
const read = (name: string) => JSON.parse(fs.readFileSync(path.join(DIR, name), 'utf-8')) as LocalBudgetFile;

test('前年度比の割合: 増は +、減は △、前年度 0 は null', () => {
  assert.equal(previousRatio(105, 100), '+5.0%');
  assert.equal(previousRatio(97, 100), '△3.0%');
  assert.equal(previousRatio(100, 100), '±0.0%');
  assert.equal(previousRatio(100_000_001, 100_000_000), '±0.0%');
  assert.equal(previousRatio(50, 0), null);
});

test('実データ R8: 内訳の行の合計 = 選んだ箱の額。行は図の帯の額で、額の大きい順', { skip: !has }, () => {
  const initial = read('budget-2026-initial.json');
  const composed = composeLatest(initial, [1, 2, 3, 4].map(n => read(`budget-2026-supplementary-${n}.json`)));
  const settlement = read('settlement-2024.json');
  for (const file of [initial, composed, settlement]) {
    for (const view of ['general', 'all'] as const) {
      const g = buildLocalGraph(file, { view });
      const valueOf = new Map(g.nodes.map(n => [n.id, n.value]));
      // 目より左の列の箱（財源・部局・歳入の款・会計・款・項）すべて
      const lastCols = new Set(['moku', 'item', 'setsu']);
      let checked = 0;
      for (const n of g.nodes) {
        if (lastCols.has(n.col)) continue;
        const b = boxBreakdown(file, view, n.id, n.col);
        assert.ok(b, `${view} ${n.id} の内訳がない`);
        assert.equal(b.parent.value, n.value, `${view} ${n.id}`);
        const sum = b.items.reduce((s, it) => s + it.value, 0);
        assert.equal(sum, n.value, `${view} ${n.id} の内訳の合計`);
        for (let i = 1; i < b.items.length; i++) assert.ok(b.items[i - 1].value >= b.items[i].value, `${view} ${n.id} の並び`);
        // 行の箱の全部が入る（whole）なら、帯の額 = 行の箱の額
        for (const it of b.items) assert.equal(it.whole, it.value === valueOf.get(it.id), `${view} ${it.id}`);
        checked++;
      }
      assert.ok(checked > 10, `${view} の確かめた箱が少ない`);
    }
  }
  // 款 → 項・項 → 目は全部の行が whole。財源 → 款は一部だけの行がある
  const kan = boxBreakdown(initial, 'general', 'kan:general:expense:2', 'kan')!;
  assert.equal(kan.childLabel, '項');
  assert.ok(kan.items.every(it => it.whole));
  const national = boxBreakdown(initial, 'general', 'funding:national', 'funding')!;
  assert.equal(national.childLabel, '款');
  assert.ok(national.items.some(it => !it.whole));
  // 目（一番右の手前の列でない）・存在しない箱は null
  assert.equal(boxBreakdown(initial, 'general', 'kan:general:expense:999', 'kan'), null);
  assert.equal(boxBreakdown(initial, 'general', 'x', 'item'), null);
});

test('実データ R8: 箱の前年度の額 = その箱に入る目の前年度の合計。会計は歳出だけ。財源は入らない', { skip: !has }, () => {
  const initial = read('budget-2026-initial.json');
  const prev = previousBoxValues(initial);
  const sumOf = (pred: (r: LocalBudgetFile['rows'][number]) => boolean) =>
    initial.rows.filter(pred).reduce((s, r) => s + (r.previous?.v ?? 0), 0);
  assert.equal(prev.get('account:general'), sumOf(r => r.account === 'general' && r.side === 'expense'));
  assert.equal(prev.get('kan:general:expense:2'), sumOf(r => r.account === 'general' && r.side === 'expense' && r.kan.no === 2));
  assert.equal(
    prev.get('kou:general:expense:2-1'),
    sumOf(r => r.account === 'general' && r.side === 'expense' && r.kan.no === 2 && r.kou.no === 1)
  );
  assert.equal(prev.get('revenue:県税'), sumOf(r => r.side === 'revenue' && r.kan.name === '県税'));
  // 一般会計の歳出の款の前年度の合計 = 一般会計の歳出の前年度
  const kanSum = [...prev].filter(([id]) => id.startsWith('kan:general:expense:')).reduce((s, [, v]) => s + v, 0);
  assert.equal(kanSum, prev.get('account:general'));
  assert.ok(![...prev.keys()].some(id => id.startsWith('funding:')));
  // 実装と別の性質で: 予算は歳入 = 歳出なので、前年度（前の年度の当初予算）も会計ごとに歳入の合計 = 歳出の合計
  // （目の前年度の読み取り・前年度にだけあった目の取りこぼしがあれば合わない）
  // 既知の抜け: 前年度にだけあった款は、本年度 0 円で明細のページがなく、行にならない（総括表にだけ載る）。
  // 県営埠頭施設: 款「財産収入」前年度 2,530千円（特別会計の説明書 p.93 の総括表。本年度 0・比較 △2,530）
  const missingRevenue: Record<string, number> = { 'special:kenei-futo-shisetsu': 2_530_000 };
  for (const acc of initial.accounts.filter(a => a.kind !== 'enterprise')) {
    const rev = sumOf(r => r.account === acc.id && r.side === 'revenue');
    const exp = sumOf(r => r.account === acc.id && r.side === 'expense');
    assert.ok(exp > 0, `${acc.id} の前年度がない`);
    assert.equal(rev + (missingRevenue[acc.id] ?? 0), exp, `${acc.id} の前年度の歳入と歳出`);
  }
  // 足りない額は previousRevenueGap で分かる（画面の断り書き）
  assert.equal(previousRevenueGap(initial), 2_530_000);
  // 前年度の額のないデータ（決算）は空
  assert.equal(previousBoxValues(read('settlement-2024.json')).size, 0);
  // 前年度の読めない目（null）を含む箱は外す（足りない額で前年度比を出さない）。ほかの箱は残る
  const kou21 = initial.rows.find(r => r.account === 'general' && r.side === 'expense' && r.kan.no === 2 && r.kou.no === 1)!;
  const broken: LocalBudgetFile = { ...initial, rows: initial.rows.map(r => (r === kou21 ? { ...r, previous: { ...r.previous!, v: null } } : r)) };
  const pb = previousBoxValues(broken);
  for (const id of ['kan:general:expense:2', 'kou:general:expense:2-1', 'account:general', `moku:${kou21.id}`]) assert.equal(pb.has(id), false, id);
  assert.equal(pb.get('kan:general:expense:3'), prev.get('kan:general:expense:3'));
});

test('実データ R8: 内訳の行の補正の増減は、箱の全部が入る行だけ', { skip: !has }, () => {
  const initial = read('budget-2026-initial.json');
  const composed = composeLatest(initial, [1, 2, 3, 4].map(n => read(`budget-2026-supplementary-${n}.json`)));
  const before = initialBoxValues(initial, 'general');
  const ids = initialBoxIds(initial);
  const g = buildLocalGraph(composed, { view: 'general' });
  const kanNode = g.nodes.find(n => n.col === 'kan')!;
  const kan = boxBreakdown(composed, 'general', kanNode.id, 'kan')!;
  const d = breakdownDeltas(kan, before, ids);
  for (const it of kan.items) assert.equal(d.get(it.id)?.delta, it.value - (before.get(it.id) ?? 0), it.id);
  const national = boxBreakdown(composed, 'general', 'funding:national', 'funding')!;
  const dn = breakdownDeltas(national, before, ids);
  for (const it of national.items) assert.equal(dn.has(it.id), it.whole, it.id);
});
