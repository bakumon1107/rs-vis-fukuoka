import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { composeLatest } from '../app/lib/local-gov/supplement';
import { buildLocalGraph } from '../app/lib/local-gov/graph';
import type { LocalBudgetFile, MokuRow, Value } from '../types/local-gov';

const v = (n: number, src: Value['src'] = 'ocr'): Value => ({ v: n, src });

function row(id: string, amount: number, over: Partial<MokuRow> = {}): MokuRow {
  const [kan, kou, moku] = id.split('/')[2].split('-').map(Number);
  return {
    id,
    account: 'general',
    side: id.includes('/expense/') ? 'expense' : 'revenue',
    kan: { no: kan, name: `款${kan}` },
    kou: { no: kou, name: `項${kou}` },
    moku: { no: moku, name: `目${moku}` },
    amount: v(amount),
    pages: [{ source: 'r8-setsumeisho-ippan', page: 1 }],
    ...over,
  };
}

function file(basis: LocalBudgetFile['basis'], rows: MokuRow[], round?: string): LocalBudgetFile {
  return {
    schema_version: 1,
    gov_id: 'fukuoka-pref',
    year: 2026,
    year_label: '令和8年度',
    basis,
    ...(round ? { supplementary: { round, kind: '定例' as const } } : {}),
    unit_source: '千円',
    accounts: [{ id: 'general', kind: 'general', name: '一般会計' }],
    rows,
    checks: { rows: rows.length, all_ok: rows.length, rules: {} },
  };
}

test('composeLatest adds supplement amounts, funding, items and setsu by id/name/no', () => {
  const init = file('initial', [
    row('general/expense/2-6-4', 33_000, {
      funding: { national: v(0), bond: v(0), other: v(0), general: v(33_000) },
      items: [{ name: '銃砲火薬類取締費', amount: v(33_000) }],
      setsu: [{ no: 10, name: '需用費', amount: v(33_000), sub: [{ name: '食糧費', amount: v(1_000) }] }],
    }),
    row('general/expense/3-4-2', 100),
  ]);
  const s1 = file(
    'supplementary',
    [
      row('general/expense/2-6-4', 1_604_118, {
        before: v(33_000),
        after: v(1_637_118),
        funding: { national: v(0), bond: v(0), other: v(0), general: v(1_604_118) },
        items: [{ name: 'ガス等行政費', amount: v(1_604_118) }],
        setsu: [
          { no: 10, name: '需用費', amount: v(112), sub: [{ name: 'その他需用費', amount: v(112) }] },
          { no: 18, name: '負担金、補助及び交付金', amount: v(1_604_006) },
        ],
      }),
      row('general/expense/2-5-3', 31_684, { before: v(0), after: v(31_684) }),
    ],
    '6月補正（第1号）',
  );
  const out = composeLatest(init, [s1]);
  const r = out.rows.find(x => x.id === 'general/expense/2-6-4')!;
  assert.equal(r.amount.v, 1_637_118);
  assert.equal(r.before?.v, 33_000);
  assert.equal(r.funding?.general.v, 1_637_118);
  assert.deepEqual(
    r.items?.map(i => [i.name, i.amount.v, i.added_in]),
    [
      ['銃砲火薬類取締費', 33_000, undefined],
      ['ガス等行政費', 1_604_118, '6月補正（第1号）'],
    ],
  );
  assert.deepEqual(
    r.setsu?.map(s => [s.no, s.amount.v, s.added_in]),
    [
      [10, 33_112, undefined],
      [18, 1_604_006, '6月補正（第1号）'],
    ],
  );
  // 細節は当初（食糧費）と補正（その他需用費）の両方にあるので足す（当初の細節の合計 1,000 は節 33,000 と合わないが、
  // これはテストの当初データの都合。実データでは細節の合計 = 節の額）
  assert.deepEqual(r.setsu?.[0].sub?.map(x => x.name), ['食糧費', 'その他需用費']);
  // 当初にない目は加わり、当初の額 0・その回の印
  const added = out.rows.find(x => x.id === 'general/expense/2-5-3')!;
  assert.equal(added.added_in, '6月補正（第1号）');
  assert.equal(added.before?.v, 0);
  // 補正のない目はそのまま（before に当初の額）
  assert.equal(out.rows.find(x => x.id === 'general/expense/3-4-2')!.amount.v, 100);
  assert.equal(out.composed?.through, '6月補正（第1号）');
  assert.equal(out.basis, 'initial');
  // 元のデータは書き換えない
  assert.equal(init.rows[0].amount.v, 33_000);
});

