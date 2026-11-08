import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { buildLocalGraph } from '../app/lib/local-gov/graph';
import {
  aggregateTail, composeDisplay, edgeKey, NOTE_EXPENSE_UNKNOWN, NOTE_ITEM_FUNDING, NOTE_REVENUE_UNKNOWN, selectionToFilter, windowColumns,
} from '../app/lib/local-gov/graph-view';
import {
  nameSourceCounts, noAmountPrintedCount, sourcesUsed, valueNotes, valueSourceCounts, zeroAmountRows,
} from '../app/lib/local-gov/summary';
import { pickDataset } from '../client/hooks/useLocalBudget';
import type { LocalBudgetFile, LocalGovIndex, LocalGraph, MokuRow, Value } from '../types/local-gov';

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

test('表示: 選ぶ箱ごとの開く深さ（設計書 4.3）', () => {
  const cols = (view: 'general' | 'all', id: string) => [...new Set(composeDisplay(FILE, view, id).graph.nodes.map(n => n.col))];
  // 一般会計: 財源・款は目まで、項・目・事項は事項まで
  assert.deepEqual(cols('general', 'funding:general'), ['funding', 'kan', 'kou', 'moku']);
  assert.deepEqual(cols('general', 'kou:general:expense:2-1'), ['funding', 'kan', 'kou', 'moku', 'item']);
  assert.deepEqual(cols('general', 'moku:general/expense/2-1-1'), ['funding', 'kan', 'kou', 'moku', 'item']);
  assert.deepEqual(cols('general', 'item:general/expense/2-1-1:0'), ['funding', 'kan', 'kou', 'moku', 'item']);
  // 全会計: 会計は項まで、款・項・目は目まで
  assert.deepEqual(cols('all', 'account:general'), ['revenue', 'account', 'kan', 'kou']);
  assert.deepEqual(cols('all', 'kan:general:expense:2'), ['revenue', 'account', 'kan', 'kou', 'moku']);
  assert.deepEqual(cols('all', 'kou:general:expense:2-1'), ['revenue', 'account', 'kan', 'kou', 'moku']);
  assert.deepEqual(cols('all', 'moku:general/expense/2-1-1'), ['revenue', 'account', 'kan', 'kou', 'moku']);
});

test('表示: 図にない箱を指す選択（古い事項の番号・歳入の目・別の見方の ID）は選択なしに戻す', () => {
  for (const [view, id] of [
    ['general', 'item:general/expense/2-1-1:99'],
    ['general', 'kan:general:revenue:1'],
    ['general', 'moku:general/revenue/1-1-1'],
    ['all', 'item:general/expense/2-1-1:0'],
    ['all', 'funding:bond'],
  ] as const) {
    const d = composeDisplay(FILE, view, id);
    assert.equal(d.selected, null, id);
    assert.equal(d.highlight.size, 0, id);
    assert.deepEqual([...new Set(d.graph.nodes.map(n => n.col))].length, 3, id);
  }
});

test('一般会計: 財源内訳のない目は「財源の記載なし」の箱から流す（目を落とさず、財源の列の合計は歳出の総額のまま）', () => {
  const f: LocalBudgetFile = {
    ...FILE,
    rows: [...FILE.rows, row('general/expense/3-1-2', { amount: v(7) })],
  };
  const g = buildLocalGraph(f, { view: 'general' });
  assert.equal(colTotal(g, 'funding'), 187);
  assert.equal(colTotal(g, 'moku'), 187);
  assert.equal(edgesInto(g, 'kan:general:expense:3')['funding:none'], 7);
  // 財源を選んだときは、財源内訳のない目は出さない
  assert.ok(!buildLocalGraph(f, { view: 'general', filter: { funding: 'general' } }).nodes.some(n => n.id === 'moku:general/expense/3-1-2'));
  // 「財源の記載なし」を選んだときは、財源内訳のある行から箱を作らない（図に出ない行の印を混ぜない）
  const mixed: LocalBudgetFile = {
    ...f,
    rows: [...f.rows, row('general/expense/3-1-3', { amount: v(5), funding: fund(0, 0, 0, 5), kan: { no: 3, name: '款3' } })],
  };
  const nk = buildLocalGraph(mixed, { view: 'general', filter: { funding: 'none' } }).nodes.find(n => n.id === 'kan:general:expense:3');
  assert.equal(nk?.value, 7);
  // 「財源の記載なし」を選ぶと、財源内訳のない目の本年度で目まで追う
  const d = composeDisplay(f, 'general', 'funding:none');
  assert.equal(d.highlight.get(edgeKey('kou:general:expense:3-1', 'moku:general/expense/3-1-2')), 7);
  assert.deepEqual(d.graph.nodes.filter(n => n.col === 'moku').map(n => n.id), ['moku:general/expense/3-1-2']);
});

