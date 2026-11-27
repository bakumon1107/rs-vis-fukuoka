/**
 * 公営企業会計の見方（収入の項・補填財源 → 会計・条 → 支出の項 → 目）のグラフと選択のテスト。
 * 設計: docs/local-gov/tasks/20261121_0100_公開前のサンキー図の足しと公営企業会計の設計.md 4.4・4.5
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { buildLocalGraph } from '../app/lib/local-gov/graph';
import {
  composeDisplay, edgeKey, NOTE_ENTERPRISE_EXPENSE_UNKNOWN, NOTE_ENTERPRISE_REVENUE_UNKNOWN, selectionToFilter, windowColumns,
} from '../app/lib/local-gov/graph-view';
import { enterpriseExpense } from '../app/lib/local-gov/totals';
import type { LocalBudgetFile, LocalGraph, MokuRow } from '../types/local-gov';

function ent(account: string, side: 'revenue' | 'expense', section: '収益的' | '資本的', nums: string, amount: number, kouName: string): MokuRow {
  const [kan, kou, moku] = nums.split('-').map(Number);
  const art = section === '収益的' ? 3 : 4;
  return {
    id: `${account}/${side}/${art}-${nums}`, account, side, enterprise_section: section,
    kan: { no: kan, name: `款${kan}`, name_src: 'readings' }, kou: { no: kou, name: kouName, name_src: 'readings' },
    moku: { no: moku, name: `目${art}-${nums}`, name_src: 'correction' },
    amount: { v: amount, src: 'text' }, pages: [{ source: 's', page: 1 }],
  };
}

// 病院: 収益的は利益 10、資本的は不足 20（補填財源 2つ）。用地: 収益的は不足 5。企業債は2会計にある（名前でまとめる）
const FILE: LocalBudgetFile = {
  schema_version: 1, gov_id: 'test', year: 2026, year_label: '令和8年度', basis: 'initial', unit_source: '千円',
  accounts: [
    { id: 'general', kind: 'general', name: '一般会計' },
    { id: 'enterprise:byoin', kind: 'enterprise', name: '病院事業会計',
      enterprise: { capital_shortfall: { amount: 20, items: [{ name: '留保資金', amount: 15 }, { name: '繰越利益剰余金処分額', amount: 5 }],
        source: { source: 'g', page: 1 } } } },
    { id: 'enterprise:yochi', kind: 'enterprise', name: '工業用地造成事業会計' },
  ],
  rows: [
    { id: 'general/expense/1-1-1', account: 'general', side: 'expense', kan: { no: 1, name: '議会費' }, kou: { no: 1, name: '議会費' },
      moku: { no: 1, name: '議会費' }, amount: { v: 999, src: 'text' }, pages: [{ source: 's', page: 1 }] },
    ent('enterprise:byoin', 'revenue', '収益的', '1-1-1', 70, '医業収益'),
    ent('enterprise:byoin', 'revenue', '収益的', '1-2-1', 30, '医業外収益'),
    ent('enterprise:byoin', 'expense', '収益的', '1-1-1', 60, '医業費用'),
    ent('enterprise:byoin', 'expense', '収益的', '1-1-2', 30, '医業費用'),
    ent('enterprise:byoin', 'revenue', '資本的', '1-1-1', 30, '企業債'),
    ent('enterprise:byoin', 'expense', '資本的', '1-1-1', 50, '建設改良費'),
    ent('enterprise:yochi', 'revenue', '収益的', '1-1-1', 10, '営業収益'),
    ent('enterprise:yochi', 'expense', '収益的', '1-1-1', 15, '営業費用'),
    ent('enterprise:yochi', 'revenue', '資本的', '1-1-1', 8, '企業債'),
    ent('enterprise:yochi', 'expense', '資本的', '1-1-1', 8, '償還金'),
    ent('enterprise:yochi', 'expense', '資本的', '1-1-2', 0, '償還金'),
  ],
  checks: { rows: 12, all_ok: 12, rules: {} },
};

const colTotal = (g: LocalGraph, col: string) => g.nodes.filter(n => n.col === col).reduce((s, n) => s + n.value, 0);

/** 帯の入りと出が両方ある箱（真ん中の箱）は入り = 出 */
function assertBalanced(g: LocalGraph) {
  const into = new Map<string, number>();
  const out = new Map<string, number>();
  for (const e of g.edges) {
    assert.ok(e.value > 0, `${e.source} → ${e.target} が ${e.value}`);
    into.set(e.target, (into.get(e.target) ?? 0) + e.value);
    out.set(e.source, (out.get(e.source) ?? 0) + e.value);
  }
  for (const n of g.nodes) if (into.has(n.id) && out.has(n.id)) assert.equal(out.get(n.id), into.get(n.id), n.id);
}

