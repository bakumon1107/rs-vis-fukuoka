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
    # 区分の欄は左端で見る。縦書きの1字ずつのほか、横書きの長い区分名（R8 278133 p27「人権が尊重される心豊かな社会づくり」）は
    # 字の中心が欄の右にはみ出す（中心で見ると区分が空になった。6件）
    pos = (lambda w: w["x0"]) if col == "kubun" else (lambda w: (w["x0"] + w["x1"]) / 2)
    return [w for w in words if a <= pos(w) < b and y0 <= (w["top"] + w["bottom"]) / 2 < y1]


def text_of(ws):
    ws = sorted(ws, key=lambda w: (round(w["top"]), w["x0"]))
    return "".join(w["text"] for w in ws)


OUTSIDE_PILLAR_HEAD = "計画推進の基盤づくり"
DIVISION_ENDS = ("課", "室", "本部", "局", "所", "センター", "部", "庁")


def division_of(ws) -> str:
    """課の欄 → 課名。複数の課が担当する事項は、課が1行ずつ縦に並ぶ（R8 278133 p40「教員の働き方改革推進費」は5課）。
    行ごとに分けて「、」でつなぐ。課名の終わり（課・室・本部…）で終わらない行は、長い課名の折り返しとして次の行とつなぐ。
    「外」で始まる行（「外21課」）は前の課の続き"""
    lines: dict[int, list] = {}
    for w in ws:
        lines.setdefault(round(w["top"]), []).append(w)
    out: list[str] = []
    for top in sorted(lines):
        t = "".join(w["text"] for w in sorted(lines[top], key=lambda w: w["x0"]))
        # 「外21課」（ほか 21 課）は前の課の続き（「財産活用課外21課」。R8「公用車への電動車導入費」）
        # 「…事務局」の次の行の課はその事務局の課（「議会事務局」「総務課」→ 議会事務局総務課。R8 277220 の5事項。事務局だけの課名はない）
        if out and (not out[-1].endswith(DIVISION_ENDS) or t.startswith("外") or out[-1].endswith("事務局")):
            out[-1] += t
        else:
            out.append(t)
    # 区切りは「、」（課名そのものに「・」がある: 「自動車・水素産業振興課」「水・大気環境課」「九博・世界遺産・文化施設課」）
    return "、".join(out)


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


# 科目の欄の中の款・項・目の列の境（x の中心。R8 で 款 ≈107〜114・項 ≈120〜126・目 ≈133〜139）
KAMOKU_SPLIT = (117, 130)


# 結合セルの字の高さと、かたまりの最初・最後の目の行の真ん中の差の許し（pt。R8 で 0.05〜0.5）
RANGE_TOL = 1.5


