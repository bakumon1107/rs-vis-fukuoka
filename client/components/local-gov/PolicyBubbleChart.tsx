'use client';

/**
 * 施策のバブル図（表示専用）。一般会計の歳出の全体を1つの入れ子の円にする（d3-hierarchy の pack。円の面積が予算額に比例）:
 * - 「施策別資料の事項」の円（柱 → 取組 → 事項）
 * - 施策の円の外の経費の灰色の円（5つ。制度融資は施策別資料の事項だが灰色で見せる）。同じ pack に並べるので縮尺は同じ
 * 設計: docs/local-gov/tasks/20261120_1500_地方版バブル図の設計.md 6章
 *
 * 操作: 円（施策・柱・取組）を押すとその円に寄る（viewBox を変える）。寄った円をもう一度押すか背景を押すと1つ外に戻る。
 * 事項の円を押すと選ぶ（取組より外から押したときは、その取組にも寄る）。灰色の円を押すと中身の説明を選ぶ
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { hierarchy, pack, type HierarchyCircularNode } from 'd3-hierarchy';
import type { PolicyItem } from '@/types/local-gov';
import { type PolicyGroup, type PolicyLeaf, type PolicyRoot, MUTED_COLOR, chordPx, fitLabel, fitWidth } from '@/app/lib/local-gov/policies';
import { formatBudgetFromYen } from '@/client/lib/formatBudget';

export interface OutsideCircle {
  key: string;
  label: string;
  amount: number;
}
type OutsideLeaf = OutsideCircle & { kind: 'outside' };
type AllRoot = { kind: 'all'; key: 'all'; children: (PolicyRoot | OutsideLeaf)[] };
type Datum = AllRoot | PolicyRoot | PolicyGroup | PolicyLeaf | OutsideLeaf;
type Circle = HierarchyCircularNode<Datum>;

const SIZE = 1000;
/** ツールチップの最大の幅（max-w-64 = 16rem）。右端からはみ出さないよう左の位置を抑える */
const TIP_WIDTH = 256;
/** 施策・柱の円の名前の、円の上端からの深さ（px。字の中心） */
const TOP_LABEL_DEPTH = 24;

interface Props {
  tree: PolicyRoot;
  outside: OutsideCircle[];
  colorOf: (it: PolicyItem) => string;
  /** 寄っている円の key（null は全体） */
  focus: string | null;
  onFocus: (key: string | null) => void;
  selected: number | null;
  /** 事項を選ぶ（取組の key も渡す。外から押したときに寄るため） */
  onSelect: (index: number, initiativeKey: string) => void;
  selectedOutside: string | null;
  onOutside: (key: string) => void;
}

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(600);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(es => setW(es[0].contentRect.width || 600));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

const keyOf = (d: Datum): string | null => (d.kind === 'item' || d.kind === 'outside' ? null : d.key);
const childrenOf = (d: Datum): Datum[] | undefined =>
  d.kind === 'item' || d.kind === 'outside' ? undefined : (d.children as Datum[]);