test('全会計: 公営企業会計はデータにあっても描かない（歳入と歳出が一致しない様式）', () => {
  const f: LocalBudgetFile = {
    ...FILE,
    accounts: [...FILE.accounts, { id: 'enterprise:hospital', kind: 'enterprise', name: '病院事業会計' }],
    rows: [
      ...FILE.rows,
      row('enterprise:hospital/revenue/1-1-1', { amount: v(100) }),
      row('enterprise:hospital/expense/1-1-1', { amount: v(120) }),
    ],
  };
  const g = buildLocalGraph(f, { view: 'all' });
  assert.ok(!g.nodes.some(n => n.id.includes('enterprise:hospital')));
  assert.equal(g.totals.gross, buildLocalGraph(FILE, { view: 'all' }).totals.gross);
});

test('全会計: 名前でまとめた歳入の款は、まとめた行のどれかが読み取りのみなら印を付ける', () => {
  const f: LocalBudgetFile = {
    ...FILE,
    rows: [
      row('general/revenue/5-1-1', { amount: v(3), kan: { no: 5, name: '繰入金', name_src: 'text' } }),
      row('special:a/revenue/1-1-1', { amount: v(40), kan: { no: 1, name: '繰入金', name_src: 'ocr' } }),
      row('special:a/expense/1-1-1', { amount: v(40) }),
      row('general/expense/2-1-1', { amount: v(3), funding: fund(0, 0, 0, 3) }),
    ],
  };
  const g = buildLocalGraph(f, { view: 'all' });
  assert.deepEqual(g.nodes.find(n => n.id === 'revenue:繰入金')?.flags, ['name-ocr']);
  // 図に出ない 0 円の行の印は混ぜない
  const z: LocalBudgetFile = {
    ...f,
    rows: [
      row('general/revenue/5-1-1', { amount: v(3), kan: { no: 5, name: '繰入金', name_src: 'text' } }),
      row('special:a/revenue/1-1-1', { amount: v(0), kan: { no: 1, name: '繰入金', name_src: 'ocr' } }),
      row('general/expense/2-1-1', { amount: v(3), funding: fund(0, 0, 0, 3), kan: { no: 2, name: '款2', name_src: 'text' } }),
    ],
  };
  assert.equal(buildLocalGraph(z, { view: 'all' }).nodes.find(n => n.id === 'revenue:繰入金')?.flags, undefined);
});

test('名前の出典がない名前は、読み取りのみ（ocr）と同じく印を付ける', () => {
  const f: LocalBudgetFile = {
    ...FILE,
    rows: [row('general/expense/4-1-1', { amount: v(10), funding: fund(0, 0, 0, 10),
      kan: { no: 4, name: '款4', name_src: 'text' }, kou: { no: 1, name: '項4-1' } })],
  };
  const g = buildLocalGraph(f, { view: 'general' });
  assert.equal(g.nodes.find(n => n.id === 'kan:general:expense:4')?.flags, undefined);
  assert.deepEqual(g.nodes.find(n => n.id === 'kou:general:expense:4-1')?.flags, ['name-ocr']);
});

test('データの一覧: 年度の指定がなければ、その基準で最も新しい年度（並び順に頼らない）', () => {
  const index = {
    schema_version: 1, gov: { id: 't', name: 'テスト県', kind: 'prefecture' }, sources: [],
    datasets: [
      { year: 2026, label: '令和8年度', basis: 'initial', file: 'b-2026.json', status: 'verified' },
      { year: 2025, label: '令和7年度', basis: 'initial', file: 'b-2025.json', status: 'verified' },
      { year: 2027, label: '令和9年度', basis: 'settlement', file: 's-2027.json', status: 'verified' },
    ],
  } as LocalGovIndex;
  assert.equal(pickDataset(index, 'initial')?.year, 2026);
  assert.equal(pickDataset(index, 'initial', 2025)?.file, 'b-2025.json');
  assert.equal(pickDataset(index, 'initial', 2024), undefined);
});

