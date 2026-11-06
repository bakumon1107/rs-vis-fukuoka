import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { expectedRowId, totalsByAccount, validateAgainstIndex, validateBudgetFile } from '../app/lib/local-gov/validate';
import type { LocalBudgetFile, LocalGovIndex, MokuRow, Value } from '../types/local-gov';

const v = (n: number | null, src: Value['src'] = 'ocr'): Value => ({ v: n, src });

function row(over: Partial<MokuRow> = {}): MokuRow {
  const base: MokuRow = {
    id: 'general/expense/2-1-1',
    account: 'general',
    side: 'expense',
    kan: { no: 2, name: '総務費' },
    kou: { no: 1, name: '総務管理費' },
    moku: { no: 1, name: '一般管理費' },
    amount: v(17_854_435_000),
    previous: v(17_000_000_000),
    funding: { national: v(0), bond: v(0), other: v(7_450_403_000), general: v(10_404_032_000) },
    items: [
      { name: '職員費', amount: v(2_459_659_000), headcount: 293 },
      { name: '管理事務費', amount: v(15_394_776_000) },
    ],
    setsu: [
      { no: 1, name: '報酬', amount: v(2_444_000) },
      { no: 2, name: '給料', amount: v(17_851_991_000) },
    ],
    pages: [{ source: 'r8-setsumeisho-ippan', page: 131 }],
  };
  return { ...base, ...over };
}

function file(rows: MokuRow[], over: Partial<LocalBudgetFile> = {}): LocalBudgetFile {
  return {
    schema_version: 1,
    gov_id: 'fukuoka-pref',
    year: 2026,
    year_label: '令和8年度',
    basis: 'initial',
    unit_source: '千円',
    accounts: [{ id: 'general', kind: 'general', name: '一般会計' }],
    rows,
    checks: { rows: rows.length, all_ok: rows.length, rules: {} },
    ...over,
  };
}

test('正しいデータは誤りなし', () => {
  const r = validateBudgetFile(file([row()]));
  assert.deepEqual(r.errors, []);
  assert.equal(r.inferredCount, 0);
});

test('ID は会計/歳入歳出/款-項-目', () => {
  assert.equal(expectedRowId(row()), 'general/expense/2-1-1');
  const r = validateBudgetFile(file([row({ id: 'general/expense/2-1-9' })]));
  assert.ok(r.errors.some(e => e.includes('ID が款・項・目の番号と合わない')));
});

test('ID の重複・知らない会計を検出する', () => {
  const r = validateBudgetFile(file([row(), row()]));
  assert.ok(r.errors.some(e => e.includes('目の ID が重複')));
  const r2 = validateBudgetFile(file([row({ account: 'special:x', id: 'special:x/expense/2-1-1' })]));
  assert.ok(r2.errors.some(e => e.includes('accounts にない')));
});

test('財源内訳・説明欄・節の合計のずれを検出する（打ち消し合いは検出できないので OCR 側の突き合わせで防ぐ）', () => {
  const bad = row({ funding: { national: v(0), bond: v(0), other: v(452_000), general: v(17_854_000_000) } });
  assert.ok(validateBudgetFile(file([bad])).errors.some(e => e.includes('財源内訳の合計')));
  const bad2 = row({ items: [{ name: '職員費', amount: v(1) }] });
  assert.ok(validateBudgetFile(file([bad2])).errors.some(e => e.includes('説明欄の事項の合計')));
  const bad3 = row({ setsu: [{ no: 1, name: '報酬', amount: v(1) }] });
  assert.ok(validateBudgetFile(file([bad3])).errors.some(e => e.includes('節の合計')));
});

test('入れ子の内訳（parent つき）は事項の合計に含めない', () => {
  const r = row({
    items: [
      { name: '中小企業振興資金融資費', amount: v(17_854_435_000) },
      { name: '内訳A', amount: v(10_000_000_000), parent: 0 },
      { name: '内訳B', amount: v(7_854_435_000), parent: 0 },
    ],
  });
  assert.deepEqual(validateBudgetFile(file([r])).errors, []);
});

