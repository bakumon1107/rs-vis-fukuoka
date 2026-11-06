"""読めなかった数字のセルだけを拡大して OCR し直し、OCR 結果の JSON に書き足す。

小さな「1」1文字（1 千円の科目: 証紙収入・繰越金・利子割精算金など）は、列単位の文字検出では拾えないことがある。
セルを切り出して 3 倍に拡大し、余白を付けて読み直す（かすれた文字は大津の二値化をしてから 2 倍）。
読めた値は「refill: true」の印を付けて列に足すので、parse_setsumeisho.py を再実行すると
検算（比較・節の合計・項と款の合計）で正しさが確かめられる。

対象（目ごと）:
- 本年度・前年度・比較が読めなかった（None。ただし空欄を 0 とみなして C が成り立ったものは除く）
- 節の区分の文字が欄にあるのに節の金額が1つも読めなかった（欄がもともと空の目は対象外）

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/ocr/refill_missing.py <説明書.pdf> <OCR出力ディレクトリ> <setsumeisho.json>
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

if os.environ.get("PYLIB"):
    for p in reversed(os.environ["PYLIB"].split(":")):
        sys.path.insert(0, p)
import cv2  # noqa: E402

_spec = importlib.util.spec_from_file_location("ocr_pages", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ocr_pages.py"))
ocr_pages = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ocr_pages)

# 表の元の列番号（歳出 11列 / 歳入 7列）
COLS = {"歳出": {"本年度": 1, "前年度": 2, "比較": 3, "節": 9}, "歳入": {"本年度": 1, "前年度": 2, "比較": 3, "節": 5}}


def targets_of(m):
    out = []
    for k in ("本年度", "前年度", "比較"):
        if m.get(k) is None:
            out.append(k)
    # 節の金額は、節の区分の文字が欄にあるのに金額が1つも読めないときだけ読み直す。
    # 節の欄がもともと空の目（予備費）を読み直すと、ないはずの「1」を拾った実例（R8 281299 p119 住宅管理の予備費）
    if (m.get("節") is not None and not any(s.get("amount") for s in m["節"]) and m.get("本年度") not in (None, 0)
            and m.get("節の欄の文字数", 0) > 0):
        out.append("節")
    return out


def main():
    pdf, ocr_dir, parsed = sys.argv[1:4]
    ms = json.load(open(parsed, encoding="utf-8"))
    todo = [(m, k) for m in ms if m["kind"] == "目" and m.get("cell") for k in targets_of(m)]
    print(f"読み直すセル: {len(todo)}", file=sys.stderr)
    eng = ocr_pages.make_engine(int(os.environ.get("OCR_THREADS", "4")))
    with tempfile.TemporaryDirectory() as tmp:
        for m, key in todo:
            c = m["cell"]
            path = os.path.join(ocr_dir, f"p{c['page']:04d}.json")
            rec = json.load(open(path, encoding="utf-8"))
            table = next((t for t in rec["tables"] if t["box"][1] <= c["y0"] <= t["box"][3]), None)
            if table is None:
                continue
            vl = table.get("vlines") or rec["vlines"]
            ci = COLS[m["side"]][key]
            if ci + 1 >= len(vl):
                continue
            x0, x1 = vl[ci], vl[ci + 1]
            base = os.path.join(tmp, "p")
            subprocess.run(["pdftoppm", "-r", str(rec["dpi"]), "-gray", "-png", "-f", str(c["page"]), "-l", str(c["page"]),
                            "-singlefile", pdf, base], check=True)
            img = cv2.imread(base + ".png", cv2.IMREAD_GRAYSCALE)
            raw = img[c["y0"] + 4:c["y1"] - 4, x0 + 6:x1 - 6]
            if raw.size == 0:
                continue
            _, bw = cv2.threshold(raw, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            res, scale = [], 3
            for scale, variant in ((3, cv2.resize(raw, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)),
                                   (2, cv2.resize(bw, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST))):
                crop = cv2.copyMakeBorder(variant, 60, 60, 60, 60, cv2.BORDER_CONSTANT, value=255)
                res = eng(crop)
                if res and any(ch.isdigit() for _, t, _ in res for ch in t):
                    break
            found = []
            for box, text, score in res or []:
                ys = [p[1] for p in box]
                y = int((min(ys) - 60) / scale) + 4 + c["y0"]
                found.append({"y0": y, "y1": y + 30, "x0": x0 + 10, "x1": x1 - 10,
                              "text": text, "score": round(float(score), 3), "refill": True})
            print(f"p{c['page']} {m['目名']} {key}: {[f['text'] for f in found]}", file=sys.stderr)
            if not found:
                continue
            col = table["cols"][ci]
            # 同じ高さの範囲に以前の読み直し結果があれば置き換える
            table["cols"][ci] = [d for d in col if not (d.get("refill") and c["y0"] <= d["y0"] <= c["y1"])] + found
            with open(path, "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False)


main()
