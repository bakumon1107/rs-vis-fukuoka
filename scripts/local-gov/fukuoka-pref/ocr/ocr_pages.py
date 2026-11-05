"""予算に関する説明書（スキャン画像 PDF）のページを、罫線で列に分けて OCR し、結果を JSON に保存する。

OCR は時間がかかるので、この段階では「どの列の、どの高さに、どんな文字列があったか」だけを保存し、
表の解釈と検算は別のスクリプト（parse_setsumeisho.py）で行う。結果を使い回せるようにするため。

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/ocr/ocr_pages.py <説明書.pdf> <出力ディレクトリ> <PDFページ範囲 例 121-420> [--dpi 300]

必要なパッケージ: rapidocr-onnxruntime, opencv-python-headless, numpy（PYLIB 環境変数のディレクトリを sys.path に足す）
出力: <出力ディレクトリ>/p0123.json  … {page, dpi, size, vlines, hlines, title:[...], cols:[[{y,x,text,score}...], ...]}
"""
import json
import os
import subprocess
import sys
import tempfile
import time

if os.environ.get("PYLIB"):
    sys.path.insert(0, os.environ["PYLIB"])
import cv2  # noqa: E402
import numpy as np  # noqa: E402
from rapidocr_onnxruntime import RapidOCR  # noqa: E402


def render(pdf: str, page: int, dpi: int, tmp: str) -> str:
    base = os.path.join(tmp, f"p{page}")
    subprocess.run(["pdftoppm", "-r", str(dpi), "-gray", "-png", "-f", str(page), "-l", str(page), "-singlefile", pdf, base],
                   check=True)
    return base + ".png"


def merge(a, gap):
    out = []
    for x in a:
        if out and x - out[-1][-1] <= gap:
            out[-1].append(x)
        else:
            out.append([x])
    return out


