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


def lines_of(ws, tol: float = 2.0) -> list[list[dict]]:
    """字を行にまとめる（行の最初の字の高さとの差が tol 以内なら同じ行。行の中は左から）。
    高さを四捨五入して並べると、同じ行の字が 158.46 と 158.54 のように境をまたいで別の行になり、
    説明欄の「○」と本文の順が入れ替わった（R8 で13件以上の内訳が語の途中で割れた）"""
    lines: list[list[dict]] = []
    for w in sorted(ws, key=lambda w: w["top"]):
        if lines and abs(w["top"] - lines[-1][0]["top"]) <= tol:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(ln, key=lambda w: w["x0"]) for ln in lines]


def text_of(ws):
    return "".join(w["text"] for ln in lines_of(ws) for w in ln)


# 額の欄の左の事項名の欄にこぼれた、額の字の切れ端（「2」「,783,636」→ 2,783,636。「(」「189,508)」→ (189,508)。R8 で4件）。
# 事項名の欄の右端（x0 がこれ以上）にある、数字・コンマ・括弧だけの字
AMOUNT_SPILL_X0 = 255
SPILL_RE = re.compile(r"[\d,()（）]+")
DEBT_RE = re.compile(r"[（(]債務負担行為?[）)]?$")


def amounts_of(name_ws, amount_ws):
    """事項名の欄と額の欄の字 → (事項名の字, 前年度, 今年度の額, 債務負担行為の限度額, 読めない字)。
    額の欄は行ごとに「(前年度)」と額。債務負担行為の行は1つのセルに 名前・(前年度)・今年度の額・（債務負担行為）・限度額 が
    縦に並ぶ（R8 278133 p41「県立学校施設整備費」: (14,585,909)・18,845,825・30,932,675。説明の内訳の合計は今年度の額）"""
    spill = [w for w in name_ws if w["x0"] >= AMOUNT_SPILL_X0 and SPILL_RE.fullmatch(w["text"])]
    name_words = [w for w in name_ws if w not in spill]
    prev, plains, bad = None, [], []
    for ln in lines_of(spill + amount_ws):
        s = "".join(w["text"] for w in ln).replace(" ", "").replace("（", "(").replace("）", ")")
        if re.fullmatch(r"\([\d,]+\)", s):
            if prev is not None:
                bad.append(f"前年度の括弧が2つ {s}")  # どちらが前年度か決められない（黙って後の数で上書きしない）
                continue
            prev = int(s[1:-1].replace(",", ""))
        elif re.fullmatch(r"\d[\d,]*", s):
            plains.append(int(s.replace(",", "")))
        else:
            bad.append(s)
    return name_words, prev, plains, bad


OUTSIDE_PILLAR_HEAD = "計画推進の基盤づくり"
DIVISION_ENDS = ("課", "室", "本部", "局", "所", "センター", "部", "庁")


def division_of(ws) -> str:
    """課の欄 → 課名。複数の課が担当する事項は、課が1行ずつ縦に並ぶ（R8 278133 p40「教員の働き方改革推進費」は5課）。
    行ごとに分けて「、」でつなぐ。課名の終わり（課・室・本部…）で終わらない行は、長い課名の折り返しとして次の行とつなぐ。
    「外」で始まる行（「外21課」）は前の課の続き"""
    out: list[str] = []
    for ln in lines_of(ws):
        t = "".join(w["text"] for w in ln)
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


HEAD_MARKS = ("○", "〇", "◯")
NEW_MARKS = ("[新]", "［新］")