test('表示: 深い列の箱は全体の額で描き、選んだ分は重ねる帯で示す（全会計で目を選んでも項の箱は項全体の額）', () => {
  // 項 2-1 には目 2-1-1（100）と 2-1-2（50）がある
  const d = composeDisplay(FILE, 'all', 'moku:general/expense/2-1-1');
  assert.equal(d.graph.nodes.find(n => n.id === 'kou:general:expense:2-1')?.value, 150);
  assert.equal(d.graph.edges.find(e => e.target === 'kou:general:expense:2-1')?.value, 150);
  assert.equal(d.highlight.get(edgeKey('kan:general:expense:2', 'kou:general:expense:2-1')), 100);
  // 深い列の目は選んだ目だけ
  assert.deepEqual(d.graph.nodes.filter(n => n.col === 'moku').map(n => [n.id, n.value]), [['moku:general/expense/2-1-1', 100]]);
});

test('表示: 元の色の箱は、選んだものに全部が含まれる箱だけ（一部だけなら灰色のまま帯だけ色付け）', () => {
  // 地方債を選ぶ: 款2（150 のうち地方債 30）・目 2-1-2（50 のうち 30）は一部だけなので灰色。選んだ地方債の箱は元の色
  const f = composeDisplay(FILE, 'general', 'funding:bond');
  assert.ok(f.highlightNodes.has('funding:bond'));
  assert.ok(!f.highlightNodes.has('kan:general:expense:2'));
  assert.ok(!f.highlightNodes.has('moku:general/expense/2-1-2'));
  assert.equal(f.highlight.get(edgeKey('funding:bond', 'kan:general:expense:2')), 30);
  // 款2 を選ぶ: 款2 と、その下の項・目は全部が含まれるので元の色。一般財源の箱（ほかの款の分も含む）は灰色
  const k = composeDisplay(FILE, 'general', 'kan:general:expense:2');
  assert.ok(k.highlightNodes.has('kan:general:expense:2') && k.highlightNodes.has('kou:general:expense:2-1'));
  assert.ok(k.highlightNodes.has('moku:general/expense/2-1-1'));
  assert.ok(!k.highlightNodes.has('funding:general'));
  // 地方債の箱は、地方債がすべて款2 にあるので元の色
  assert.ok(k.highlightNodes.has('funding:bond'));
});

test('表示: 深い列で同じ名前の箱が並ぶときは、上の箱の名前を添える', () => {
  const f: LocalBudgetFile = {
    ...FILE,
    rows: [
      row('general/expense/2-1-1', { amount: v(100), funding: fund(0, 0, 0, 100), moku: { no: 1, name: '教職員費' } }),
      row('general/expense/2-2-1', { amount: v(50), funding: fund(0, 0, 0, 50), kou: { no: 2, name: '項B' }, moku: { no: 1, name: '教職員費' } }),
      row('general/expense/2-2-2', { amount: v(10), funding: fund(0, 0, 0, 10), kou: { no: 2, name: '項B' }, moku: { no: 2, name: '旅費' } }),
    ],
  };
  const d = composeDisplay(f, 'general', 'kan:general:expense:2');
  assert.deepEqual(d.graph.nodes.filter(n => n.col === 'moku').map(n => n.name).sort(),
    ['教職員費（項2-1）', '教職員費（項B）', '旅費']);
});

test('スマートフォンの幅: 選んだ箱の列を真ん中にした3列だけを見せる（額と重ねる帯は変えない）', () => {
  const cols = (d: ReturnType<typeof composeDisplay>) => d.graph.columns.map(c => c.key);
  // 選んでいなければ最初の3列（そのまま）
  assert.deepEqual(cols(windowColumns(composeDisplay(FILE, 'general', null))), ['funding', 'kan', 'kou']);
  // 目を選ぶと 項 → 目 → 事項（目が真ん中）
  const m = windowColumns(composeDisplay(FILE, 'general', 'moku:general/expense/2-1-1'));
  assert.deepEqual(cols(m), ['kou', 'moku', 'item']);
  assert.ok(m.graph.edges.every(e => m.graph.nodes.some(n => n.id === e.source) && m.graph.nodes.some(n => n.id === e.target)));
  assert.equal(m.graph.nodes.find(n => n.id === 'kou:general:expense:2-1')?.value, 150);
  // 事項（右端）を選ぶと右端から3列
  assert.deepEqual(cols(windowColumns(composeDisplay(FILE, 'general', 'item:general/expense/2-1-1:0'))), ['kou', 'moku', 'item']);
  // 款を選ぶと 財源 → 款 → 項（款が真ん中）。目の列は右へ進むと見える
  assert.deepEqual(cols(windowColumns(composeDisplay(FILE, 'general', 'kan:general:expense:2'))), ['funding', 'kan', 'kou']);
  // 左端の財源を選ぶと、開いた列の右端まで（款 → 項 → 目）。財源で絞った目の列が見える
  assert.deepEqual(cols(windowColumns(composeDisplay(FILE, 'general', 'funding:bond'))), ['kan', 'kou', 'moku']);
});