test('公営企業会計: 会計・条の箱は入り = 出（補填財源・収益的収支の差・不足の箱で合わせる）。一般会計は描かない', () => {
  const g = buildLocalGraph(FILE, { view: 'enterprise' });
  assertBalanced(g);
  assert.deepEqual(g.columns.map(c => c.key), ['erevenue', 'esection', 'ekou', 'moku']);
  assert.ok(!g.nodes.some(n => n.name === '議会費'));
  const node = (id: string) => g.nodes.find(n => n.id === id);
  assert.equal(node('esection:enterprise:byoin:3')?.name, '病院 収益的');
  // 会計・条の列は金額をラベルに出さない（名前が長く支出の項の列に重なる）
  assert.equal(g.columns.find(c => c.key === 'esection')?.hideAmount, true);
  // 補填財源の内訳は1つずつ箱にする
  assert.equal(node('efill:留保資金')?.value, 15);
  assert.equal(node('efill:繰越利益剰余金処分額')?.value, 5);
  // 病院の収益的は利益 10（右へ）、用地の収益的は不足 5（左から）。資本的は補填財源でちょうど合うので差の箱はない
  assert.equal(node('esurplus:enterprise:byoin:3')?.value, 10);
  assert.equal(node('esurplus:enterprise:byoin:3')?.name, '病院・収益的収支の差（予算上の利益）');
  assert.equal(node('eshort:enterprise:yochi:3')?.value, 5);
  // 差の箱は同じ会計・条の支出の項のすぐ下（列の最後ではない）
  const kouCol = g.nodes.filter(n => n.col === 'ekou').map(n => n.id);
  assert.equal(kouCol[kouCol.indexOf('ekou:enterprise:byoin:3:1-1') + 1], 'esurplus:enterprise:byoin:3');
  assert.ok(!g.nodes.some(n => n.id.startsWith('esurplus:') && n.id.endsWith(':4')));
  // 企業債は会計をまたいで1つの箱（30 + 8）
  assert.equal(node('erevenue:企業債')?.value, 38);
  // 支出の項は会計・条ごと（同じ名前「医業費用」の目2つは1つの項の箱）。0 円の目は描かない
  assert.equal(node('ekou:enterprise:byoin:3:1-1')?.value, 90);
  assert.ok(!g.nodes.some(n => n.id === 'moku:enterprise:yochi/expense/4-1-1-2'));
  // 支出の合計（gross）は第3条 + 第4条
  assert.equal(g.totals.gross, 60 + 30 + 50 + 15 + 8);
  // 列の合計: 左（収入 + 補填財源 + 不足） = 真ん中 = 右（支出の項 + 利益）
  assert.equal(colTotal(g, 'erevenue'), colTotal(g, 'esection'));
  assert.equal(colTotal(g, 'esection'), colTotal(g, 'ekou'));
});

test('公営企業会計: 支出の項・目で絞ったときは収入・差の箱を足さない（支出だけの箱に「不足」を出さない）', () => {
  const g = buildLocalGraph(FILE, { view: 'enterprise', filter: { account: 'enterprise:byoin', section: '収益的', side: 'expense', kan: 1, kou: 1 } });
  assert.ok(!g.nodes.some(n => /^(eshort|esurplus|efill|erevenue):/.test(n.id)));
  assert.equal(g.totals.gross, 90);
});