def parse_expl(ws):
    """説明欄: 「○」（または「[新]」）で始まる内訳。行の右端（x0>440）の数字がその内訳の金額。"""
    # 内訳の額: 「○」の行に額があればそれ（下の「・」の細目の額は内訳の内訳なので足さない。R8 278133 p14「地域精神保健福祉対策費」:
    # ○協議会に対する助成 6,000 の下に ・「心の電話」相談事業 4,000・・普及啓発等 2,000）。「○」の行に額がなければ、続く行の額の合計
    # （細目にだけ額がある。R8「民生委員活動費」○民生委員の設置 の下の ・手当 282,775・・協議会補助金 65,955・・研修費等 1,017）
    expl: list[dict] = []
    cur: dict | None = None

    def close():
        if cur and (cur["buf"] or cur["head"] is not None or cur["rest"]):
            if cur["head"] is not None:
                amount, src = cur["head"], "head"
            else:
                amount, src = (sum(cur["rest"]), "sub") if cur["rest"] else (None, None)
            # amount_from: 額が「○」の行のものか、細目の合計か（ページをまたぐ続きの足し方に使う。parse_pdf の最後で外す）
            expl.append({"text": "".join(cur["buf"]), "amount": amount, "starts_new": cur["new"], "amount_from": src})

    for ln in lines_of(ws):
        t0 = ln[0]["text"]
        # 見出しの印は「○」のほか「〇」（漢数字のゼロ。R8 278133 p37・p38）「◯」、新規の「[新]」「［新］」
        is_head = t0 in HEAD_MARKS or t0.startswith(HEAD_MARKS) or t0 in NEW_MARKS
        if is_head or cur is None:
            close()
            cur = {"buf": [], "head": None, "rest": [], "new": is_head}
        line_amt = None
        for i, w in enumerate(ln):
            t = w["text"]
            if is_head and t in HEAD_MARKS:
                continue  # 行頭の印（「[新]」の後に別の語で続く「○」も）
            if i == 0 and is_head:
                cur["buf"].append(t.lstrip("".join(HEAD_MARKS)))  # 「[新]」は文の頭に残す（新規の内訳の印）
                continue
            if re.fullmatch(r"[\d,]+", t) and w["x0"] > 440:
                line_amt = int(t.replace(",", ""))
            else:
                cur["buf"].append(t)
        if line_amt is not None:
            if is_head:
                cur["head"] = line_amt
            else:
                cur["rest"].append(line_amt)
    close()
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
                name_words, prev, plains, bad_amounts = amounts_of(words_in(words, "name", y0, y1), words_in(words, "amount", y0, y1))
                name = text_of(name_words)
                amts = plains + ([] if prev is None else [prev]) + bad_amounts
                # 表の列見出しの行（「事項名」「事項新規表示予算表示…」。予算額なし）は、ページの最初の行の印を消さずに捨てる
                # （先に印を消すと、見出しの次にある前のページからの続きを読み落とす）
                if name.startswith("事項名") or (not amts and is_header_row(name)):
                    continue
                if not name and not amts and first_on_page and items:
                    # 前のページから続く事項（説明欄の続きだけがある）
                    cont = parse_expl(words_in(words, "expl", y0, y1))
                    if not cont:
                        continue  # 何もない帯（ページの頭の余白）: 続きではない。最初の行の印は残す
                    if cont and not cont[0]["starts_new"] and items[-1]["説明"]:
                        last = items[-1]["説明"][-1]
                        last["text"] += cont[0]["text"]
                        # 前のページの内訳の額が「○」の行のものなら、続きの額は細目の額なので足さない。
                        # 額がまだない・細目の合計なら、続きの細目の額を足す（細目がページをまたぐ）
                        if last.get("amount_from") != "head" and cont[0]["amount"] is not None:
                            last["amount"] = (last["amount"] or 0) + cont[0]["amount"]
                            last["amount_from"] = "sub"
                        cont = cont[1:]
                    items[-1]["説明"] += [{k: v for k, v in c.items() if k != "starts_new"} for c in cont]
                    items[-1]["pdf_pages"].append(pi)
                    first_on_page = False
                    continue
                first_on_page = False
                # 事項名・予算額の両方が取れない行を捨てる（表の列見出しの行は上で捨てた）。
                # 片方だけ取れたそれ以外の行は事項として残し、main の WARN（欠け）で知らせる
                if not name and not amts:
                    continue
                # 債務負担行為の行: 今年度の額と限度額の2つ（名前の「(債務負担行為)」は外し、限度額は別に持つ）。ほかの行は額が1つ
                debt = bool(DEBT_RE.search(name))
                if debt:
                    name = DEBT_RE.sub("", name)
                want = 2 if debt else 1
                cur = plains[0] if len(plains) == want else None
                limit = plains[1] if debt and len(plains) == 2 else None
                if len(plains) != want:
                    bad_amounts = bad_amounts + [f"額が {len(plains)} つ（{'債務負担行為の行は2つ' if debt else '1つのはず'}）"]
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
                    **({"債務負担行為": limit} if debt else {}), **({"額の読めない字": bad_amounts} if bad_amounts else {}),
                    "source": os.path.basename(path), "pdf_page": pi, "pdf_pages": [pi],
                })
    for it in items:
        for e in it["説明"]:
            e.pop("amount_from", None)
    return items


