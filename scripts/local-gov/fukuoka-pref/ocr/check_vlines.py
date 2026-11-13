"""縦線の選び方（ocr_pages.py の choose_vlines）を変えたときに、切り方が変わる表を洗い出す。

保存済みの OCR 結果の各ページについて、線の検出だけをやり直し（文字は読まない。1ページ約1.5秒）、
今の choose_vlines で選ぶ線が、保存済みの表の線と変わる表を出す。変わったページだけを退避して ocr_pages.py で流し直せば、
OCR を全ページ取り直さずに済む（ocr_pages.py は既にあるページを飛ばす）。

見出しの文字・直前の表の列数は保存済みの OCR 結果のものを使う（見出しを読み直さない）。そのため、見出しの判定（ocr_pages.py の
is_header の語）を変えたときの影響は拾えない（見出しと認めなかった表は見出しの文字を保存していない）。そのときは --same-as で
新旧の OCR の線を比べるか、そのページを流し直す。線の検出をやり直した結果に表が見つからないページも「変わる」に数える。

使い方:
    PYLIB=<pylib> python3 -P scripts/local-gov/fukuoka-pref/ocr/check_vlines.py <説明書.pdf> <OCR出力ディレクトリ> <PDFページ範囲 例 9-420>
    python3 -P scripts/local-gov/fukuoka-pref/ocr/check_vlines.py --same-as <新OCRのディレクトリ> <旧OCRのディレクトリ> <PDFページ範囲>
出力: 変わる表ごとに「CHANGED p<ページ> table <番号>: <本数> -> <本数> lines old=[...] new=[...]」、最後に「changed pages: [...]」
--same-as: 2つの OCR 結果で、保存済みの表の線が違うページと、片方にしかないページを「differs: [...]」で出す（線の検出はしない）。
  旧 OCR（中国語モデル）は見出しを簡体字で読むので、見出しで選ぶ線が新 OCR と違うことがある（R8 281298 p138 ほか）
"""
import importlib.util
import json
import os
import sys
import tempfile


def load_ocr_pages():
    """ocr_pages.py（cv2 を使う）を読み込む。--same-as では線の検出をしないので読み込まない。"""
    spec = importlib.util.spec_from_file_location(
        "ocr_pages", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ocr_pages.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # PYLIB を sys.path に足すのも ocr_pages.py が行う
    return mod


def load_page(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def same_as(dir_a, dir_b, rng):
    a, b = (int(x) for x in rng.split("-"))
    differs = []
    for page in range(a, b + 1):
        pa, pb = (os.path.join(d, f"p{page:04d}.json") for d in (dir_a, dir_b))
        ea, eb = os.path.exists(pa), os.path.exists(pb)
        if not (ea and eb):
            if ea or eb:  # 片方だけにある（OCR の流し忘れ・途中で止まった）も違いに数える
                print(f"WARN p{page}: 片方の OCR 結果がない（{pb if ea else pa}）", file=sys.stderr)
                differs.append(page)
            continue
        ta, tb = load_page(pa)["tables"], load_page(pb)["tables"]
        if [t["vlines"] for t in ta] != [t["vlines"] for t in tb]:
            differs.append(page)
    print("differs:", differs)


def main():
    if sys.argv[1] == "--same-as":
        same_as(sys.argv[2], sys.argv[3], sys.argv[4])
        return
    pdf, ocrdir, rng = sys.argv[1], sys.argv[2], sys.argv[3]
    op = load_ocr_pages()
    cv2 = op.cv2
    a, b = (int(x) for x in rng.split("-"))
    changed = []
    with tempfile.TemporaryDirectory() as tmp:
        for page in range(a, b + 1):
            path = os.path.join(ocrdir, f"p{page:04d}.json")
            if not os.path.exists(path):
                print(f"WARN p{page}: OCR 結果がない", file=sys.stderr)
                continue
            rec = load_page(path)
            if not rec["tables"]:
                continue
            png = op.render(pdf, page, rec.get("dpi", 300), tmp)
            img = cv2.imread(png, cv2.IMREAD_GRAYSCALE)
            os.remove(png)  # 300dpi の画像は1枚数 MB。全ページ分を溜めない（ocr_pages.py と同じ）
            vlines, _hlines, spans, per_table = op.detect_lines(img)
            for i, t in enumerate(rec["tables"]):
                # 表は縦線の上端（box の2つ目）で、線の検出をやり直した結果の表と対応づける
                tv = next((tv for (top, _), tv in zip(spans, per_table) if top == t["box"][1]), None)
                if tv is None:
                    print(f"WARN p{page} table {i}: 表の上端 {t['box'][1]} が線の検出をやり直した結果にない", file=sys.stderr)
                    changed.append(page)  # 確かめられない表は流し直す側に倒す
                    continue
                header = t["header"]  # ocr_pages.py は見出しと認めなかった表で [] を保存する
                htext = "".join(d["text"] for d in header) if header else None
                prev_cols = len(rec["tables"][i - 1]["cols"]) if i > 0 else op.previous_table_cols(ocrdir, page)[0]
                new = op.choose_vlines(tv, vlines, htext, prev_cols)
                if new != t["vlines"]:
                    changed.append(page)
                    print(f"CHANGED p{page} table {i}: {len(t['vlines'])} -> {len(new) if new else None} lines "
                          f"old={t['vlines']} new={new}")
    print("changed pages:", sorted(set(changed)))


if __name__ == "__main__":
    main()
