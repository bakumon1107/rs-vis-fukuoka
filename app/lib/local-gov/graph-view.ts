/**
 * 地方版のサンキー図の「表示するグラフ」を、見方と選択から決める。純粋関数（HTTP・React なし）。
 * 設計: docs/local-gov/tasks/20261106_1327_地方版サンキー図の画面とグラフの設計.md 3.3・4.3
 *
 * - 最初は左の BASE_DEPTH 列（一般会計: 財源 → 款 → 項）を全体で出す
 * - 箱を選ぶと、選んだものに含まれる目だけから組み立て直したグラフ（buildLocalGraph の絞り込み）を作り、
 *   左の列ではその帯を元の色で重ね（ほかは灰色）、深い列（目・事項）は選んだものの分だけ開く
 * - 重ねる帯の値は組み立て直したグラフの値そのもの（按分しない）。帯の一部だけが選んだものに当たるとき
 *   （目を選んだときの 財源 → 款）は、その割合の太さで重ねる
 */
import type { LocalBudgetFile, LocalGraph } from '@/types/local-gov';
import { buildLocalGraph, type FundingKey, type LocalGraphFilter, type LocalGraphView } from './graph';

/** 最初に出す列の数（深い列は選んだときだけ開く） */
export const BASE_DEPTH = 3;

export interface LocalGraphDisplay {
  /** 描くグラフ（左の列は全体、深い列は選んだものの分） */
  graph: LocalGraph;
  /** 選んだもの。なければ null */
  selected: { id: string; name: string; col: string } | null;
  /** 選んだときに元の色で重ねる帯の値（帯のキー → 値）。選んでいなければ空 */
  highlight: Map<string, number>;
  /** 選んだときに元の色で描く箱 */
  highlightNodes: Set<string>;
  /** 選んだ目の行の ID（詳細パネルに出す）。目・事項を選んだときだけ */
  row: string | null;
  /** 資料にない対応に色を付けなかったときの理由（図の上に出す）。なければ null */
  note: string | null;
}

export const edgeKey = (source: string, target: string) => `${source}\u0000${target}`;

/** 右端の列の箱がこれより多ければ、上位だけを残して残りを「その他」にまとめる（設計書 4.3） */
export const TOP_N = 25;
const AGGREGATE_COLS = new Set(['moku', 'item']);

/**
 * 右端の列（先へ帯の出ない箱）の箱が多いとき、金額の大きい上位 n 件（と keep の箱）を残し、残りを1つの「その他」にまとめる。
 * 帯は送り手ごとに足し合わせる。選んだ帯の重ね（highlight）も同じようにまとめる。途中の列はまとめない（先の帯が切れるため）
 */
export function aggregateTail(
  graph: LocalGraph,
  highlight: Map<string, number>,
  highlightNodes: Set<string>,
  n: number,
  keep: Set<string>
): { graph: LocalGraph; highlight: Map<string, number>; highlightNodes: Set<string> } {
  const hasOut = new Set(graph.edges.map(e => e.source));
  const lastCol = graph.columns.filter(c => graph.nodes.some(nd => nd.col === c.key)).at(-1)?.key;
  // まとめるのは選んで開いた深い列（目・事項）だけ。最初の画面の右端（項）は、選んで先を開く入口なのでまとめない
  if (!lastCol || !AGGREGATE_COLS.has(lastCol)) return { graph, highlight, highlightNodes };
  const tail = graph.nodes.filter(nd => nd.col === lastCol && !hasOut.has(nd.id));
  if (tail.length <= n + 1) return { graph, highlight, highlightNodes };
  const ranked = [...tail].sort((a, b) => b.value - a.value);
  const merged = new Set(ranked.slice(n).filter(nd => !keep.has(nd.id)).map(nd => nd.id));
  if (merged.size <= 1) return { graph, highlight, highlightNodes };
  const otherId = `other:${lastCol}`;
  const nodes = graph.nodes.filter(nd => !merged.has(nd.id));
  const otherValue = tail.filter(nd => merged.has(nd.id)).reduce((s, nd) => s + nd.value, 0);
  nodes.push({ id: otherId, col: lastCol, name: `その他 ${merged.size}件`, value: otherValue, flags: ['aggregate'] });

  const edges = new Map<string, LocalGraph['edges'][number]>();
  const hl = new Map(highlight);
  for (const e of graph.edges) {
    const target = merged.has(e.target) ? otherId : e.target;
    const k = edgeKey(e.source, target);
    const cur = edges.get(k);
    if (cur) cur.value += e.value;
    else edges.set(k, { source: e.source, target, value: e.value });
    if (target === otherId) {
      const h = highlight.get(edgeKey(e.source, e.target)) ?? 0;
      hl.delete(edgeKey(e.source, e.target));
      if (h > 0) hl.set(k, (hl.get(k) ?? 0) + h);
    }
  }
  const hn = new Set([...highlightNodes].filter(id => !merged.has(id)));
  if ([...highlightNodes].some(id => merged.has(id))) hn.add(otherId);
  return { graph: { ...graph, nodes, edges: [...edges.values()] }, highlight: hl, highlightNodes: hn };
}

