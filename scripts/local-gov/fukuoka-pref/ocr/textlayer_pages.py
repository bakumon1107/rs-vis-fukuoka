"""スキャン画像 PDF に発行元が付けた文字層（OCR 層）を、ocr_pages.py の出力と同じ形式で書き出す。

OCR（ocr_pages.py）とは独立したもう1つの読み取りとして使う。表の構造（縦線・表の範囲・区画の横線・見出し）は
ocr_pages.py の出力をそのまま借り、各列の中身だけを文字層の単語に置き換える。
同じ parse_setsumeisho.py にかけると、もう1通りの解釈・検算の結果ができるので、目ごとに比べられる。

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/ocr/textlayer_pages.py <説明書.pdf> <ocr_pages の出力ディレクトリ> <出力ディレクトリ> <ページ範囲>

文字層の癖（福岡県 R8 281298.pdf）:
- 金額が2語に割れることがある（「14,907,」「192」）。同じ行で隣り合う数字の断片はつなぐ
- 名前の字は崩れている（使うのは数字だけと考える）
- 座標はポイント（ページ幅 842pt）。画像（300dpi・3508px）に合わせて 300/72 倍する
"""
import json
import os
import re
import sys

import pdfplumber


def merged_words(page, scale):
    ws = page.extract_words(x_tolerance=1.5, y_tolerance=2, keep_blank_chars=False)
    ws.sort(key=lambda w: (round(w["top"]), w["x0"]))
    out = []
    for w in ws:
        d = {"x0": w["x0"] * scale, "x1": w["x1"] * scale, "y0": w["top"] * scale, "y1": w["bottom"] * scale,
             "text": w["text"], "score": 1.0, "textlayer": True}
        prev = out[-1] if out else None
        # 数字の断片（「14,907,」+「192」）: 同じ高さ・隙間 4pt 未満・両方が数字とカンマだけ
        if (prev and abs(prev["y0"] - d["y0"]) < 3 * scale and 0 <= d["x0"] - prev["x1"] < 4 * scale
                and re.fullmatch(r"[\d,]+", prev["text"]) and re.fullmatch(r"[\d,]+", d["text"])
                and (prev["text"].endswith(",") or d["text"].startswith(","))):
            prev["text"] += d["text"]
            prev["x1"] = d["x1"]
            continue
        out.append(d)
    return out


def calibrate(words, rec):
    """文字層の座標と画像（OCR）の座標のずれを、ページごとに測って直す。
    文字層は画像に対して右に 10〜15px（300dpi）ずれている（R8 281298 p239 で「452」の右端が OCR 1907・文字層 1921）。
    列の境目の近くにある右寄せの小さな数字（「1」）が隣の列に入る原因になった（財源の「その他」の 1 が一般財源に入り、
    別の誤りと打ち消し合って検算を通った実例）。OCR と同じ文字列の数字（4文字以上）を対応させ、ずれの中央値を引く。"""
    ocr_words = [d for t in rec.get("tables", []) for col in t["cols"] for d in col
                 if re.fullmatch(r"[\d,]{4,}", d["text"])]
    by_text = {}
    for d in ocr_words:
        by_text.setdefault(d["text"], []).append(d)
    dxs, dys = [], []
    for w in words:
        cands = by_text.get(w["text"])
        if not cands:
            continue
        c = min(cands, key=lambda d: abs(d["x1"] - w["x1"]) + abs(d["y0"] - w["y0"]))
        if abs(c["x1"] - w["x1"]) < 60 and abs(c["y0"] - w["y0"]) < 60:
            dxs.append(w["x1"] - c["x1"])
            dys.append(w["y0"] - c["y0"])
    if len(dxs) < 3:
        return 0.0, 0.0
    dxs.sort()
    dys.sort()
    dx, dy = dxs[len(dxs) // 2], dys[len(dys) // 2]
    # ずれを測ったのは数字だけ。名前（節の区分など）は動かさない（動かすと、字下げで見分ける細節が
    # すべて節と判定された実例。名前の文字はずれ方が違う）
    for w in words:
        if not re.fullmatch(r"[\d,]+", w["text"]):
            continue
        w["x0"] -= dx
        w["x1"] -= dx
        w["y0"] -= dy
        w["y1"] -= dy
    return dx, dy


def main():
    pdf_path, ocr_dir, outdir, rng = sys.argv[1:5]
    a, b = (int(x) for x in rng.split("-"))
    os.makedirs(outdir, exist_ok=True)
    with pdfplumber.open(pdf_path) as pdf:
        for pno in range(a, b + 1):
            src = os.path.join(ocr_dir, f"p{pno:04d}.json")
            if not os.path.exists(src):
                continue
            rec = json.load(open(src, encoding="utf-8"))
            page = pdf.pages[pno - 1]
            scale = rec["size"][0] / float(page.width)
            words = merged_words(page, scale)
            dx, dy = calibrate(words, rec)
            rec["textlayer_offset"] = [round(dx, 1), round(dy, 1)]
            for t in rec.get("tables", []):
                vl = t.get("vlines") or rec["vlines"]
                y_top, y_bot = t["head"] + 4, t["box"][3] - 4
                cols = []
                for x0, x1 in zip(vl, vl[1:]):
                    cols.append([w for w in words if x0 <= (w["x0"] + w["x1"]) / 2 <= x1
                                 and y_top <= (w["y0"] + w["y1"]) / 2 <= y_bot])
                t["cols"] = cols
                # 見出し（款・項）は OCR の方が読める。文字層の見出しは参考に別に持つ
                t["title_textlayer"] = [w for w in words if (w["y0"] + w["y1"]) / 2 < t["box"][1]]
            rec["source"] = "textlayer"
            with open(os.path.join(outdir, f"p{pno:04d}.json"), "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