test('補正（差分）のファイルからはグラフを組み立てない（当初 + 補正 は未実装。差分を補正後の額として描かない）', () => {
  assert.throws(() => buildLocalGraph({ ...FILE, basis: 'supplementary' }, { view: 'general' }), /補正/);
});

test('表示: 款を選ぶと目まで開く（一般会計）', () => {
  const d = composeDisplay(FILE, 'general', 'kan:general:expense:2');
  assert.deepEqual([...new Set(d.graph.nodes.map(n => n.col))], ['funding', 'kan', 'kou', 'moku']);
  assert.equal(d.note, null);
});

test('表示: 財源を選ぶと、各目のその財源の額で 款 → 項 → 目 まで重ねる（按分しない・事項は開かない）', () => {
  const d = composeDisplay(FILE, 'general', 'funding:bond');
  assert.deepEqual([...new Set(d.graph.nodes.map(n => n.col))], ['funding', 'kan', 'kou', 'moku']);
  // 地方債は目 2-1-2 の 30 だけ
  assert.equal(d.highlight.get(edgeKey('funding:bond', 'kan:general:expense:2')), 30);
  assert.equal(d.highlight.get(edgeKey('kan:general:expense:2', 'kou:general:expense:2-1')), 30);
  assert.equal(d.highlight.get(edgeKey('kou:general:expense:2-1', 'moku:general/expense/2-1-2')), 30);
  assert.equal(d.highlight.has(edgeKey('funding:general', 'kan:general:expense:2')), false);
  // 深い列の目は、地方債のある目だけ。箱は目の額（50）で出し、地方債の分（30）は重ねる帯で示す
  assert.deepEqual(d.graph.nodes.filter(n => n.col === 'moku').map(n => [n.id, n.value]), [['moku:general/expense/2-1-2', 50]]);
  assert.ok(!d.highlightNodes.has('funding:general'));
});

test('表示: 事項を選ぶと、款 → 項 → 目 → 事項 に事項の金額だけを重ね、財源の帯には色を付けない', () => {
  const d = composeDisplay(FILE, 'general', 'item:general/expense/2-1-1:0');
  assert.equal(d.selected?.name, '職員費');
  assert.equal(d.row, 'general/expense/2-1-1');
  assert.equal(d.note, NOTE_ITEM_FUNDING);
  assert.equal([...d.highlight.keys()].some(k => k.startsWith('funding:')), false);
  assert.equal(d.highlight.get(edgeKey('kan:general:expense:2', 'kou:general:expense:2-1')), 60);
  assert.equal(d.highlight.get(edgeKey('kou:general:expense:2-1', 'moku:general/expense/2-1-1')), 60);
  assert.equal(d.highlight.get(edgeKey('moku:general/expense/2-1-1', 'item:general/expense/2-1-1:0')), 60);
  // 同じ目のほかの事項は並べるが灰色
  assert.ok(d.graph.nodes.some(n => n.id === 'item:general/expense/2-1-1:1'));
  assert.ok(!d.highlightNodes.has('item:general/expense/2-1-1:1'));
  assert.ok(!d.highlightNodes.has('funding:general'));
});

