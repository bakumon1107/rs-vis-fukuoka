/**
 * グラフのツールチップの位置（表示専用の計算。地方版の三基金のグラフ・財政の指標の小さなグラフで使う）。
 * 点が右半分なら左に、左半分なら右に寄せる（点の近くの線を隠さないように）。図の幅からはみ出さないように詰める
 */
export function tipStyle(px: number, W: number, width: number, padL: number, padR: number, top: number) {
  const want = px > W / 2 ? padL : W - padR - width;
  return { width, left: Math.max(0, Math.min(want, W - width)), top };
}
