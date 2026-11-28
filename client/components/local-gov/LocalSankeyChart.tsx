'use client';

/**
 * 地方版のサンキー図の描画（SVG）。表示専用: データの読み込み・選択の状態は持たない（page.tsx が持つ）。
 * 設計: docs/local-gov/tasks/20261106_1327_地方版サンキー図の画面とグラフの設計.md 4章
 *
 * 配置計算と帯の形は国版（app/lib/mof-sankey-layout.ts）を使う。列はグラフの列の順で固定（columnOf）し、上詰めにする。
 * 選んでいるときは、全体の帯を灰色で敷き、選んだものに含まれる分（display.highlight の値）を元の色で重ねる。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { computeMOFSankeyLayout, mofRibbonPath, type MOFLayoutLink } from '@/app/lib/mof-sankey-layout';
import { edgeKey, type LocalGraphDisplay } from '@/app/lib/local-gov/graph-view';
import { orderEdges } from '@/app/lib/local-gov/graph';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';
import { shortAmount, shortDelta, type BoxDelta } from '@/app/lib/local-gov/supplement-diff';
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

/** 文字列の幅の見積もり（px）。半角（数字・記号）は字の大きさの 0.6 倍、ほかは1字分 */
function textPx(s: string, fontSize: number) {
  let w = 0;
  for (const ch of s) w += ch.charCodeAt(0) < 0x100 ? fontSize * 0.6 : fontSize;
  return w;
}

/** 図の幅は枠の幅に合わせる（minWidth より狭くはしない。スマートフォンでは3列だけを描くので小さくてよい） */
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

interface ChartSize {
  minWidth: number;
  labelMax: number;
  /** 1行のラベルで、名前の後ろの金額の幅の見積もり */
  amountPx: number;
  maxSide: number;
  fontSize: number;
  charPx: number;
  /** 金額を名前の下の2行目に出す（スマートフォンの縦。横に並べると3列のラベルが重なる） */
  twoLine: boolean;
  /** 箱1つの最低の高さ（ラベルの行が重ならないように） */
  slot: number;
}

/**
 * スマートフォンの縦の描き方: 3列だけを描く。名前は6字までで、金額は名前の下の2行目に小さく出す
 * （設計: スマートフォンのサンキー図と簡易表示 2.2。前は金額を出していなかった）
 */
const NARROW: ChartSize = { minWidth: 300, labelMax: 6, amountPx: 0, maxSide: 110, fontSize: 11, charPx: 11, twoLine: true, slot: 28 };
/** スマートフォンの横の描き方: 3列だけを描く。幅があるので名前は10字・金額は名前の後ろ（同 2.1） */
const MEDIUM: ChartSize = { minWidth: 560, labelMax: 10, amountPx: AMOUNT_LABEL_PX, maxSide: 240, fontSize: 12, charPx: 12, twoLine: false, slot: 18 };
const WIDE: ChartSize = {
  minWidth: 640,
  labelMax: LABEL_MAX,
  amountPx: AMOUNT_LABEL_PX,
  maxSide: MAX_SIDE_MARGIN,
  fontSize: 12,
  charPx: LABEL_CHAR_PX,
  twoLine: false,
  slot: 18,
};
const SIZES = { narrow: NARROW, medium: MEDIUM, wide: WIDE } as const;
export type ChartSizeKey = keyof typeof SIZES;

/** 3行のラベル（名前・金額・増減）の箱1つの最低の高さ */
const THREE_LINE_SLOT = 38;