test('表示: 全会計で歳出を選ぶと歳入の列に色を付けない。歳入の款を選ぶと会計から先に色を付けない', () => {
  const d = composeDisplay(FILE, 'all', 'kan:general:expense:2');
  assert.equal([...d.highlight.keys()].some(k => k.startsWith('revenue:')), false);
  assert.ok(d.highlight.get(edgeKey('account:general', 'kan:general:expense:2')));
  assert.equal(d.note, NOTE_REVENUE_UNKNOWN);
  const r = composeDisplay(FILE, 'all', 'revenue:繰入金');
  assert.deepEqual([...r.highlight.keys()], [edgeKey('revenue:繰入金', 'account:special:a')]);
  assert.equal(r.note, NOTE_EXPENSE_UNKNOWN);
});

test('表示: 会計の ID に「:」が入っていても絞り込みを読める', () => {
  assert.deepEqual(selectionToFilter('all', 'kan:special:a:expense:1')?.filter,
    { account: 'special:a', side: 'expense', kan: 1 });
  assert.deepEqual(selectionToFilter('all', 'moku:special:a/expense/1-1-1')?.filter,
    { account: 'special:a', side: 'expense', kan: 1, kou: 1, moku: 1 });
  // 財源は一般会計の見方では目まで追う絞り込みになる。全会計の歳入の款は絞り込まない
  assert.deepEqual(selectionToFilter('general', 'funding:bond'), { filter: { funding: 'bond' }, depth: 4 });
  assert.equal(selectionToFilter('all', 'revenue:県税'), null);
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
  const entry = new Set(['funding', 'kan', 'kou']);
  const out = aggregateTail(g, hl, new Set(['m3', 'm0']), 1, new Set(['m4']), entry);
  // 上位1件（重ねる帯の額が最大の m0）と残す指定の m4 は残り、m1・m2・m3 が「その他 3件」になる。
  // 色の付いた m3 の重ねる帯（6）は「その他」への帯に足し合わされる
  assert.deepEqual(out.graph.nodes.filter(n => n.col === 'moku').map(n => [n.id, n.value]),
    [['m0', 40], ['m4', 4], ['other:moku', 56]]);
  assert.equal(out.graph.edges.find(e => e.target === 'other:moku')?.value, 56);
  assert.equal(out.highlight.get(edgeKey('k', 'other:moku')), 6);
  // 「その他」（56）のうち選んだ分は 6 だけなので、箱は灰色のまま（帯だけ色付け）。まとめた m3 は箱としては消える
  assert.ok(!out.highlightNodes.has('other:moku') && !out.highlightNodes.has('m3'));
  // まとめた箱がすべて選んだものに全部含まれるときは、「その他」も元の色
  const allLit = new Map([40, 30, 20, 6, 4].map((v, i) => [edgeKey('k', `m${i}`), v]));
  const whole = aggregateTail(g, allLit, new Set(['m0', 'm1', 'm2', 'm3', 'm4']), 1, new Set(), entry);
  assert.ok(whole.highlightNodes.has('other:moku'));
  // 項の列（一般会計の最初の画面の右端）はまとめない
  const kouOnly = { ...g, columns: [{ key: 'kou', label: '項' }], nodes: g.nodes.map(n => ({ ...n, col: 'kou' })), edges: [] };
  assert.equal(aggregateTail(kouOnly, new Map(), new Set(), 2, new Set(), entry).graph.nodes.length, 6);
  // 全会計で会計を選んで開いた項の列は深い列なのでまとめる（全会計の最初の画面は 歳入の款 → 会計 → 款）
  const allEntry = new Set(['revenue', 'account', 'kan']);
  assert.equal(aggregateTail(g, new Map(), new Set(), 2, new Set(), allEntry).graph.nodes.some(n => n.id === 'other:moku'), true);
  const kouDeep = { ...g, nodes: g.nodes.map(n => (n.col === 'kou' ? { ...n, col: 'account' } : { ...n, col: 'kou' })),
    columns: [{ key: 'account', label: '会計' }, { key: 'kou', label: '項' }] };
  assert.ok(aggregateTail(kouDeep, new Map(), new Set(), 2, new Set(), allEntry).graph.nodes.some(n => n.id === 'other:kou'));
});

const R8_FILE = path.join(process.cwd(), 'public', 'data', 'local-gov', 'fukuoka-pref', 'budget-2026-initial.json');

