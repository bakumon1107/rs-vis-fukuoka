"""福岡県「当初予算の編成概要」の施策別資料（総合計画の柱ごとの主要事業一覧、Excel から出力したテキスト PDF）を抽出する。

1行（事項）の中身: 区分（取組事項）/ 課名 / 科目（款 項 目）/ [新] の印 / 事項名 / 予算額（括弧内は前年度額）/ 説明（○内訳 金額）
課名と科目は複数の事項にまたがる結合セルに1回だけ書かれているので、罫線の左端の位置でセルの範囲を求めて割り当てる
（R8 で確認: 事項の区切り線は x0≈143、科目セルの区切りは x0≈104、課セルの区切りは x0≈63、柱の区切りは x0≈49）。

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/extract_shisaku.py <柱1.pdf> [<柱2.pdf> ...] > shisaku.json

検証（stderr。FAIL で終了コード 1）:
- 説明欄の内訳に金額が付いている事項は、内訳の合計 = 予算額（内訳の一部にしか金額がないものは対象外）
- すべての事項に、事項名・予算額・課名・科目（款 項 目）がある
単位は千円（原資料のまま）。
"""
import json
import os
import re
import sys

import pdfplumber

COL = {"kubun": (0, 63), "ka": (63, 105), "kamoku": (105, 143), "new": (143, 158), "name": (158, 275),
       "amount": (275, 303), "expl": (303, 600)}
Z2H = str.maketrans("０１２３４５６７８９", "0123456789")
AMT = re.compile(r"^\(?\s*([\d,]+)\s*\)?$")


def is_header_row(name: str) -> bool:
    """表の列見出しの行か。事項名の欄に列見出し「事項名」「新規表示」「予算表示」の字が混ざって読まれる
    （R8 で「事項事新項規表示予算表示」）。事項名に「表示」が入るだけの事項（「食品表示…」）は見出しにしない。"""
    return bool(re.search(r"(新規|予算)表示", name))


def words_in(words, col, y0, y1):
    a, b = COL[col]
    return [w for w in words if a <= (w["x0"] + w["x1"]) / 2 < b and y0 <= (w["top"] + w["bottom"]) / 2 < y1]


def text_of(ws):
    ws = sorted(ws, key=lambda w: (round(w["top"]), w["x0"]))
    return "".join(w["text"] for w in ws)


def hlines(page):
    out = []
    for r in page.rects:
        if r["height"] < 1.5 and r["width"] > 30:
            out.append((r["top"], r["x0"]))
    for ln in page.lines:
        if abs(ln["top"] - ln["bottom"]) < 1 and abs(ln["x1"] - ln["x0"]) > 30:
            out.append((ln["top"], ln["x0"]))
    return sorted(out)


def bounds(lines, max_x0):
    return sorted({round(y, 1) for y, x0 in lines if x0 <= max_x0 + 1})


def enclosing(bs, y0, y1):
    lo = max([b for b in bs if b <= y0 + 1], default=None)
    hi = min([b for b in bs if b >= y1 - 1], default=None)
    return lo, hi


def parse_expl(ws):
    """説明欄: 「○」（または「[新]」）で始まる内訳。行の右端（x0>440）の数字がその内訳の金額。"""
    ex_words = sorted(ws, key=lambda w: (round(w["top"]), w["x0"]))
    expl, buf, amt, starts_new = [], [], None, False
    for w in ex_words:
        t = w["text"]
        if t == "○" or t.startswith("○") or t == "[新]":
            if buf or amt is not None:
                expl.append({"text": "".join(buf), "amount": amt, "starts_new": starts_new})
            buf, amt, starts_new = ([t.lstrip("○")] if t not in ("○",) else []), None, True
            continue
        if re.fullmatch(r"[\d,]+", t) and w["x0"] > 440:
            amt = int(t.replace(",", ""))
        else:
            buf.append(t)
    if buf or amt is not None:
        expl.append({"text": "".join(buf), "amount": amt, "starts_new": starts_new})
    return expl


