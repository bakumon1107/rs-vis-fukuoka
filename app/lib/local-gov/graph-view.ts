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
import { buildLocalGraph, type LocalGraphFilter, type LocalGraphView } from './graph';

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
}

export const edgeKey = (source: string, target: string) => `${source}\u0000${target}`;

/**
 * 箱の ID から絞り込みと開く深さを決める（graph.ts の ID の形に対応）。
 * 財源・歳入の款（左端の列）は絞り込みにできない（財源の内訳は款より先で按分しないと分けられない）ので、その箱から出る帯だけを重ねる
 */
export function selectionToFilter(view: LocalGraphView, id: string): { filter: LocalGraphFilter; depth: number } | null {
  let m = /^kan:(.+):(revenue|expense):(\d+)$/.exec(id);
  if (m) {
    // 一般会計の見方で款を選んだら目まで（事項まで開くと民生費などで数百件になる）。全会計の見方は項・目まで
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

export function composeDisplay(file: LocalBudgetFile, view: LocalGraphView, selectedId: string | null): LocalGraphDisplay {
  const base = buildLocalGraph(file, { view, depth: BASE_DEPTH });
  const highlight = new Map<string, number>();
  const highlightNodes = new Set<string>();
  if (!selectedId) return { graph: base, selected: null, highlight, highlightNodes, row: null };

  const sel = selectionToFilter(view, selectedId);
  const nodeOf = (g: LocalGraph) => g.nodes.find(n => n.id === selectedId);
  if (!sel) {
    // 左端の列の箱: その箱から出る帯だけを重ねる
    const n = nodeOf(base);
    if (!n) return { graph: base, selected: null, highlight, highlightNodes, row: null };
    highlightNodes.add(n.id);
    for (const e of base.edges) {
      if (e.source === n.id) {
        highlight.set(edgeKey(e.source, e.target), e.value);
        highlightNodes.add(e.target);
      }
    }
    return { graph: base, selected: { id: n.id, name: n.name, col: n.col }, highlight, highlightNodes, row: null };
  }

  const focused = buildLocalGraph(file, { view, filter: sel.filter, depth: sel.depth });
  const baseCols = new Set(base.columns.map(c => c.key));
  // 深い列（左の列にない列）は選んだものの分だけ足す。左の列から深い列への帯も選んだものの分
  const deepNodes = focused.nodes.filter(n => !baseCols.has(n.col));
  const deepIds = new Set(deepNodes.map(n => n.id));
  const deepEdges = focused.edges.filter(e => deepIds.has(e.target));
  for (const e of focused.edges) highlight.set(edgeKey(e.source, e.target), e.value);
  for (const n of focused.nodes) highlightNodes.add(n.id);
  const graph: LocalGraph = {
    ...base,
    columns: focused.columns,
    nodes: [...base.nodes, ...deepNodes],
    edges: [...base.edges, ...deepEdges],
  };
  const n = nodeOf(graph);
  const selected = n ? { id: n.id, name: n.name, col: n.col } : null;
  // 目・事項を選んだら、その目を詳細パネルに出す
  return { graph, selected, highlight, highlightNodes, row: n?.row ?? null };
}