def main():
    items = []
    for p in sys.argv[1:]:
        items += parse_pdf(p)
    warns = 0
    fail_lines: list[str] = []
    for it in items:
        # 区分（取組）が空: 読み取りの失敗（区分のセルには必ず名前がある。前のページからの続きは parse_pdf で埋めた）
        # 予算額は 0 もある（債務負担行為だけの行「国際園芸博覧会出展事業費」の今年度の額 0）ので、None だけを欠けとする
        missing = [k for k in ("事項名", "課名", "区分", "柱") if not it[k]] + (["予算額"] if it["予算額"] is None else []) + \
            (["科目"] if not it["科目"] or any(not re.fullmatch(r"\d+ \d+ \d+", k) for k in it["科目"]) else []) + \
            (["科目の当て方"] if it.get("科目の当て方") else [])  # 款・項が目の行のかたまりに分けられず、間の行を「?」にした
        if missing:
            warns += 1
            print(f"WARN {it['source']} p{it['pdf_page']} {it['事項名']}: 欠け {missing} 科目={it['科目']}", file=sys.stderr)
        if it.get("額の読めない字"):
            # 額の欄に、額として読めない字・数の合わない額がある（黙って最後の数を使わない）
            fail_lines.append(f"{it['source']} p{it['pdf_page']} {it['事項名']}: 額の欄が読めない {it['額の読めない字']}")
        amts = [e["amount"] for e in it["説明"]]
        known = [a for a in amts if a is not None]
        if it["予算額"] is not None and known:
            # 内訳の額がすべて読めたら合計 = 予算額（内訳が1つでも）。一部だけ読めたときも、読めた額の合計が予算額を超えれば誤り
            if (len(known) == len(amts) and sum(known) != it["予算額"]) or sum(known) > it["予算額"]:
                fail_lines.append(f"{it['source']} p{it['pdf_page']} {it['事項名']}: 内訳の合計 {sum(known):,} ≠ 予算額 {it['予算額']:,}"
                                  f"（内訳 {len(amts)}・額のある内訳 {len(known)}）")
    for f in fail_lines:
        print("FAIL " + f, file=sys.stderr)
    total = sum(it["予算額"] or 0 for it in items)
    print(f"事項 {len(items)} 件、予算額合計 {total:,} 千円、新規 {sum(it['新規'] for it in items)} 件、"
          f"WARN={warns} FAIL={len(fail_lines)}", file=sys.stderr)
    # 失敗の一覧も書く（書き出し export_policies はこれが空でなければ止める。終了コードを見ない使い方でも通さない）
    json.dump({"unit": "千円", "items": items, "fails": fail_lines}, sys.stdout, ensure_ascii=False, indent=1)
    sys.exit(1 if fail_lines else 0)


if __name__ == "__main__":
    main()
