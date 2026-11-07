import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { buildLocalGraph } from '../app/lib/local-gov/graph';
import { aggregateTail, composeDisplay, edgeKey, selectionToFilter } from '../app/lib/local-gov/graph-view';
import { nameSourceCounts, noAmountPrintedCount, sourcesUsed, valueCorrections, valueSourceCounts } from '../app/lib/local-gov/summary';
import type { LocalBudgetFile, LocalGraph, MokuRow, Value } from '../types/local-gov';

const v = (n: number): Value => ({ v: n, src: 'ocr' });

function row(id: string, over: Partial<MokuRow>): MokuRow {
  const [account, side, nums] = id.split('/');
  const [kan, kou, moku] = nums.split('-').map(Number);
  return {
    id, account, side: side as MokuRow['side'],
    kan: { no: kan, name: `款${kan}` }, kou: { no: kou, name: `項${kan}-${kou}` }, moku: { no: moku, name: `目${nums}` },
    amount: v(0), pages: [{ source: 's', page: 1 }], ...over,
  };
}

const fund = (national: number, bond: number, other: number, general: number) =>
  ({ national: v(national), bond: v(bond), other: v(other), general: v(general) });

// 2款の歳出: 款2 は目が2つ（財源の内訳が違う）、款3 は事項のない目
const FILE: LocalBudgetFile = {
  schema_version: 1, gov_id: 'test', year: 2026, year_label: '令和8年度', basis: 'initial', unit_source: '千円',
  accounts: [{ id: 'general', kind: 'general', name: '一般会計' }, { id: 'special:a', kind: 'special', name: 'A特別会計' }],
  rows: [
    row('general/expense/2-1-1', { amount: v(100), funding: fund(10, 0, 20, 70),
      items: [{ name: '職員費', amount: v(60) }, { name: '事務費', amount: v(40) }, { name: '内訳', amount: v(5), parent: 1 }] }),
    row('general/expense/2-1-2', { amount: v(50), funding: fund(0, 30, 0, 20),
      items: [{ name: '施設整備費', amount: v(50), name_src: 'ocr' }] }),
    row('general/expense/3-1-1', { amount: v(30), funding: fund(0, 0, 0, 30) }),
    row('general/revenue/1-1-1', { amount: v(150) }),
    row('general/revenue/2-1-1', { amount: v(30) }),
    row('special:a/revenue/1-1-1', { amount: v(40), kan: { no: 1, name: '繰入金' } }),
    row('special:a/expense/1-1-1', { amount: v(40) }),
  ],
  checks: { rows: 7, all_ok: 7, rules: {} },
};

function colTotal(g: LocalGraph, col: string) {
  return g.nodes.filter(n => n.col === col).reduce((s, n) => s + n.value, 0);
}

function edgesInto(g: LocalGraph, target: string) {
  return Object.fromEntries(g.edges.filter(e => e.target === target).map(e => [e.source, e.value]));
}

test('一般会計: 財源 → 款 → 項 → 目 の各列の合計は歳出の合計と同じ', () => {
  const g = buildLocalGraph(FILE, { view: 'general' });
  for (const col of ['funding', 'kan', 'kou', 'moku']) assert.equal(colTotal(g, col), 180, col);
  assert.equal(g.totals.gross, 180);
  assert.deepEqual(g.columns.map(c => c.key), ['funding', 'kan', 'kou', 'moku', 'item']);
});

test('一般会計: 財源 → 款 の帯は、その款の目の財源内訳の合計（按分しない）', () => {
  const g = buildLocalGraph(FILE, { view: 'general' });
  assert.deepEqual(edgesInto(g, 'kan:general:expense:2'),
    { 'funding:national': 10, 'funding:bond': 30, 'funding:other': 20, 'funding:general': 90 });
  assert.deepEqual(edgesInto(g, 'kan:general:expense:3'), { 'funding:general': 30 });
});

test('一般会計: 目を選ぶと、その目の財源内訳だけから組み立て直す', () => {
  const g = buildLocalGraph(FILE, { view: 'general', filter: { kan: 2, kou: 1, moku: 2 } });
  assert.deepEqual(edgesInto(g, 'kan:general:expense:2'), { 'funding:bond': 30, 'funding:general': 20 });
  assert.equal(g.nodes.find(n => n.id === 'kan:general:expense:2')?.value, 50);
  assert.equal(g.totals.gross, 50);
});

test('一般会計: 事項は親の事項だけ。事項のない目は目で止まる。名前が OCR のままの事項に印', () => {
  const g = buildLocalGraph(FILE, { view: 'general' });
  const items = g.nodes.filter(n => n.col === 'item');
  assert.deepEqual(items.map(n => [n.name, n.value]), [['職員費', 60], ['事務費', 40], ['施設整備費', 50]]);
  assert.deepEqual(items.find(n => n.name === '施設整備費')?.flags, ['name-ocr']);
  assert.equal(g.edges.some(e => e.source === 'moku:general/expense/3-1-1'), false);
});

