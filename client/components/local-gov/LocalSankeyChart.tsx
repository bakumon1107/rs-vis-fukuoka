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

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(1200);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setWidth(Math.max(640, el.clientWidth));
    measure();
    const ob = new ResizeObserver(measure);
    ob.observe(el);
    return () => ob.disconnect();
  }, []);
  return { ref, width };
}

export interface LocalSankeyChartProps {
  display: LocalGraphDisplay;
  onSelect: (id: string) => void;
}

export function LocalSankeyChart({ display, onSelect }: LocalSankeyChartProps) {
  const { graph, highlight, highlightNodes, selected } = display;
  const { ref, width } = useWidth<HTMLDivElement>();
  const [hovered, setHovered] = useState<string | null>(null);

  const colIndex = useMemo(() => new Map(graph.columns.map((c, i) => [c.key, i])), [graph.columns]);
  // 左端の列のラベルは箱の左、それ以外は右に出す。左右の余白は、左端・右端の列のラベルの長さで決める
  // （全会計の見方の歳入の款のように名前が長い列で、ラベルが画面の端で切れないように）
  const margin = useMemo(() => {
    const presentCols = graph.columns.filter(c => graph.nodes.some(n => n.col === c.key));
    const labelPx = (col: string | undefined) =>
      Math.max(0, ...graph.nodes.filter(n => n.col === col).map(n => Math.min(n.name.length, LABEL_MAX))) * LABEL_CHAR_PX +
      AMOUNT_LABEL_PX;
    return {
      top: 16,
      bottom: 24,
      left: Math.min(MAX_SIDE_MARGIN, labelPx(presentCols[0]?.key)),
      right: Math.min(MAX_SIDE_MARGIN, labelPx(presentCols.at(-1)?.key)),
    };
  }, [graph]);
  const layout = useMemo(
    () =>
      computeMOFSankeyLayout<GraphNode>(
        {
          nodes: graph.nodes.map(n => ({ id: n.id, name: n.name, value: n.value, type: n.col, details: n })),
          links: graph.edges,
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
              const dim = hovered !== null && hovered !== link.source.id && hovered !== link.target.id;
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
            const cy = node.y + node.height / 2;
            return (
              <g
                key={node.id}
                onClick={() => onSelect(node.id)}
                onMouseEnter={() => setHovered(node.id)}
                onMouseLeave={() => setHovered(null)}
                style={{ cursor: 'pointer' }}
              >
                <title>
                  {`${n.name}　${formatBudgetFromYen(n.value)}${ocrName ? '\n※名前は読み取り（資料で裏付けが取れていない）' : ''}`}
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
                  fontSize={12}
                  fontWeight={isSelected ? 700 : 500}
                  fill={lit ? '#1f2937' : '#9ca3af'}
                  stroke="#ffffff"
                  strokeWidth={3}
                  paintOrder="stroke"
                >
                  {shorten(n.name, LABEL_MAX)}
                  {ocrName && <tspan fill="#b45309">※</tspan>}
                  <tspan fill={lit ? '#6b7280' : '#9ca3af'} fontWeight={400}>
                    {' '}
                    {formatBudgetFromYen(n.value)}
                  </tspan>
                </text>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
