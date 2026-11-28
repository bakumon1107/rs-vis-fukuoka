/**
 * かんたんの図の3列（一般会計・当初予算）: 歳入の款 → 財源 → 歳出の款。純粋関数（HTTP・React なし）。
 * 設計: docs/local-gov/tasks/20261128_1408_かんたんの図に歳入から財源への振り分けを足す設計.md
 *
 * - 歳入の款 → 財源 の帯は、書き出しが作った general_fund.flows（財源ごとの合計 = 歳出の財源内訳の合計を確かめたもの）
 * - 財源 → 歳出の款 の帯は、今の一般会計の見方のグラフと同じ（呼ぶ側が fullGraph で渡す）
 * - 帯の色を財源で塗るため、帯・箱ごとの財源（funding）と、概算の帯（estimated）も返す
 */
import type { LocalBudgetFile, LocalGraph } from '@/types/local-gov';
import { edgeKey, FUNDING_KINDS, isOcrName, type FundingKey } from './graph';

export interface FundingFlowGraph {
  graph: LocalGraph;
  /** 帯のキー・財源の箱の ID → 財源（色を決める） */
  funding: Map<string, FundingKey>;
  /** 概算の帯（縁を点線にする）のキー */
  estimated: Set<string>;
  /** 「その他の収入」にまとめた歳入の款の名前（額の大きい順。まとめなければ空） */
  groupedNames: string[];
  /** 概算の帯の元の款ごとの額（凡例に並べる。まとめた帯は確かな額も含むので、元の款の単位で出す） */
  estimatedParts: { name: string; value: number }[];
}

/** まとめた歳入の款の箱（「その他の収入」）の ID */
export const OTHER_REVENUE_ID = 'revenue:__others';

const FUNDING_KEYS = new Set<string>(FUNDING_KINDS.map(f => f.key));

/**
 * 3列のグラフ。作れないとき（一般会計の見方でない・当初予算でない・general_fund.flows がない・財源の記載のない目がある）は null
 * （呼ぶ側は今の2列にする）。
 * groupBelow: 歳入の款のうち、額が歳入の合計のこの割合より小さいものを「その他の収入」にまとめる（スマートフォンの幅。0 ならまとめない）
 */
export function simpleFundingFlow(file: LocalBudgetFile, base: LocalGraph, groupBelow = 0): FundingFlowGraph | null {
  const flows = file.general_fund?.flows;
  if (file.basis !== 'initial' || file.composed || !flows?.length) return null;
  // base: 一般会計の見方の左2列（財源 → 款）の全体のグラフ（graph-view の fullGraph(file, 'general', 2)）
  if (!base.columns.some(c => c.key === 'funding')) return null;
  // 財源の記載のない目（funding:none）があると、歳入から入る帯と合わないので作らない
  if (base.nodes.some(n => n.col === 'funding' && !FUNDING_KEYS.has(n.id.slice('funding:'.length)))) return null;

  const kanTotal = new Map<number, number>();
  for (const f of flows) kanTotal.set(f.kan, (kanTotal.get(f.kan) ?? 0) + f.amount);
  const grand = [...kanTotal.values()].reduce((s, v) => s + v, 0);
  const grouped = (kan: number) => groupBelow > 0 && (kanTotal.get(kan) ?? 0) < grand * groupBelow;

  // 名前が読み取りだけの歳入の款（図の ※。全会計の見方の歳入の款と同じく、款のどれかの目が読み取りなら印を付ける）
  const ocrKan = new Set(
    file.rows.filter(r => r.account === 'general' && r.side === 'revenue' && isOcrName(r.kan.name_src)).map(r => r.kan.no)
  );
  const funding = new Map<string, FundingKey>();
  const estimated = new Set<string>();
  const groupedNames: string[] = [];
  const edgeValue = new Map<string, { source: string; target: string; value: number }>();
  const revNodes = new Map<string, LocalGraph['nodes'][number]>();
  // 歳入の款の並び: 一番多く流れる財源の順（財源の箱の並び）→ 額の大きい順。帯の交差を減らす（「その他の収入」は最後）
  const fundingOrder = new Map(base.nodes.filter(n => n.col === 'funding').map((n, i) => [n.id.slice('funding:'.length), i]));
  const mainFunding = new Map<number, number>();
  for (const k of kanTotal.keys()) {
    const top = flows.filter(f => f.kan === k).sort((a, b) => b.amount - a.amount)[0];
    mainFunding.set(k, fundingOrder.get(top.funding) ?? fundingOrder.size);
  }
  const order = [...kanTotal.keys()].sort(
    (a, b) => (mainFunding.get(a) ?? 0) - (mainFunding.get(b) ?? 0) || (kanTotal.get(b) ?? 0) - (kanTotal.get(a) ?? 0)
  );
  const rank = new Map(order.map((k, i) => [k, i]));
  const sorted = [...flows].sort(
    (a, b) => Number(grouped(a.kan)) - Number(grouped(b.kan)) || (rank.get(a.kan) ?? 0) - (rank.get(b.kan) ?? 0)
  );
  for (const f of sorted) {
    const id = grouped(f.kan) ? OTHER_REVENUE_ID : `revenue:${f.kan_name}`;
    if (id === OTHER_REVENUE_ID && !groupedNames.includes(f.kan_name)) groupedNames.push(f.kan_name);
    const node = revNodes.get(id);
    if (node) node.value += f.amount;
    else {
      const flags = id === OTHER_REVENUE_ID ? ['aggregate'] : ocrKan.has(f.kan) ? ['name-ocr'] : undefined;
      revNodes.set(id, {
        id,
        col: 'revenue',
        name: id === OTHER_REVENUE_ID ? 'その他の収入' : f.kan_name,
        value: f.amount,
        ...(flags ? { flags } : {}),
      });
    }
    const target = `funding:${f.funding}`;
    const k = edgeKey(id, target);
    const e = edgeValue.get(k);
    if (e) e.value += f.amount;
    else edgeValue.set(k, { source: id, target, value: f.amount });
    funding.set(k, f.funding);
    // まとめた帯は、概算の分を含めば概算にする（確かな額に見せない）
    if (f.estimated) estimated.add(k);
  }

  const fundingNodes = base.nodes.filter(n => n.col === 'funding');
  const kanNodes = base.nodes.filter(n => n.col === 'kan');
  for (const n of fundingNodes) funding.set(n.id, n.id.slice('funding:'.length) as FundingKey);
  const right = base.edges.filter(e => e.source.startsWith('funding:'));
  for (const e of right) funding.set(edgeKey(e.source, e.target), e.source.slice('funding:'.length) as FundingKey);

  const columns = [
    { key: 'revenue', label: '歳入の款' },
    ...base.columns.filter(c => c.key === 'funding'),
    { key: 'kan', label: '歳出の款' },
  ];
  return {
    graph: {
      ...base,
      columns,
      nodes: [...revNodes.values(), ...fundingNodes, ...kanNodes],
      edges: [...edgeValue.values(), ...right],
    },
    funding,
    estimated,
    groupedNames,
    estimatedParts: flows.filter(f => f.estimated).sort((a, b) => b.amount - a.amount).map(f => ({ name: f.kan_name, value: f.amount })),
  };
}