test('composeLatest drops breakdowns that would not add up', () => {
  const init = file('initial', [
    row('general/revenue/15-1-7', 100, {
      items: [{ name: '道路事業債', amount: v(100) }],
      setsu: [{ no: 13, name: '道路事業債', amount: v(100) }],
    }),
    row('general/expense/8-3-2', 500, { setsu: [{ no: 10, name: '需用費', amount: v(500) }] }),
  ]);
  const s = file(
    'supplementary',
    [
      // 事項を載せなかった歳入の目（事項の合計が目の額と合わない）: 当初の事項だけでは補正後の額にならない
      row('general/revenue/15-1-7', 20, { before: v(100), after: v(120), setsu: [{ no: 3, name: '河川事業債', amount: v(20) }] }),
      // 当初の節には細節がなく、補正の節に細節がある: 細節を出さない
      row('general/expense/8-3-2', 7, {
        before: v(500),
        after: v(507),
        setsu: [{ no: 10, name: '需用費', amount: v(7), sub: [{ name: 'その他需用費', amount: v(7) }] }],
      }),
    ],
    '9月補正（第3号）',
  );
  const out = composeLatest(init, [s]);
  const rev = out.rows.find(x => x.id === 'general/revenue/15-1-7')!;
  assert.equal(rev.amount.v, 120);
  assert.equal(rev.items, undefined);
  const ex = out.rows.find(x => x.id === 'general/expense/8-3-2')!;
  assert.equal(ex.setsu?.[0].amount.v, 507);
  assert.equal(ex.setsu?.[0].sub, undefined);
});

test('composeLatest keeps same-named items of one round separate', () => {
  const init = file('initial', [row('general/revenue/9-2-6', 100, { items: [{ name: '橋りょう補修費補助金', amount: v(100) }] })]);
  const s = file(
    'supplementary',
    [
      row('general/revenue/9-2-6', 60, {
        before: v(100),
        after: v(160),
        items: [
          { name: '社会資本整備総合交付金', amount: v(10) },
          { name: '橋りょう補修費補助金', amount: v(20) },
          { name: '社会資本整備総合交付金', amount: v(30) },
        ],
      }),
    ],
    '9月補正（第3号）',
  );
  const r = composeLatest(init, [s]).rows[0];
  assert.deepEqual(
    r.items?.map(i => [i.name, i.amount.v]),
    [
      ['橋りょう補修費補助金', 120],
      ['社会資本整備総合交付金', 10],
      ['社会資本整備総合交付金', 30],
    ],
  );
});

test('composeLatest drops one-sided breakdowns and places new moku in their kou', () => {
  const init = file('initial', [
    row('general/revenue/7-2-3', 1_000),
    row('general/expense/2-5-1', 100, { funding: { national: v(0), bond: v(0), other: v(0), general: v(100) } }),
    row('general/expense/2-5-2', 50),
    row('general/expense/3-1-1', 10),
  ]);
  const s = file(
    'supplementary',
    [
      // 当初に事項のない目に、補正の事項だけ（補正の分だけの内訳になる）
      row('general/revenue/7-2-3', 39, { items: [{ name: '港湾局部改良事業費負担金', amount: v(39) }] }),
      // 当初に財源があり、補正に財源がない
      row('general/expense/2-5-1', 5),
      // 補正で新しく設けた目（同じ項の最後の目の後ろに入る）
      row('general/expense/2-5-3', 7, { items: [{ name: '県議会議員補欠選挙費', amount: v(7) }] }),
    ],
    '8月専決補正（第2号）',
  );
  const out = composeLatest(init, [s]);
  const get = (id: string) => out.rows.find(x => x.id === id)!;
  assert.equal(get('general/revenue/7-2-3').amount.v, 1_039);
  assert.equal(get('general/revenue/7-2-3').items, undefined);
  assert.equal(get('general/expense/2-5-1').funding, undefined);
  assert.deepEqual(
    out.rows.map(r => r.id),
    ['general/revenue/7-2-3', 'general/expense/2-5-1', 'general/expense/2-5-2', 'general/expense/2-5-3', 'general/expense/3-1-1'],
  );
  assert.equal(get('general/expense/2-5-3').items?.[0].name, '県議会議員補欠選挙費');
});

