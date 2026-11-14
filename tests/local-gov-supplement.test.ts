import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { composeLatest } from '../app/lib/local-gov/supplement';
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

test('composeLatest rejects mismatched files', () => {
  const init = file('initial', [row('general/expense/2-6-4', 1)]);
  assert.throws(() => composeLatest(init, [file('initial', [], '6月')]), /補正予算のファイルではありません/);
  assert.throws(() => composeLatest({ ...init, basis: 'settlement' }, []), /当初予算のファイルではありません/);
  assert.throws(() => composeLatest(init, [{ ...file('supplementary', [], '6月'), year: 2025 }]), /年度・自治体が違います/);
});

// 書き出した実データがあれば、補正後の合計が最後の回の議案の総額（9月補正（第4号）後 2,313,266,114 千円）と一致することを確かめる
test('composed real data matches the last bill total when files exist', () => {
  const dir = path.join(__dirname, '../public/data/local-gov/fukuoka-pref');
  const idxPath = path.join(dir, 'index.json');
  if (!fs.existsSync(idxPath)) return;
  const index = JSON.parse(fs.readFileSync(idxPath, 'utf8'));
  const sups = index.datasets.filter((d: { basis: string; year: number }) => d.basis === 'supplementary' && d.year === 2026);
  if (sups.length < 4) return;
  const init = JSON.parse(fs.readFileSync(path.join(dir, 'budget-2026-initial.json'), 'utf8'));
  const files = sups.map((d: { file: string }) => JSON.parse(fs.readFileSync(path.join(dir, d.file), 'utf8')));
  const out = composeLatest(init, files);
  const total = out.rows.filter(r => r.side === 'expense').reduce((s, r) => s + (r.amount.v ?? 0), 0);
  assert.equal(total, 2_313_266_114_000);
});
