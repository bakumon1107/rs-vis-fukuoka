"""福岡県「歳入歳出決算概要説明書」の「特別会計歳入歳出決算の状況」（7章）を抽出・検証する。

会計ごとに、歳入の款（予算現額・調定額・収入済額・不納欠損額・収入未済額・増減額）、歳出の款・項の決算額、
項ごとの目（予算現額・支出済額・翌年度繰越額・不用額）と、目ごとの「決算の内容」「不用額の内容」の文を取る。
設計: docs/local-gov/tasks/20261114_0043_R6決算の書き出しと見方の設計.md 8章

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/extract_kessan_toku.py <概要説明書.pdf> > kessan-toku.json

前提（R6 で確認）:
- テキスト PDF（272595）。目次の「７ 特別会計歳入歳出決算の状況」に会計と印字ページ、「附属資料」の前で終わる
- 会計の始まりは「《福岡県○○特別会計》」。【歳入】の款の表 →【歳出】の款・項の表 →「N款 M項 項の名前」ごとの目の表
- 款・項の表は、款の欄と項の欄が同じ行に並び、長い名前は上下の行に折り返す（空行で区切られる）

検証（すべて完全一致。1円でもずれたら FAIL。終了コード 1）:
- 歳入: 款の合計 = 計（6列）、増減額 = 収入済額 − 予算現額、調定額 = 収入済額 + 不納欠損額 + 収入未済額
- 歳出: 項ごとに 目の合計 = 計（4列）、予算現額 = 支出済額 + 翌年度繰越額 + 不用額、項の計の支出済額 = 款・項の表の決算額
- 会計ごと: 款・項の表の合計 = 計、歳入の予算現額の計 = 歳出の目の予算現額の合計
- 会計ごとの歳入・歳出の合計を「特別会計歳入歳出決算一覧表」（5章）と突き合わせる
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kessan_common import ExplainReader, assemble_rows, attach_explain, flat, pdftext, printed_page, to_int  # noqa: E402

COLS = ["予算現額", "支出済額", "翌年度繰越額", "不用額"]
REV_COLS = ["予算現額", "調定額", "収入済額", "不納欠損額", "収入未済額", "増減額"]
NUM = r"▲?\s?[\d,]+"
Z2H = str.maketrans("０１２３４５６７８９", "0123456789")


def toc(pdf: str) -> tuple[list[tuple[str, int]], int, int]:
    """目次から 7章の会計と印字ページ、7章の終わり（附属資料の始まり）、5章（一覧表）の印字ページを取る。"""
    t = flat("".join(pdftext(pdf, p) for p in range(1, 8)))
    if "特別会計歳入歳出決算の状況" not in t or "附属資料" not in t:
        raise SystemExit("目次が見つからない")
    sec = t.split("特別会計歳入歳出決算の状況", 1)[1].split("附属資料", 1)[0]
    items = [(name, int(pg)) for _, name, pg in re.findall(r"（([0-9０-９]+)）([^…（）]+?)…+([0-9]+)", sec)]
    end = int(re.search(r"…+([0-9]+)", t.split("附属資料", 1)[1]).group(1))
    ichiran = int(re.search(r"特別会計歳入歳出決算一覧表…+([0-9]+)", t).group(1))
    print(f"目次: {items} 終わり {end} 一覧表 {ichiran}", file=sys.stderr)
    return items, end, ichiran


def page_map(pdf: str, last: int) -> dict[int, int]:
    pmap: dict[int, int] = {}
    for p in range(1, 400):
        try:
            t = pdftext(pdf, p)
        except Exception:  # noqa: BLE001
            break
        pp = printed_page(t)
        if pp is not None:
            pmap.setdefault(pp, p)
            if pp >= last:
                break
    return pmap


def is_header(line: str) -> bool:
    f = flat(line)
    return (bool(re.fullmatch(r"[-‑―]\d+[-‑―]", f)) or f in ("区分", "円", "決算額") or re.fullmatch(r"円+％?", f) is not None
            or f.startswith(("目目の名称", "款款の名称", "予算現額", "区分予算現額", "（Ｐ")) or "予算現額対比" in f
            or f.startswith("増減額"))


REV_RE = re.compile(rf"^\s*(?P<no>\d+)?\s*(?P<name>\D*?)\s+(?P<nums>(?:{NUM}\s+){{5}}{NUM})\s+(?P<pct>[\d.]+)\s*$")


def parse_revenue(lines: list[str], fails: list[str], label: str):
    """歳入の款の表。名前の折り返しは、番号のない名前だけの行を直前・直後の款につなぐ。"""
    rows, total, pending = [], None, ""
    for ln in lines:
        m = REV_RE.match(ln)
        if not m:
            if not re.search(r"\d", ln):
                pending += flat(ln)
            continue
        nums = [to_int(x) for x in re.findall(NUM, m.group("nums"))]
        name = flat(m.group("name"))
        if name == "計":
            total = dict(zip(REV_COLS, nums))
            continue
        if m.group("no") is None:
            fails.append(f"{label} 歳入: 番号のない行 {ln.strip()}")
            continue
        rows.append({"no": int(m.group("no")), "name": pending + name, **dict(zip(REV_COLS, nums))})
        pending = ""
    return rows, total


def parse_summary(blocks: list[list[str]], split: int, fails: list[str], label: str):
    """歳出の款・項の表。空行で区切られた区画ごとに、左（款）と右（項）に分けて番号と名前を取る。決算額は区画の最後の数字。"""
    out, total, cur_kan = [], None, None
    waiting: list[dict] = []  # 款の名前より上に出た項（款の欄は項が複数あると真ん中の行に出る。R6 国民健康保険の 1款）
    for blk in blocks:
        text = "\n".join(blk)
        if flat(text).startswith("計") or re.match(r"^\s*計\s", blk[-1]) or flat(blk[0]).startswith("計"):
            nums = re.findall(rf"{NUM}\s*$", blk[-1])
            if nums:
                total = to_int(nums[0])
            continue
        amt = None
        left, right = [], []
        for ln in blk:
            m = re.search(rf"({NUM})\s*$", ln)
            body = ln
            # 決算額は項の欄より右の、行末の数字（予備費は 0）。項の番号は項の欄の左端にあるので、それより十分右のものだけ
            if m and m.start() > split + 20:
                amt = to_int(m.group(1))
                body = ln[:m.start()]
            left.append(body[:split])
            right.append(body[split:])
        if amt is None:
            fails.append(f"{label} 歳出の款・項の表: 決算額のない区画 {flat(text)[:40]}")
            continue
        lt, rt = " ".join(left), " ".join(right)
        kno = re.search(r"\b(\d+)\b", lt)
        qno = re.search(r"\b(\d+)\b", rt)
        if qno is None:
            fails.append(f"{label} 歳出の款・項の表: 項の番号が読めない区画 {flat(text)[:40]}")
            continue
        row = {"款": None, "款名": None, "項": int(qno.group(1)), "項名": flat(re.sub(r"\d", "", rt)), "決算額": amt}
        out.append(row)
        if kno:
            cur_kan = {"no": int(kno.group(1)), "name": flat(re.sub(r"\d", "", lt))}
            # 款の名前より上に出た項は、項の番号が 1 から続く間だけこの款に付ける
            for w in waiting:
                w["款"], w["款名"] = cur_kan["no"], cur_kan["name"]
            waiting = []
        elif cur_kan is None or row["項"] == 1:
            waiting.append(row)
            continue
        row["款"], row["款名"] = cur_kan["no"], cur_kan["name"]
    for w in waiting:
        fails.append(f"{label} 歳出の款・項の表: 款の分からない項 {w['項']} {w['項名']}")
    return out, total


def parse(pdf: str):
    items, end, ichiran = toc(pdf)
    pmap = page_map(pdf, end)
    starts = [pg for _, pg in items] + [end]
    accounts, fails = [], []
    for (name, pstart), pnext in zip(items, starts[1:]):
        lines = []
        for pno in range(pmap[pstart], pmap[pnext]):
            lines.extend(pdftext(pdf, pno).splitlines())
        acc = {"会計": name, "印字ページ": [pstart, pnext - 1], "pdf_page": pmap[pstart],
               "歳入": [], "歳入の計": None, "款項": [], "款項の計": None, "項": []}
        mode, rev_lines, sum_blocks, blk, split = None, [], [], [], None
        kou = None
        for ln in lines:
            f = flat(ln)
            if f.startswith("【歳入】"):
                mode = "revenue"
                continue
            if f.startswith("【歳出】"):
                mode = "summary"
                continue
            mk = re.match(r"^([0-9０-９]+)款([0-9０-９]+)項(.+)$", f)
            if mk and mode in ("summary", "kou", "explain"):
                if mode == "summary" and blk:
                    sum_blocks.append(blk)
                    blk = []
                kou = {"款": int(mk.group(1).translate(Z2H)), "項": int(mk.group(2).translate(Z2H)), "項名": mk.group(3),
                       "目": [], "計": None, "_lines": [], "_explain": ExplainReader()}
                acc["項"].append(kou)
                mode = "kou"
                continue
            if f == "説明" or f.startswith("説明"):
                if mode == "kou":
                    mode = "explain"
                elif mode == "revenue":
                    mode = "revenue_explain"
                continue
            if mode == "revenue":
                if not is_header(ln) and ln.strip():
                    rev_lines.append(ln)
            elif mode == "summary":
                if "項の名称" in f or "項項の名称" in f:
                    split = ln.index("項", ln.index("称") + 1) - 2 if "称" in ln else None
                    continue
                if is_header(ln):
                    continue
                if not ln.strip():
                    if blk:
                        sum_blocks.append(blk)
                        blk = []
                    continue
                blk.append(ln)
            elif mode == "kou":
                if ln.strip() and not is_header(ln):
                    kou["_lines"].append(ln)
            elif mode == "explain":
                kou["_explain"].feed(ln, is_header)
        if blk:
            sum_blocks.append(blk)
        acc["歳入"], acc["歳入の計"] = parse_revenue(rev_lines, fails, name)
        if split is None:
            fails.append(f"{name}: 歳出の款・項の表の見出しが見つからない")
            split = 36
        acc["款項"], acc["款項の計"] = parse_summary(sum_blocks, split, fails, name)
        for k in acc["項"]:
            for kind, r in assemble_rows(k.pop("_lines"), 4, label=f"{name} {k['款']}款{k['項']}項", strip_notes=True):
                if kind != "row":
                    continue
                if r.no is None and r.name == "計":
                    k["計"] = dict(zip(COLS, r.nums))
                elif r.no is not None:
                    k["目"].append({"no": r.no, "name": r.name, **dict(zip(COLS, r.nums)), **r.extra})
                else:
                    fails.append(f"{name} {k['款']}款{k['項']}項: 番号のない行 {r.name} {r.nums}")
            attach_explain(k["目"], k.pop("_explain").result())
        accounts.append(acc)
    return accounts, fails, ichiran, pmap


def parse_ichiran(pdf: str, pmap: dict[int, int], page: int) -> list[dict]:
    """特別会計歳入歳出決算一覧表（5章。2ページ）: 会計ごとの 予算現額・歳入決算額・歳出決算額。
    会計の名前は3行に折り返すので、数字の行（10列以上）を上から順に目次の会計の順と対応させる（R6 で確認）。
    列: 予算現額 / 歳入決算額 / 収入率 / 歳出決算額 / 執行率 / 差引残額 / 繰越額3列 / 翌年度へ繰越金"""
    t = pdftext(pdf, pmap[page]) + pdftext(pdf, pmap[page] + 1)
    rows = []
    for ln in t.splitlines():
        toks = re.findall(r"▲?[\d,]+(?:\.\d+)?", ln)
        if len(toks) >= 10 and "." in toks[2] and "." in toks[4]:
            v = [to_int(x) if "." not in x else float(x) for x in toks]
            rows.append({"合計": "合計" in flat(ln), "予算現額": v[0], "歳入決算額": v[1], "歳出決算額": v[3]})
    return rows


def verify(accounts, fails, ichiran_rows) -> int:
    def fail(msg):
        fails.append(msg)

    for a in accounts:
        n = a["会計"]
        rt = a["歳入の計"]
        if rt is None:
            fail(f"{n} 歳入: 計の行がない")
        else:
            for c in REV_COLS:
                s = sum(r[c] for r in a["歳入"])
                if s != rt[c]:
                    fail(f"{n} 歳入 {c}: 款の合計 {s:,} ≠ 計 {rt[c]:,}")
        for r in a["歳入"]:
            if r["収入済額"] - r["予算現額"] != r["増減額"]:
                fail(f"{n} 歳入 {r['no']}款 {r['name']}: 増減額が合わない")
            over = r["収入済額"] + r["不納欠損額"] + r["収入未済額"] - r["調定額"]
            if over > 0:
                # 収入済額は過誤納金（払い過ぎ）を内数に含む。調定額 = 収入済額 − 過誤納金 + 不納欠損額 + 収入未済額（一般会計の明細表と同じ。
                # 特別会計の款の表には過誤納金の行がない。R6 住宅管理 1款で 177,125 円）
                r["過誤納金"] = over
                print(f"WARN {n} 歳入 {r['no']}款 {r['name']}: 過誤納金とみなす {over:,} 円（収入済額 + 不納欠損額 + 収入未済額 − 調定額）",
                      file=sys.stderr)
            elif over < 0:
                fail(f"{n} 歳入 {r['no']}款 {r['name']}: 調定額が 収入済額 + 不納欠損額 + 収入未済額 より {-over:,} 円多い")
        summ = {(x["款"], x["項"]): x["決算額"] for x in a["款項"]}
        if a["款項の計"] is not None and sum(summ.values()) != a["款項の計"]:
            fail(f"{n} 歳出の款・項の表: 合計 {sum(summ.values()):,} ≠ 計 {a['款項の計']:,}")
        bc = 0
        for k in a["項"]:
            ms = {c: sum(m[c] for m in k["目"]) for c in COLS}
            bc += ms["予算現額"]
            if k["計"] is not None:
                for c in COLS:
                    if ms[c] != k["計"][c]:
                        fail(f"{n} {k['款']}款{k['項']}項 {c}: 目の合計 {ms[c]:,} ≠ 計 {k['計'][c]:,}")
            elif len(k["目"]) != 1:
                fail(f"{n} {k['款']}款{k['項']}項: 計の行がない（目 {len(k['目'])} 件）")
            for m in k["目"]:
                if m["予算現額"] != m["支出済額"] + m["翌年度繰越額"] + m["不用額"]:
                    fail(f"{n} {k['款']}款{k['項']}項{m['no']}目 {m['name']}: 予算現額 ≠ 支出済額 + 繰越 + 不用額")
            key = (k["款"], k["項"])
            if key not in summ:
                fail(f"{n} {k['款']}款{k['項']}項: 款・項の表にない")
            elif summ[key] != ms["支出済額"]:
                fail(f"{n} {k['款']}款{k['項']}項: 款・項の表 {summ[key]:,} ≠ 目の支出済額の合計 {ms['支出済額']:,}")
        missing = set(summ) - {(k["款"], k["項"]) for k in a["項"]}
        if missing:
            fail(f"{n}: 款・項の表にあるが目の表がない項 {sorted(missing)}")
        if rt is not None and rt["予算現額"] != bc:
            fail(f"{n}: 歳入の予算現額 {rt['予算現額']:,} ≠ 歳出の目の予算現額の合計 {bc:,}")
    body = [r for r in ichiran_rows if not r["合計"]]
    if len(body) != len(accounts):
        fail(f"一覧表の会計の行 {len(body)} ≠ 会計 {len(accounts)}")
    for a, ich in zip(accounts, body):
        n, rt = a["会計"], a["歳入の計"]
        spent = sum(x["決算額"] for x in a["款項"])
        for col, got in (("予算現額", rt and rt["予算現額"]), ("歳入決算額", rt and rt["収入済額"]), ("歳出決算額", spent)):
            if got != ich[col]:
                fail(f"{n}: 一覧表の{col} {ich[col]:,} ≠ 抽出 {got:,}")
    tot = next((r for r in ichiran_rows if r["合計"]), None)
    if tot is None or tot["歳出決算額"] != sum(x["決算額"] for a in accounts for x in a["款項"]):
        fail(f"一覧表の合計の歳出決算額 {tot and tot['歳出決算額']} ≠ 抽出の合計")
    for f in fails:
        print("FAIL " + f, file=sys.stderr)
    print(f"会計 {len(accounts)}、項 {sum(len(a['項']) for a in accounts)}、目 {sum(len(k['目']) for a in accounts for k in a['項'])}、"
          f"歳出の支出済額の合計 {sum(x['決算額'] for a in accounts for x in a['款項']):,}", file=sys.stderr)
    print(f"FAIL={len(fails)}", file=sys.stderr)
    return len(fails)


if __name__ == "__main__":
    accs, fl, ich_page, pm = parse(sys.argv[1])
    ich = parse_ichiran(sys.argv[1], pm, ich_page)
    nf = verify(accs, fl, ich)
    json.dump({"source": os.path.basename(sys.argv[1]), "unit": "円", "会計": accs}, sys.stdout, ensure_ascii=False, indent=1)
    sys.exit(1 if nf else 0)
