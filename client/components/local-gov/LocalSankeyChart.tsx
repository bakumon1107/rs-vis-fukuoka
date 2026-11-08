'use client';

/**
 * 地方版のサンキー図の描画（SVG）。表示専用: データの読み込み・選択の状態は持たない（page.tsx が持つ）。
 * 設計: docs/local-gov/tasks/20261106_1327_地方版サンキー図の画面とグラフの設計.md 4章
 *
 * 配置計算と帯の形は国版（app/lib/mof-sankey-layout.ts）を使う。列はグラフの列の順で固定（columnOf）し、上詰めにする。
 * 選んでいるときは、全体の帯を灰色で敷き、選んだものに含まれる分（display.highlight の値）を元の色で重ねる。
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { computeMOFSankeyLayout, mofRibbonPath, type MOFLayoutLink } from '@/app/lib/mof-sankey-layout';
import { edgeKey, type LocalGraphDisplay } from '@/app/lib/local-gov/graph-view';
import { orderEdges } from '@/app/lib/local-gov/graph';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';
import type { LocalGraph } from '@/types/local-gov';

type GraphNode = LocalGraph['nodes'][number];

/** 列ごとの色（財源 → 款 → 項 → 目 → 事項 のように左から） */
const COLUMN_COLORS = ['#64748b', '#2aa693', '#3b82f6', '#8b5cf6', '#f59e0b', '#ef4444'];
const GREY = '#d1d5db';
const NODE_WIDTH = 12;
const LABEL_MAX = 18;
/** ラベルの幅の見積もり（12px の文字1字の幅・金額の部分・余白の上限） */
const LABEL_CHAR_PX = 12;
const AMOUNT_LABEL_PX = 90;
const MAX_SIDE_MARGIN = 320;

function shorten(s: string, max: number) {
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

/** 図の幅は枠の幅に合わせる（minWidth より狭くはしない。狭い幅では3列だけを描くので小さくてよい） */
function useWidth<T extends HTMLElement>(minWidth: number) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(1200);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setWidth(Math.max(minWidth, el.clientWidth));
    measure();
    const ob = new ResizeObserver(measure);
    ob.observe(el);
    return () => ob.disconnect();
  }, [minWidth]);
  return { ref, width };
}

/** 狭い幅（スマートフォン）の描き方: 3列だけを描くので、図の最小幅・ラベルの長さ・左右の余白を小さくする（設計書 4.3） */
const NARROW = { minWidth: 300, labelMax: 6, amountPx: 8, maxSide: 90, fontSize: 11, charPx: 11, showAmount: false };
const WIDE = {
  minWidth: 640,
  labelMax: LABEL_MAX,
  amountPx: AMOUNT_LABEL_PX,
  maxSide: MAX_SIDE_MARGIN,
  fontSize: 12,
  charPx: LABEL_CHAR_PX,
  showAmount: true,
};

export interface LocalSankeyChartProps {
  display: LocalGraphDisplay;
  onSelect: (id: string) => void;
  /** スマートフォンの幅か（page.tsx が useIsNarrow で決め、表示するグラフも3列に絞って渡す） */
  narrow?: boolean;
}

