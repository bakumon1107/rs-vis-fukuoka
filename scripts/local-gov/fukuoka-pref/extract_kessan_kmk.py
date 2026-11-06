"""福岡県「歳入歳出決算概要説明書」の「一般会計歳入歳出決算款項目別明細表」を抽出・検証する。

入力: 決算概要説明書の PDF（R6: https://www.pref.fukuoka.lg.jp/uploaded/attachment/272595.pdf）
出力: JSON（stdout）。款・項・目の階層と金額（1円単位）。検証結果は stderr。終了コード 1 = 検証 FAIL あり。

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/extract_kessan_kmk.py <概要説明書.pdf> > kessan-kmk.json

前提（R6 で確認）:
- テキスト PDF。pdftotext -layout で1行1科目（長い名称は折り返し。kessan_common.assemble_rows 参照）
- 歳入の列: 予算現額 / 調定額 / 収入済額 / 不納欠損額 / 収入未済額 / 予算現額と収入済額との増減額
- 歳出の列: 予算現額 / 支出済額 / 翌年度繰越額 / 不用額 / 予算現額と支出済額との比較
- 負の数は「▲」付き。行の字下げで階層が分かる（R6 実測: 款 0-1 / 項 4-5 / 目 8-9 文字）

検証（すべて完全一致。1円でもずれたら FAIL）:
- 縦: 目の合計 = 項、項の合計 = 款（全列）
- 横（歳出）: 予算現額 = 支出済額 + 翌年度繰越額 + 不用額、比較 = 予算現額 - 支出済額
- 横（歳入）: 増減額 = 収入済額 - 予算現額、調定額 = 収入済額 - 過誤納金 + 不納欠損額 + 収入未済額
- 合計行: 表末尾の「歳入合計」「歳出合計」と款の合計
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kessan_common import assemble_rows, flat, page_count, pdftext  # noqa: E402

REVENUE_COLS = ["予算現額", "調定額", "収入済額", "不納欠損額", "収入未済額", "増減額"]
EXPENSE_COLS = ["予算現額", "支出済額", "翌年度繰越額", "不用額", "比較"]


def is_header(line: str) -> bool:
    f = flat(line)
    return (
        bool(re.fullmatch(r"[-‑―]\d+[-‑―]", f))
        or f.startswith("款項目")
        or "予算現額と" in f
        or f.startswith("済額との")
        or "款項目別明細表" in f
        or f.startswith("（単位")
        or "▲は減を示す" in f
        or "収入済額欄の" in f
        or f == "歳入"
    )


def find_section_pages(pdf: str) -> tuple[int, int]:
    start = end = None
    for p in range(1, min(page_count(pdf), 80) + 1):
        f = flat(pdftext(pdf, p))
        if start is None and "款項目別明細表" in f and "予算現額" in f and "目次" not in f:
            start = p
        if start is not None and p > start and "特別会計歳入歳出決算一覧表" in f:
            return start, p - 1
    raise SystemExit("款項目別明細表のページ範囲が見つからない")


def parse(pdf: str) -> tuple[dict, dict, list[str]]:
    start, end = find_section_pages(pdf)
    tree: dict[str, list] = {"revenue": [], "expense": []}
    totals: dict[str, list[int]] = {}
    skipped: list[str] = []
    side = "revenue"
    for pno in range(start, end + 1):
        lines = [ln for ln in pdftext(pdf, pno).splitlines() if ln.strip() and not is_header(ln)]
        # 「歳出」の見出しでページ内の側が切り替わる
        chunks: list[tuple[str, list[str]]] = [(side, [])]
        for ln in lines:
            if flat(ln) == "歳出":
                side = "expense"
                chunks.append((side, []))
            else:
                chunks[-1][1].append(ln)
        for s, chunk in chunks:
            cols = REVENUE_COLS if s == "revenue" else EXPENSE_COLS
            for kind, item in assemble_rows(chunk, len(cols), split_income_col=2 if s == "revenue" else None,
                                            skipped=skipped, label=f"p{pno}"):
                if kind != "row":
                    continue
                if item.no is None:
                    if item.name in ("歳入合計", "歳出合計"):
                        totals[s] = item.nums
                    elif not item.name.startswith("うち"):
                        skipped.append(f"p{pno}: 番号のない行: {item.name} {item.nums}")
                    continue
                lv = 0 if item.indent <= 2 else (1 if item.indent <= 6 else 2)
                node = {"no": item.no, "name": item.name, "pdf_page": pno, **dict(zip(cols, item.nums)), **item.extra}
                if lv == 0:
                    tree[s].append({**node, "children": []})
                elif lv == 1:
                    tree[s][-1]["children"].append({**node, "children": []})
                else:
                    tree[s][-1]["children"][-1]["children"].append(node)
    return tree, totals, skipped


def verify(tree: dict, totals: dict, skipped: list[str]) -> int:
    fails = 0

    def fail(msg):
        nonlocal fails
        fails += 1
        print("FAIL " + msg, file=sys.stderr)

    def check_sum(parent, kids, cols, label):
        for c in cols:
            s = sum(k[c] for k in kids)
            if s != parent[c]:
                fail(f"縦 {label} {c}: 子の合計 {s:,} ≠ {parent[c]:,}（差 {parent[c]-s:,}）")

    def check_row(s, node):
        if s == "expense":
            ok = (node["予算現額"] == node["支出済額"] + node["翌年度繰越額"] + node["不用額"]
                  and node["比較"] == node["予算現額"] - node["支出済額"])
        else:
            # 収入済額は過誤納金を内数で含むので、調定額との関係では差し引く（R6 県税で確認）
            ok = (node["増減額"] == node["収入済額"] - node["予算現額"]
                  and node["調定額"] == node["収入済額"] - node.get("過誤納金（内数）", 0) + node["不納欠損額"] + node["収入未済額"])
        if not ok:
            fail(f"横 {s} p{node['pdf_page']}: { {k: v for k, v in node.items() if k != 'children'} }")

    for s, cols in (("revenue", REVENUE_COLS), ("expense", EXPENSE_COLS)):
        for kan in tree[s]:
            check_sum(kan, kan["children"], cols, f"{s} {kan['no']}款{kan['name']}")
            check_row(s, kan)
            for kou in kan["children"]:
                check_sum(kou, kou["children"], cols, f"{s} {kan['no']}款{kou['no']}項{kou['name']}")
                check_row(s, kou)
                for moku in kou["children"]:
                    check_row(s, moku)
        if s not in totals:
            fail(f"合計行 {s}: 見つからない")
        else:
            for c, v in zip(cols, totals[s]):
                ssum = sum(k[c] for k in tree[s])
                if ssum != v:
                    fail(f"合計行 {s} {c}: 款の合計 {ssum:,} ≠ 合計行 {v:,}")
    # 名称の検査: 合計の検証では名前の誤り（断片の取り違え）は検出できないので別に確認する
    for s in tree:
        for kan in tree[s]:
            for node in [kan, *kan["children"], *[m for c in kan["children"] for m in c["children"]]]:
                if re.search(r"[0-9０-９,。（）()]", node["name"]) or not node["name"]:
                    fail(f"名称 {s} p{node['pdf_page']}: 不審な名称「{node['name']}」")
    for m in skipped:
        print(f"WARN 読み飛ばした行: {m}", file=sys.stderr)
    counts = {s: (len(tree[s]), sum(len(k["children"]) for k in tree[s]),
                  sum(len(c["children"]) for k in tree[s] for c in k["children"])) for s in tree}
    print(f"件数（款, 項, 目）: {counts}", file=sys.stderr)
    print(f"合計行: {totals}", file=sys.stderr)
    print(f"FAIL={fails}", file=sys.stderr)
    return fails


if __name__ == "__main__":
    t, tot, sk = parse(sys.argv[1])
    f = verify(t, tot, sk)
    json.dump({"source": os.path.basename(sys.argv[1]), "unit": "円", "totals": tot, **t},
              sys.stdout, ensure_ascii=False, indent=1)
    sys.exit(1 if f else 0)