test('深さ: 指定した列までしか作らない', () => {
  const g = buildLocalGraph(FILE, { view: 'general', depth: 3 });
  assert.deepEqual([...new Set(g.nodes.map(n => n.col))], ['funding', 'kan', 'kou']);
  assert.ok(g.edges.every(e => !e.target.startsWith('moku:')));
});

test('全会計: 歳入の款 → 会計 → 款 → 項 → 目。歳入の款は名前でまとめ、会計で歳入と歳出が合流する', () => {
  const g = buildLocalGraph(FILE, { view: 'all' });
  assert.deepEqual(edgesInto(g, 'account:general'), { 'revenue:款1': 150, 'revenue:款2': 30 });
  assert.deepEqual(edgesInto(g, 'account:special:a'), { 'revenue:繰入金': 40 });
  assert.equal(colTotal(g, 'kan'), 220);
  assert.equal(g.totals.gross, 220);
  // 同じ番号の款でも会計が違えば別の箱
  assert.ok(g.nodes.some(n => n.id === 'kan:special:a:expense:1'));
});

test('全会計: 歳出の款を選ぶときは side で歳入の同じ番号の款を混ぜない', () => {
  const g = buildLocalGraph(FILE, { view: 'all', filter: { account: 'general', side: 'expense', kan: 2 } });
  assert.equal(g.nodes.some(n => n.col === 'revenue'), false);
  assert.equal(colTotal(g, 'kan'), 150);
});

test('表示: 選んでいなければ左の3列だけ、重ねる帯なし', () => {
  const d = composeDisplay(FILE, 'general', null);
  assert.deepEqual([...new Set(d.graph.nodes.map(n => n.col))], ['funding', 'kan', 'kou']);
  assert.equal(d.highlight.size, 0);
  assert.equal(d.selected, null);
});

test('表示: 目を選ぶと事項まで開き、財源 → 款 の帯はその目の財源の分だけ重ねる', () => {
  const d = composeDisplay(FILE, 'general', 'moku:general/expense/2-1-2');
  assert.equal(d.selected?.name, '目2-1-2');
  assert.equal(d.row, 'general/expense/2-1-2');
  // 左の列は全体のまま（灰色の下地）
  assert.equal(d.graph.edges.find(e => e.source === 'funding:general' && e.target === 'kan:general:expense:2')?.value, 90);
  // 重ねる帯は選んだ目の財源内訳そのもの
  assert.equal(d.highlight.get(edgeKey('funding:general', 'kan:general:expense:2')), 20);
  assert.equal(d.highlight.get(edgeKey('funding:bond', 'kan:general:expense:2')), 30);
  assert.equal(d.highlight.has(edgeKey('funding:national', 'kan:general:expense:2')), false);
  // 深い列は選んだ目の分だけ
  assert.deepEqual(d.graph.nodes.filter(n => n.col === 'moku').map(n => n.id), ['moku:general/expense/2-1-2']);
  assert.deepEqual(d.graph.nodes.filter(n => n.col === 'item').map(n => n.name), ['施設整備費']);
});

test('表示: 款を選ぶと目まで開く（一般会計）。財源の箱は、その箱から出る帯だけを重ねる', () => {
  const d = composeDisplay(FILE, 'general', 'kan:general:expense:2');
  assert.deepEqual([...new Set(d.graph.nodes.map(n => n.col))], ['funding', 'kan', 'kou', 'moku']);
  const f = composeDisplay(FILE, 'general', 'funding:bond');
  assert.deepEqual([...f.highlight.values()], [30]);
  assert.ok(f.highlightNodes.has('kan:general:expense:2'));
});

test('表示: 会計の ID に「:」が入っていても絞り込みを読める', () => {
  assert.deepEqual(selectionToFilter('all', 'kan:special:a:expense:1')?.filter,
    { account: 'special:a', side: 'expense', kan: 1 });
  assert.deepEqual(selectionToFilter('all', 'moku:special:a/expense/1-1-1')?.filter,
    { account: 'special:a', side: 'expense', kan: 1, kou: 1, moku: 1 });
  assert.equal(selectionToFilter('general', 'funding:bond'), null);
});

