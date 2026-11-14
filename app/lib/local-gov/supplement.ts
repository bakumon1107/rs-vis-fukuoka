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
import type { Funding, Item, LocalBudgetFile, LocalGovIndex, MokuRow, Setsu, Value } from '@/types/local-gov';

const add = (a: Value, b: Value | undefined): Value =>
  b === undefined ? a : { ...a, v: a.v === null || b.v === null ? null : a.v + b.v };

const FUNDING_KEYS: (keyof Funding)[] = ['national', 'bond', 'other', 'general'];

/**
 * 片方にしか内訳（事項・節）がないとき: もう片方の額が 0 ならそのまま使い、0 でなければ内訳を出さない
 * （当初に事項のない歳入の目に補正の事項だけを付けると、補正の分だけの内訳が目の内訳に見える。合計の合わない内訳は見せない）。
 * 戻り値 null は「両方にあるので足し合わせる」
 */
function oneSided<T>(base: T[] | undefined, sup: T[] | undefined, baseAmount: Value, supAmount: Value): T[] | undefined | null {
  const hasBase = !!base && base.length > 0;
  const hasSup = !!sup && sup.length > 0;
  if (hasBase && hasSup) return null;
  if (hasBase) return supAmount.v === 0 ? base : undefined;
  if (hasSup) return baseAmount.v === 0 ? sup : undefined;
  return undefined;
}

const hasNegative = (xs: { amount: Value }[]) => xs.some(x => (x.amount.v ?? 0) < 0);
const anyNegativeSetsu = (xs: Setsu[]) => hasNegative(xs) || xs.some(s => !!s.sub && hasNegative(s.sub));
/**
 * 補正の事項をそのまま使うとき（当初に事項がない目・補正で新しく設けた目）の確かめ。配列をそのまま使うので入れ子の parent は
 * 正しい位置を指す（親が前・1段まで）。負の事項・指し先のおかしい入れ子があれば出さない
 */
const supOnlyItems = (xs: Item[]) =>
  hasNegative(xs) ||
  xs.some(
    (it, i) =>
      it.parent !== undefined &&
      !(Number.isInteger(it.parent) && it.parent >= 0 && it.parent < i && xs[it.parent].parent === undefined),
  )
    ? undefined
    : xs;
/** 負の区分のある財源内訳は出さない（財源の振り替えで当初より多く減らした など。負の帯は描けない） */
const noNegativeFunding = (f: Funding | undefined) => (f && FUNDING_KEYS.some(k => (f[k].v ?? 0) < 0) ? undefined : f);

/**
 * 事項を足す（同じ名前の事項に足し、なければ added_in を付けて末尾に加える）。次のときは事項を出さない（合計の合わない・
 * どれに足すか決まらない内訳を見せない）:
 * - 片方にしか事項がない（oneSided）
 * - 補正の事項に入れ子がある（parent は補正の配列の位置なので、当初の後ろに付けると親を指し違える）
 * - 子のある当初の事項に補正が当たる（親だけ足すと子の合計が親と合わない）
 * - 同じ名前が当初の上の段に2つ以上ある、または当初に1つあって補正に2つ以上ある（どれに足すか決まらない）
 * - 足した結果が負の事項がある（帯を描けない）
 * - 補正の事項が、当初の上の段にはなく入れ子の子（「内訳」「その他」など）と同じ名前（どの親の分か決まらない。
 *   上の段に加えると、意味の取れない「その他」が1つ並ぶ）
 * 当初の入れ子はそのまま使える（補正の事項は末尾に加えるので、当初の事項の位置は変わらない。R8 の商業総務費）
 */
function mergeItems(base: Item[] | undefined, sup: Item[] | undefined, round: string, baseAmount: Value, supAmount: Value): Item[] | undefined {
  const only = oneSided(base, sup, baseAmount, supAmount);
  if (only !== null) {
    if (only === sup && only !== undefined) {
      const ok = supOnlyItems(only);
      return ok && ok.map(it => ({ ...it, added_in: round }));
    }
    return only;
  }
  if (sup!.some(it => it.parent !== undefined)) return undefined;
  const out = base!.map(it => ({ ...it }));
  const n = base!.length;
  const top = (it: Item) => it.parent === undefined;
  const count = (xs: Item[], name: string) => xs.filter(it => top(it) && it.name === name).length;
  for (const s of sup!) {
    // 突き合わせるのは当初（それまでの回を足したもの）の上の段の事項だけ。同じ回の中の同じ名前の新しい事項（R8 9月第3号の
    // 「社会資本整備総合交付金」は節ごとに3つ）は、それぞれ別の事項として加える
    const idx = out.findIndex((it, i) => i < n && top(it) && it.name === s.name);
    if (idx < 0) {
      if (base!.some(it => !top(it) && it.name === s.name)) return undefined;
      out.push({ ...s, added_in: round });
      continue;
    }
    if (count(base!, s.name) > 1 || count(sup!, s.name) > 1) return undefined;
    // 子のある事項に当たると、親と子の合計が合わなくなる
    if (base!.some(it => it.parent === idx)) return undefined;
    out[idx].amount = add(out[idx].amount, s.amount);
  }
  return hasNegative(out) ? undefined : out;
}

