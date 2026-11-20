"""画像だけの PDF のページを OCR し、行ごとのテキスト（pdftotext -layout に近い形）にして保存する。

財産に関する調書の基金の表（画像の年度: H24・H26〜H29・R1・R3・R4）を、テキストの年度と同じ抜き出し（extract_funds.py）に
かけるために使う。説明書の表（ocr_pages.py。縦線の本数が決まった表）とは違い、表の形を仮定しない。

使い方:
    PYLIB=$D/pylib3 python3 -P scripts/local-gov/fukuoka-pref/ocr/ocr_lines.py <PDF> <出力ディレクトリ> <PDFページ範囲 例 59-70>
出力: <出力ディレクトリ>/p0059.txt …（1行 = 高さの近い文字枠を左から並べたもの。文字枠の間は3つ以上の空白）。既にあるページは飛ばす
エンジン: ocr_pages.make_engine（PP-OCRv6 の日本語。OCR_ENGINE で切り替え）。▲ を読み落とすことがあるので、符号は
extract_funds.py が検算（前年度末 + 増減 = 年度末）で確かめる
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ocr_pages import make_engine, ocr_region, render  # noqa: E402  （ocr_pages が PYLIB を sys.path に足す）
import cv2  # noqa: E402


def to_lines(items: list[dict]) -> list[str]:
    """文字枠を行にまとめる。中心の高さの差が、枠の高さの中央値の半分以内なら同じ行"""
    if not items:
        return []
    hs = sorted(d["y1"] - d["y0"] for d in items)
    tol = max(6, hs[len(hs) // 2] / 2)
    rows: list[list[dict]] = []
    for d in sorted(items, key=lambda d: (d["y0"] + d["y1"]) / 2):
        cy = (d["y0"] + d["y1"]) / 2
        if rows and abs(cy - rows[-1][-1]["cy"]) <= tol:
            rows[-1].append({**d, "cy": cy})
        else:
            rows.append([{**d, "cy": cy}])
    return ["   ".join(d["text"] for d in sorted(r, key=lambda d: d["x0"])) for r in rows]


def main():
    pdf, outdir, rng = sys.argv[1], sys.argv[2], sys.argv[3]
    a, b = (int(x) for x in rng.split("-"))
    os.makedirs(outdir, exist_ok=True)
    eng = make_engine(int(os.environ.get("OCR_THREADS", "5")))
    with tempfile.TemporaryDirectory() as tmp:
        for p in range(a, b + 1):
            out = os.path.join(outdir, f"p{p:04d}.txt")
            if os.path.exists(out):
                continue
            img = cv2.imread(render(pdf, p, 300, tmp), cv2.IMREAD_GRAYSCALE)
            h, w = img.shape
            lines = to_lines(ocr_region(eng, img, 0, 0, w, h))
            with open(out + ".partial", "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            os.replace(out + ".partial", out)
            print(f"p{p}: {len(lines)} 行", file=sys.stderr)


if __name__ == "__main__":
    main()
