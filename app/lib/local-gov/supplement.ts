/**
 * 補正後（当初 + Σ補正）の組み立て（純粋関数。補正予算の取り込み設計 3章・R8 補正予算の抽出の設計 8章）。
 *
 * 補正のファイルは差分（補正のある目だけ。amount = 補正額）。当初のファイルに回の順に足して、補正後のファイルを作る。
 * - 目: 同じ ID の目の金額・財源内訳を足す。当初にない目は「補正で新しく設けた目」（added_in）として加える
 * - 説明欄の事項: 同じ名前の事項に足す。なければ「補正で加わった事項」（added_in）として加える
 * - 節: 同じ番号の節に足す（細節は同じ名前に足す）。なければ加える
 * - 行の before に当初の額、supplements に回ごとの補正額を残す（詳細パネルで「当初 → 補正後」を見せる）
 * 値の出典（src）は当初の値のものを残す（足した額は議案・総括との照合と回の鎖で確かめてある）。
 */
import type { Funding, Item, LocalBudgetFile, MokuRow, Setsu, Value } from '@/types/local-gov';

const add = (a: Value, b: Value | undefined): Value =>
  b === undefined ? a : { ...a, v: a.v === null || b.v === null ? null : a.v + b.v };

const FUNDING_KEYS: (keyof Funding)[] = ['national', 'bond', 'other', 'general'];

function mergeItems(base: Item[] | undefined, sup: Item[] | undefined, round: string): Item[] | undefined {
  if (!sup || sup.length === 0) return base;
  const out = (base ?? []).map(it => ({ ...it }));
  for (const s of sup) {
    const hit = out.find(it => it.name === s.name && it.parent === undefined);
    if (hit) hit.amount = add(hit.amount, s.amount);
    else out.push({ ...s, added_in: round });
  }
  return out;
}

function mergeSetsu(base: Setsu[] | undefined, sup: Setsu[] | undefined, round: string): Setsu[] | undefined {
  if (!sup || sup.length === 0) return base;
  const out = (base ?? []).map(s => ({ ...s, sub: s.sub?.map(x => ({ ...x })) }));
  for (const s of sup) {
    const hit = s.no !== null ? out.find(x => x.no === s.no) : out.find(x => x.name === s.name);
    if (!hit) {
      out.push({ ...s, added_in: round });
      continue;
    }
    hit.amount = add(hit.amount, s.amount);
    for (const sb of s.sub ?? []) {
      const h2 = hit.sub?.find(x => x.name === sb.name);
      if (h2) h2.amount = add(h2.amount, sb.amount);
      else hit.sub = [...(hit.sub ?? []), { ...sb }];
    }
  }
  return out.sort((a, b) => (a.no ?? 99) - (b.no ?? 99));
}

/**
 * 当初のファイルに補正のファイル（古い順）を足して、補正後のファイルを作る。
 * 年度が違う・補正でないファイルは受け付けない（取り違えて足さない）。
 */
export function composeLatest(initial: LocalBudgetFile, supplements: LocalBudgetFile[]): LocalBudgetFile {
  if (initial.basis !== 'initial') throw new Error('当初予算のファイルではありません');
  for (const s of supplements) {
    if (s.basis !== 'supplementary' || !s.supplementary) throw new Error('補正予算のファイルではありません');
    if (s.year !== initial.year || s.gov_id !== initial.gov_id) throw new Error('当初と補正の年度・自治体が違います');
  }
  const rows = new Map<string, MokuRow>(initial.rows.map(r => [r.id, { ...r, before: r.amount }]));
  const order = initial.rows.map(r => r.id);
  for (const s of supplements) {
    const round = s.supplementary!.round;
    for (const sr of s.rows) {
      const base = rows.get(sr.id);
      if (!base) {
        // 補正で新しく設けた目: 当初の額は 0
        rows.set(sr.id, {
          ...sr,
          before: { v: 0, src: sr.amount.src },
          after: undefined,
          added_in: round,
          supplements: [{ round, amount: sr.amount }],
        });
        order.push(sr.id);
        continue;
      }
      const funding =
        base.funding && sr.funding
          ? (Object.fromEntries(FUNDING_KEYS.map(k => [k, add(base.funding![k], sr.funding![k])])) as unknown as Funding)
          : base.funding ?? sr.funding;
      rows.set(sr.id, {
        ...base,
        amount: add(base.amount, sr.amount),
        funding,
        items: mergeItems(base.items, sr.items, round),
        setsu: mergeSetsu(base.setsu, sr.setsu, round),
        notes: sr.notes ? [...new Set([...(base.notes ?? []), ...sr.notes])] : base.notes,
        pages: [...base.pages, ...sr.pages],
        supplements: [...(base.supplements ?? []), { round, amount: sr.amount }],
      });
    }
  }
  const last = supplements[supplements.length - 1];
  return {
    ...initial,
    rows: order.map(id => rows.get(id)!),
    composed: {
      through: last ? last.supplementary!.round : '当初予算',
      rounds: supplements.map(s => ({ round: s.supplementary!.round, kind: s.supplementary!.kind })),
    },
  };
}