export function PolicyBubbleChart({ tree, outside, colorOf, focus, onFocus, selected, onSelect, selectedOutside, onOutside }: Props) {
  const [wrapRef, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<{ x: number; y: number; title: string; sub: string } | null>(null);

  const root = useMemo(() => {
    const all: AllRoot = {
      kind: 'all',
      key: 'all',
      children: [tree, ...outside.filter(o => o.amount > 0).map(o => ({ ...o, kind: 'outside' as const }))],
    };
    const h = hierarchy<Datum>(all, childrenOf)
      .sum(d => (d.kind === 'item' ? d.value : d.kind === 'outside' ? d.amount : 0))
      .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
    return pack<Datum>()
      .size([SIZE, SIZE])
      .padding(n => (n.depth <= 1 ? 8 : n.depth === 2 ? 4 : 1.5))(h);
  }, [tree, outside]);

  const nodes = useMemo(() => root.descendants(), [root]);
  const focusNode = useMemo(() => (focus ? nodes.find(n => keyOf(n.data) === focus) ?? null : null), [nodes, focus]);
  const view = focusNode ?? root;
  const pad = view.r * 0.03;
  const vb = { x: view.x - view.r - pad, y: view.y - view.r - pad, s: 2 * (view.r + pad) };
  // 画面の 1px あたりの図の単位の逆数（図の単位 → px）
  const pxPerUnit = width / vb.s;
  const px = (v: number) => v / pxPerUnit;

  // 円の説明はマウス・ペンだけ（指で触ったときは、押したあとに説明が残って別の円に重なるので出さない）
  const showTip = (e: React.PointerEvent, title: string, sub: string) => {
    if (e.pointerType === 'touch') return;
    const box = wrapRef.current?.getBoundingClientRect();
    if (box) setHover({ x: e.clientX - box.left, y: e.clientY - box.top, title, sub });
  };
  // 1つ外の円（施策の円の外は全体）
  const parentKey = (n: Circle | null): string | null => {
    const p = n?.parent;
    return p && p.data.kind !== 'all' ? keyOf(p.data) : null;
  };
  // 押した事項の取組より外を見ているか（寄っている円が取組でも、その事項の取組でもない）
  const initiativeOf = (n: Circle) => (n.parent?.data.kind === 'initiative' ? (n.parent.data as PolicyGroup).key : '');

  return (
    <div ref={wrapRef} className="relative" onMouseLeave={() => setHover(null)}>
      <svg
        viewBox={`${vb.x} ${vb.y} ${vb.s} ${vb.s}`}
        className="h-auto w-full touch-manipulation select-none"
        role="img"
        aria-label="一般会計の歳出の入れ子の円（施策別資料の事項を柱・取組で分けたものと、施策の円の外の経費。面積が予算額）。右の一覧からも選べます"
        onClick={() => onFocus(parentKey(focusNode))}
        // 押すと寄る先が変わり、ポインタの下の円も変わるので、前の円の説明を消す（円の onClick より先に）
        onClickCapture={() => setHover(null)}
        // 円の外（背景）に動いたら、前の円の説明を消す（円の上では円の onPointerMove が出し直す）
        onPointerMove={e => {
          if (e.target === e.currentTarget) setHover(null);
        }}
      >
        {nodes.map(n => {
          const d = n.data;
          if (d.kind === 'all') return null;
          if (d.kind === 'item') {
            const sel = selected === d.index;
            return (
              <circle
                key={`it:${d.index}`}
                cx={n.x}
                cy={n.y}
                r={Math.max(n.r, px(0.6))}
                fill={colorOf(d.item)}
                fillOpacity={selected === null || sel ? 0.9 : 0.5}
                stroke={sel ? '#111827' : '#ffffff'}
                strokeWidth={px(sel ? 2.5 : 0.75)}
                className="cursor-pointer"
                onClick={e => {
                  e.stopPropagation();
                  onSelect(d.index, initiativeOf(n));
                }}
                onPointerMove={e => showTip(e, d.name, formatBudgetFromYen(d.value))}
              />
            );
          }
          if (d.kind === 'outside') {
            const sel = selectedOutside === d.key;
            return (
              <circle
                key={`o:${d.key}`}
                cx={n.x}
                cy={n.y}
                r={n.r}
                fill={MUTED_COLOR}
                fillOpacity={sel ? 0.75 : 0.45}
                stroke={sel ? '#111827' : '#ffffff'}
                strokeWidth={px(sel ? 2.5 : 1)}
                className="cursor-pointer"
                onClick={e => {
                  e.stopPropagation();
                  onOutside(d.key);
                }}
                onPointerMove={e => showTip(e, d.label, `${formatBudgetFromYen(d.amount)}（施策の円の外の経費）`)}
              />
            );
          }
          const isFocus = focusNode === n;
          return (
            <circle
              key={d.key}
              cx={n.x}
              cy={n.y}
              r={n.r}
              fill={d.kind === 'root' ? '#f8fafc' : d.kind === 'pillar' ? '#eef2f7' : '#ffffff'}
              fillOpacity={0.9}
              stroke={isFocus ? '#0f766e' : '#cbd5e1'}
              strokeWidth={px(isFocus ? 2 : 1)}
              className={isFocus ? 'cursor-zoom-out' : 'cursor-zoom-in'}
              onClick={e => {
                e.stopPropagation();
                onFocus(isFocus ? parentKey(n) : d.key);
              }}
              onPointerMove={e => showTip(e, d.kind === 'root' ? '施策別資料の事項' : d.name, formatBudgetFromYen(n.value ?? 0))}
            />
          );
        })}
        <g pointerEvents="none">
          {nodes.map(n => {
            const d = n.data;
            const rpx = n.r * pxPerUnit;
            const text = (x: number, y: number, s: string, fs: number, cls: string, key: string) => (
              <text
                key={key}
                x={x}
                y={y}
                textAnchor="middle"
                dominantBaseline="middle"
                fontSize={px(fs)}
                className={cls}
                stroke="#ffffff"
                strokeWidth={px(3)}
                paintOrder="stroke"
              >
                {s}
              </text>
            );
            if (d.kind === 'outside') {
              const l = fitLabel(d.label.replace(/（.*$/, ''), rpx, 12);
              if (!l) return null;
              return (
                <g key={`lo:${d.key}`}>
                  {text(n.x, n.y - px(8), l, 12, 'fill-slate-700', 'a')}
                  {text(n.x, n.y + px(9), formatBudgetFromYen(d.amount), 12, 'fill-slate-600', 'b')}
                </g>
              );
            }
            // 施策の円・柱の円の名前は円の上端に（寄っている円の中のものだけ）
            if (d.kind === 'root' || d.kind === 'pillar') {
              if (focusNode && focusNode !== n && !(d.kind === 'pillar' && focusNode.data.kind === 'root')) return null;
              if (rpx < 50) return null;
              const name = d.kind === 'root' ? `施策別資料の事項 ${formatBudgetFromYen(n.value ?? 0)}` : d.name;
              // 上端の近くでは円が狭いので、字の上端の高さでの円の幅（弦）に収まる字数で切る（はみ出して隣の円を隠さないよう）
              const l = fitWidth(name, chordPx(rpx, TOP_LABEL_DEPTH - 7), 13);
              return l ? text(n.x, n.y - n.r + px(TOP_LABEL_DEPTH), l, 13, 'fill-slate-600 font-bold', `l:${d.key}`) : null;
            }
            if (d.kind === 'initiative') {
              if (rpx < 34 || (focusNode && focusNode === n)) return null;
              const l = fitLabel(d.name, rpx, 11);
              return l ? text(n.x, n.y, l, 11, 'fill-slate-800', `l:${d.key}`) : null;
            }
            if (d.kind === 'item') {
              // 事項の名前は取組に寄っているときだけ（柱に寄っているときは取組の名前を円の真ん中に出すので、重ねない）
              if (!focusNode || focusNode.data.kind !== 'initiative' || rpx < 22) return null;
              const l = fitLabel(d.name, rpx, 11);
              return l ? text(n.x, n.y, l, 11, 'fill-slate-900', `li:${d.index}`) : null;
            }
            return null;
          })}
        </g>
      </svg>

      {hover && (
        <div
          className="pointer-events-none absolute z-10 max-w-64 rounded-md border border-mirai-border bg-card px-2 py-1 text-xs shadow-soft"
          style={{ left: Math.max(0, Math.min(hover.x + 12, width - TIP_WIDTH)), top: hover.y + 12 }}
        >
          <div className="font-bold">{hover.title}</div>
          <div className="text-mirai-text-muted">{hover.sub}</div>
        </div>
      )}
    </div>
  );
}
