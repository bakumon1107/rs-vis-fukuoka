/**
 * 補正後予算の当初からの増減（app/lib/local-gov/supplement-diff.ts）のテスト。R8 の実データ（当初 + 4 回の補正）で確かめる。
 * 設計: docs/local-gov/tasks/20261127_2337_補正後予算の当初からの増減の表示の設計.md 5章
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { buildLocalGraph } from '../app/lib/local-gov/graph';
import { composeLatest } from '../app/lib/local-gov/supplement';
import {
  boxDeltas, diffTotal, grossDelta, initialBoxIds, initialBoxValues, shortAmount, shortDelta, sortDiff, supplementDiffTree, withoutZero, type DiffNode,
} from '../app/lib/local-gov/supplement-diff';
import { simpleDisplay, SIMPLE_DEPTH } from '../app/lib/local-gov/graph-view';
import type { LocalBudgetFile, LocalGraph } from '../types/local-gov';

test('短い増減: 1万円未満は出さない。億は小数1桁、兆は2桁、万は整数。減は △', () => {
  assert.equal(shortDelta(0), '');
  assert.equal(shortDelta(9_999), '');
  assert.equal(shortDelta(8_500_000), '+850万');
  assert.equal(shortDelta(-450_000_000), '△4.5億');
  assert.equal(shortDelta(1_230_000_000), '+12.3億');
  assert.equal(shortDelta(2_000_000_000), '+20億');
  assert.equal(shortDelta(1_234_000_000_000), '+1.23兆');
  // 丸めると次の単位に届く額（「10000万」「10000億」にしない）
  assert.equal(shortDelta(99_995_000), '+1億');
  assert.equal(shortDelta(-999_995_000_000), '△1兆');
});

test('短い額（スマートフォンの縦の図の2行目）: 単位の決め方は短い増減と同じで、円を付ける', () => {
  assert.equal(shortAmount(84_567_000_000), '845.7億円');
  assert.equal(shortAmount(2_310_000_000_000), '2.31兆円');
  assert.equal(shortAmount(65_934_000), '6593万円');
  assert.equal(shortAmount(99_995_000), '1億円');
  assert.equal(shortAmount(5_000), '5000円');
  assert.equal(shortAmount(0), '0円');
});

test('増減のない行を外す: 子の増減が打ち消し合って親の増減が 0 でも、動いた子があれば親ごと残す', () => {
  const node = (key: string, before: number, after: number, children: DiffNode[] = []): DiffNode =>
    ({ key, name: key, level: 'moku', before, after, rounds: [after - before], children });
  const kou = node('kou', 10, 10, [node('a', 5, 10), node('b', 5, 0), node('c', 3, 3)]);
  const out = withoutZero([kou, node('zero', 1, 1)]);
  assert.deepEqual(out.map(n => n.key), ['kou']);
  assert.deepEqual(out[0].children.map(n => n.key), ['a', 'b']);
});

test('図の「新」は当初予算のファイルのどの行も入らない箱。当初 0 円の目は当初 0 からの増（新ではない）', () => {
  // 当初: 款1 項1 に 0 円の目 1 だけ。補正で 目 1 が 3、新しい項 2（目 1）が 5
  const initialRow = { id: 'general/expense/1-1-1', account: 'general', side: 'expense',
    kan: { no: 1, name: '款1' }, kou: { no: 1, name: '項1' }, moku: { no: 1, name: '当初0円の目' }, amount: { v: 0, src: 'text' }, pages: [] };
  const initialIds = initialBoxIds({ rows: [initialRow] } as unknown as LocalBudgetFile);
  const graph = {
    schema_version: 1, gov_id: 't', year: 2026, basis: 'initial', totals: { gross: 8 }, edges: [],
    columns: [{ key: 'kan', label: '款' }, { key: 'kou', label: '項' }, { key: 'moku', label: '目' }],
    nodes: [
      { id: 'kan:general:expense:1', col: 'kan', name: '款1', value: 8 },
      { id: 'kou:general:expense:1-1', col: 'kou', name: '項1', value: 3 },
      { id: 'kou:general:expense:1-2', col: 'kou', name: '新しい項', value: 5 },
      { id: 'moku:general/expense/1-1-1', col: 'moku', name: '当初0円の目', value: 3 },
      { id: 'moku:general/expense/1-2-1', col: 'moku', name: '新設の目', value: 5 },
    ],
  } as LocalGraph;
  const d = boxDeltas(graph, new Map(), initialIds);
  assert.deepEqual(d.get('moku:general/expense/1-1-1'), { delta: 3, added: false });
  assert.deepEqual(d.get('kou:general:expense:1-1'), { delta: 3, added: false });
  assert.deepEqual(d.get('kan:general:expense:1'), { delta: 8, added: false });
  // 新しい項とその目は新
  assert.deepEqual(d.get('kou:general:expense:1-2'), { delta: 5, added: true });
  assert.deepEqual(d.get('moku:general/expense/1-2-1'), { delta: 5, added: true });
});

test('並べ替え: 自分の増減が 0 でも子が動いた行は、子の動いた額で並ぶ', () => {
  const node = (key: string, before: number, after: number, children: DiffNode[] = []): DiffNode =>
    ({ key, name: key, level: 'kou', before, after, rounds: [after - before], children });
  const moved = node('付け替え', 10, 10, [node('a', 0, 10), node('b', 10, 0)]);
  const small = node('小さい増', 0, 1);
  assert.deepEqual(sortDiff([small, moved], 'delta').map(n => n.key), ['付け替え', '小さい増']);
});

const DIR = path.join(process.cwd(), 'public', 'data', 'local-gov', 'fukuoka-pref');
const has = fs.existsSync(path.join(DIR, 'budget-2026-supplementary-4.json'));
const read = (name: string) => JSON.parse(fs.readFileSync(path.join(DIR, name), 'utf-8')) as LocalBudgetFile;

test('実データ R8: 増減の表の合計 = 補正のファイルの額の合計（会計・歳入歳出ごと）。回ごとの額の合計 = 増減', { skip: !has }, () => {
  const initial = read('budget-2026-initial.json');
  const sups = [1, 2, 3, 4].map(n => read(`budget-2026-supplementary-${n}.json`));
  const composed = composeLatest(initial, sups);
  const enterprise = new Set(initial.accounts.filter(a => a.kind === 'enterprise').map(a => a.id));
  for (const side of ['expense', 'revenue'] as const) {
    const tree = supplementDiffTree(composed, { side, byAccount: true });
    for (const acc of tree) {
      const id = acc.key.replace(/^account:/, '');
      const supSum = sups.flatMap(s => s.rows).filter(r => r.account === id && r.side === side).reduce((t, r) => t + (r.amount.v ?? 0), 0);
      assert.equal(acc.after - acc.before, supSum, `${id} ${side}`);
      // 回ごとの額の合計 = 増減。子の合計 = 親
      assert.equal(acc.rounds.reduce((t, v) => t + v, 0), acc.after - acc.before, `${id} ${side} 回ごと`);
      assert.equal(diffTotal(acc.children).after, acc.after);
      assert.ok(!enterprise.has(id), '公営企業会計は入れない');
    }
    // 一般会計だけ（一般会計の見方）は会計の段がなく款から
    const general = supplementDiffTree(composed, { side, byAccount: false });
    assert.ok(general.every(n => n.level === 'kan' && n.key.startsWith('kan:general:')));
  }
  // 補正で新しく設けた目に印（R8 8月専決の県議会議員補欠選挙費など）。当初 0
  const all = supplementDiffTree(composed, { side: 'expense', byAccount: true });
  const flat = (ns: ReturnType<typeof supplementDiffTree>): ReturnType<typeof supplementDiffTree> => ns.flatMap(n => [n, ...flat(n.children)]);
  const added = flat(all).filter(n => n.addedIn);
  assert.ok(added.length > 0);
  assert.ok(added.every(n => n.before === 0 && n.level === 'moku'));
  // 増減のない行を外す・増減の大きい順
  const nz = withoutZero(all);
  assert.ok(flat(nz).every(n => n.after !== n.before));
  const sorted = sortDiff(nz, 'delta')[0].children;
  for (let i = 1; i < sorted.length; i++) {
    assert.ok(Math.abs(sorted[i - 1].after - sorted[i - 1].before) >= Math.abs(sorted[i].after - sorted[i].before));
  }
});

test('実データ R8: 図の箱の増減 = 補正後の箱の額 − 当初の同じ箱の額。財源の箱には出さない。見出しの総計の増減', { skip: !has }, () => {
  const initial = read('budget-2026-initial.json');
  const composed = composeLatest(initial, [1, 2, 3, 4].map(n => read(`budget-2026-supplementary-${n}.json`)));
  for (const view of ['general', 'all'] as const) {
    const before = initialBoxValues(initial, view);
    const after = buildLocalGraph(composed, { view });
    const deltas = boxDeltas(after, before, initialBoxIds(initial));
    // 「新」の確かめは実装と別の性質で: 新の箱は当初の図にない。当初の図にある箱は新ではない。
    // 補正で新しく設けた目（added_in）の箱は新
    const addedMoku = new Set(composed.rows.filter(r => r.added_in).map(r => `moku:${r.id}`));
    const initialGraph = buildLocalGraph(initial, { view });
    for (const n of after.nodes) {
      const d = deltas.get(n.id);
      if (n.col === 'funding' || n.col === 'item') {
        assert.equal(d, undefined, `${n.id} には増減を出さない`);
        continue;
      }
      const b = initialGraph.nodes.find(x => x.id === n.id);
      assert.equal(d?.delta, n.value - (b?.value ?? 0), n.id);
      if (d?.added) assert.equal(b, undefined, `${n.id} は新なのに当初の図にある`);
      if (b !== undefined) assert.equal(d?.added, false, `${n.id} は当初の図にあるのに新`);
      if (addedMoku.has(n.id)) assert.equal(d?.added, true, `${n.id} は補正で設けた目なのに新でない`);
    }
    // 見出しの総計の増減 = 補正後の総計 − 当初の総計
    assert.equal(grossDelta(initial, view, after.totals.gross), after.totals.gross - initialGraph.totals.gross);
  }
  // かんたんの図: 見方の左2列だけで、総計・箱の額はくわしくの図と同じ（推計しない）
  for (const file of [initial, composed]) {
    for (const view of ['general', 'all'] as const) {
      const s = simpleDisplay(file, view).graph;
      const full = buildLocalGraph(file, { view });
      assert.deepEqual(s.columns.map(c => c.key), full.columns.slice(0, SIMPLE_DEPTH).map(c => c.key));
      assert.equal(s.totals.gross, full.totals.gross, `${view} かんたんの総計`);
      for (const n of s.nodes) assert.equal(n.value, full.nodes.find(x => x.id === n.id)?.value, `${view} ${n.id}`);
    }
  }
  // 一般会計の歳出の増減 = 一般会計の歳出の増減の表の合計
  const tree = supplementDiffTree(composed, { side: 'expense', byAccount: false });
  const t = diffTotal(tree);
  const g = buildLocalGraph(composed, { view: 'general' }).totals.gross;
  assert.equal(grossDelta(initial, 'general', g), t.after - t.before);
});