def detect_lines(img):
    """縦線の x と、横線（x 方向の範囲つき）を返す。"""
    h, w = img.shape
    bw = cv2.adaptiveThreshold(255 - img, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 15, -2)
    # 縦線: 高さの 1/20（300dpi で約 120px ≒ 1cm）以上連続するもの。文字の縦画（40px 程度）は残らない
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, h // 20))
    v = cv2.morphologyEx(bw, cv2.MORPH_OPEN, vk)
    # 縦線が引かれている高さの範囲＝表。1ページに複数の表がある（項がページ途中で変わる）ので、
    # 縦線が 40px 以上途切れるところで表を分ける
    rows = list(np.where(v.sum(axis=1) > 0)[0])
    vspan = [(int(g[0]), int(g[-1])) for g in merge(rows, 40) if g[-1] - g[0] > 60] if rows else []
    total_h = sum(b - a for a, b in vspan) or h
    # 罫線＝表の高さの合計の半分以上にわたって引かれている縦線。列見出しの中の短い線（財源内訳の区切りなど）は除く。
    # 短い線を罫線と取り違えると列の境界がずれ、右寄せの数字の末尾が欠ける（実例あり）
    cov = v.sum(axis=0) / 255
    cand = [g for g in merge(list(np.where(cov > 0)[0]), 8)]
    vlines = []
    for g in cand:
        best = max(g, key=lambda x: cov[x])
        if cov[best] >= total_h * 0.5:
            vlines.append(int(best))
    # 二重線（30px 程度の間隔）は、列として扱わないよう外側の1本にまとめる
    vl2 = []
    for x in vlines:
        if vl2 and x - vl2[-1] < 45:
            vl2[-1] = x if cov[x] > cov[vl2[-1]] else vl2[-1]
            continue
        vl2.append(x)
    vlines = vl2
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (w // 30, 1))
    hz = cv2.morphologyEx(bw, cv2.MORPH_OPEN, hk)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(hz, connectivity=8)
    hlines = []
    for i in range(1, n):
        x, y, ww, hh, _ = stats[i]
        if ww >= w // 30 and hh <= 25:
            hlines.append({"y": int(y + hh // 2), "x0": int(x), "x1": int(x + ww)})
    hlines.sort(key=lambda d: (d["y"], d["x0"]))
    # 同じ高さで途切れた線をつなぐ
    merged = []
    for d in hlines:
        if merged and abs(d["y"] - merged[-1]["y"]) <= 4 and d["x0"] <= merged[-1]["x1"] + 20:
            merged[-1]["x1"] = max(merged[-1]["x1"], d["x1"])
            merged[-1]["x0"] = min(merged[-1]["x0"], d["x0"])
        else:
            merged.append(dict(d))
    return vlines, merged, vspan


def ocr_column(eng, img, x0, y0, x1, y1, margin=-5):
    """列を左右に margin だけ広く切り出して OCR し、文字枠の中心が列の中にあるものだけを残す。
    数字は右寄せで縦線のすぐ近くまで印字されているため、列ちょうどで切ると末尾の桁が欠ける（実例あり）。"""
    items = ocr_region(eng, img, x0 - margin, y0, x1 + margin, y1)
    return [d for d in items if x0 <= (d["x0"] + d["x1"]) / 2 <= x1]


def ocr_region(eng, img, x0, y0, x1, y1):
    x0, y0 = max(0, x0), max(0, y0)
    crop = img[y0:y1, x0:x1]
    if crop.size == 0 or crop.shape[0] < 8 or crop.shape[1] < 8:
        return []
    # 余白を足すと端の文字の検出が安定する
    crop = cv2.copyMakeBorder(crop, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)
    res, _ = eng(crop)
    out = []
    for box, text, score in res or []:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        out.append({"y0": int(min(ys)) - 12 + y0, "y1": int(max(ys)) - 12 + y0,
                    "x0": int(min(xs)) - 12 + x0, "x1": int(max(xs)) - 12 + x0,
                    "text": text, "score": round(float(score), 3)})
    out.sort(key=lambda d: (d["y0"], d["x0"]))
    return out


def main():
    pdf, outdir, rng = sys.argv[1], sys.argv[2], sys.argv[3]
    dpi = int(sys.argv[sys.argv.index("--dpi") + 1]) if "--dpi" in sys.argv else 300
    a, b = (int(x) for x in rng.split("-"))
    os.makedirs(outdir, exist_ok=True)
    eng = RapidOCR()
    with tempfile.TemporaryDirectory() as tmp:
        for page in range(a, b + 1):
            dst = os.path.join(outdir, f"p{page:04d}.json")
            if os.path.exists(dst):
                continue
            t0 = time.time()
            png = render(pdf, page, dpi, tmp)
            img = cv2.imread(png, cv2.IMREAD_GRAYSCALE)
            h, w = img.shape
            vlines, hlines, spans = detect_lines(img)
            rec = {"page": page, "dpi": dpi, "size": [w, h], "vlines": vlines, "hlines": hlines, "tables": []}
            if len(vlines) >= 6 and spans:
                width = vlines[-1] - vlines[0]
                prev_bottom = 0
                for vtop, vbottom in spans:
                    # 列見出しの下の線: 表の上端より下で、表の幅いっぱいに引かれた最初の横線
                    full = [d["y"] for d in hlines if d["x1"] - d["x0"] > width * 0.9 and vtop + 20 < d["y"] < vbottom]
                    head = min(full) if full else vtop
                    t = {"box": [vlines[0], vtop, vlines[-1], vbottom], "head": head,
                         "title": ocr_region(eng, img, 0, prev_bottom, w, vtop + 4),
                         "header": ocr_region(eng, img, vlines[0], vtop, vlines[-1], head),
                         "rowlines": [d for d in hlines if head < d["y"] < vbottom - 4],
                         "cols": [ocr_column(eng, img, x0, head + 4, x1, vbottom - 4)
                                  for x0, x1 in zip(vlines, vlines[1:])]}
                    rec["tables"].append(t)
                    prev_bottom = vbottom
                rec["footer"] = ocr_region(eng, img, 0, prev_bottom, w, h)
            else:
                rec["page_text"] = ocr_region(eng, img, 0, 0, w, h)
            os.remove(png)
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False)
            print(f"p{page} tables={len(rec['tables'])} sec={time.time()-t0:.1f}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
