"""予算に関する説明書（スキャン画像 PDF）のページを、罫線で列に分けて OCR し、結果を JSON に保存する。

OCR は時間がかかるので、この段階では「どの列の、どの高さに、どんな文字列があったか」だけを保存し、
表の解釈と検算は別のスクリプト（parse_setsumeisho.py）で行う。結果を使い回せるようにするため。

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/ocr/ocr_pages.py <説明書.pdf> <出力ディレクトリ> <PDFページ範囲 例 121-420> [--dpi 300] [--redo-unknown]
    既にあるページは飛ばす。--redo-unknown は、見出しのない続きの表を前のページの結果なしで判定したページ（WARN が出る）だけ読み直す

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


# 予算に関する説明書の表の縦線の本数（福岡県。歳入 7列＝8本、歳出 11列＝12本）
VALID_LINE_COUNTS = (8, 12)


def union_vlines(tv, page_vlines, tol=45):
    """表ごとの線とページ共通の線がどちらも歳出の本数より1本少ないとき（それぞれ別の線を1本ずつ取りこぼした）、
    表ごとの線に、ページ共通の線のうち表ごとの線から tol px 以上離れたものを足す。それ以外は表ごとの線をそのまま返す。
    近い線は同じ線とみなし、表ごとの位置を使う（tol は二重線をまとめる間隔と同じ）。
    本数を絞るのは、様式の違う表（特別会計の総括の表は 9本・ページ共通 5本。R8 281299 p7）を、
    たまたま足して 12本になった線で切らないため。"""
    exp = VALID_LINE_COUNTS[1]
    if len(tv) != exp - 1 or len(page_vlines) != exp - 1:
        return list(tv)
    extra = [x for x in page_vlines if all(abs(x - y) >= tol for y in tv)]
    return sorted(list(tv) + extra)


def choose_vlines(tv, page_vlines, header_text, prev_cols):
    """表の縦線を、表ごとの線（tv）とページ共通の線（page_vlines）から選ぶ。表でなければ None。
    header_text: 列見出しの文字（見出しのない続きの表は None）。prev_cols: 直前の表の列数（なければ None）。
    規則と実例は main のコメント（R8 281299 p9・p45・p51、281298 p131）。"""
    rev, exp = VALID_LINE_COUNTS
    # 旧 OCR（中国語モデル）は簡体字で読む（「财源」「国支出金」）。財源の語を見落とすと歳出の表を歳入（8本）で切り、
    # 歳入・歳出の取り違えが後ろの表まで続く（R8 281298 p138 ほか 9表。2026-11-13 に取り直して分かった）
    if header_text is not None and re.search(r"[財财]源|国[庫库]|一般[財财]", header_text):
        if len(tv) == exp:
            return tv
        if len(page_vlines) == exp:
            return page_vlines
        # どちらも 12本でない: 表ごとの線とページ共通の線が1本ずつ別の線を取りこぼした（R8 281298 p238: 表ごとは左端の
        # 区分の線、ページ共通は節の区分と金額の間の線がない）。どちらか一方では列がつながる（「2扶助費30,999,209」）ので、
        # 両方を合わせて 12本になればそれを使う
        merged = union_vlines(tv, page_vlines)
        return merged if len(merged) == exp else max(tv, page_vlines, key=len)
    if header_text is not None and len(tv) == rev:
        return tv
    if header_text is None and prev_cols == rev - 1 and len(tv) == rev:
        return tv
    if header_text is None and prev_cols == exp - 1 and len(tv) != exp and len(page_vlines) != exp:
        # 見出しのない歳出の続きの表でも同じ取りこぼし方があれば、財源の見出しのある表（上）と同じく合わせる
        merged = union_vlines(tv, page_vlines)
        if len(merged) == exp:
            return merged
    if header_text is None and len(tv) == len(page_vlines) >= 6:
        # 見出しのない続きの表で本数が同じなら、ページ共通の線を使う。表ごとの線は、細節の行の区切りの短い縦線を
        # 列の境界と取り違えることがある（R8 281298 p367: 節の欄の左端がページ共通 2153 → 表ごと 2180。
        # 節の番号が欄の外に落ち、節と細節の字下げの差が消えて細節を節として数えた）。ページの高さ全体で測った線の方が確か
        return page_vlines
    if len(tv) < max(6, len(page_vlines)):
        return page_vlines if len(page_vlines) >= 6 else None
    return tv if len(tv) >= 6 else None


def previous_table_cols(outdir: str, page: int):
    """前のページの OCR 結果の最後の表の列数（見出しのない続きの表が歳入か歳出かの手がかり）と、それが確かか。
    返り値: (列数 or None, 未確定か)。未確定とするのは、間のページの結果がまだない（並べて流して、さらに前のページで
    代わりに判定した）ときと、見つけた表そのものが未確定（prev_cols_unknown）のとき（未確定は後ろのページへ伝わる）。
    表のないページ（扉など）はとばしてさらに前を見る（未確定にはしない）。"""
    missing = False
    for p in range(page - 1, max(0, page - 4), -1):
        path = os.path.join(outdir, f"p{p:04d}.json")
        if not os.path.exists(path):
            missing = True
            continue
        tables = json.load(open(path, encoding="utf-8")).get("tables", [])
        if tables:
            return len(tables[-1]["cols"]), missing or bool(tables[-1].get("prev_cols_unknown"))
    return None, True


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
    # 白黒2値（CCITT）で取り込んだ年度の説明書（R7 259281.pdf）は、罫線が 1px と細く途切れ途切れで、
    # 長く連続した線を探す開き（opening）では見つからない（412ページ中 163ページで表なし）。
    # OCR_LINE_CLOSE=<px> を指定したときだけ、縦・横それぞれの向きに途切れを埋めて（closing）から線を探す。
    # 指定しなければ従来どおり（R8 の結果は変えない）
    close_px = int(os.environ.get("OCR_LINE_CLOSE", "0"))
    if close_px > 0:
        bw_v = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, close_px)))
        bw_h = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (close_px, 1)))
    else:
        bw_v = bw_h = bw
    # 縦線: 高さの 1/20（300dpi で約 120px ≒ 1cm）以上連続するもの。文字の縦画（40px 程度）は残らない
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, h // 20))
    v = cv2.morphologyEx(bw_v, cv2.MORPH_OPEN, vk)
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
    # 罫線と認める長さ（表の高さに対する割合）。R7（白黒2値）は罫線が最大 680px 途切れ、長さが表の高さの 41〜76% しかない
    # （R7 p140）。OCR_LINE_COVERAGE で下げられる（既定 0.5 = 従来どおり）
    min_cov = float(os.environ.get("OCR_LINE_COVERAGE", "0.5"))
    for g in cand:
        best = max(g, key=lambda x: cov[x])
        if cov[best] >= total_h * min_cov:
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
    hz = cv2.morphologyEx(bw_h, cv2.MORPH_OPEN, hk)
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
    v2 = cv2.morphologyEx(bw_v, cv2.MORPH_OPEN, vk2)
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
    # --redo-unknown: 見出しのない続きの表を、前のページの結果がないまま判定したページ（prev_cols_unknown）だけ読み直す
    # （ページを分けて並べて流すと、前のページがまだできていないことがある。前のページができてから流し直す）
    redo_unknown = "--redo-unknown" in sys.argv
    os.makedirs(outdir, exist_ok=True)
    # 回転の判定（cls）は横書きの表には不要。スレッド数は並列実行で取り合わないよう絞る。
    eng = make_engine(int(os.environ.get("OCR_THREADS", "5")))
    with tempfile.TemporaryDirectory() as tmp:
        for page in range(a, b + 1):
            dst = os.path.join(outdir, f"p{page:04d}.json")
            if os.path.exists(dst):
                done = json.load(open(dst, encoding="utf-8"))
                if not (redo_unknown and any(t.get("prev_cols_unknown") for t in done.get("tables", []))):
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
                    outer = tv if len(tv) >= 2 else vlines
                    if len(outer) < 2:
                        continue
                    width = outer[-1] - outer[0]
                    # 列見出しの下の線: 表の上端より下で、表の幅いっぱいに引かれた最初の横線
                    full = [d["y"] for d in hlines if d["x1"] - d["x0"] > width * 0.9 and vtop + 20 < d["y"] < vbottom]
                    head = min(full) if full else vtop
                    # 列見出しは表の外枠の幅で読むので、縦線の選び方に関係なく先に読める
                    header = ocr_region(eng, img, outer[0], vtop, outer[-1], head)
                    htext = "".join(d["text"] for d in header)
                    # 縦線の選び方。歳入（7列＝8本）と歳出（11列＝12本）の表が同じページにあると、ページ共通の線（12本）で
                    # 歳入の表を切って歳出の表として読む（R8 281299 p9）。一方、歳出の表でも下端まで届かない線があると表ごとの線が
                    # 8本になる（p45）ので、本数だけでは見分けられない。列見出しの語で見分ける:
                    #   財源の見出し（国庫支出金・一般財源）がある → 歳出: 12本の線（表ごと、なければページ共通）
                    #   見出しがあり財源の語がない → 歳入: 8本の線（表ごと）
                    #   見出しがない（前のページから続く表）→ 直前の表（同じページの前の表、なければ前のページの最後の表）が
                    #     歳入で、表ごとの線が8本ならそれを使う（R8 281299 p51: 歳入の続きの表と歳出の表が同じページ）
                    #   表ごともページ共通も 11本（別の線を1本ずつ取りこぼした）で歳出の表 → 合わせて 12本（一般会計 p238）
                    #   見出しのない続きの表で本数が同じ → ページ共通（表ごとは細節の区切りの線を拾うことがある。一般会計 p367）
                    #   それ以外 → 表ごとの本数がページ共通以上なら表ごと、でなければページ共通
                    #     （長い表は行の区切りで線が途切れ、表ごとだと本数が減る。一般会計 p131 で 12→10）
                    is_header = bool(re.search(r"年度|区分|説明|说明|節|节|款名|[財财]源", htext)) and head - vtop <= 400
                    if rec["tables"]:
                        prev_cols = len(rec["tables"][-1]["cols"])
                        prev_unknown = bool(rec["tables"][-1].get("prev_cols_unknown"))
                    else:
                        prev_cols, prev_unknown = previous_table_cols(outdir, page)
                    tv = choose_vlines(tv, vlines, htext if is_header else None, prev_cols)
                    if tv is None:
                        continue  # 表ではない（枠だけの囲みなど）
                    # 前のページから続く表には列見出しがない（R8 一般会計 p151 で確認）。最初の全幅の線は目の区切り。
                    # 見出し語がなければ表の上端から本文として読む（見出しと誤認すると前の目の節を取りこぼす）
                    if not is_header:
                        head, header = vtop, []
                    t = {"box": [tv[0], vtop, tv[-1], vbottom], "head": head, "vlines": tv,
                         "title": ocr_region(eng, img, 0, prev_bottom, w, vtop + 4),
                         "header": header,
                         "rowlines": [d for d in hlines if head < d["y"] < vbottom - 4],
                         "cols": [ocr_column(eng, img, x0, head + 4, x1, vbottom - 4)
                                  for x0, x1 in zip(tv, tv[1:])]}
                    if not is_header and prev_unknown:
                        # 見出しのない続きの表なのに、直前の表の列数が確かでないまま縦線を選んだ（前のページの結果がない・
                        # 前の表も未確定）。未確定であることを残し（後ろのページの続きの表にも伝わる）、
                        # 前のページができてから --redo-unknown で読み直す（ページの順に読み直すので、伝わった先も直る）
                        t["prev_cols_unknown"] = True
                        print(f"WARN p{page}: 続きの表の歳入・歳出が未確定（前のページの結果がない・前の表も未確定）。"
                              f"前のページの後に --redo-unknown で読み直す", file=sys.stderr)
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
