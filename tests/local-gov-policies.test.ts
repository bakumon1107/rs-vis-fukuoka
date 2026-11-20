import test from 'node:test';
import assert from 'node:assert/strict';
import {
  MUTED_COLOR,
  OTHER_KAN_COLOR,
  SERIES_COLORS,
  bigItems,
  chordPx,
  colorScheme,
  fitWidth,
  fitLabel,
  focusPath,
  initiativeLeaves,
  initiativeTotals,
  itemKan,
  policyTree,
  sourceForDoc,
  type PolicyGroup,
} from '../app/lib/local-gov/policies';
import type { LocalPolicies, PolicyItem } from '../types/local-gov';

const item = (name: string, pillar: number | null, initiative: string, amount: number, kans: number[]): PolicyItem => ({
  name, pillar, initiative, division: '課', amount, previous: null, is_new: false, notes: [],
  kamoku: kans.map(k => ({ kan: k, kou: 1, moku: 1, row: `general/expense/${k}-1-1` })),
  source: { doc: 'a.pdf', page: 1 },
});

const policies: LocalPolicies = {
  pillars: [{ no: 1, name: '柱一' }, { no: 2, name: '柱二' }],
  items: [
    item('甲', 2, '取組A', 30_000_000_000, [3]),
    item('乙', 1, '取組B', 500, [10]),
    item('丙', 2, '取組A', 200, [3, 10]),
    item('丁', null, '行政改革', 100, [2]),
    item('戊', 2, '取組C', 0, [3]),
  ],
  excluded: { special: { count: 0, amount: 0 }, debt_burden: { count: 0, amount: 0 } },
  outside: [],
  expense_total: 1,
  source_docs: ['a.pdf'],
};

test('policyTree: 柱は番号順で柱の外は最後。取組の下に事項。額 0 と外した事項は入れない', () => {
  const t = policyTree(policies);
  assert.deepEqual(t.children.map(c => c.key), ['p:1', 'p:2', 'p:none']);
  const p2 = t.children[1];
  assert.deepEqual(p2.children.map(c => (c as PolicyGroup).name), ['取組A']);
  assert.deepEqual((p2.children[0] as PolicyGroup).children.map(c => c.name), ['甲', '丙']);
  const hidden = policyTree(policies, bigItems(policies));
  assert.deepEqual(((hidden.children[1].children[0] as PolicyGroup).children).map(c => c.name), ['丙']);
});

test('initiativeTotals: 取組ごとの合計の多い順。外した事項・額 0 の事項は数えない（円のない取組は出さない）', () => {
  assert.deepEqual(initiativeTotals(policies).map(t => [t.name, t.amount]), [
    ['取組A', 30_000_000_200], ['取組B', 500], ['行政改革', 100],
  ]);
  assert.equal(initiativeTotals(policies, bigItems(policies))[0].name, '取組B');
});

test('itemKan と色: 款をまたぐ事項は multi。款の色は全事項の額の順で、外しても変わらない', () => {
  assert.equal(itemKan(policies.items[2]), 'multi');
  assert.equal(itemKan(policies.items[0]), 3);
  const names = new Map([[3, '保健費'], [10, '教育費'], [2, '総務費']]);
  const s = colorScheme(policies, 'kan', names);
  assert.equal(s.colorOf(policies.items[0]), SERIES_COLORS[0]); // 保健費が最多
  assert.equal(s.colorOf(policies.items[2]), SERIES_COLORS[6]);
  assert.equal(s.legend.at(-1)?.color, OTHER_KAN_COLOR);
  const p = colorScheme(policies, 'pillar', names);
  assert.equal(p.colorOf(policies.items[1]), SERIES_COLORS[0]);
  assert.equal(p.colorOf(policies.items[3]), SERIES_COLORS[2]); // 柱の外は柱の数の次
  assert.notEqual(OTHER_KAN_COLOR, MUTED_COLOR);
});

test('itemKan: 資料に「外」の印があれば、款が1つでも款をまたぐ事項', () => {
  assert.equal(itemKan({ ...policies.items[0], other_kamoku: true }), 'multi');
});

test('focusPath・initiativeLeaves: 木にある円だけ道すじを返す。外した事項だけの取組は null', () => {
  const t = policyTree(policies);
  assert.deepEqual(focusPath(t, 'i:2:取組A')?.map(c => c.label), ['施策別資料の事項', '2. 柱二', '取組A']);
  assert.deepEqual(focusPath(t, 'p:none')?.map(c => c.key), ['root', 'p:none']);
  assert.deepEqual(initiativeLeaves(t, 'i:2:取組A').map(l => [l.name, l.index]), [['甲', 0], ['丙', 2]]);
  // 取組B の事項（乙 500円）だけを外すと、取組B の円はなくなる
  const hidden = policyTree(policies, new Set([1]));
  assert.equal(focusPath(hidden, 'i:1:取組B'), null);
  assert.deepEqual(initiativeLeaves(hidden, 'i:1:取組B'), []);
});

test('sourceForDoc: PDF のファイル名で資料を探し、サンキー図の使い道の注記を外す', () => {
  const sources = [{ id: 'x', url: 'https://example.jp/uploaded/attachment/278133.pdf', title: '施策別資料（柱2。名前の検索に使用）' }];
  assert.equal(sourceForDoc(sources, '278133.pdf')?.title, '施策別資料（柱2）');
  assert.equal(sourceForDoc(sources, '8133.pdf'), undefined);
});

test('chordPx・fitWidth: 円の上端近くの名前は、その高さの円の幅で切る', () => {
  assert.equal(chordPx(100, 100), 200); // 真ん中は直径
  assert.equal(Math.round(chordPx(166, 17)), 2 * Math.round(Math.sqrt(2 * 166 * 17 - 17 * 17)));
  assert.equal(chordPx(10, 50), 20); // 深さが半径を超えたら直径
  assert.equal(fitWidth('あいうえおかきく', 65, 13), 'あいうえ…');
});

test('fitLabel: 円に収まらない名前は切り、小さすぎる円は空', () => {
  assert.equal(fitLabel('高等学校等就学支援金交付金', 100, 11), '高等学校等就学支援金交付金');
  // 半径 40px・11px の字: 40 × 1.6 / 11 → 5 文字分（4文字 + …）
  assert.equal(fitLabel('高等学校等就学支援金交付金', 40, 11), '高等学校…');
  assert.equal(fitLabel('長い名前', 10, 11), '');
});