test('入れ子は1段まで・親は子より前。細節の合計は節の額と一致する', () => {
  const items = (parents: (number | undefined)[]) =>
    parents.map((parent, i) => ({ name: `事項${i}`, amount: v(i === 0 ? 17_854_435_000 : 1), ...(parent !== undefined ? { parent } : {}) }));
  // 孫（内訳の内訳）と、後ろの親を指す内訳は不正
  assert.ok(validateBudgetFile(file([row({ items: items([undefined, 0, 1]) })])).errors.some(e => e.includes('parent が不正')));
  const fwd = [{ name: '内訳', amount: v(1), parent: 1 }, { name: '親', amount: v(17_854_435_000) }];
  assert.ok(validateBudgetFile(file([row({ items: fwd })])).errors.some(e => e.includes('parent が不正')));
  // 細節の合計が節の額と合わない（細節の欠け・付け違い）
  const setsu = [
    { no: 1, name: '報酬', amount: v(2_444_000), sub: [{ name: '委員報酬', amount: v(2_000_000) }] },
    { no: 2, name: '給料', amount: v(17_851_991_000) },
  ];
  assert.ok(validateBudgetFile(file([row({ setsu })])).errors.some(e => e.includes('細節の合計')));
  setsu[0].sub = [{ name: '委員報酬', amount: v(2_444_000) }];
  assert.deepEqual(validateBudgetFile(file([row({ setsu })])).errors, []);
});

test('金額が不明・整数でない・出典が不正を検出し、推定の数を数える', () => {
  assert.ok(validateBudgetFile(file([row({ amount: v(null) })])).errors.some(e => e.includes('金額が不明')));
  assert.ok(validateBudgetFile(file([row({ previous: v(1.5) })])).errors.some(e => e.includes('整数でない')));
  assert.ok(validateBudgetFile(file([row({ previous: { v: 1, src: 'guess' as never } })])).errors.some(e => e.includes('出典が不正')));
  assert.equal(validateBudgetFile(file([row({ previous: v(1, 'inferred') })])).inferredCount, 1);
});

test('読み取りの一致の数・名前の出典・名前の有無を確かめる', () => {
  assert.ok(validateBudgetFile(file([row({ previous: { v: 1, src: 'ocr', agree: -1 } })])).errors.some(e => e.includes('一致の数が不正')));
  assert.ok(validateBudgetFile(file([row({ previous: { v: 1, src: 'ocr', agree: 1.5 } })])).errors.some(e => e.includes('一致の数が不正')));
  assert.ok(validateBudgetFile(file([row({ moku: { no: 1, name: '一般管理費', name_src: 'guess' as never } })])).errors.some(e => e.includes('名前の出典が不正')));
  assert.ok(validateBudgetFile(file([row({ moku: { no: 1, name: '' } })])).errors.some(e => e.includes('名前がない')));
  assert.deepEqual(validateBudgetFile(file([row({ moku: { no: 1, name: '一般管理費', name_src: 'reference' } })])).errors, []);
});

test('全文検索で確かめた名前には見つかった資料がいる。事項・節・細節の名前の出典と節番号の出典も確かめる', () => {
  const searched = { no: 1, name: '一般管理費', name_src: 'search' as const };
  assert.ok(validateBudgetFile(file([row({ moku: searched })])).errors.some(e => e.includes('name_evidence')));
  assert.deepEqual(validateBudgetFile(file([row({ moku: { ...searched, name_evidence: ['r6-kessan-gaiyou'] } })])).errors, []);
  const items = [{ name: '職員費', name_src: 'guess' as never, amount: v(17_854_435_000) }];
  assert.ok(validateBudgetFile(file([row({ items })])).errors.some(e => e.includes('items[0]: 名前の出典が不正')));
  const setsu = [
    { no: 1, no_src: 'order' as never, name: '報酬', amount: v(2_444_000) },
    { no: null, no_src: 'ocr' as const, name: '給料', amount: v(17_851_991_000),
      sub: [{ name: '給料', name_src: 'readings' as const, amount: v(17_851_991_000) }] },
  ];
  const errs = validateBudgetFile(file([row({ setsu })])).errors;
  assert.ok(errs.some(e => e.includes('setsu[0]: 節番号の出典が不正')));
  assert.ok(errs.some(e => e.includes('setsu[1]: 番号がないのに番号の出典がある')));
  assert.equal(errs.filter(e => e.includes('sub')).length, 0);
});