/**
 * 箱の ID から絞り込みと開く深さを決める（graph.ts の ID の形に対応）。
 * 財源・歳入の款（左端の列）は絞り込みにできない（財源の内訳は款より先で按分しないと分けられない）ので、その箱から出る帯だけを重ねる
 */
export function selectionToFilter(view: LocalGraphView, id: string): { filter: LocalGraphFilter; depth: number } | null {
  // 一般会計の財源: その財源の額で目まで追う（財源内訳は目ごとに印字。事項ごとの内訳はないので目まで）
  let m = /^funding:(national|bond|other|general)$/.exec(id);
  if (m && view === 'general') return { filter: { funding: m[1] as FundingKey }, depth: BASE_DEPTH + 1 };
  m = /^kan:(.+):(revenue|expense):(\d+)$/.exec(id);
  if (m) {
    // 一般会計の見方で款を選んだら目まで（事項まで開くと、R8 で農林水産業費 178件・教育費 160件などになる）。全会計の見方は目まで
    return { filter: { account: m[1], side: m[2] as 'revenue' | 'expense', kan: Number(m[3]) },
      depth: view === 'general' ? BASE_DEPTH + 1 : BASE_DEPTH + 2 };
  }
  m = /^kou:(.+):(revenue|expense):(\d+)-(\d+)$/.exec(id);
  if (m) {
    return { filter: { account: m[1], side: m[2] as 'revenue' | 'expense', kan: Number(m[3]), kou: Number(m[4]) },
      depth: BASE_DEPTH + 2 };
  }
  m = /^(?:moku|item):(.+)\/(revenue|expense)\/(\d+)-(\d+)-(\d+)(?::\d+)?$/.exec(id);
  if (m) {
    return { filter: { account: m[1], side: m[2] as 'revenue' | 'expense', kan: Number(m[3]), kou: Number(m[4]),
      moku: Number(m[5]) }, depth: BASE_DEPTH + 2 };
  }
  m = /^account:(.+)$/.exec(id);
  if (m && view === 'all') return { filter: { account: m[1] }, depth: BASE_DEPTH + 1 };
  return null;
}

/** 資料にない対応に色を付けないときに、図の上に出す理由（設計書 3.3 の表） */
export const NOTE_ITEM_FUNDING = '事項ごとの財源は資料にないため、財源の帯は色を付けていません';
export const NOTE_REVENUE_UNKNOWN = '歳入のどれが使われたかは資料にないため、歳入の列は色を付けていません';
export const NOTE_EXPENSE_UNKNOWN = 'どの歳出に使われたかは資料にないため、会計から先は色を付けていません';