export interface LocalSankeyChartProps {
  display: LocalGraphDisplay;
  onSelect: (id: string) => void;
  /**
   * 描き方（page.tsx が決め、narrow・medium では表示するグラフも3列に絞って渡す）。
   * narrow: スマートフォンの縦、medium: スマートフォンの横、wide: パソコン
   */
  size?: ChartSizeKey;
  /** かんたんの図（列が少ないので、図の高さを低くする） */
  simple?: boolean;
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

export function LocalSankeyChart({ display, onSelect, size: sizeKey = 'wide', simple = false, deltas }: LocalSankeyChartProps) {
  const { graph, highlight, highlightNodes, selected } = display;
  const size = SIZES[sizeKey];
  const { ref, width } = useWidth<HTMLDivElement>(size.minWidth);
  const [hovered, setHovered] = useState<string | null>(null);

  const colIndex = useMemo(() => new Map(graph.columns.map((c, i) => [c.key, i])), [graph.columns]);
  const hideAmountCols = useMemo(() => new Set(graph.columns.filter(c => c.hideAmount).map(c => c.key)), [graph.columns]);
  // 増減の印を実際に出す箱か（1万円未満は出さない）
  const shows = useCallback(
    (id: string) => {
      const d = deltas?.get(id);
      return !!d && (d.added || shortDelta(d.delta) !== '');
    },
    [deltas]
  );
  const presentCols = useMemo(() => graph.columns.filter(c => graph.nodes.some(n => n.col === c.key)), [graph]);
  // 左端の列のラベルは箱の左、それ以外は右に出す。左右の余白は、左端・右端の列のラベルの長さで決める
  // （全会計の見方の歳入の款のように名前が長い列で、ラベルが画面の端で切れないように）
  const margin = useMemo(() => {
    // 描く条件（金額を出す列だけ）と同じにする
    const withDelta = (col: string | undefined, px: number) =>
      deltas && col && !hideAmountCols.has(col) && graph.nodes.some(n => n.col === col && shows(n.id)) ? px : 0;
    const labelPx = (col: string | undefined) => {
      const namePx = Math.max(0, ...graph.nodes.filter(n => n.col === col).map(n => Math.min(n.name.length, size.labelMax) + 1)) * size.charPx;
      // 2行のラベル: 名前の行と金額の行の長い方。金額の行は実際の文字列（短い額と増減）から見積もる
      if (size.twoLine) {
        if (!col || hideAmountCols.has(col)) return namePx;
        const amountLine = Math.max(
          0,
          ...graph.nodes
            .filter(n => n.col === col)
            .map(n => {
              const d = deltas?.get(n.id);
              const dt = d && shows(n.id) ? ` ${d.added ? '新' : shortDelta(d.delta)}` : '';
              return textPx(shortAmount(n.value), size.fontSize - 1) + textPx(dt, size.fontSize - 1);
            })
        );
        return Math.max(namePx, amountLine + 6);
      }
      return namePx + size.amountPx + withDelta(col, DELTA_LABEL_PX);
    };
    return {
      top: 16,
      bottom: 24,
      left: Math.min(size.maxSide, labelPx(presentCols[0]?.key)),
      right: Math.min(size.maxSide, labelPx(presentCols.at(-1)?.key)),
    };
  }, [graph, size, deltas, hideAmountCols, shows, presentCols]);
  // 箱1つの最低の高さ。スマートフォンの縦で、真ん中の列に増減の印を出す箱があるとき（補正後の見方）は、そのラベルが3行（約 34px）に
  // なるので広げる（小さい箱が隣り合うと、名前と隣の箱の増減の行が重なる）。真ん中の列のない図（かんたんの2列）は広げない
  const middleCols = new Set(presentCols.slice(1, -1).map(c => c.key));
  const threeLine =
    size.twoLine && !!deltas && graph.nodes.some(n => middleCols.has(n.col) && !hideAmountCols.has(n.col) && shows(n.id));
  const slot = threeLine ? THREE_LINE_SLOT : size.slot;
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
          // かんたんの図は箱が少ない（款 14 前後）ので低く描き、スマートフォンでも1画面に収める
          height: simple ? (sizeKey === 'wide' ? 480 : 360) : 720,
          margin,
          nodeWidth: NODE_WIDTH,
          nodePadding: 3,
          align: 'top',
          minNodeSlot: slot,
          columnOf: n => colIndex.get(n.type ?? '') ?? 0,
        }
      ),
    [graph, width, colIndex, margin, simple, sizeKey, slot]
  );

  // 列の色は元の列の位置で決める（スマートフォンの幅で左の列を外しても、同じ列は広い幅と同じ色。設計書 4.3）
  const colorOf = (col: number) => COLUMN_COLORS[(col + (display.colorOffset ?? 0)) % COLUMN_COLORS.length];
  const height = Math.max(layout.height, layout.contentHeight);
  // ホバー中の箱が選択の解除などで図から消えると onMouseLeave が来ないので、図にない箱を指すホバーは無視する
  // （残ると全部の帯が薄いままになる）
  const hoveredShown = hovered !== null && layout.nodes.some(n => n.id === hovered) ? hovered : null;
  const lastColumn = Math.max(0, ...layout.nodes.map(n => n.column));
  // 箱のある列の左端（左から。真ん中の列のラベルを、右隣の箱のある列までに収めるため）
  const columnXs = [...new Set(layout.nodes.map(n => n.x))].sort((a, b) => a - b);

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
                {(() => {
                  const tx = labelLeft ? node.x - 6 : node.x + node.width + 6;
                  // 列によっては金額を出さない（公営企業会計の会計・条。名前が長く支出の項の列に重なる）
                  const showAmount = !hideAmountCols.has(n.col);
                  const amount = showAmount && (
                    <tspan fill={lit ? '#6b7280' : '#9ca3af'} fontWeight={400}>
                      {size.twoLine ? shortAmount(n.value) : ` ${formatBudgetFromYen(n.value)}`}
                    </tspan>
                  );
                  // 補正後の見方: 当初からの増減（増は緑・減は赤・新しくできた箱は「新」）。金額を出す列だけ
                  // 真ん中の列の箱は、スマートフォンの縦では増減を3行目に出す（2行目に並べると右の列の箱に重なる）
                  const ownLine = size.twoLine && !labelLeft && node.column < lastColumn;
                  const delta = showAmount && (() => {
                    const d = deltas?.get(n.id);
                    if (!d) return null;
                    const text = d.added ? '新' : shortDelta(d.delta);
                    if (!text) return null;
                    const color = !lit ? '#9ca3af' : d.added ? '#b45309' : d.delta > 0 ? '#047857' : '#b91c1c';
                    return (
                      <tspan fill={color} fontWeight={600} fontSize={size.fontSize - 1}>
                        {/* 行の頭に出すときは空けない（名前・金額の行と左をそろえる） */}
                        {ownLine ? '' : ' '}
                        {text}
                      </tspan>
                    );
                  })();
                  // スマートフォンの横の真ん中の列: 名前・金額・増減が次の列の箱までに収まるよう、名前を縮める（全会計の会計の名前（10字）と
                  // 金額・増減を並べると右の列の箱に重なる）。最低4字は残す。パソコンの幅は今までどおり（列が多く、縮めると名前が読めなくなる）
                  let nameMax = size.labelMax;
                  const nextX = columnXs.find(x => x > node.x);
                  if (sizeKey === 'medium' && !labelLeft && nextX !== undefined) {
                    const room = nextX - tx - 4;
                    const d = deltas?.get(n.id);
                    // 選んだ箱は太字なので少し広めに見積もる
                    const bold = isSelected ? 1.1 : 1;
                    const tail =
                      (ocrName ? size.fontSize : 0) +
                      (showAmount ? textPx(` ${formatBudgetFromYen(n.value)}`, size.fontSize) : 0) +
                      (showAmount && d && shows(n.id) ? textPx(` ${d.added ? '新' : shortDelta(d.delta)}`, size.fontSize - 1) : 0);
                    while (nameMax > 4 && textPx(shorten(n.name, nameMax), size.fontSize) * bold + tail > room) nameMax--;
                  }
                  const name = (
                    <>
                      {shorten(n.name, nameMax)}
                      {ocrName && <tspan fill="#b45309">※</tspan>}
                    </>
                  );
                  return (
                    <text
                      x={tx}
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
                      {size.twoLine && showAmount ? (
                        // 2行: 1行目に名前、2行目に小さい字で金額と増減（スマートフォンの縦）。
                        // 真ん中の列は右の列までの間が狭く、金額と増減を横に並べると右の列の箱に重なるので、増減は3行目に
                        delta && ownLine ? (
                          <>
                            <tspan x={tx} dy="-1.1em">{name}</tspan>
                            <tspan x={tx} dy="1.2em" fontSize={size.fontSize - 1}>{amount}</tspan>
                            <tspan x={tx} dy="1.15em" fontSize={size.fontSize - 1}>{delta}</tspan>
                          </>
                        ) : (
                          <>
                            <tspan x={tx} dy="-0.6em">{name}</tspan>
                            <tspan x={tx} dy="1.25em" fontSize={size.fontSize - 1}>
                              {amount}
                              {delta}
                            </tspan>
                          </>
                        )
                      ) : (
                        <>
                          {name}
                          {amount}
                          {delta}
                        </>
                      )}
                    </text>
                  );
                })()}
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