test('公営企業会計: 選択（会計・条、支出の項・目は目まで。収入・補填財源は絞り込まない）', () => {
  assert.deepEqual(selectionToFilter('enterprise', 'esection:enterprise:byoin:4'),
    { filter: { account: 'enterprise:byoin', section: '資本的' }, depth: 4 });
  assert.deepEqual(selectionToFilter('enterprise', 'ekou:enterprise:byoin:3:1-1'),
    { filter: { account: 'enterprise:byoin', section: '収益的', side: 'expense', kan: 1, kou: 1 }, depth: 4 });
  assert.deepEqual(selectionToFilter('enterprise', 'moku:enterprise:byoin/expense/3-1-1-2'),
    { filter: { account: 'enterprise:byoin', section: '収益的', side: 'expense', kan: 1, kou: 1, moku: 2 }, depth: 4 });
  assert.equal(selectionToFilter('enterprise', 'erevenue:企業債'), null);
  assert.equal(selectionToFilter('enterprise', 'efill:留保資金'), null);
  // 款の番号は条ごとに振り直される: 第3条の項を選んでも第4条の同じ番号の項は混ざらない
  const d = composeDisplay(FILE, 'enterprise', 'ekou:enterprise:byoin:3:1-1');
  assert.equal(d.selected?.id, 'ekou:enterprise:byoin:3:1-1');
  assert.ok(d.graph.nodes.some(n => n.id === 'moku:enterprise:byoin/expense/3-1-1-2'));
  assert.ok(!d.graph.nodes.some(n => n.id === 'moku:enterprise:byoin/expense/4-1-1-1'));
  assert.equal(d.note, NOTE_ENTERPRISE_REVENUE_UNKNOWN);
  // 目を選ぶと詳細パネルにその目
  assert.equal(composeDisplay(FILE, 'enterprise', 'moku:enterprise:byoin/expense/3-1-1-2').row, 'enterprise:byoin/expense/3-1-1-2');
  // 会計・条を選ぶと、その条の収入・補填財源の帯にも色が付く（目まで開く）
  const s = composeDisplay(FILE, 'enterprise', 'esection:enterprise:byoin:4');
  assert.ok(s.highlightNodes.has('efill:留保資金'));
  assert.ok(s.graph.nodes.some(n => n.id === 'moku:enterprise:byoin/expense/4-1-1-1'));
  // 収入・補填財源の箱は、その箱から出る帯だけ（どの支出かは資料にない）
  assert.equal(composeDisplay(FILE, 'enterprise', 'erevenue:企業債').note, NOTE_ENTERPRISE_EXPENSE_UNKNOWN);
  assert.equal(composeDisplay(FILE, 'enterprise', 'efill:留保資金').note, NOTE_ENTERPRISE_EXPENSE_UNKNOWN);
  // 収益的収支の不足も、どの支出の項に入ったかは分からないので同じ断り書き。差（利益）の箱は出る帯がないので、入る帯を重ねる
  assert.equal(composeDisplay(FILE, 'enterprise', 'eshort:enterprise:yochi:3').note, NOTE_ENTERPRISE_EXPENSE_UNKNOWN);
  const sur = composeDisplay(FILE, 'enterprise', 'esurplus:enterprise:byoin:3');
  assert.equal(sur.highlight.get(edgeKey('esection:enterprise:byoin:3', 'esurplus:enterprise:byoin:3')), 10);
  // スマートフォンの幅で会計・条を選んだら、開いた目の列まで見せる
  assert.deepEqual(windowColumns(s).graph.columns.map(c => c.key), ['esection', 'ekou', 'moku']);
});