export function LocalSankeyChart({ display, onSelect, narrow = false }: LocalSankeyChartProps) {
  const { graph, highlight, highlightNodes, selected } = display;
  const size = narrow ? NARROW : WIDE;
  const { ref, width } = useWidth<HTMLDivElement>(size.minWidth);
  const [hovered, setHovered] = useState<string | null>(null);

  const colIndex = useMemo(() => new Map(graph.columns.map((c, i) => [c.key, i])), [graph.columns]);
  // 左端の列のラベルは箱の左、それ以外は右に出す。左右の余白は、左端・右端の列のラベルの長さで決める
  // （全会計の見方の歳入の款のように名前が長い列で、ラベルが画面の端で切れないように）
  const margin = useMemo(() => {
    const presentCols = graph.columns.filter(c => graph.nodes.some(n => n.col === c.key));
    const labelPx = (col: string | undefined) =>
      Math.max(0, ...graph.nodes.filter(n => n.col === col).map(n => Math.min(n.name.length, size.labelMax) + 1)) * size.charPx +
      size.amountPx;
    return {
      top: 16,
      bottom: 24,
      left: Math.min(size.maxSide, labelPx(presentCols[0]?.key)),
      right: Math.min(size.maxSide, labelPx(presentCols.at(-1)?.key)),
    };
  }, [graph, size]);
  const layout = useMemo(
    () =>
      computeMOFSankeyLayout<GraphNode>(
        {
          nodes: graph.nodes.map(n => ({ id: n.id, name: n.name, value: n.value, type: n.col, details: n })),
          // 帯を箱の並び順に並べ直す（配置計算は帯を並び順に積むので、ずれると帯が交差する）
          links: orderEdges(graph),
        },
        {
          width,
          height: 720,
          margin,
          nodeWidth: NODE_WIDTH,
          nodePadding: 3,
          align: 'top',
          minNodeSlot: 18,
          columnOf: n => colIndex.get(n.type ?? '') ?? 0,
        }
      ),
    [graph, width, colIndex, margin]
  );

  const colorOf = (col: number) => COLUMN_COLORS[col % COLUMN_COLORS.length];
  const height = Math.max(layout.height, layout.contentHeight);
  // ホバー中の箱が選択の解除などで図から消えると onMouseLeave が来ないので、図にない箱を指すホバーは無視する
  // （残ると全部の帯が薄いままになる）
  const hoveredShown = hovered !== null && layout.nodes.some(n => n.id === hovered) ? hovered : null;

  return (
    <div ref={ref} className="w-full">
      {/* 列の見出し */}
      <div className="relative h-6 text-xs text-mirai-text-muted" style={{ width }}>
        {graph.columns.map((c, i) => {
          const node = layout.nodes.find(n => n.column === i);
          return node ? (
            <span key={c.key} className="absolute" style={{ left: node.x - 8 }}>
              {c.label}
            </span>
          ) : null;
        })}
      </div>
      <svg width={width} height={height} role="img" aria-label="予算の流れ（サンキー図）">
        <g>
          {layout.links.map(link => {
            const k = edgeKey(link.source.id, link.target.id);
            const color = colorOf(link.target.column);
            if (!selected) {
              const dim = hoveredShown !== null && hoveredShown !== link.source.id && hoveredShown !== link.target.id;
              return <path key={k} d={mofRibbonPath(link)} fill={color} opacity={dim ? 0.08 : 0.3} />;
            }
            const part = highlight.get(k) ?? 0;
            // 選んだものに含まれる分だけを、帯の上側に元の色で重ねる（按分しない。値は組み立て直したグラフの値）
            const sub: MOFLayoutLink<GraphNode> | null =
              part > 0 && link.value > 0 ? { ...link, width: link.width * Math.min(1, part / link.value) } : null;
            return (
              <g key={k}>
                <path d={mofRibbonPath(link)} fill={GREY} opacity={0.35} />
                {sub && <path d={mofRibbonPath(sub)} fill={color} opacity={0.55} />}
              </g>
            );
          })}
        </g>
        <g>
          {layout.nodes.map(node => {
            const n = node.details!;
            const lit = !selected || highlightNodes.has(node.id);
            const isSelected = selected?.id === node.id;
            const labelLeft = node.column === 0;
            const ocrName = n.flags?.includes('name-ocr');
            // 「その他」（まとめた箱）は選べない。中身はほかの箱（左の列の款・項など）を選び直して見る（設計書 4.3）
            const aggregate = n.flags?.includes('aggregate');
            const cy = node.y + node.height / 2;
            return (
              <g
                key={node.id}
                onClick={
                  aggregate
                    ? undefined
                    : () => {
                        // タッチではタップでホバーが付き、離れても消えない（mouseleave が来ない）。押したらホバーを消す
                        setHovered(null);
                        onSelect(node.id);
                      }
                }
                onMouseEnter={() => setHovered(node.id)}
                onMouseLeave={() => setHovered(null)}
                style={{ cursor: aggregate ? 'default' : 'pointer' }}
              >
                <title>
                  {`${n.name}　${formatBudgetFromYen(n.value)}${ocrName ? '\n※名前は読み取り（資料で裏付けが取れていない）' : ''}${aggregate ? '\n上位以外の項目をまとめています（選んでいるときは、選んだものの分の大きい順）' : ''}`}
                </title>
                <rect
                  x={node.x}
                  y={node.y}
                  width={node.width}
                  height={node.height}
                  rx={2}
                  fill={lit ? colorOf(node.column) : GREY}
                  stroke={isSelected ? '#111827' : 'none'}
                  strokeWidth={isSelected ? 2 : 0}
                />
                <text
                  x={labelLeft ? node.x - 6 : node.x + node.width + 6}
                  y={cy}
                  textAnchor={labelLeft ? 'end' : 'start'}
                  dominantBaseline="middle"
                  fontSize={size.fontSize}
                  fontWeight={isSelected ? 700 : 500}
                  fill={lit ? '#1f2937' : '#9ca3af'}
                  stroke="#ffffff"
                  strokeWidth={3}
                  paintOrder="stroke"
                >
                  {shorten(n.name, size.labelMax)}
                  {ocrName && <tspan fill="#b45309">※</tspan>}
                  {/* 狭い幅では金額を出さない（3列のラベルが重なる。金額はツールチップと詳細パネルで見る） */}
                  {size.showAmount && (
                    <tspan fill={lit ? '#6b7280' : '#9ca3af'} fontWeight={400}>
                      {' '}
                      {formatBudgetFromYen(n.value)}
                    </tspan>
                  )}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