def parse_pdf(path):
    items = []
    with pdfplumber.open(path) as pdf:
        pillar = None
        for pi, page in enumerate(pdf.pages, 1):
            words = page.extract_words(x_tolerance=1.5, keep_blank_chars=False)
            head = [w for w in words if w["top"] < 60]
            t = text_of(head)
            m = re.match(r"^([１-９\d])．(.+)$", t)
            if m:
                pillar = t
            hl = hlines(page)
            item_b = bounds(hl, 143)
            kamoku_b = bounds(hl, 104)
            ka_b = bounds(hl, 64)
            kubun_b = bounds(hl, 50)
            first_on_page = True
            for y0, y1 in zip(item_b, item_b[1:]):
                name = text_of(words_in(words, "name", y0, y1))
                amts = [w["text"] for w in sorted(words_in(words, "amount", y0, y1), key=lambda w: w["top"])]
                if name.startswith("事項名"):
                    continue
                if not name and not amts and first_on_page and items:
                    # 前のページから続く事項（説明欄の続きだけがある）
                    cont = parse_expl(words_in(words, "expl", y0, y1))
                    if cont and not cont[0]["starts_new"] and items[-1]["説明"]:
                        last = items[-1]["説明"][-1]
                        last["text"] += cont[0]["text"]
                        last["amount"] = last["amount"] if cont[0]["amount"] is None else cont[0]["amount"]
                        cont = cont[1:]
                    items[-1]["説明"] += [{k: v for k, v in c.items() if k != "starts_new"} for c in cont]
                    items[-1]["pdf_pages"].append(pi)
                    first_on_page = False
                    continue
                first_on_page = False
                # 事項名・予算額の両方が取れない行と、表の列見出しの行（R8 で 49行、どれも予算額なし）を捨てる。
                # 片方だけ取れたそれ以外の行は事項として残し、main の WARN（欠け）で知らせる
                if (not name and not amts) or (not amts and is_header_row(name)):
                    continue
                prev = cur = None
                for s in amts:
                    s2 = s.replace(" ", "")
                    if s2.startswith("("):
                        mm = re.search(r"[\d,]+", s2)
                        prev = int(mm.group(0).replace(",", "")) if mm else prev
                    elif re.fullmatch(r"[\d,]+", s2):
                        cur = int(s2.replace(",", ""))
                    elif re.fullmatch(r"\d+\)", s2):  # 「( 0)」が2語に分かれる
                        prev = int(s2[:-1])
                expl = [{k: v for k, v in c.items() if k != "starts_new"} for c in parse_expl(words_in(words, "expl", y0, y1))]
                lo, hi = enclosing(ka_b, y0, y1)
                ka = text_of(words_in(words, "ka", lo or y0, hi or y1))
                lo2, hi2 = enclosing(kamoku_b, y0, y1)
                # 科目は「款 項 目」が1行に並ぶ。複数の科目にまたがる事項は行が複数になる
                km_words = sorted(words_in(words, "kamoku", lo2 or y0, hi2 or y1), key=lambda w: (round(w["top"] / 3), w["x0"]))
                km_lines: dict[int, list[str]] = {}
                for w in km_words:
                    km_lines.setdefault(round(w["top"] / 3), []).append(w["text"].translate(Z2H))
                km = [" ".join(v) for v in km_lines.values()]
                lo3, hi3 = enclosing(kubun_b, y0, y1)
                kubun = text_of(words_in(words, "kubun", lo3 or y0, hi3 or y1))
                items.append({
                    "柱": pillar, "区分": kubun, "課名": ka, "科目": km, "新規": bool(words_in(words, "new", y0, y1)),
                    "事項名": name, "予算額": cur, "前年度": prev, "説明": expl,
                    "source": os.path.basename(path), "pdf_page": pi, "pdf_pages": [pi],
                })
    return items


def main():
    items = []
    for p in sys.argv[1:]:
        items += parse_pdf(p)
    fails = warns = 0
    for it in items:
        missing = [k for k in ("事項名", "予算額", "課名") if not it[k]] + \
            (["科目"] if not it["科目"] or any(not re.fullmatch(r"\d+ \d+ \d+", k) for k in it["科目"]) else [])
        if missing:
            warns += 1
            print(f"WARN {it['source']} p{it['pdf_page']} {it['事項名']}: 欠け {missing} 科目={it['科目']}", file=sys.stderr)
        amts = [e["amount"] for e in it["説明"]]
        if len(amts) >= 2 and all(a is not None for a in amts) and it["予算額"] is not None:
            if sum(amts) != it["予算額"]:
                fails += 1
                print(f"FAIL {it['source']} p{it['pdf_page']} {it['事項名']}: 内訳の合計 {sum(amts):,} ≠ 予算額 {it['予算額']:,}", file=sys.stderr)
    total = sum(it["予算額"] or 0 for it in items)
    print(f"事項 {len(items)} 件、予算額合計 {total:,} 千円、新規 {sum(it['新規'] for it in items)} 件、"
          f"WARN={warns} FAIL={fails}", file=sys.stderr)
    json.dump({"unit": "千円", "items": items}, sys.stdout, ensure_ascii=False, indent=1)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
