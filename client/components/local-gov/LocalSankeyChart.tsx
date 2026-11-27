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
import { shortDelta, type BoxDelta } from '@/app/lib/local-gov/supplement-diff';
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

/**
 * 帯を描くときの最低の太さ（px）。額に比例した太さだと、数百万円の帯（公営企業会計の収益的収支の差 527.9万円など）は
 * 0.02px ほどになり、箱だけが浮いて見える。描くときだけ太さを足す（配置・箱の額・合計は変えない）。
 * 本来の位置の中心に合わせて太らせるので、隣の帯と最大 0.5px ずつ重なる
 */
const MIN_RIBBON_PX = 1;
function visible<T extends { width: number; y0: number; y1: number }>(link: T): T {
  if (link.width >= MIN_RIBBON_PX) return link;
  const pad = (MIN_RIBBON_PX - link.width) / 2;
  return { ...link, width: MIN_RIBBON_PX, y0: link.y0 - pad, y1: link.y1 - pad };
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
  /**
   * 補正後の見方で、箱ごとの当初からの増減（app/lib/local-gov/supplement-diff.ts の boxDeltas）。
   * 額の後ろに短く添える（増は「+12.3億」、減は「△4.5億」、補正で新しくできた箱は「新」）
   */
  deltas?: Map<string, BoxDelta>;
}

/** 増減の印の幅の見積もり（「 △12.3億」くらい）。左右の余白に足す */
const DELTA_LABEL_PX = 56;

/** ツールチップに添える当初と増減（補正後の見方だけ） */
function deltaTooltip(d: BoxDelta | undefined, after: number): string {
  if (!d) return '';
  if (d.added) return '\n補正で新しくできた項目（当初予算になし）';
  if (d.delta === 0) return '\n当初予算から増減なし';
  const sign = d.delta > 0 ? '+' : '△';
  return `\n当初 ${formatBudgetFromYen(after - d.delta)}・補正 ${sign}${formatBudgetFromYen(Math.abs(d.delta))}`;
}

