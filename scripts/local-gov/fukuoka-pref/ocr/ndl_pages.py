"""説明書の名前の欄を NDLOCR-Lite の文字の認識（PARSeq）で読み直し、ocr_pages.py の出力と同じ形式で書き出す。

設計: docs/local-gov/tasks/20261114_2353_名前の読み取りにNDLOCR-Liteを組み込む設計.md
PP-OCRv6・v4（同じ PaddleOCR の系統）とは系統の違う、名前の3つ目の読み取りにする（textlayer_pages.py と同じ考え方）。
表の構造（縦線・表の範囲・区画の横線・見出し）と金額の文字枠は ocr_pages.py の出力をそのまま使い、
名前の欄（目・節の区分・説明）の金額でない文字枠だけを、行ごとに NDLOCR-Lite で読んだ文字に置き換える。
同じ parse_setsumeisho.py にかけると、金額は同じで名前だけが違う読み取りができ、書き出しで名前の候補に足せる。

切り抜き: 行の高さは OCR の文字枠の帯、横は**欄の縦線**から取る（OCR の文字枠から取ると、OCR が端の字を落としたときに
NDLOCR-Lite にも渡らない。OCR の別ツール検証の設計 5.2）。説明欄は同じ行の金額の文字枠より左まで。
置き換えた文字枠の左端は OCR の文字枠の左端のまま（細節・入れ子の事項の字下げで見分けるため）。

NDLOCR-Lite（国立国会図書館、CC BY 4.0。https://github.com/ndl-lab/ndlocr-lite）の同梱の PARSeq の ONNX モデル3つと文字表
（src/config/NDLmoji.yaml）だけを onnxruntime で動かす。NDLOCR-Lite のコードは実行も複製もしない。前処理・後処理
（高さ×幅に縮める、RGB を [-1,1]、出力の各位置の最大の字を 0（終わり）まで、30字・50字・100字のモデルを字数で使い分ける）は
NDLOCR-Lite の src/parseq.py に倣った。配置の検出モデル（DEIM。DINOv3 のライセンス）は使わない。
モデル・文字表はリポジトリに入れない。場所は環境変数 NDLOCR_LITE_DIR（または --ndl）で指す。

使い方:
    NDLOCR_LITE_DIR=<ndlocr-lite> PYLIB=<pylib> python3 -P scripts/local-gov/fukuoka-pref/ocr/ndl_pages.py \
        <説明書.pdf> <ocr_pages の出力ディレクトリ> <出力ディレクトリ> <ページ範囲> [--ndl=<ndlocr-lite>]
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# onnxruntime・opencv・pyyaml は PYLIB 環境変数のディレクトリから読む（ocr_pages.py と同じ）
if os.environ.get("PYLIB"):
    for p in reversed(os.environ["PYLIB"].split(":")):
        sys.path.insert(0, p)
from parse_setsumeisho import amount, lines_of, norm_name  # noqa: E402

# 名前の欄（列の数 → 名前の列）。歳出は 0 目 / 8 節の区分 / 10 説明、歳入は 0 目 / 4 節の区分 / 6 説明（parse_setsumeisho と同じ）。
# 10列の表（節の区分と金額の間の縦線が取れなかった表）は 8 に区分と金額が混ざるので、金額でない文字枠だけを読む
NAME_COLS = {11: (0, 8, 10), 7: (0, 4, 6), 10: (0, 8, 9)}
# 欄の縦線から内側に空ける幅（罫線を読まない）と、行の上下の余白（300dpi の px）
INSET, PAD_Y = 6, 6
# OCR の文字枠の両端から広げる幅（行の高さの倍。字の約1個分）
EXTEND = 1.2
# 名前の両端に付く罫線の読み（細節の内側の枠）
FRAME_RE = re.compile(r"^[|｜丨]+|[|｜丨]+$")


def keep_ocr_line(ocr_text: str, moku_col: bool) -> bool:
    """NDLOCR-Lite で読み直さず、OCR の読みのまま残す行。
    - 1字の行（「計」「費」）: 入力の大きさへ横に数倍引き伸ばすので、数字・別の字に読む（「計」→「10」、2行目の「費」→「19」）
    - 目の欄の計の行（解釈の is_total と同じ見分け方: 字形を直した名前が「計」で終わり、数字がない）: 解釈が計の行を目と見なし、
      架空の目ができた（R8 で 74行）
    OCR が「计」（簡体字）・「合　計」と読んでも当たるよう、解釈と同じ norm_name で直してから見る"""
    name = norm_name(ocr_text)
    if len(name) <= 1:
        return True
    return moku_col and name.endswith("計") and not re.search(r"\d", ocr_text)


class Parseq:
    def __init__(self, path, charlist, threads=4):
        import onnxruntime
        so = onnxruntime.SessionOptions()
        so.intra_op_num_threads = threads
        self.s = onnxruntime.InferenceSession(path, so, providers=["CPUExecutionProvider"])
        self.inp = self.s.get_inputs()[0]
        self.h, self.w = self.inp.shape[2:]
        self.charlist = charlist

    def read(self, img):
        import cv2
        import numpy as np
        h, w = img.shape[:2]
        if h > w * 0.8:
            img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        # 縦横比を保たずに入力の大きさへ引き伸ばす（parseq.py と同じ）。短い行（1字の「計」）は横に数倍伸びて「10」と読むことがあるが、
        # 縦横比を保って右を白で埋めると、目の名前の正解が 20件中 18 → 1件に落ちた（R8 p18〜30。2026-11-15）。1字の行・計の行は読み直さない（keep_ocr_line）
        x = cv2.resize(img, (self.w, self.h), interpolation=cv2.INTER_LINEAR)
        x = np.ascontiguousarray(x[:, :, ::-1]).astype(np.float32) / 127.5 - 1.0
        out = self.s.run(None, {self.inp.name: x.transpose(2, 0, 1)[None]})[0]
        idx = np.argmax(out[0], axis=1)
        stop = np.where(idx == 0)[0]
        idx = idx[: stop[0] if stop.size else len(idx)]
        return "".join(self.charlist[i - 1] for i in idx.tolist())


class Ndl:
    """NDLOCR-Lite の文字の認識（行の画像 → 文字列）。30字のモデルで読み、長ければ 50字・100字のモデルで読み直す"""

    def __init__(self, root):
        import yaml
        with open(os.path.join(root, "src/config/NDLmoji.yaml"), encoding="utf-8") as f:
            cl = list(yaml.safe_load(f)["model"]["charset_train"])
        m = os.path.join(root, "src/model")
        self.r30 = Parseq(f"{m}/parseq-ndl-24x256-30-tiny-189epoch-tegaki3-r8data-202604.onnx", cl)
        self.r50 = Parseq(f"{m}/parseq-ndl-24x384-50-tiny-300epoch-tegaki3-r8data-202604.onnx", cl)
        self.r100 = Parseq(f"{m}/parseq-ndl-24x768-100-tiny-153epoch-tegaki3-r8data-202604.onnx", cl)

    def read(self, img):
        s = self.r30.read(img)
        if len(s) >= 25:
            s = self.r50.read(img)
            if len(s) >= 45:
                s = self.r100.read(img)
        return s


def squeeze_gaps(img):
    """字間の広い行（「期 末 手 当」）は、横長に縮めると字が落ちる。空白の列が続くところを、行の高さの 1/4 の幅まで詰める。"""
    import cv2
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ink = (g < 160).sum(axis=0) > 0
    keep, run, gap = [], 0, max(4, img.shape[0] // 4)
    for i, v in enumerate(ink):
        run = 0 if v else run + 1
        if v or run <= gap:
            keep.append(i)
    return img[:, keep] if keep else img


def is_amount_box(d) -> bool:
    """金額の文字枠（parse_setsumeisho の説明欄と同じ判定）。金額は読み替えない"""
    return amount(d["text"]) is not None and (d["x1"] - d["x0"]) < 400


def name_lines(col: list[dict], left: float, right: float, full: bool = False) -> list[tuple[list[dict], tuple[int, int, int, int]]]:
    """欄の金額でない文字枠を行にまとめ、行ごとの切り抜きの範囲 (x0, y0, x1, y1) を返す。
    横は OCR の文字枠の両端から字の約 EXTEND 個分だけ広げる（OCR が端の字を落としても入るように）。ただし欄の縦線の内側と、
    同じ行の金額の文字枠の左まで。説明欄・目の欄を欄の端まで広げると、罫線・記号を読んで名前の端にごみが付いた（事項「○会計事務費(一」）。
    full: 欄の幅いっぱい（節の区分の欄。字間の広い細節「筆　耕　翻　訳　料」は字1個分では端の字に届かない。区分の欄にはごみになる記号がない）"""
    names = [d for d in col if not is_amount_box(d)]
    amts = [d for d in col if is_amount_box(d)]
    out = []
    for row in lines_of(names):
        y0, y1 = min(d["y0"] for d in row), max(d["y1"] for d in row)
        ext = float("inf") if full else (y1 - y0) * EXTEND
        bx0, bx1 = min(d["x0"] for d in row), max(d["x1"] for d in row)
        x0, x1 = max(left + INSET, bx0 - ext), min(right - INSET, bx1 + ext)
        for a in amts:
            cy = (a["y0"] + a["y1"]) / 2
            if not (y0 <= cy <= y1):
                continue
            if a["x0"] > bx1 - 5:
                x1 = min(x1, a["x0"] - INSET)
            elif a["x1"] < bx0 + 5:
                # 名前の左の数字だけの文字枠（節番号・目の番号「1」）。数字は OCR の文字枠のまま残すので、切り抜きに入れない
                # （入れると NDLOCR-Lite が「1県民税」と読み、番号を外す処理（OCR の別の文字枠の番号）が効かず、OCR の名前と一致しない）
                x0 = max(x0, a["x1"] + INSET)
        out.append((row, (int(x0), int(y0 - PAD_Y), int(max(x1, bx1)), int(y1 + PAD_Y))))
    return out


def merge_numbers(ocr_text: str, ndl_text: str) -> str:
    """数字は OCR の読みを使う（NDLOCR-Lite は名前の読み直しにだけ使う。数字に弱い）。
    - NDLOCR-Lite の読みの頭の数字を外し、OCR の行の頭の数字（目・節の番号）を付ける（「7林業改善…」と読んで、番号の印字のない前年度のみの目に
      番号が付いた。R8 歳入 12-1）
    - NDLOCR-Lite の読みが金額の形（数字だけ）になったら、OCR の読みのまま（2行の事項の2行目の1字「費」を「19」と読み、解釈が金額にした。R8 13目）"""
    if not ndl_text or amount(ndl_text) is not None:
        return ocr_text
    m = re.match(r"\s*(\d+)", ocr_text)
    if not re.search(r"\d", ocr_text):
        # OCR の行に数字がなければ、NDLOCR-Lite の読みの数字はすべて罫線・記号の読み違い（「林業改善資金1」「林業改善資金|1」
        # 「林業改善資金1)」。2行の目の名前の1行目の右端の罫線。解釈がそれを目の番号にして、番号の印字のない前年度のみの目に番号が付いた。R8 歳入 12-1）
        return FRAME_RE.sub("", re.sub(r"\d", "", ndl_text)).strip()
    body = re.sub(r"^\d+", "", ndl_text)
    # OCR の行に数字があれば、頭の番号は OCR の読みを使い、末尾の数字は OCR の行が数字で終わらなければ外す
    if not re.search(r"\d\s*$", ocr_text):
        body = re.sub(r"\d+$", "", body)
    return (m.group(1) if m else "") + FRAME_RE.sub("", body).strip()


def replace_names(rec: dict, img, ndl) -> int:
    """ページの名前の欄の文字枠を、行ごとに NDLOCR-Lite で読んだ1つの文字枠に置き換える。置き換えた行の数を返す"""
    n = 0
    for t in rec.get("tables", []):
        cols = NAME_COLS.get(len(t["cols"]))
        if not cols:
            continue
        vl = t.get("vlines") or rec["vlines"]
        for ci in cols:
            if ci + 1 >= len(vl):
                continue
            new_col = [d for d in t["cols"][ci] if is_amount_box(d)]
            # 節の区分の欄（各表の名前の列の2つ目）は欄の幅いっぱいに読む
            for row, (x0, y0, x1, y1) in name_lines(t["cols"][ci], vl[ci], vl[ci + 1], full=ci == cols[1]):
                ocr_text = "".join(d["text"] for d in row)
                if keep_ocr_line(ocr_text, moku_col=ci == cols[0]):
                    new_col += row  # 1字の行・計の行は OCR の文字枠のまま
                    continue
                crop = img[max(0, y0):y1, max(0, x0):max(x0 + 1, x1)]
                text = FRAME_RE.sub("", ndl.read(squeeze_gaps(crop))).strip() if crop.size else ""
                text = merge_numbers(ocr_text, text)
                new_col.append({"x0": min(d["x0"] for d in row), "x1": max(d["x1"] for d in row),
                                "y0": min(d["y0"] for d in row), "y1": max(d["y1"] for d in row),
                                "text": text, "score": 1.0, "ndl": True})
                n += 1
            t["cols"][ci] = sorted(new_col, key=lambda d: (d["y0"], d["x0"]))
    rec["source"] = "ndl"
    return n


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--ndl=")]
    root = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--ndl=")), os.environ.get("NDLOCR_LITE_DIR"))
    if not root or not os.path.isdir(root):
        sys.exit("NDLOCR-Lite の場所がない（環境変数 NDLOCR_LITE_DIR か --ndl=<dir>）")
    import cv2
    pdf_path, ocr_dir, outdir, rng = args[:4]
    a, b = (int(x) for x in rng.split("-"))
    ndl = Ndl(root)  # モデルが読めなければ、出力ディレクトリを作る前に止まる
    # 全ページを読み終えてから出力ディレクトリに置く（途中で止まったときに、一部のページだけの読み取りを残さない。
    # 残すと後の解釈が一部の目だけの読み取りを作り、書き出しが気づかずに使う）
    work = outdir.rstrip("/") + ".partial"
    if os.path.exists(work):
        shutil.rmtree(work)
    os.makedirs(work)
    total = pages = 0
    with tempfile.TemporaryDirectory() as tmp:
        for pno in range(a, b + 1):
            src = os.path.join(ocr_dir, f"p{pno:04d}.json")
            if not os.path.exists(src):
                continue
            rec = json.load(open(src, encoding="utf-8"))
            png = os.path.join(tmp, "p")
            # OCR と同じ解像度で描く（座標をそのまま使う）
            subprocess.run(["pdftoppm", "-r", str(rec.get("dpi", 300)), "-f", str(pno), "-l", str(pno), "-png", "-singlefile",
                            pdf_path, png], check=True)
            img = cv2.imread(png + ".png")
            if img is None or [img.shape[1], img.shape[0]] != rec["size"]:
                sys.exit(f"p{pno}: ページ画像の大きさが OCR と違う（{None if img is None else img.shape[1::-1]} / {rec['size']}）")
            total += replace_names(rec, img, ndl)
            pages += 1
            with open(os.path.join(work, f"p{pno:04d}.json"), "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False)
    if os.path.exists(outdir):
        shutil.rmtree(outdir)
    os.replace(work, outdir)
    print(f"NDLOCR-Lite: {pages} ページ・名前の行 {total} 行を読み直した", file=sys.stderr)


if __name__ == "__main__":
    main()