test('表示: まとめの上位は重ねる帯の額で選ぶ（財源を選んだとき、その財源が多い目を残す）', () => {
  const g: LocalGraph = {
    schema_version: 1, gov_id: 't', year: 2026, basis: 'initial', totals: { gross: 100 },
    columns: [{ key: 'kou', label: '項' }, { key: 'moku', label: '目' }],
    nodes: [
      { id: 'k', col: 'kou', name: '項', value: 100 },
      ...[40, 30, 20, 10].map((v, i) => ({ id: `m${i}`, col: 'moku', name: `目${i}`, value: v })),
    ],
    edges: [40, 30, 20, 10].map((v, i) => ({ source: 'k', target: `m${i}`, value: v })),
  };
  // 選んだ財源は m3（10 のうち 9）と m2（20 のうち 5）に多い。箱の額では m0・m1 が上位だが、重ねる帯の額で m3・m2 を残す
  const hl = new Map([[edgeKey('k', 'm3'), 9], [edgeKey('k', 'm2'), 5], [edgeKey('k', 'm0'), 1]]);
  const out = aggregateTail(g, hl, new Set(['m3', 'm2', 'm0']), 2, new Set(), new Set(['funding', 'kan', 'kou']));
  assert.deepEqual(out.graph.nodes.filter(n => n.col === 'moku').map(n => n.id), ['m2', 'm3', 'other:moku']);
});

test('実データ（福岡県 R8）: 全会計で一般会計を選ぶと、開いた項の列（62件）を上位 N 件＋その他にまとめる', { skip: !fs.existsSync(R8_FILE) }, () => {
  const file = JSON.parse(fs.readFileSync(R8_FILE, 'utf8')) as LocalBudgetFile;
  const d = composeDisplay(file, 'all', 'account:general');
  const kou = d.graph.nodes.filter(n => n.col === 'kou');
  assert.equal(kou.length, 26);
  assert.ok(kou.some(n => n.id === 'other:kou' && n.name === 'その他 37件'));
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
  assert.deepEqual(valueNotes(f).map(c => [c.field, c.value, c.src, c.note]), [['前年度', 90, 'correction', '画像で確認']]);
  assert.match(valueNotes(f)[0].where, /^一般会計 ／ 歳出 ／ 総務費/);
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
const DATA = R8_FILE;

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
  // 事項の列は、事項のない目（水防費など4つ）の分だけ小さい（設計書 3.2）
  assert.equal(colTotal(g, 'item'), total - 328_571_000);
  // 右端の箱は正規化データの額と比べる（箱の値は入りの帯の合計なので、入りと比べても誤りに気づけない）
  const rowOf = new Map(file.rows.map(r => [r.id, r]));
  for (const n of g.nodes) {
    if (out.has(n.id)) continue;
    const r = rowOf.get(n.row ?? '');
    if (n.col === 'moku') assert.equal(n.value, r?.amount.v, n.id);
    if (n.col === 'item') assert.equal(n.value, r?.items?.[Number(n.id.split(':').at(-1))].amount.v, n.id);
  }
  // 本年度の計上がない目（選挙費6件・歳入4件）は箱を作らず、「データについて」の一覧に出す
  assert.equal(zeroAmountRows(file).length, 10);
  assert.ok(zeroAmountRows(file).every(r => !g.nodes.some(n => n.id === `moku:${r.id}`)));
  // 左端の財源の箱: 出の合計 = その財源の内訳の合計（全目）
  for (const f of ['national', 'bond', 'other', 'general'] as const) {
    const sum = file.rows
      .filter(r => r.account === 'general' && r.side === 'expense')
      .reduce((s, r) => s + (r.funding?.[f].v ?? 0), 0);
    assert.equal(out.get(`funding:${f}`), sum, f);
  }
  // サンキー図は負の太さの帯を描けない。0 円の帯も作らない。どちらの見方でも帯の値はすべて正（負の値が来たら graph.ts の扱いを決める）
  for (const view of ['general', 'all'] as const) {
    const bad = buildLocalGraph(file, { view }).edges.filter(e => e.value <= 0);
    assert.deepEqual(bad, [], `${view} に正でない帯`);
  }
});

