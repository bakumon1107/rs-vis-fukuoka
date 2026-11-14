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


def mark(rec: dict, tris: list[dict]) -> int:
    n = 0
    for tri in tris:
        cy = (tri["y0"] + tri["y1"]) / 2
        best = None
        for t in rec.get("tables", []):
            vl = t.get("vlines") or rec["vlines"]
            for ci, col in enumerate(t["cols"]):
                lo, hi = vl[ci], vl[ci + 1]
                if not (lo <= tri["x0"] < hi):
                    continue
                for d in col:
                    if not NUM.match(d["text"]) or d["x0"] < tri["x1"] - 5:
                        continue
                    if not (d["y0"] - 15 <= cy <= d["y1"] + 15):
                        continue
                    if best is None or d["x0"] < best["x0"]:
                        best = d
        if best is not None and not best["text"].startswith("△"):
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
            n = mark(rec, tris) if tris else 0
            if tris:
                print(f"p{pno}: △ {len(tris)} 個のうち {n} 個を数字に付けた", file=sys.stderr)
            total += n
            with open(os.path.join(outdir, f"p{pno:04d}.json"), "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False)
    print(f"△ を付けた数字 {total} 個", file=sys.stderr)


if __name__ == "__main__":
    main()