def kamoku_lines(ws, notes: list | None = None) -> list[str]:
    """科目の欄の字 → ["款 項 目", ...]。複数の科目にまたがる事項は、目の字ごとに1つの科目。款・項は結合したセルで、
    またがる目の行の縦の真ん中に1回だけ印字される（R8 278133 p1「中小企業成長投資・賃上げ応援費」: 款「7」が全部の目の真ん中、
    項「1」が目 1・3 の真ん中、項「2」が目 5・6 の真ん中。277214 p3「ワンヘルス教育推進費」: 款「10」の高さ 307.8 が
    目 4・1・2 の真ん中 307.85 → 5-3-1・10-1-4・10-8-1・10-9-2。前の行から受け継ぐと 5-1-4 と誤る）。
    款・項の字ごとに、目の行のかたまり（縦の真ん中が字の高さ）を当てる（by_range。いちばん近い字を当てると、長いセルの端の行が
    隣の短いセルの字に近くなり、黙って別の款・項になる）。かたまりに分けられないときは by_order（最初と最後の行だけ決め、間の行は「?」。
    字が1種類ならどの行もその字）で、「?」が残れば notes に書く（main の WARN で知らせる。「?」は書き出しが予算の目と直しの表で決める）。
    目のない字の並び（「企業会計」「特別会計」「外」）はそのまま返す"""
    cols: list[list[dict]] = [[], [], []]
    other = []
    for w in ws:
        t = w["text"].translate(Z2H)
        if not t.isdigit():
            other.append(t)
            continue
        cx = (w["x0"] + w["x1"]) / 2
        cols[0 if cx < KAMOKU_SPLIT[0] else 1 if cx < KAMOKU_SPLIT[1] else 2].append({**w, "text": t})
    if not cols[2]:
        if cols[0] or cols[1]:
            # 款・項の字はあるのに目の字がない（目の字が項の列に寄った、など）: 黙って科目を落とさず、決まらない科目として返す
            # （main の WARN、書き出し export_policies の FAIL で知らせる）
            kan = "".join(c["text"] for c in cols[0]) or "?"
            kou = "".join(c["text"] for c in cols[1]) or "?"
            return [f"{kan} {kou} ?"] + (["".join(other)] if other else [])
        return ["".join(other)] if other else []

    rows = sorted(cols[2], key=lambda w: w["top"])
    tops = [m["top"] for m in rows]

    def by_range(cands):
        """字ごとに、続いた目の行のかたまりを当てる（結合セルの字は、かたまりの縦の真ん中に印字される）。上の字から順に、
        かたまりの最初の行と最後の行の真ん中が字の高さと合う最後の行を1つに決める。決まらない・行が余るときは None"""
        labels = sorted(cands, key=lambda c: c["top"])
        out, s = [None] * len(tops), 0
        for i, c in enumerate(labels):
            ends = [e for e in range(s, len(tops)) if abs((tops[s] + tops[e]) / 2 - c["top"]) <= RANGE_TOL]
            if i == len(labels) - 1:
                ends = [e for e in ends if e == len(tops) - 1]
            if len(ends) != 1:
                return None
            out[s:ends[0] + 1] = [c["text"]] * (ends[0] + 1 - s)
            s = ends[0] + 1
        return out if s == len(tops) else None

    def by_order(cands):
        """かたまりに分けられないとき（字が行の間に半行ずれて印字された。R8 で5件）: セルは上から字の順に並ぶので、最初の行は
        最初の字、最後の行は最後の字に決まる。その間の行は、字が1つなら決まり、2つ以上なら決めない（「?」。書き出しが予算の目と
        確かめた直しの表で決める）。いちばん近い字は当てない（長いセルの端の行が隣のセルの字に近くなり、黙って誤る）"""
        labels = [c["text"] for c in sorted(cands, key=lambda c: c["top"])]
        if len(labels) > len(tops):
            return ["?"] * len(tops)  # 字が目の行より多い（目の字を読み落とした）: どの行も決めない
        if len(set(labels)) == 1:
            # 字が1種類なら、どの行もその款・項（R8 の款の列で、字がかたまりの真ん中からずれた3件。どれも予算の目で確かめた）
            return [labels[0]] * len(tops)
        return [labels[0]] + ["?"] * (len(tops) - 2) + [labels[-1]] if len(tops) >= 2 else ["?"]

    cells = []
    for col in (cols[0], cols[1]):
        r = by_range(col) if col else None
        if r is None:
            r = by_order(col) if col else ["?"] * len(tops)
            if col and "?" in r and notes is not None:
                notes.append("款・項の字の位置が目の行のかたまりと合わず、最初と最後の行だけ決めた")
        cells.append(r)
    out = [f"{cells[0][i]} {cells[1][i]} {m['text']}" for i, m in enumerate(rows)]
    return out + (["".join(other)] if other else [])


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
                # 柱の名前は2行に折り返すことがある（「２．…子どもを安心して産み育」「てることができる」。R8 278133 p1）。
                # 2行目は1行目のすぐ下（top 60〜70）の左寄せの字。表の列見出し（「区分」「課」…）は同じ高さでも字が1〜2字。
                # 1行目が右端まで届いた（折り返した）ときだけつなぐ（R8: 折り返す柱2 は x1=500、ほかは 350 以下）。
                # 1行に収まった柱の名前に、すぐ下の別の字をつながないため
                wrapped = max((w["x1"] for w in head), default=0) >= 450
                second = [w for w in words if 60 <= w["top"] < 70 and w["x0"] < 100 and len(w["text"]) >= 3] if wrapped else []
                pillar = t + text_of(second)
            elif t.startswith(OUTSIDE_PILLAR_HEAD):
                # 4つの柱の後の「計画推進の基盤づくり」（番号のない見出し。R8 277220）。柱の外のグループとして名前で持つ
                # （柱が読めない None と分ける。書き出しは None を止める）
                pillar = OUTSIDE_PILLAR_HEAD
            hl = hlines(page)
            item_b = bounds(hl, 143)
            kamoku_b = bounds(hl, 104)
            ka_b = bounds(hl, 64)
            kubun_b = bounds(hl, 50)
            first_on_page = True
            kubun_seen_on_page = False
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
                ka = division_of(words_in(words, "ka", lo or y0, hi or y1))
                lo2, hi2 = enclosing(kamoku_b, y0, y1)
                km_notes: list[str] = []
                km = kamoku_lines(words_in(words, "kamoku", lo2 or y0, hi2 or y1), km_notes)
                lo3, hi3 = enclosing(kubun_b, y0, y1)
                kubun = text_of(words_in(words, "kubun", lo3 or y0, hi3 or y1))
                if kubun:
                    kubun_seen_on_page = True
                elif not kubun_seen_on_page and items and items[-1]["柱"] == pillar and items[-1]["区分"]:
                    # 区分のセルに名前がない: 前のページの区分が続いている（R8 278133 p27 の警察本部の2事項。
                    # 区分「社会的・経済的に厳しい状況にある方への支援」が p26 から続く。区分のセルには必ず名前があるので、
                    # 名前のないセルは前のページからの続きだけ）。続きはページの頭（そのページで区分の名前が出る前）だけなので、
                    # 名前が出た後の空のセルは読み取りの失敗として空のまま残す（main の WARN で知らせる）
                    kubun = items[-1]["区分"]
                items.append({
                    "柱": pillar, "区分": kubun, "課名": ka, "科目": km, **({"科目の当て方": km_notes} if km_notes else {}),
                    "新規": bool(words_in(words, "new", y0, y1)),
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
        # 区分（取組）が空: 読み取りの失敗（区分のセルには必ず名前がある。前のページからの続きは parse_pdf で埋めた）
        missing = [k for k in ("事項名", "予算額", "課名", "区分", "柱") if not it[k]] + \
            (["科目"] if not it["科目"] or any(not re.fullmatch(r"\d+ \d+ \d+", k) for k in it["科目"]) else []) + \
            (["科目の当て方"] if it.get("科目の当て方") else [])  # 款・項が目の行のかたまりに分けられず、間の行を「?」にした
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
