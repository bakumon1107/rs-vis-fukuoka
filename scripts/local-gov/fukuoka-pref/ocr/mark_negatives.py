"""OCR の結果に、発行元の文字層の減額の印（△）を付け足す（補正予算の説明書の前処理）。

補正予算の説明書（R8 9月第3号 298930）では、減額は数字の左に離れて印字された △ で示される（「△ 1,609」）。
OCR（PP-OCRv6・v4）はどちらも △ を読まず、数字だけを正の値として読む（R8 p28 の河川改良費で財源内訳・節の合計が合わなかった実例）。
文字層（画像に発行元が付けた OCR 層）には △ が単独の語として入っているので、同じ行・同じ欄で △ の右にある最も近い
OCR の数字の頭に「△」を付ける。付けた数は stderr に出す。△ のない数字には触らない。

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/ocr/mark_negatives.py <説明書.pdf> <OCR の出力ディレクトリ> <出力ディレクトリ> <ページ範囲>
"""
import json
import os
import re
import sys

import pdfplumber

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from textlayer_pages import calibrate, merged_words  # noqa: E402

NUM = re.compile(r"^[\d,，.\s]+$")


def mark(rec: dict, tris: list[dict], unplaced: list | None = None) -> int:
    """文字層の △ を、同じ行・同じ欄のすぐ右の OCR の数字に付ける。付けた数を返す。付ける数字のない △ は unplaced に入れる"""
    n = 0
    for tri in tris:
        cy = (tri["y0"] + tri["y1"]) / 2
        same = []  # 同じ行（数字の文字枠の高さに △ の中心が入る）の、△ より右の数字
        for t in rec.get("tables", []):
            vl = t.get("vlines") or rec["vlines"]
            for ci, col in enumerate(t["cols"]):
                lo, hi = vl[ci], vl[ci + 1]
                if not (lo <= tri["x0"] < hi):
                    continue
                for d in col:
                    if not NUM.match(d["text"]) or d["x0"] < tri["x1"] - 5:
                        continue
                    if d["y0"] <= cy <= d["y1"]:
                        same.append(d)
        # 同じ行の数字だけに付ける。同じ行の数字を OCR が読めなかったとき、上下の行の数字に付けると別の金額を減額にするので、
        # 付けずに知らせる（unplaced。目の検算で符号の誤りとして見つかる）
        if not same:
            if unplaced is not None:
                unplaced.append(tri)
            continue
        best = min(same, key=lambda d: d["x0"])
        if not best["text"].startswith("△"):
            best["text"] = "△" + best["text"]
            n += 1
    return n


def main():
    pdf_path, ocr_dir, outdir, rng = sys.argv[1:5]
    a, b = (int(x) for x in rng.split("-"))
    os.makedirs(outdir, exist_ok=True)
    total = 0
    with pdfplumber.open(pdf_path) as pdf:
        for pno in range(a, b + 1):
            src = os.path.join(ocr_dir, f"p{pno:04d}.json")
            if not os.path.exists(src):
                continue
            rec = json.load(open(src, encoding="utf-8"))
            page = pdf.pages[pno - 1]
            scale = rec["size"][0] / float(page.width)
            words = merged_words(page, scale)
            calibrate(words, rec)
            tris = [w for w in words if w["text"].strip() in ("△", "▲")]
            unplaced: list = []
            n = mark(rec, tris, unplaced) if tris else 0
            if tris:
                print(f"p{pno}: △ {len(tris)} 個のうち {n} 個を数字に付けた", file=sys.stderr)
            for tri in unplaced:
                print(f"WARN p{pno}: 同じ行に数字のない △（x {tri['x0']:.0f}・y {tri['y0']:.0f}）。付けない（画像で確かめる）", file=sys.stderr)
            total += n
            with open(os.path.join(outdir, f"p{pno:04d}.json"), "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False)
    print(f"△ を付けた数字 {total} 個", file=sys.stderr)


if __name__ == "__main__":
    main()