test('公営企業会計: 支出の項の名前が複数の会計・条にあれば会計・条を添える。補填財源の内訳が不足額と合わなければ補填財源を描かない', () => {
  const dup: LocalBudgetFile = { ...FILE, rows: [...FILE.rows, ent('enterprise:yochi', 'expense', '収益的', '1-2-1', 1, '医業費用'),
    ent('enterprise:yochi', 'revenue', '収益的', '1-1-2', 1, '営業収益')] };
  const g = buildLocalGraph(dup, { view: 'enterprise' });
  const label = (id: string) => g.nodes.find(n => n.id === id)?.name;
  assert.equal(label('ekou:enterprise:byoin:3:1-1'), '医業費用（病院・収益）');
  assert.equal(label('ekou:enterprise:yochi:3:1-2'), '医業費用（用地・収益）'); // 工業用地造成は「用地」（工業用水道と頭が同じ）
  assert.equal(label('ekou:enterprise:yochi:3:1-1'), '営業費用'); // 1つだけの名前はそのまま
  // 同じ会計・条の中にも同じ名前の項があれば款-項の番号も添える（同じ款の中でも見分けられる）
  const sameSec: LocalBudgetFile = { ...FILE, rows: [...FILE.rows, ent('enterprise:byoin', 'expense', '収益的', '1-3-1', 3, '医業費用'),
    ent('enterprise:byoin', 'revenue', '収益的', '1-2-2', 3, '医業外収益')] };
  const gs = buildLocalGraph(sameSec, { view: 'enterprise' });
  assert.equal(gs.nodes.find(n => n.id === 'ekou:enterprise:byoin:3:1-1')?.name, '医業費用（病院・収益・1-1）');
  assert.equal(gs.nodes.find(n => n.id === 'ekou:enterprise:byoin:3:1-3')?.name, '医業費用（病院・収益・1-3）');
  // その2つの項の目に同じ名前があれば、目のラベルは項の名前と番号で見分ける
  const sameSecMoku: LocalBudgetFile = { ...sameSec, rows: sameSec.rows.map(r => r.id === 'enterprise:byoin/expense/3-1-3-1'
    ? { ...r, moku: { ...r.moku, name: '目3-1-1-1' } } : r) };
  const ds = composeDisplay(sameSecMoku, 'enterprise', 'esection:enterprise:byoin:3');
  const mokuNames = ds.graph.nodes.filter(n => n.col === 'moku').map(n => n.name);
  assert.ok(mokuNames.includes('目3-1-1-1（医業費用・1-1）') && mokuNames.includes('目3-1-1-1（医業費用・1-3）'), JSON.stringify(mokuNames));
  // 目のラベルに添える上の項の名前は、添えた（会計・条）を外す（入れ子の括弧にしない）
  const sameMoku: LocalBudgetFile = { ...dup, rows: dup.rows.map(r => r.id === 'enterprise:byoin/expense/3-1-1-2'
    ? { ...r, moku: { ...r.moku, name: '目3-1-1-1' } } : r).concat(ent('enterprise:byoin', 'expense', '収益的', '1-2-1', 4, '医業外費用'),
    ent('enterprise:byoin', 'revenue', '収益的', '1-2-3', 4, '医業外収益')) };
  const sm = sameMoku.rows.find(r => r.id === 'enterprise:byoin/expense/3-1-2-1')!;
  sm.moku = { ...sm.moku, name: '目3-1-1-1' };
  const dm = composeDisplay(sameMoku, 'enterprise', 'esection:enterprise:byoin:3');
  assert.ok(dm.graph.nodes.some(n => n.name === '目3-1-1-1（医業費用）'), JSON.stringify(dm.graph.nodes.filter(n => n.col === 'moku').map(n => n.name)));
  // 内訳の合計 25 ≠ 不足 20: 補填財源の箱を作らず、「補填財源の記載なし」の不足 20 にする（ありもしない「収入の残り」を作らない）
  const bad: LocalBudgetFile = { ...FILE, accounts: FILE.accounts.map(a => a.id === 'enterprise:byoin'
    ? { ...a, enterprise: { capital_shortfall: { amount: 20, items: [{ name: '留保資金', amount: 25 }], source: { source: 'g', page: 1 } } } } : a) };
  const gb = buildLocalGraph(bad, { view: 'enterprise' });
  assert.ok(!gb.nodes.some(n => n.id.startsWith('efill:')));
  assert.equal(gb.nodes.find(n => n.id === 'eshort:enterprise:byoin:4')?.value, 20);
  assert.ok(!gb.nodes.some(n => n.id === 'esurplus:enterprise:byoin:4'));
  // 内訳の合計 15 < 不足 20: 内訳は描き、残り 5 を「補填財源の記載なし」にする
  const less: LocalBudgetFile = { ...FILE, accounts: FILE.accounts.map(a => a.id === 'enterprise:byoin'
    ? { ...a, enterprise: { capital_shortfall: { amount: 20, items: [{ name: '留保資金', amount: 15 }], source: { source: 'g', page: 1 } } } } : a) };
  const gl = buildLocalGraph(less, { view: 'enterprise' });
  assert.equal(gl.nodes.find(n => n.id === 'efill:留保資金')?.value, 15);
  assert.equal(gl.nodes.find(n => n.id === 'eshort:enterprise:byoin:4')?.value, 5);
  assert.equal(gl.nodes.find(n => n.id === 'eshort:enterprise:byoin:4')?.name, '病院・資本的収支の不足（補填財源の内訳にない残り）');
  // 負の内訳は描かない（負の帯は描けない）
  const neg: LocalBudgetFile = { ...FILE, accounts: FILE.accounts.map(a => a.id === 'enterprise:byoin'
    ? { ...a, enterprise: { capital_shortfall: { amount: 20, items: [{ name: '留保資金', amount: 30 }, { name: 'x', amount: -15 }],
      source: { source: 'g', page: 1 } } } } : a) };
  const gn = buildLocalGraph(neg, { view: 'enterprise' });
  assert.ok(!gn.nodes.some(n => n.id.startsWith('efill:')) && gn.edges.every(e => e.value > 0));
});

