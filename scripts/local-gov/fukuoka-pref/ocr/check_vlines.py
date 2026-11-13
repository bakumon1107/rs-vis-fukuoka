"""縦線の選び方（ocr_pages.py の choose_vlines）を変えたときに、切り方が変わる表を洗い出す。

保存済みの OCR 結果の各ページについて、線の検出だけをやり直し（文字は読まない。1ページ約1.5秒）、
今の choose_vlines で選ぶ線が、保存済みの表の線と変わる表を出す。変わったページだけを退避して ocr_pages.py で流し直せば、
OCR を全ページ取り直さずに済む（ocr_pages.py は既にあるページを飛ばす）。

- 見出しのない続きの表は直前の表の列数で線を選ぶので、前の表の切り方が変わると後ろの表（次のページの表も）が変わることがある。
  直前の表の列数は、このスクリプトが選び直した線の列数を使って伝える（ページの順に流す）
- 線の検出をやり直した結果に、保存済みの表と対応しない範囲があり、今の規則ではそれが表になる（見出しなしとみなして判定）なら、
  そのページも「変わる」に数える。保存済みの表が線の検出をやり直した結果に見つからないときも同じ（確かめられないので流し直す側）
- 見出しの文字は保存済みの OCR 結果のものを使う（見出しを読み直さない）。そのため、見出しの判定（ocr_pages.py の HEADER_RE・
  見出しの位置の条件）を変えたときの影響は拾えない（見出しと認めなかった表は見出しの文字を保存していない）。そのときは --same-as で
  新旧の OCR の線を比べるか、そのページを流し直す。線を選ぶ入力の組み立ては ocr_pages.py の main と同じにすること（変えたら両方）
- 線の検出の設定（環境変数 OCR_LINE_CLOSE・OCR_LINE_COVERAGE）は、OCR を流したときと同じにして実行する（OCR の結果には残らない。
  R8 は既定のまま）

使い方:
    PYLIB=<pylib> python3 -P scripts/local-gov/fukuoka-pref/ocr/check_vlines.py <説明書.pdf> <OCR出力ディレクトリ> <PDFページ範囲 例 9-420>
    python3 -P scripts/local-gov/fukuoka-pref/ocr/check_vlines.py --same-as <新OCRのディレクトリ> <旧OCRのディレクトリ> <PDFページ範囲>
出力: 変わる表ごとに「CHANGED p<ページ> table <番号>: ...」「NEW p<ページ>: ...」、最後に「changed pages: [...]」
--same-as: 2つの OCR 結果で、保存済みの表の線が違うページと、片方にしかないページを「differs: [...]」で出す（線の検出はしない）。
  旧 OCR（中国語モデル）は見出しを簡体字で読むので、見出しで選ぶ線が新 OCR と違うことがある（R8 281298 p138 ほか）
"""
import argparse
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


def parse_args(argv):
    p = argparse.ArgumentParser(description="縦線の選び方を変えたときに、切り方が変わる表を洗い出す（詳しくはファイルの先頭の説明）")
    p.add_argument("--same-as", nargs=2, metavar=("新OCRのディレクトリ", "旧OCRのディレクトリ"),
                   help="2つの OCR 結果で、保存済みの表の線が違うページを出す（線の検出はしない）")
    p.add_argument("args", nargs="+", metavar="引数",
                   help="通常: <説明書.pdf> <OCR出力ディレクトリ> <PDFページ範囲>。--same-as のとき: <PDFページ範囲>")
    a = p.parse_args(argv)
    want = 1 if a.same_as else 3
    if len(a.args) != want:
        p.error("--same-as のときは <PDFページ範囲> だけを渡す" if a.same_as
                else "<説明書.pdf> <OCR出力ディレクトリ> <PDFページ範囲> の3つを渡す")
    return a


def main():
    opts = parse_args(sys.argv[1:])
    if opts.same_as:
        same_as(opts.same_as[0], opts.same_as[1], opts.args[0])
        return
    pdf, ocrdir, rng = opts.args
    op = load_ocr_pages()
    cv2 = op.cv2
    a, b = (int(x) for x in rng.split("-"))
    changed = []
    # ページごとの最後の表の列数（選び直した線で数える）。次のページの続きの表に伝える。
    # 選び直して表がなくなったページは None（ocr_pages.py と同じく、表のないページとしてとばしてさらに前を見る）
    last_cols: dict[int, int | None] = {}

    def prev_cols_before(page):
        # ocr_pages.previous_table_cols と同じく3ページ前まで見る。選び直したページがあればその列数、なければ保存済み
        for p in range(page - 1, max(0, page - 4), -1):
            if p in last_cols:
                if last_cols[p] is None:
                    continue
                return last_cols[p]
            path = os.path.join(ocrdir, f"p{p:04d}.json")
            if not os.path.exists(path):
                continue
            tables = load_page(path).get("tables")
            if tables:
                return len(tables[-1]["cols"])  # 範囲より前のページ（選び直していない）
        return None

    with tempfile.TemporaryDirectory() as tmp:
        for page in range(a, b + 1):
            path = os.path.join(ocrdir, f"p{page:04d}.json")
            if not os.path.exists(path):
                print(f"WARN p{page}: OCR 結果がない", file=sys.stderr)
                continue
            rec = load_page(path)
            dpi = rec.get("dpi", 300)
            png = op.render(pdf, page, dpi, tmp)
            img = cv2.imread(png, cv2.IMREAD_GRAYSCALE)
            os.remove(png)  # 300dpi の画像は1枚数 MB。全ページ分を溜めない（ocr_pages.py と同じ）
            vlines, _hlines, spans, per_table = op.detect_lines(img)
            saved = {t["box"][1]: (i, t) for i, t in enumerate(rec["tables"])}
            prev_cols = prev_cols_before(page)
            cols_here = None
            for (top, _bottom), tv in zip(spans, per_table):
                if top not in saved:
                    # 保存済みの表にない範囲。今の規則で表になるなら（見出しなしとみなす）流し直す
                    # 見出しの文字がないので見出しなしとして判定する。本数は見出しによって変わりうるので、後ろの表へは伝えない
                    # （このページは流し直すので、流し直した後にもう一度洗い出す）
                    new = op.choose_vlines(tv, vlines, None, prev_cols, dpi)
                    if new is not None:
                        changed.append(page)
                        print(f"NEW p{page}: 上端 {top} の範囲が今の規則では表になりうる（見出しなしとみなして {len(new)}本）")
                    continue
                i, t = saved.pop(top)
                header = t["header"]  # ocr_pages.py は見出しと認めなかった表で [] を保存する
                htext = "".join(d["text"] for d in header) if header else None
                new = op.choose_vlines(tv, vlines, htext, prev_cols, dpi)
                if new != t["vlines"]:
                    changed.append(page)
                    print(f"CHANGED p{page} table {i}: {len(t['vlines'])} -> {len(new) if new else None} lines "
                          f"old={t['vlines']} new={new}")
                if new is not None:
                    prev_cols = cols_here = len(new) - 1
            for top, (i, t) in saved.items():
                print(f"WARN p{page} table {i}: 表の上端 {top} が線の検出をやり直した結果にない", file=sys.stderr)
                changed.append(page)  # 確かめられない表は流し直す側に倒す
            last_cols[page] = cols_here  # 表がない（なくなった）ページは None
    print("changed pages:", sorted(set(changed)))


if __name__ == "__main__":
    main()