test('実データ（福岡県 R8）: 全会計は入りと出の両方がある箱（会計の箱を含む）で入り = 出。款のラベルは会計で見分けられる', { skip: !fs.existsSync(DATA) }, () => {
  const file = JSON.parse(fs.readFileSync(DATA, 'utf8')) as LocalBudgetFile;
  const g = buildLocalGraph(file, { view: 'all' });
  const into = new Map<string, number>();
  const out = new Map<string, number>();
  for (const e of g.edges) {
    into.set(e.target, (into.get(e.target) ?? 0) + e.value);
    out.set(e.source, (out.get(e.source) ?? 0) + e.value);
  }
  let accounts = 0;
  for (const n of g.nodes) {
    if (into.has(n.id) && out.has(n.id)) assert.equal(out.get(n.id), into.get(n.id), n.id);
    if (n.col === 'account') accounts++;
  }
  // 公営企業会計は描かない（設計書 3.2）。R8 にはないが、書き出した後もこのテストがそのまま使えるように除いて数える
  const enterprise = new Set(file.accounts.filter(a => a.kind === 'enterprise').map(a => a.id));
  assert.equal(accounts, file.accounts.length - enterprise.size);
  // 歳入の款・会計・款・項・目の列の合計はどれも全会計の総計（歳入 = 歳出）
  for (const col of ['revenue', 'account', 'kan', 'kou', 'moku']) assert.equal(colTotal(g, col), g.totals.gross, col);
  // 左端の歳入の款の箱は、同じ名前の歳入の款の目の本年度の合計（公営企業会計を除く全会計をまたいで。表記ゆれで箱が割れたり混ざったりしたら気づく）
  const revByName = new Map<string, number>();
  for (const r of file.rows) {
    if (r.side === 'revenue' && !enterprise.has(r.account)) {
      revByName.set(r.kan.name, (revByName.get(r.kan.name) ?? 0) + (r.amount.v ?? 0));
    }
  }
  const revNodes = g.nodes.filter(n => n.col === 'revenue');
  // 表記ゆれで同じ款が2つの箱に割れていないこと（空白・全角半角の違いを除くと同じになる名前の箱が2つない）
  const norm = (s: string) => s.normalize('NFKC').replace(/\s/g, '');
  assert.equal(new Set(revNodes.map(n => norm(n.name))).size, revNodes.length);
  assert.equal(revNodes.length, [...revByName.values()].filter(v => v > 0).length);
  for (const n of revNodes) assert.equal(n.value, revByName.get(n.name), n.id);
  // 右端の目の箱は正規化データの目の本年度と比べる（列の合計が合っていても、目が別の款・会計の下に入る誤りに気づけるように）
  const rowOf = new Map(file.rows.map(r => [r.id, r]));
  const mokuNodes = g.nodes.filter(n => n.col === 'moku');
  assert.equal(mokuNodes.length, file.rows.filter(r => r.side === 'expense' && (r.amount.v ?? 0) > 0).length);
  for (const n of mokuNodes) {
    const r = rowOf.get(n.row ?? '');
    assert.equal(n.value, r?.amount.v, n.id);
    // 目の帯は、同じ会計・同じ款・同じ項の箱から入る
    const e = g.edges.find(x => x.target === n.id);
    assert.equal(e?.source, `kou:${r?.account}:expense:${r?.kan.no}-${r?.kou.no}`, n.id);
  }
  // 同じ名前の歳出の款（公債費 4 など）は会計の名前を添えて、ラベルが重ならない
  const kanNames = g.nodes.filter(n => n.col === 'kan').map(n => n.name);
  assert.equal(new Set(kanNames).size, kanNames.length);
  assert.equal(kanNames.filter(n => n.startsWith('公債費（')).length, 4);
});

test('全会計: 同じ名前の歳出の款が複数の会計にあれば、ラベルに会計の名前を添える（絞り込んでも同じラベル）', () => {
  const f: LocalBudgetFile = {
    ...FILE,
    rows: [
      ...FILE.rows,
      row('special:a/expense/2-1-1', { amount: v(5), kan: { no: 2, name: '款2' } }),
      row('special:a/revenue/2-1-1', { amount: v(5) }),
    ],
  };
  const g = buildLocalGraph(f, { view: 'all' });
  assert.equal(g.nodes.find(n => n.id === 'kan:general:expense:2')?.name, '款2（一般会計）');
  assert.equal(g.nodes.find(n => n.id === 'kan:special:a:expense:2')?.name, '款2（A特別会計）');
  assert.equal(g.nodes.find(n => n.id === 'kan:general:expense:3')?.name, '款3');
  const focused = buildLocalGraph(f, { view: 'all', filter: { account: 'general', side: 'expense', kan: 2 } });
  assert.equal(focused.nodes.find(n => n.id === 'kan:general:expense:2')?.name, '款2（一般会計）');
});