test('公営企業会計の支出の合計（見出し）。公営企業会計がなければ null', () => {
  assert.deepEqual(enterpriseExpense(FILE), { accounts: 2, revenueSection: 105, capitalSection: 58 });
  assert.equal(enterpriseExpense({ ...FILE, accounts: FILE.accounts.slice(0, 1) }), null);
});

const R8_FILE = path.join(process.cwd(), 'public', 'data', 'local-gov', 'fukuoka-pref', 'budget-2026-initial.json');

test('実データ R8: 公営企業会計の見方は入り = 出、列の合計がそろい、支出の合計は予算書の第3条・第4条の支出の合計', { skip: !fs.existsSync(R8_FILE) }, () => {
  const file = JSON.parse(fs.readFileSync(R8_FILE, 'utf-8')) as LocalBudgetFile;
  const g = buildLocalGraph(file, { view: 'enterprise' });
  assertBalanced(g);
  assert.equal(colTotal(g, 'erevenue'), colTotal(g, 'esection'));
  assert.equal(colTotal(g, 'esection'), colTotal(g, 'ekou'));
  assert.equal(g.nodes.filter(n => n.col === 'esection').length, 10); // 5会計 × 2条
  // 第3条 25,738,408 千円・第4条 21,959,600 千円（予算書の本体）
  assert.deepEqual(enterpriseExpense(file), { accounts: 5, revenueSection: 25_738_408_000, capitalSection: 21_959_600_000 });
  assert.equal(g.totals.gross, 25_738_408_000 + 21_959_600_000);
  // 資本的収支は5会計とも補填財源でちょうど合う（差・不足の箱は第3条だけ）
  assert.ok(!g.nodes.some(n => /^(eshort|esurplus):.*:4$/.test(n.id)));
  // 支出の項の箱の名前はどれも見分けられる（予備費 6・建設改良費 4 などに会計・条を添える）
  const kouNames = g.nodes.filter(n => n.col === 'ekou').map(n => n.name);
  assert.equal(new Set(kouNames).size, kouNames.length);
  // R8 は工業用地造成の収益的収支が不足（設計 4.4）
  assert.ok(g.nodes.some(n => n.id === 'eshort:enterprise:kogyo-yochi:3'));
  // すべての会計・条・支出の項・目は選べる（図にある箱を指す）
  for (const n of buildLocalGraph(file, { view: 'enterprise', depth: 4 }).nodes) {
    if (!/^(esection|ekou|moku):/.test(n.id)) continue;
    assert.equal(composeDisplay(file, 'enterprise', n.id).selected?.id, n.id, n.id);
  }
});