test('composeLatest keeps nested initial items, drops ambiguous matches and negative funding', () => {
  const init = file('initial', [
    // 当初の入れ子（内訳の親 = 位置 0）。補正は入れ子のない別の事項に当たる
    row('general/expense/7-1-1', 100, {
      items: [
        { name: '中小企業振興資金融資費', amount: v(60) },
        { name: '内訳', amount: v(60), parent: 0 },
        { name: '商工総務費', amount: v(40) },
      ],
    }),
    // 同じ名前の事項が当初に2つ
    row('general/revenue/9-2-6', 30, {
      items: [
        { name: '社会資本整備総合交付金', amount: v(10) },
        { name: '社会資本整備総合交付金', amount: v(20) },
      ],
    }),
    row('general/expense/8-2-1', 10, { funding: { national: v(5), bond: v(0), other: v(0), general: v(5) } }),
  ]);
  const s = file(
    'supplementary',
    [
      row('general/expense/7-1-1', 15, {
        items: [
          { name: '商工総務費', amount: v(5) },
          { name: '信用保証料補填費', amount: v(10) },
        ],
      }),
      row('general/revenue/9-2-6', 3, { items: [{ name: '社会資本整備総合交付金', amount: v(3) }] }),
      // 国の分を当初より多く減らして一般財源に振り替える（国の分が負になる）
      row('general/expense/8-2-1', 0, { funding: { national: v(-8), bond: v(0), other: v(0), general: v(8) } }),
    ],
    '6月補正（第1号）',
  );
  const out = composeLatest(init, [s]);
  const get = (id: string) => out.rows.find(x => x.id === id)!;
  assert.deepEqual(
    get('general/expense/7-1-1').items?.map(i => [i.name, i.amount.v, i.parent]),
    [
      ['中小企業振興資金融資費', 60, undefined],
      ['内訳', 60, 0],
      ['商工総務費', 45, undefined],
      ['信用保証料補填費', 10, undefined],
    ],
  );
  assert.equal(get('general/revenue/9-2-6').items, undefined);
  assert.equal(get('general/expense/8-2-1').funding, undefined);
  // 子のある当初の事項に補正が当たるときは出さない
  const s2 = file('supplementary', [row('general/expense/7-1-1', 5, { items: [{ name: '中小企業振興資金融資費', amount: v(5) }] })], '9月');
  assert.equal(composeLatest(init, [s2]).rows[0].items, undefined);
  // 補正の事項（いつも上の段）は、当初の入れ子の子と同じ名前でも子には足さず、新しい事項として加える
  const s3 = file('supplementary', [row('general/expense/7-1-1', 5, { items: [{ name: '内訳', amount: v(5) }] })], '9月');
  assert.deepEqual(
    composeLatest(init, [s3]).rows[0].items?.map(i => [i.name, i.amount.v, i.parent]),
    [
      ['中小企業振興資金融資費', 60, undefined],
      ['内訳', 60, 0],
      ['商工総務費', 40, undefined],
      ['内訳', 5, undefined],
    ],
  );
  // 補正で新しく設けた目にも、入れ子・負の値の確かめをする
  const s4 = file(
    'supplementary',
    [
      row('general/expense/2-5-9', 10, {
        funding: { national: v(-1), bond: v(0), other: v(0), general: v(11) },
        items: [{ name: 'a', amount: v(10) }, { name: 'b', amount: v(3), parent: 0 }],
        setsu: [{ no: 1, name: '報酬', amount: v(12) }, { no: 2, name: '給料', amount: v(-2) }],
      }),
    ],
    '9月',
  );
  const added = composeLatest(init, [s4]).rows.find(r => r.id === 'general/expense/2-5-9')!;
  assert.equal(added.funding, undefined);
  assert.equal(added.items, undefined);
  assert.equal(added.setsu, undefined);
});