test('表示: 右端の深い列の箱が多ければ上位だけ残し、残りを「その他」にまとめる（帯と重ねも足し合わせる）', () => {
  const g: LocalGraph = {
    schema_version: 1, gov_id: 't', year: 2026, basis: 'initial', totals: { gross: 100 },
    columns: [{ key: 'kou', label: '項' }, { key: 'moku', label: '目' }],
    nodes: [
      { id: 'k', col: 'kou', name: '項', value: 100 },
      ...[40, 30, 20, 6, 4].map((v, i) => ({ id: `m${i}`, col: 'moku', name: `目${i}`, value: v })),
    ],
    edges: [40, 30, 20, 6, 4].map((v, i) => ({ source: 'k', target: `m${i}`, value: v })),
  };
  const hl = new Map([[edgeKey('k', 'm3'), 6], [edgeKey('k', 'm0'), 40]]);
  const out = aggregateTail(g, hl, new Set(['m3', 'm0']), 2, new Set(['m4']));
  // 上位2件（m0・m1）と残す指定の m4 は残り、m2・m3 が「その他 2件」になる
  assert.deepEqual(out.graph.nodes.filter(n => n.col === 'moku').map(n => [n.id, n.value]),
    [['m0', 40], ['m1', 30], ['m4', 4], ['other:moku', 26]]);
  assert.equal(out.graph.edges.find(e => e.target === 'other:moku')?.value, 26);
  assert.equal(out.highlight.get(edgeKey('k', 'other:moku')), 6);
  assert.ok(out.highlightNodes.has('other:moku') && !out.highlightNodes.has('m3'));
  // 項の列（最初の画面の右端）はまとめない
  const kouOnly = { ...g, columns: [{ key: 'kou', label: '項' }], nodes: g.nodes.map(n => ({ ...n, col: 'kou' })), edges: [] };
  assert.equal(aggregateTail(kouOnly, new Map(), new Set(), 2, new Set()).graph.nodes.length, 6);
});

test('要約: 画像で直した値・出典ごとの件数を集める', () => {
  const f: LocalBudgetFile = {
    ...FILE,
    rows: [row('general/expense/2-1-1', {
      amount: v(100), previous: { v: 90, src: 'correction', note: '画像で確認' },
      kan: { no: 2, name: '総務費', name_src: 'text' }, moku: { no: 1, name: '一般管理費', name_src: 'ocr' },
      items: [{ name: '事務費', amount: v(100), no_amount_printed: true, name_src: 'readings' }],
    })],
  };
  assert.deepEqual(valueCorrections(f).map(c => [c.field, c.value, c.note]), [['前年度', 90, '画像で確認']]);
  assert.deepEqual(valueSourceCounts(f), { ocr: 2, correction: 1 });
  const n = nameSourceCounts(f);
  assert.deepEqual([n.kan, n.moku, n.item], [{ text: 1 }, { ocr: 1 }, { readings: 1 }]);
  assert.equal(noAmountPrintedCount(f), 1);
});

test('要約: 出典に出す資料は、目の行が参照している資料（重複なし・出てきた順）', () => {
  const f: LocalBudgetFile = {
    ...FILE,
    rows: [
      row('general/expense/1-1-1', { pages: [{ source: 'r8-ippan', page: 10 }, { source: 'r8-ippan', page: 11 }] }),
      row('special-a/expense/1-1-1', { pages: [{ source: 'r8-toku', page: 3 }] }),
    ],
  };
  assert.deepEqual(sourcesUsed(f), ['r8-ippan', 'r8-toku']);
});

// 実データ（福岡県 R8 当初予算）で組み立てて、列の合計と帯の保存を確かめる
const DATA = path.join(process.cwd(), 'public', 'data', 'local-gov', 'fukuoka-pref', 'budget-2026-initial.json');

test('実データ（福岡県 R8）: 一般会計の列の合計がすべて歳出の総額、どのノードも入り = 出', { skip: !fs.existsSync(DATA) }, () => {
  const file = JSON.parse(fs.readFileSync(DATA, 'utf8')) as LocalBudgetFile;
  const g = buildLocalGraph(file, { view: 'general' });
  const total = 2_300_027_028_000;
  for (const col of ['funding', 'kan', 'kou', 'moku']) assert.equal(colTotal(g, col), total, col);
  const into = new Map<string, number>();
  const out = new Map<string, number>();
  for (const e of g.edges) {
    into.set(e.target, (into.get(e.target) ?? 0) + e.value);
    out.set(e.source, (out.get(e.source) ?? 0) + e.value);
  }
  // 事項のある目は、事項の合計 = 目の額（説明欄の検算 A）。事項のない目は目で止まる
  for (const n of g.nodes) {
    if (into.has(n.id) && out.has(n.id)) assert.equal(out.get(n.id), into.get(n.id), n.id);
  }
  // サンキー図は負の太さの帯を描けない。どちらの見方でも帯の値はすべて正（負の値が来たら graph.ts の扱いを決める）
  for (const view of ['general', 'all'] as const) {
    const neg = buildLocalGraph(file, { view }).edges.filter(e => e.value < 0);
    assert.deepEqual(neg, [], `${view} に負の帯`);
  }
});