export function composeDisplay(file: LocalBudgetFile, view: LocalGraphView, selectedId: string | null): LocalGraphDisplay {
  const base = buildLocalGraph(file, { view, depth: BASE_DEPTH });
  const highlight = new Map<string, number>();
  const highlightNodes = new Set<string>();
  if (!selectedId) return { graph: base, selected: null, highlight, highlightNodes, row: null, note: null };

  const sel = selectionToFilter(view, selectedId);
  const nodeOf = (g: LocalGraph) => g.nodes.find(n => n.id === selectedId);
  if (!sel) {
    // 絞り込まない左端の箱（全会計の歳入の款）: その箱から出る帯だけを重ねる
    const n = nodeOf(base);
    if (!n) return { graph: base, selected: null, highlight, highlightNodes, row: null, note: null };
    highlightNodes.add(n.id);
    for (const e of base.edges) {
      if (e.source === n.id) {
        highlight.set(edgeKey(e.source, e.target), e.value);
        highlightNodes.add(e.target);
      }
    }
    const note = n.col === 'revenue' ? NOTE_EXPENSE_UNKNOWN : null;
    return { graph: base, selected: { id: n.id, name: n.name, col: n.col }, highlight, highlightNodes, row: null, note };
  }

  const focused = buildLocalGraph(file, { view, filter: sel.filter, depth: sel.depth });
  const baseCols = new Set(base.columns.map(c => c.key));
  // 深い列（左の列にない列）は選んだものの分だけ足す。箱と帯は全体の額で出し（灰色の下地）、選んだものの分は重ねる帯で示す。
  // 財源で絞り込んだときは、組み立て直したグラフの目の値がその財源の額なので、箱は財源で絞らないグラフから取る（目の額に見えないように）
  const deepFrom = sel.filter.funding
    ? buildLocalGraph(file, { view, filter: { ...sel.filter, funding: undefined }, depth: sel.depth })
    : focused;
  const focusedDeep = new Set(focused.nodes.filter(n => !baseCols.has(n.col)).map(n => n.id));
  const deepNodes = deepFrom.nodes.filter(n => focusedDeep.has(n.id));
  const deepEdges = deepFrom.edges.filter(e => focusedDeep.has(e.target));
  for (const e of focused.edges) highlight.set(edgeKey(e.source, e.target), e.value);
  for (const n of focused.nodes) highlightNodes.add(n.id);

  let note: string | null = null;
  const item = /^item:/.test(selectedId) ? focused.nodes.find(n => n.id === selectedId) : undefined;
  if (item) {
    // 事項を選んだら、款 → 項 → 目 → 事項 に事項の金額だけを重ねる（事項は目に含まれるので按分にならない）。
    // 財源 → 款 は色を付けない（事項ごとの財源内訳は資料にない）。同じ目のほかの事項は灰色
    highlight.clear();
    highlightNodes.clear();
    for (const e of focused.edges) {
      if (e.source.startsWith('funding:')) continue;
      if (e.target.startsWith('item:') && e.target !== item.id) continue;
      highlight.set(edgeKey(e.source, e.target), item.value);
      highlightNodes.add(e.source);
      highlightNodes.add(e.target);
    }
    note = NOTE_ITEM_FUNDING;
  } else if (view === 'all' && sel.filter.side === 'expense') {
    note = NOTE_REVENUE_UNKNOWN;
  } else if (view === 'all' && sel.filter.side === 'revenue') {
    note = NOTE_EXPENSE_UNKNOWN;
  }

  const graph: LocalGraph = {
    ...base,
    columns: focused.columns,
    nodes: [...base.nodes, ...deepNodes],
    edges: [...base.edges, ...deepEdges],
  };
  const n = nodeOf(graph);
  const selected = n ? { id: n.id, name: n.name, col: n.col } : null;
  // 右端の深い列の箱が多ければ上位だけ残す（選んだ箱は残す）
  const agg = aggregateTail(graph, highlight, highlightNodes, TOP_N, new Set(selectedId ? [selectedId] : []));
  // 目・事項を選んだら、その目を詳細パネルに出す
  return { ...agg, selected, row: n?.row ?? null, note };
}