export function LocalSankeyChart({ display, onSelect, narrow = false, deltas }: LocalSankeyChartProps) {
  const { graph, highlight, highlightNodes, selected } = display;
  const size = narrow ? NARROW : WIDE;
  const { ref, width } = useWidth<HTMLDivElement>(size.minWidth);
  const [hovered, setHovered] = useState<string | null>(null);

  const colIndex = useMemo(() => new Map(graph.columns.map((c, i) => [c.key, i])), [graph.columns]);
  const hideAmountCols = useMemo(() => new Set(graph.columns.filter(c => c.hideAmount).map(c => c.key)), [graph.columns]);
  // 左端の列のラベルは箱の左、それ以外は右に出す。左右の余白は、左端・右端の列のラベルの長さで決める
  // （全会計の見方の歳入の款のように名前が長い列で、ラベルが画面の端で切れないように）
  const margin = useMemo(() => {
    const presentCols = graph.columns.filter(c => graph.nodes.some(n => n.col === c.key));
    // 増減の印を実際に出す箱（1万円未満は出さない）がある列だけ、余白を足す
    const shows = (id: string) => {
      const d = deltas?.get(id);
      return !!d && (d.added || shortDelta(d.delta) !== '');
    };
    const withDelta = (col: string | undefined) => (size.showAmount && deltas && graph.nodes.some(n => n.col === col && shows(n.id)) ? DELTA_LABEL_PX : 0);
    const labelPx = (col: string | undefined) =>
      Math.max(0, ...graph.nodes.filter(n => n.col === col).map(n => Math.min(n.name.length, size.labelMax) + 1)) * size.charPx +
      size.amountPx + withDelta(col);
    return {
      top: 16,
      bottom: 24,
      left: Math.min(size.maxSide, labelPx(presentCols[0]?.key)),
      right: Math.min(size.maxSide, labelPx(presentCols.at(-1)?.key)),
    };
  }, [graph, size, deltas]);
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

  // 列の色は元の列の位置で決める（スマートフォンの幅で左の列を外しても、同じ列は広い幅と同じ色。設計書 4.3）
  const colorOf = (col: number) => COLUMN_COLORS[(col + (display.colorOffset ?? 0)) % COLUMN_COLORS.length];
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
      {/* role="img" だと中の箱が支援技術から隠れるので group にし、箱をボタンとして選べるようにする */}
      <svg width={width} height={height} role="group" aria-label="予算の流れ（サンキー図）。四角を選ぶと、その流れに色を付けます">
        <style>{`.local-node:focus{outline:none}.local-node:focus-visible rect{stroke:#111827;stroke-width:2;stroke-dasharray:3 2}`}</style>
        <g>
          {layout.links.map(link => {
            const k = edgeKey(link.source.id, link.target.id);
            const color = colorOf(link.target.column);
            if (!selected) {
              const dim = hoveredShown !== null && hoveredShown !== link.source.id && hoveredShown !== link.target.id;
              return <path key={k} d={mofRibbonPath(visible(link))} fill={color} opacity={dim ? 0.08 : 0.3} />;
            }
            const part = highlight.get(k) ?? 0;
            // 選んだものに含まれる分だけを、帯の上側に元の色で重ねる（按分しない。値は組み立て直したグラフの値）
            const sub: MOFLayoutLink<GraphNode> | null =
              part > 0 && link.value > 0 ? { ...link, width: link.width * Math.min(1, part / link.value) } : null;
            return (
              <g key={k}>
                <path d={mofRibbonPath(visible(link))} fill={GREY} opacity={0.35} />
                {sub && <path d={mofRibbonPath(visible(sub))} fill={color} opacity={0.55} />}
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
            const select = () => {
              // タッチではタップでホバーが付き、離れても消えない（mouseleave が来ない）。押したらホバーを消す
              setHovered(null);
              onSelect(node.id);
            };
            // キーボード・支援技術でも選べるように、選べる箱はボタンとして扱う（Enter・Space で選ぶ）
            // 読み上げにも増減を入れる（aria-label は <title> より優先されるので、ツールチップと同じ文を足す）
            const label = `${n.name} ${formatBudgetFromYen(n.value)}${deltaTooltip(deltas?.get(n.id), n.value).replace('\n', '。')}${ocrName ? '（名前は読み取り）' : ''}${isSelected ? '（選択中）' : ''}`;
            return (
              <g
                key={node.id}
                className={aggregate ? undefined : 'local-node'}
                role={aggregate ? 'img' : 'button'}
                tabIndex={aggregate ? undefined : 0}
                aria-label={aggregate ? `${label}。上位以外の項目をまとめた箱` : label}
                aria-pressed={aggregate ? undefined : isSelected}
                onClick={aggregate ? undefined : select}
                onKeyDown={
                  aggregate
                    ? undefined
                    : e => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          select();
                        }
                      }
                }
                onMouseEnter={() => setHovered(node.id)}
                onMouseLeave={() => setHovered(null)}
                style={{ cursor: aggregate ? 'default' : 'pointer' }}
              >
                <title>
                  {`${n.name}　${formatBudgetFromYen(n.value)}${deltaTooltip(deltas?.get(n.id), n.value)}${ocrName ? '\n※名前は読み取り（資料で裏付けが取れていない）' : ''}${aggregate ? '\n上位以外の項目をまとめています（選んでいるときは、選んだものの分の大きい順）' : ''}`}
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
                  {/* 列によっては広い幅でも出さない（公営企業会計の会計・条。名前が長く支出の項の列に重なる） */}
                  {size.showAmount && !hideAmountCols.has(n.col) && (
                    <tspan fill={lit ? '#6b7280' : '#9ca3af'} fontWeight={400}>
                      {' '}
                      {formatBudgetFromYen(n.value)}
                    </tspan>
                  )}
                  {/* 補正後の見方: 当初からの増減（増は緑・減は赤・新しくできた箱は「新」）。金額を出す列だけ */}
                  {size.showAmount && !hideAmountCols.has(n.col) && (() => {
                    const d = deltas?.get(n.id);
                    if (!d) return null;
                    const text = d.added ? '新' : shortDelta(d.delta);
                    if (!text) return null;
                    const color = !lit ? '#9ca3af' : d.added ? '#b45309' : d.delta > 0 ? '#047857' : '#b91c1c';
                    return (
                      <tspan fill={color} fontWeight={600} fontSize={size.fontSize - 1}>
                        {' '}
                        {text}
                      </tspan>
                    );
                  })()}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
