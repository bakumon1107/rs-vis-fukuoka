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

/**
 * 右端の列（先へ帯の出ない箱）の箱が多いとき、金額の大きい上位 n 件（と keep の箱）を残し、残りを1つの「その他」にまとめる。
 * 帯は送り手ごとに足し合わせる。選んだ帯の重ね（highlight）も同じようにまとめる。途中の列はまとめない（先の帯が切れるため）
 */
export function aggregateTail(
  graph: LocalGraph,
  highlight: Map<string, number>,
  highlightNodes: Set<string>,
  n: number,
  keep: Set<string>,
  /** 最初の画面の列（深い列でない列）。この列が右端ならまとめない */
  entryCols: Set<string>
): { graph: LocalGraph; highlight: Map<string, number>; highlightNodes: Set<string> } {
  const hasOut = new Set(graph.edges.map(e => e.source));
  const lastCol = graph.columns.filter(c => graph.nodes.some(nd => nd.col === c.key)).at(-1)?.key;
  // まとめるのは選んで開いた深い列（最初の3列より右。一般会計の目・事項、全会計の項・目）だけ。
  // 最初の画面の右端（一般会計の項・全会計の款）は、選んで先を開く入口なのでまとめない
  if (!lastCol || entryCols.has(lastCol)) return { graph, highlight, highlightNodes };
  const tail = graph.nodes.filter(nd => nd.col === lastCol && !hasOut.has(nd.id));
  if (tail.length <= n + 1) return { graph, highlight, highlightNodes };
  // 上位は重ねる帯の額（選んだものの分。財源を選んだときはその財源の額）で選び、同じなら箱の額。
  // 箱の額で選ぶと、選んだ財源が多く入っている目が「その他」に入ってしまう（設計書 4.3）
  const litInto = new Map<string, number>();
  for (const e of graph.edges) {
    const h = highlight.get(edgeKey(e.source, e.target));
    if (h) litInto.set(e.target, (litInto.get(e.target) ?? 0) + h);
  }
  const ranked = [...tail].sort((a, b) => (litInto.get(b.id) ?? 0) - (litInto.get(a.id) ?? 0) || b.value - a.value);
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
 * 一般会計の財源は、各目のその財源の額で目まで絞り込む（財源内訳は目ごとに印字されているので按分にならない）。
 * 全会計の歳入の款は絞り込まない（どの歳出に使われたかは資料にない）ので null を返し、その箱から出る帯だけを重ねる。
 * 「その他」（other:）も絞り込まない（選べない箱）。設計書 3.3・4.3
 */
export function selectionToFilter(view: LocalGraphView, id: string): { filter: LocalGraphFilter; depth: number } | null {
  // 一般会計の財源: その財源の額で目まで追う（財源内訳は目ごとに印字。事項ごとの内訳はないので目まで）
  // （none は財源内訳のない目の「財源の記載なし」）
  let m = /^funding:(national|bond|other|general|none)$/.exec(id);
  if (m && view === 'general') return { filter: { funding: m[1] as FundingKey | 'none' }, depth: BASE_DEPTH + 1 };
  // 款・項・目・事項は歳出だけ（歳入の目は図に箱がない。全会計の歳入の款は revenue:<名前> で、下の null の扱い）
  m = /^kan:(.+):expense:(\d+)$/.exec(id);
  if (m) {
    // 一般会計の見方で款を選んだら目まで（事項まで開くと、R8 で農林水産業費 178件・教育費 160件などになる）。全会計の見方は目まで
    return { filter: { account: m[1], side: 'expense', kan: Number(m[2]) },
      depth: view === 'general' ? BASE_DEPTH + 1 : BASE_DEPTH + 2 };
  }
  m = /^kou:(.+):expense:(\d+)-(\d+)$/.exec(id);
  if (m) {
    return { filter: { account: m[1], side: 'expense', kan: Number(m[2]), kou: Number(m[3]) }, depth: BASE_DEPTH + 2 };
  }
  m = /^(?:moku|item):(.+)\/expense\/(\d+)-(\d+)-(\d+)(?::\d+)?$/.exec(id);
  if (m) {
    return { filter: { account: m[1], side: 'expense', kan: Number(m[2]), kou: Number(m[3]), moku: Number(m[4]) },
      depth: BASE_DEPTH + 2 };
  }
  m = /^account:(.+)$/.exec(id);
  if (m && view === 'all') return { filter: { account: m[1] }, depth: BASE_DEPTH + 1 };
  return null;
}

/** 資料にない対応に色を付けないときに、図の上に出す理由（設計書 3.3 の表） */
export const NOTE_ITEM_FUNDING = '事項ごとの財源は資料にないため、財源の帯は色を付けていません';
export const NOTE_REVENUE_UNKNOWN = '歳入のどれが使われたかは資料にないため、歳入の列は色を付けていません';
export const NOTE_EXPENSE_UNKNOWN = 'どの歳出に使われたかは資料にないため、会計から先は色を付けていません';

/**
 * 最初の画面のグラフ（左の3列の全体）は、データと見方が同じなら選択によらず同じなので覚えておく（選ぶたびに全目を組み立て直さない）。
 * 正規化データは読み込んだ後に変えない前提（同じオブジェクトなら同じ結果）
 */
const fullCache = new WeakMap<LocalBudgetFile, Map<string, LocalGraph>>();
/**
 * 絞り込まない全体のグラフ（見方・深さごと）。最初の画面（depth = BASE_DEPTH）と、深い列の箱と帯の全体の額に使う。
 * データと見方と深さが同じなら選択によらず同じなので覚えておく（選ぶたびに全目を組み立て直さない）。
 * 正規化データは読み込んだ後に変えない前提（同じオブジェクトなら同じ結果）
 */
function fullGraph(file: LocalBudgetFile, view: LocalGraphView, depth: number): LocalGraph {
  let byKey = fullCache.get(file);
  if (!byKey) fullCache.set(file, (byKey = new Map()));
  const key = `${view}:${depth}`;
  let g = byKey.get(key);
  if (!g) byKey.set(key, (g = buildLocalGraph(file, { view, depth })));
  return g;
}

export function composeDisplay(file: LocalBudgetFile, view: LocalGraphView, selectedId: string | null): LocalGraphDisplay {
  const base = fullGraph(file, view, BASE_DEPTH);
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
  // 図にない箱を指す選択（書き出し直しで事項の番号が変わった URL・別の見方の ID など）は、選択なしに戻す（設計書 3.2）
  if (!focused.nodes.some(n => n.id === selectedId)) {
    return { graph: base, selected: null, highlight, highlightNodes, row: null, note: null };
  }
  const baseCols = new Set(base.columns.map(c => c.key));
  // 深い列（左の列にない列）は、選んだものに含まれる箱だけを足す。箱と帯は全体の額（絞り込まない同じ深さのグラフの値）で出し
  // （灰色の下地）、選んだものの分は重ねる帯で示す（設計書 3.3）。組み立て直したグラフの値をそのまま使うと、目を選んだときの項の箱が
  // その目の額になり、財源を選んだときの目の箱がその財源の額になって、箱の額に見えてしまう
  const full = fullGraph(file, view, sel.depth);
  const deepIds = new Set(focused.nodes.filter(n => !baseCols.has(n.col)).map(n => n.id));
  const deepNodes = full.nodes.filter(n => deepIds.has(n.id));
  const shown = new Set([...base.nodes.map(n => n.id), ...deepIds]);
  const deepEdges = full.edges.filter(e => deepIds.has(e.target) && shown.has(e.source));
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
  const agg = aggregateTail(graph, highlight, highlightNodes, TOP_N, new Set(selectedId ? [selectedId] : []), baseCols);
  // 目・事項を選んだら、その目を詳細パネルに出す
  return { ...agg, selected, row: n?.row ?? null, note };
}
