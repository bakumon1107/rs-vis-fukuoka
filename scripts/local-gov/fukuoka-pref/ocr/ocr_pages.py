"""予算に関する説明書（スキャン画像 PDF）のページを、罫線で列に分けて OCR し、結果を JSON に保存する。

OCR は時間がかかるので、この段階では「どの列の、どの高さに、どんな文字列があったか」だけを保存し、
表の解釈と検算は別のスクリプト（parse_setsumeisho.py）で行う。結果を使い回せるようにするため。

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/ocr/ocr_pages.py <説明書.pdf> <出力ディレクトリ> <PDFページ範囲 例 121-420> [--dpi 300]

必要なパッケージ: rapidocr（3.x。OCR_ENGINE=v4ch なら rapidocr-onnxruntime）, onnxruntime, opencv-python-headless, numpy（PYLIB 環境変数のディレクトリを sys.path に足す）
出力: <出力ディレクトリ>/p0123.json  … {page, dpi, size, vlines, hlines, title:[...], cols:[[{y,x,text,score}...], ...]}
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

if os.environ.get("PYLIB"):
    sys.path.insert(0, os.environ["PYLIB"])
import cv2  # noqa: E402
import numpy as np  # noqa: E402


def make_engine(threads: int):
    """OCR エンジンを作り、「画像 → [(枠, 文字列, 確からしさ), ...]」の関数を返す。

    OCR_ENGINE=v6（既定）: rapidocr 3.x の PP-OCRv6 small（日本語を含む多言語の認識モデル）。
    OCR_ENGINE=v4ch: rapidocr_onnxruntime 1.4 の中国語モデル（最初に使ったもの）。
    中国語モデルは日本の字形（総・繰・譲・災・県 など）を持たず、黙って落とすか簡体字に置き換える
    （「総務費」→「務費」、「繰入金」→「入金」の実例）。金額の検算では見つからないので、名称を使うなら v6 を使う。
    検出（文字の枠）はどちらも PP-OCRv4 の中国語モデルで同じ。"""
    if os.environ.get("OCR_ENGINE", "v6") == "v4ch":
        from rapidocr_onnxruntime import RapidOCR
        # 既定の det_limit_type=min（短い辺を 736px に拡大）だと、細長い列の切り出しが数倍に引き伸ばされて非常に遅い
        # （幅 250px × 高さ 1,700px → 高さ 5,000px 級）。長い辺の上限で縮めるだけにする。
        eng = RapidOCR(det_limit_type="max", det_limit_side_len=2400, use_cls=False,
                       intra_op_num_threads=threads, inter_op_num_threads=1)
        return lambda img: eng(img)[0] or []
    from rapidocr import LangDet, LangRec, ModelType, OCRVersion, RapidOCR
    eng = RapidOCR(params={
        "Global.use_cls": False, "Global.log_level": "error",
        # 既定の max_side_len=2000 だと縦長の列（高さ 1,700px 超）が前処理で縮む
        "Global.max_side_len": 4000,
        "Det.ocr_version": OCRVersion.PPOCRV4, "Det.lang_type": LangDet.CH, "Det.model_type": ModelType.MOBILE,
        "Det.limit_type": "max", "Det.limit_side_len": 2400,
        "Rec.ocr_version": OCRVersion.PPOCRV6, "Rec.lang_type": LangRec.JAPAN, "Rec.model_type": ModelType.SMALL,
        "EngineConfig.onnxruntime.intra_op_num_threads": threads,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1})

    def run(img):
        r = eng(img)
        if r.boxes is None:
            return []
        return [(b.tolist(), t, s) for b, t, s in zip(r.boxes, r.txts, r.scores)]
    return run


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
    # 表ごとの縦線。1ページに歳入（7列）と歳出（11列）の表が並ぶことがあり（特別会計の小さな会計。R8 281299 p6）、
    # 行の少ない短い表はページ全体の基準（表の高さの合計の半分）に届かない。表ごとに、表の下端まで届く縦線を罫線とする
    # （列見出しの中だけの短い線は下端に届かない）
    vk2 = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 60))
    v2 = cv2.morphologyEx(bw, cv2.MORPH_OPEN, vk2)
    per_table = []
    for a, b in vspan:
        seg = v2[a:b + 1]
        cov2 = seg.sum(axis=0) / 255
        lines = []
        for g in merge(list(np.where(cov2 > 0)[0]), 8):
            best = max(g, key=lambda x: cov2[x])
            col = seg[:, best] > 0
            ys = np.where(col)[0]
            if len(ys) and ys[-1] >= (b - a) - 15 and cov2[best] >= (b - a) * 0.4:
                lines.append(int(best))
        l2 = []
        for x in lines:
            if l2 and x - l2[-1] < 45:
                l2[-1] = x if cov2[x] > cov2[l2[-1]] else l2[-1]
                continue
            l2.append(x)
        per_table.append(l2)
    return vlines, merged, vspan, per_table


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
    out = []
    for box, text, score in eng(crop):
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
    # 回転の判定（cls）は横書きの表には不要。スレッド数は並列実行で取り合わないよう絞る。
    eng = make_engine(int(os.environ.get("OCR_THREADS", "5")))
    with tempfile.TemporaryDirectory() as tmp:
        for page in range(a, b + 1):
            dst = os.path.join(outdir, f"p{page:04d}.json")
            if os.path.exists(dst):
                continue
            t0 = time.time()
            png = render(pdf, page, dpi, tmp)
            img = cv2.imread(png, cv2.IMREAD_GRAYSCALE)
            h, w = img.shape
            vlines, hlines, spans, per_table = detect_lines(img)
            rec = {"page": page, "dpi": dpi, "size": [w, h], "vlines": vlines, "hlines": hlines, "tables": []}
            if spans and (len(vlines) >= 6 or any(len(t) >= 6 for t in per_table)):
                prev_bottom = 0
                for (vtop, vbottom), tv in zip(spans, per_table):
                    # 長い表では行の区切りで縦線が途切れ、表ごとの基準（下端まで届く）では本数が減る（一般会計 p131 で 12→10）。
                    # 表ごとの本数がページ共通の本数以上のときだけ表ごとの線を使う
                    if len(tv) < max(6, len(vlines)):
                        if len(vlines) < 6:
                            continue  # 表ではない（枠だけの囲みなど）
                        tv = vlines
                    width = tv[-1] - tv[0]
                    # 列見出しの下の線: 表の上端より下で、表の幅いっぱいに引かれた最初の横線
                    full = [d["y"] for d in hlines if d["x1"] - d["x0"] > width * 0.9 and vtop + 20 < d["y"] < vbottom]
                    head = min(full) if full else vtop
                    header = ocr_region(eng, img, tv[0], vtop, tv[-1], head)
                    # 前のページから続く表には列見出しがない（R8 一般会計 p151 で確認）。最初の全幅の線は目の区切り。
                    # 見出し語がなければ表の上端から本文として読む（見出しと誤認すると前の目の節を取りこぼす）
                    htext = "".join(d["text"] for d in header)
                    if not re.search(r"年度|区分|説明|節|款名|財源", htext) or head - vtop > 400:
                        head, header = vtop, []
                    t = {"box": [tv[0], vtop, tv[-1], vbottom], "head": head, "vlines": tv,
                         "title": ocr_region(eng, img, 0, prev_bottom, w, vtop + 4),
                         "header": header,
                         "rowlines": [d for d in hlines if head < d["y"] < vbottom - 4],
                         "cols": [ocr_column(eng, img, x0, head + 4, x1, vbottom - 4)
                                  for x0, x1 in zip(tv, tv[1:])]}
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
