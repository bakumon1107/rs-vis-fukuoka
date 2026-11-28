/**
 * かんたんの図の3列（歳入の款 → 財源 → 歳出の款。app/lib/local-gov/simple-flow.ts）のテスト。R8 の実データで確かめる。
 * 設計: docs/local-gov/tasks/20261128_1408_かんたんの図に歳入から財源への振り分けを足す設計.md
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { edgeKey } from '../app/lib/local-gov/graph';
import { fullGraph, simpleDisplay } from '../app/lib/local-gov/graph-view';
import { OTHER_REVENUE_ID, simpleFundingFlow } from '../app/lib/local-gov/simple-flow';
import { composeLatest } from '../app/lib/local-gov/supplement';
import { validateBudgetFile } from '../app/lib/local-gov/validate';
import type { LocalBudgetFile } from '../types/local-gov';

const DIR = path.join(process.cwd(), 'public', 'data', 'local-gov', 'fukuoka-pref');
const has = fs.existsSync(path.join(DIR, 'budget-2026-initial.json'));
const read = (name: string) => JSON.parse(fs.readFileSync(path.join(DIR, name), 'utf-8')) as LocalBudgetFile;

test('実データ R8: 3列の箱の額 = 入る帯の合計 = 出る帯の合計。財源の箱は2列の図と同じ額', { skip: !has }, () => {
  const file = read('budget-2026-initial.json');
  const base = fullGraph(file, 'general', 2);
  const flow = simpleFundingFlow(file, base)!;
  assert.ok(flow);
  const g = flow.graph;
  assert.deepEqual(g.columns.map(c => c.key), ['revenue', 'funding', 'kan']);
  const into = new Map<string, number>();
  const out = new Map<string, number>();
  for (const e of g.edges) {
    assert.ok(e.value > 0, `${e.source} → ${e.target}`);
    into.set(e.target, (into.get(e.target) ?? 0) + e.value);
    out.set(e.source, (out.get(e.source) ?? 0) + e.value);
  }
  for (const n of g.nodes) {
    if (n.col !== 'revenue') assert.equal(into.get(n.id), n.value, `${n.id} に入る帯`);
    if (n.col !== 'kan') assert.equal(out.get(n.id), n.value, `${n.id} から出る帯`);
  }
  // 財源の箱・歳出の款の箱は今の2列の図と同じ
  for (const n of base.nodes) assert.equal(g.nodes.find(x => x.id === n.id)?.value, n.value, n.id);
  // 歳入の款の箱 = 一般会計の歳入の款の額
  for (const n of g.nodes.filter(x => x.col === 'revenue')) {
    const want = file.rows
      .filter(r => r.account === 'general' && r.side === 'revenue' && `revenue:${r.kan.name}` === n.id)
      .reduce((s, r) => s + (r.amount.v ?? 0), 0);
    assert.equal(n.value, want, n.id);
  }
  assert.equal(g.nodes.filter(x => x.col === 'revenue').length, 15);
  // 国庫支出金の款 → 国庫支出金、県債 → 地方債。臨時交付金・調整債は一般財源へ
  assert.equal(flow.funding.get(edgeKey('revenue:国庫支出金', 'funding:national')), 'national');
  assert.equal(flow.funding.get(edgeKey('revenue:県債', 'funding:bond')), 'bond');
  assert.equal(g.edges.find(e => e.source === 'revenue:県債' && e.target === 'funding:general')?.value, 13_335_700_000);
  // 概算の帯は差し引きを分けた3本（諸収入・財産収入・使用料及び手数料 → 一般財源）
  assert.deepEqual(
    [...flow.estimated].sort(),
    ['revenue:使用料及び手数料', 'revenue:諸収入', 'revenue:財産収入'].map(s => edgeKey(s, 'funding:general')).sort()
  );
  // 財源 → 歳出の款の帯はその財源の色
  const right = g.edges.find(e => e.source === 'funding:bond')!;
  assert.equal(flow.funding.get(edgeKey(right.source, right.target)), 'bond');
});

test('実データ R8: スマートフォンの幅では小さい歳入の款を「その他の収入」にまとめる（額は変わらない）', { skip: !has }, () => {
  const file = read('budget-2026-initial.json');
  const base = fullGraph(file, 'general', 2);
  const all = simpleFundingFlow(file, base)!;
  const grouped = simpleFundingFlow(file, base, 0.01)!;
  const rev = (f: typeof all) => f.graph.nodes.filter(n => n.col === 'revenue');
  const total = (f: typeof all) => rev(f).reduce((s, n) => s + n.value, 0);
  assert.equal(total(grouped), total(all));
  const other = grouped.graph.nodes.find(n => n.id === OTHER_REVENUE_ID)!;
  assert.ok(other.flags?.includes('aggregate'));
  assert.equal(rev(grouped).at(-1)!.id, OTHER_REVENUE_ID, '「その他の収入」は最後');
  assert.ok(rev(grouped).length < rev(all).length);
  // まとめた中に概算の帯があれば、まとめた帯も概算（確かな額に見せない）
  const smallEstimated = ['revenue:財産収入', 'revenue:使用料及び手数料'].some(
    id => (all.graph.nodes.find(n => n.id === id)?.value ?? 0) < total(all) * 0.01
  );
  assert.equal(grouped.estimated.has(edgeKey(OTHER_REVENUE_ID, 'funding:general')), smallEstimated);
});

test('実データ R8: 検証は帯の合計の食い違い（款ごと・財源ごと）・額・財源の値を見つける', { skip: !has }, () => {
  const file = read('budget-2026-initial.json');
  assert.deepEqual(validateBudgetFile(file).errors, []);
  const withFlows = (f: (flows: NonNullable<LocalBudgetFile['general_fund']>['flows']) => typeof flows) => ({
    ...file,
    general_fund: { ...file.general_fund!, flows: f(file.general_fund!.flows) },
  });
  // 一般財源へ行く帯の 1 円を国庫支出金へ付け替える（款の合計は同じ・財源の合計が合わない）
  const moved = withFlows(fl => fl!.map((x, i) => (i === 0 ? { ...x, amount: x.amount - 1 } : x)).concat([{ ...fl![0], funding: 'national', amount: 1 }]));
  const e1 = validateBudgetFile(moved).errors;
  assert.ok(e1.some(e => e.includes('general の帯の合計')) && e1.some(e => e.includes('national の帯の合計')));
  // 帯を1本外す（款の合計が合わない）・額が 0・知らない財源
  const dropped = withFlows(fl => fl!.slice(1));
  assert.ok(validateBudgetFile(dropped).errors.some(e => e.includes('1款の帯の合計')));
  const zero = withFlows(fl => fl!.map((x, i) => (i === 0 ? { ...x, amount: 0 } : x)));
  assert.ok(validateBudgetFile(zero).errors.some(e => e.includes('正の整数でない')));
  const bad = withFlows(fl => fl!.map((x, i) => (i === 0 ? { ...x, funding: 'loan' as 'general' } : x)));
  assert.ok(validateBudgetFile(bad).errors.some(e => e.includes('funding が不正')));
  // 款の名前が行と違う（箱の ID が全会計の見方の箱に当たらない）
  const renamed = withFlows(fl => fl!.map((x, i) => (i === 0 ? { ...x, kan_name: '旧い名前' } : x)));
  assert.ok(validateBudgetFile(renamed).errors.some(e => e.includes('款の名前「旧い名前」')));
  // 差し引きの split の合計が行の額と違う・負
  const gf = file.general_fund!;
  const withSplit = (split: { kan: number; amount: number }[]) => ({
    ...file,
    general_fund: { ...gf, rows: gf.rows.map(r => (r.basis === 'residual' ? { ...r, split } : r)) },
  });
  const res = gf.rows.find(r => r.basis === 'residual')!;
  assert.ok(validateBudgetFile(withSplit([{ kan: 14, amount: res.amount - 1 }])).errors.some(e => e.includes('split の合計')));
  assert.ok(
    validateBudgetFile(withSplit([{ kan: 14, amount: res.amount + 5 }, { kan: 10, amount: -5 }])).errors.some(e => e.includes('split に負'))
  );
});

test('実データ R8: 名前が読み取りだけの歳入の款には印（※）を付ける。まとめた款の名前を返す', { skip: !has }, () => {
  const file = read('budget-2026-initial.json');
  const ocr: LocalBudgetFile = {
    ...file,
    rows: file.rows.map(r =>
      r.account === 'general' && r.side === 'revenue' && r.kan.name === '県税' ? { ...r, kan: { ...r.kan, name_src: 'ocr' as const } } : r
    ),
  };
  const flow = simpleFundingFlow(ocr, fullGraph(ocr, 'general', 2))!;
  assert.ok(flow.graph.nodes.find(n => n.id === 'revenue:県税')?.flags?.includes('name-ocr'));
  assert.ok(!flow.graph.nodes.find(n => n.id === 'revenue:地方交付税')?.flags?.includes('name-ocr'));
  assert.deepEqual(simpleFundingFlow(file, fullGraph(file, 'general', 2))!.groupedNames, []);
  const grouped = simpleFundingFlow(file, fullGraph(file, 'general', 2), 0.01)!;
  assert.ok(grouped.groupedNames.length >= 2 && grouped.groupedNames.includes('交通安全対策特別交付金'));
});

test('実データ R8: 3列は一般会計の当初予算だけ（補正後・決算・全会計は今の2列）', { skip: !has }, () => {
  const initial = read('budget-2026-initial.json');
  assert.ok(simpleDisplay(initial, 'general').fundingColors);
  assert.equal(simpleDisplay(initial, 'general').graph.columns.length, 3);
  assert.equal(simpleDisplay(initial, 'all').fundingColors, undefined);
  const composed = composeLatest(initial, [1, 2, 3, 4].map(n => read(`budget-2026-supplementary-${n}.json`)));
  assert.equal(simpleDisplay(composed, 'general').fundingColors, undefined);
  assert.equal(simpleDisplay(composed, 'general').graph.columns.length, 2);
  const settlement = read('settlement-2024.json');
  assert.equal(simpleDisplay(settlement, 'general').fundingColors, undefined);
  // flows のないデータは null
  assert.equal(simpleFundingFlow({ ...initial, general_fund: { ...initial.general_fund!, flows: undefined } }, fullGraph(initial, 'general', 2)), null);
});