/** 節を足す（同じ番号の節に足し、なければ加える）。片方にしか節がないときは oneSided。負の節・細節が残れば節を出さない */
function mergeSetsu(base: Setsu[] | undefined, sup: Setsu[] | undefined, round: string, baseAmount: Value, supAmount: Value): Setsu[] | undefined {
  const only = oneSided(base, sup, baseAmount, supAmount);
  if (only !== null) {
    if (only === sup && only !== undefined) return anyNegativeSetsu(only) ? undefined : only.map(s => ({ ...s, added_in: round }));
    return only;
  }
  const out: Setsu[] = base!.map(s => ({ ...s, sub: s.sub?.map(x => ({ ...x })) }));
  for (const s of sup!) {
    const hit = s.no !== null ? out.find(x => x.no === s.no) : out.find(x => x.name === s.name);
    if (!hit) {
      out.push({ ...s, added_in: round });
      continue;
    }
    hit.amount = add(hit.amount, s.amount);
    // 細節は、当初と補正の両方にあるときだけ足す。片方だけにあると細節の合計が節の額にならない（当初の節 33,000 に
    // 細節がなく、補正の細節「その他需用費 112」だけを付けると 33,112 の節の細節が 112 になる）ので、細節を出さない
    // 空の配列も「細節なし」と同じに扱う（当初 sub=[]・補正に細節がある、で細節が補正の分だけになるのを防ぐ）
    if (hit.sub?.length && s.sub?.length) {
      for (const sb of s.sub) {
        const h2 = hit.sub.find(x => x.name === sb.name);
        if (h2) h2.amount = add(h2.amount, sb.amount);
        else hit.sub.push({ ...sb });
      }
    } else if (hit.sub?.length || s.sub?.length) {
      hit.sub = undefined;
    }
  }
  return anyNegativeSetsu(out) ? undefined : out.sort((a, b) => (a.no ?? 99) - (b.no ?? 99));
}

/**
 * 補正後（latest）に使う、当初と同じ年度の補正のファイルの一覧（古い順）。回の順はファイル名の末尾の番号
 * （budget-<年度>-supplementary-<回>.json）で決める（index.json の並び順には頼らない）
 */
export function supplementDatasets(index: LocalGovIndex, year: number): LocalGovIndex['datasets'] {
  const no = (d: LocalGovIndex['datasets'][number]) => Number(/-(\d+)\.json$/.exec(d.file)?.[1] ?? 0);
  return index.datasets.filter(d => d.basis === 'supplementary' && d.year === year).sort((a, b) => no(a) - no(b));
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
        // 補正で新しく設けた目: 当初の額は 0。内訳には足し合わせる目と同じ確かめ（入れ子・負の値）をする
        const zero: Value = { v: 0, src: sr.amount.src };
        rows.set(sr.id, {
          ...sr,
          before: zero,
          after: undefined,
          added_in: round,
          funding: noNegativeFunding(sr.funding),
          items: sr.items && supOnlyItems(sr.items),
          setsu: sr.setsu && anyNegativeSetsu(sr.setsu) ? undefined : sr.setsu,
          supplements: [{ round, amount: sr.amount }],
        });
        // 図は行の順（款・項・目の順）に箱を並べるので、末尾ではなく同じ会計・款・項の最後の目の後ろに入れる。
        // findLastIndex（ES2023）は使わない: Next.js は .at() には polyfill を入れるが findLastIndex には入れないので、
        // 対象のブラウザ（Safari 15.4 より前など）で補正後の画面が落ちる
        const kou = `${sr.account}/${sr.side}/${sr.kan.no}-${sr.kou.no}-`;
        let at = -1;
        for (let i = order.length - 1; i >= 0; i--) {
          if (order[i].startsWith(kou)) {
            at = i;
            break;
          }
        }
        if (at >= 0) order.splice(at + 1, 0, sr.id);
        else order.push(sr.id);
        continue;
      }
      // 財源は両方にあれば足す。片方だけなら、もう片方の額が 0 のときだけ使う（でなければ補正後の額と合わないので出さない）。
      // 足した結果に負の区分が出たら（財源の振り替えで当初より多く減らした など）出さない（負の帯は描けない）
      const merged =
        base.funding && sr.funding
          ? (Object.fromEntries(FUNDING_KEYS.map(k => [k, add(base.funding![k], sr.funding![k])])) as unknown as Funding)
          : base.funding
            ? sr.amount.v === 0
              ? base.funding
              : undefined
            : sr.funding && base.amount.v === 0
              ? sr.funding
              : undefined;
      const funding = noNegativeFunding(merged);
      rows.set(sr.id, {
        ...base,
        amount: add(base.amount, sr.amount),
        funding,
        items: mergeItems(base.items, sr.items, round, base.amount, sr.amount),
        setsu: mergeSetsu(base.setsu, sr.setsu, round, base.amount, sr.amount),
        notes: sr.notes ? [...new Set([...(base.notes ?? []), ...sr.notes])] : base.notes,
        pages: [...base.pages, ...sr.pages],
        supplements: [...(base.supplements ?? []), { round, amount: sr.amount }],
      });
    }
  }
  const last = supplements[supplements.length - 1];
  return {
    ...initial,
    // 一般財源の中身（general_fund）は当初の一般財源の内訳。補正で一般財源の額が変わり、合計が合わなくなる（validate.ts の
    // total = 一般財源の合計 が成り立たない）ので外す。財源内訳と歳入の款の違いの説明文は補正後でも当てはまるので composed に残す
    general_fund: undefined,
    rows: order.map(id => rows.get(id)!),
    composed: {
      through: last ? last.supplementary!.round : '当初予算',
      rounds: supplements.map(s => ({ round: s.supplementary!.round, kind: s.supplementary!.kind })),
      ...(initial.general_fund?.notes?.length ? { funding_notes: initial.general_fund.notes } : {}),
    },
  };
}