test('補正: 補正前 + 補正額 = 計', () => {
  const sup = { supplementary: { round: 'R8-06', kind: '定例' as const } };
  const ok = row({ amount: v(2_545_648_000), before: v(8_819_677_000), after: v(11_365_325_000), funding: undefined, items: undefined, setsu: undefined, previous: undefined });
  assert.deepEqual(validateBudgetFile(file([ok], { basis: 'supplementary', ...sup })).errors, []);
  const bad = { ...ok, after: v(11_365_325_001) };
  assert.ok(validateBudgetFile(file([bad], { basis: 'supplementary', ...sup })).errors.some(e => e.includes('補正前')));
  assert.ok(validateBudgetFile(file([ok], { basis: 'supplementary' })).errors.some(e => e.includes('supplementary（回・種別）がない')));
});

test('決算: 支出済 + 繰越 + 不用 = 予算現額', () => {
  const s = row({ amount: v(2_929_992_078, 'text'), budget_current: v(3_034_708_000, 'text'), carried_over: v(0, 'text'), unused: v(104_715_922, 'text'), funding: undefined, items: undefined, setsu: undefined, previous: undefined });
  assert.deepEqual(validateBudgetFile(file([s], { basis: 'settlement' })).errors, []);
  assert.ok(validateBudgetFile(file([{ ...s, unused: v(1, 'text') }], { basis: 'settlement' })).errors.some(e => e.includes('予算現額')));
});

test('検算の要約の行数が実際の行数と合う', () => {
  const f = file([row()]);
  f.checks.rows = 2;
  assert.ok(validateBudgetFile(f).errors.some(e => e.includes('checks.rows')));
});

test('会計・歳入歳出ごとの合計', () => {
  const t = totalsByAccount(file([row()]));
  assert.equal(t.get('general/expense'), 17_854_435_000);
});

// 書き出した実データ（public/data/local-gov/<自治体>/budget-*.json・settlement-*.json）をすべて検証する。まだなければ飛ばす
const DATA_DIR = path.join(process.cwd(), 'public', 'data', 'local-gov');
const dataFiles = fs.existsSync(DATA_DIR)
  ? fs.readdirSync(DATA_DIR).flatMap(gov => {
      const dir = path.join(DATA_DIR, gov);
      return fs.statSync(dir).isDirectory()
        ? fs.readdirSync(dir).filter(f => /^(budget|settlement)-.*\.json$/.test(f)).map(f => path.join(dir, f))
        : [];
    })
  : [];

test('書き出した正規化データがすべて検証を通る', { skip: dataFiles.length === 0 ? '書き出したデータがまだない' : false }, () => {
  for (const p of dataFiles) {
    const f = JSON.parse(fs.readFileSync(p, 'utf-8')) as LocalBudgetFile;
    const r = validateBudgetFile(f);
    assert.deepEqual(r.errors, [], `${path.relative(process.cwd(), p)}`);
    // 同じ自治体の index.json（資料の一覧）と突き合わせる: 出典のページ・名前の資料の id が資料の一覧にあること
    const index = JSON.parse(fs.readFileSync(path.join(path.dirname(p), 'index.json'), 'utf-8')) as LocalGovIndex;
    assert.deepEqual(validateAgainstIndex(f, index), [], `${path.relative(process.cwd(), p)} と index.json`);
  }
});

test('index との突き合わせ: 資料の一覧にない出典・名前の資料を見つける', () => {
  const index: LocalGovIndex = {
    schema_version: 1, gov: { id: 'fukuoka-pref', name: '福岡県', kind: 'prefecture' },
    datasets: [{ year: 2026, label: '令和8年度', basis: 'initial', file: 'budget-2026-initial.json', status: 'verified' }],
    sources: [{ id: 'r8-setsumeisho-ippan', title: '説明書', url: 'https://example.invalid/a.pdf', sha256: 'x', retrieved: '2026-11-06' }],
  };
  assert.deepEqual(validateAgainstIndex(file([row()]), index), []);
  const bad = row({ moku: { no: 1, name: '一般管理費', name_src: 'search', name_evidence: ['r6-unknown'] },
    pages: [{ source: 'r8-other', page: 1 }] });
  const errs = validateAgainstIndex(file([bad]), index);
  assert.ok(errs.some(e => e.includes('出典 r8-other')));
  assert.ok(errs.some(e => e.includes('名前の資料 r6-unknown')));
  assert.ok(validateAgainstIndex(file([row()], { gov_id: 'other' }), index).some(e => e.includes('gov_id')));
});
