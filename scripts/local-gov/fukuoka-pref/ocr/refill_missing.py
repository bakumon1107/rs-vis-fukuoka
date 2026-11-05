"""本年度が読めなかった目について、本年度のセルだけを拡大して OCR し直し、OCR 結果の JSON に書き足す。

小さな「1」1文字（本年度 1 千円の科目: 証紙収入・繰越金など）は、ページ単位の文字検出では拾えないことがある。
セルを切り出して 3 倍に拡大し、余白を付けて読み直す。読めた値は「refill: true」の印を付けて列に足すので、
parse_setsumeisho.py を再実行すると検算（比較・款の合計）で正しさが確かめられる。

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/ocr/refill_missing.py <説明書.pdf> <OCR出力ディレクトリ> <setsumeisho.json>
"""
import json
import os
import subprocess
import sys
import tempfile

if os.environ.get("PYLIB"):
    sys.path.insert(0, os.environ["PYLIB"])
import cv2  # noqa: E402
from rapidocr_onnxruntime import RapidOCR  # noqa: E402


def main():
    pdf, ocr_dir, parsed = sys.argv[1:4]
    ms = json.load(open(parsed, encoding="utf-8"))
    targets = [m for m in ms if m["kind"] == "目" and m["本年度"] is None and m.get("cell")]
    print(f"本年度が読めなかった目: {len(targets)}", file=sys.stderr)
    eng = RapidOCR(use_cls=False)
    with tempfile.TemporaryDirectory() as tmp:
        for m in targets:
            c = m["cell"]
            path = os.path.join(ocr_dir, f"p{c['page']:04d}.json")
            rec = json.load(open(path, encoding="utf-8"))
            base = os.path.join(tmp, "p")
            subprocess.run(["pdftoppm", "-r", str(rec["dpi"]), "-gray", "-png", "-f", str(c["page"]), "-l", str(c["page"]),
                            "-singlefile", pdf, base], check=True)
            img = cv2.imread(base + ".png", cv2.IMREAD_GRAYSCALE)
            raw = img[c["y0"] + 4:c["y1"] - 4, c["x0"] + 6:c["x1"] - 6]
            # 1) 3倍に拡大。2) かすれた文字（R8 p415 の「1」は「一」と読まれた）向けに大津の二値化をしてから2倍
            _, bw = cv2.threshold(raw, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            res, scale = None, 3
            for scale, variant in ((3, cv2.resize(raw, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)),
                                   (2, cv2.resize(bw, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST))):
                crop = cv2.copyMakeBorder(variant, 60, 60, 60, 60, cv2.BORDER_CONSTANT, value=255)
                res, _ = eng(crop)
                if res and any(ch.isdigit() for _, t, _ in res for ch in t):
                    break
            found = []
            for box, text, score in res or []:
                ys = [p[1] for p in box]
                y = int((min(ys) - 60) / scale) + 4 + c["y0"]
                found.append({"y0": y, "y1": y + 30, "x0": c["x0"] + 10, "x1": c["x1"] - 10,
                              "text": text, "score": round(float(score), 3), "refill": True})
            print(f"p{c['page']} {m['目名']}: {[f['text'] for f in found]}", file=sys.stderr)
            if not found:
                continue
            # どの表のどの列か: 本年度の列（cols[1]）に足す。該当する表は y の範囲で選ぶ
            for t in rec["tables"]:
                if t["box"][1] <= c["y0"] <= t["box"][3]:
                    t["cols"][1] = [d for d in t["cols"][1] if not d.get("refill")] + found
                    break
            with open(path, "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False)


main()