test('composeLatest rejects mismatched files', () => {
  const init = file('initial', [row('general/expense/2-6-4', 1)]);
  assert.throws(() => composeLatest(init, [file('initial', [], '6月')]), /補正予算のファイルではありません/);
  assert.throws(() => composeLatest({ ...init, basis: 'settlement' }, []), /当初予算のファイルではありません/);
  assert.throws(() => composeLatest(init, [{ ...file('supplementary', [], '6月'), year: 2025 }]), /年度・自治体が違います/);
});

// 書き出した実データがあれば、補正後の合計が最後の回の議案の総額（9月補正（第4号）後 2,313,266,114 千円）と一致することを確かめる
// 実データがない（.gz を展開していない）・補正が4回そろっていないときは、黙って通さず skip と出す
const REAL_DIR = path.join(__dirname, '../public/data/local-gov/fukuoka-pref');
const realIndex = fs.existsSync(path.join(REAL_DIR, 'index.json'))
  ? JSON.parse(fs.readFileSync(path.join(REAL_DIR, 'index.json'), 'utf8'))
  : null;
const realSups: { file: string }[] =
  realIndex?.datasets.filter((d: { basis: string; year: number }) => d.basis === 'supplementary' && d.year === 2026) ?? [];
const realSkip = !realIndex ? '実データ（index.json）がない' : realSups.length < 4 ? 'R8 の補正のデータが4回そろっていない' : false;

test('composed real data matches the last bill total when files exist', { skip: realSkip }, () => {
  const dir = REAL_DIR;
  const sups = realSups;
  const init = JSON.parse(fs.readFileSync(path.join(dir, 'budget-2026-initial.json'), 'utf8'));
  const files = sups.map((d: { file: string }) => JSON.parse(fs.readFileSync(path.join(dir, d.file), 'utf8')));
  const out = composeLatest(init, files);
  const total = out.rows
    .filter(r => r.account === 'general' && r.side === 'expense')
    .reduce((s, r) => s + (r.amount.v ?? 0), 0);
  assert.equal(total, 2_313_266_114_000);
  // 補正後の図: 帯はすべて正（減額の事項を残すと負の帯になる）、箱の入り = 出、内訳を出す目は内訳の合計 = 目の額
  for (const view of ['general', 'all'] as const) {
    const g = buildLocalGraph(out, { view });
    assert.deepEqual(g.edges.filter(e => e.value <= 0), [], `${view} に正でない帯`);
    const into = new Map<string, number>();
    const outs = new Map<string, number>();
    for (const e of g.edges) {
      into.set(e.target, (into.get(e.target) ?? 0) + e.value);
      outs.set(e.source, (outs.get(e.source) ?? 0) + e.value);
    }
    for (const n of g.nodes) if (into.has(n.id) && outs.has(n.id)) assert.equal(outs.get(n.id), into.get(n.id), `${view} ${n.id}`);
  }
  // 財源内訳は、補正後で負の区分が出ると外す（図では「財源の記載なし」から流れる）。実データでは起きないことを確かめる
  // （起きたら、財源の振り替えの描き方を決める）
  const init0 = new Map<string, LocalBudgetFile['rows'][number]>(init.rows.map((r: LocalBudgetFile['rows'][number]) => [r.id, r]));
  for (const r of out.rows.filter(x => x.side === 'expense' && x.account === 'general')) {
    if (init0.get(r.id)?.funding || r.added_in) assert.ok(r.funding, `${r.id} 財源内訳が外れた`);
  }
  for (const r of out.rows.filter(x => x.supplements)) {
    const sum = (xs: { amount: Value; parent?: number }[]) => xs.filter(x => x.parent === undefined).reduce((s, x) => s + (x.amount.v ?? 0), 0);
    if (r.setsu) assert.equal(sum(r.setsu), r.amount.v, `${r.id} 節`);
    if (r.items && !r.items.some(i => i.no_amount_printed)) assert.equal(sum(r.items), r.amount.v, `${r.id} 事項`);
    if (r.funding) assert.equal(sum(Object.values(r.funding).map(amount => ({ amount }))), r.amount.v, `${r.id} 財源`);
  }
});
