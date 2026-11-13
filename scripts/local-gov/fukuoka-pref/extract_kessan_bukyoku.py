"""福岡県「歳入歳出決算概要説明書」の「一般会計歳入歳出決算の状況」（部局別）の歳出を抽出・検証する。

部局 → 款 → 項 → 目 の決算（予算現額・支出済額・翌年度繰越額・不用額）を取り、
同じ書類の「款項目別明細表」（extract_kessan_kmk.py の出力）と全件突き合わせる。

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/extract_kessan_bukyoku.py <概要説明書.pdf> <kessan-kmk.json> > kessan-bukyoku.json

検証（すべて完全一致。1円でもずれたら FAIL。終了コード 1）:
1. 部局×項: 目の合計 = 目の表の「計」 = 項の集計表の決算額
2. 部局×款: 項の集計表の合計 = 集計表の「計」
3. 全部局の同じ目の合計 = 款項目別明細表の目（4列）。款項目別明細表のすべての目がどこかの部局に現れる
4. 目の名称が款項目別明細表と一致する
"""
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kessan_common import ExplainReader, assemble_rows, attach_explain, flat, pdftext, printed_page  # noqa: E402

COLS = ["予算現額", "支出済額", "翌年度繰越額", "不用額"]
Z2H = str.maketrans("０１２３４５６７８９", "0123456789")


def toc(pdf: str) -> list[tuple[str, int]]:
    """目次から「６ 一般会計歳入歳出決算の状況」の部局と印字ページを取る。"""
    # 目次は2ページにまたがる（R6: PDF 3〜4ページ）ので、先頭の数ページをつなげて読む
    t = "".join(pdftext(pdf, p) for p in range(1, 8))
    if not ("一般会計歳入歳出決算の状況" in flat(t) and "特別会計歳入歳出決算の状況" in flat(t)):
        raise SystemExit("目次が見つからない")
    sec = flat(t).split("一般会計歳入歳出決算の状況", 1)[1].split("特別会計歳入歳出決算の状況", 1)[0]
    # \d は全角数字にも一致するので [0-9] を使う（「教育庁……186」の直後の章番号「７」を巻き込んだ実例あり）
    items = re.findall(r"（([0-9０-９]+)）([^…（）]+?)…+([0-9]+)", sec)
    out = [(name, int(pg)) for _, name, pg in items]
    # 次の章（特別会計）の最初の項目の開始ページを終端にする
    after = flat(t).split("特別会計歳入歳出決算の状況", 1)[1]
    m = re.search(r"…+([0-9]+)", after)
    if not m:
        raise SystemExit("目次の終端（特別会計の開始ページ）が見つからない")
    out.append(("__END__", int(m.group(1))))
    print(f"目次: {out}", file=sys.stderr)
    return out


def is_header(line: str) -> bool:
    f = flat(line)
    return (
        bool(re.fullmatch(r"[-‑―]\d+[-‑―]", f))
        or f in ("区分", "円", "決算額")
        or f.startswith(("目目の名称", "項項の名称", "予算現額", "決算額", "区分予算現額"))
        or "及び流用増減額" in f
        or "当初予算額" in f
        or f.startswith("予備費支出")
        or re.fullmatch(r"円+", f) is not None
    )


def parse(pdf: str):
    parts = toc(pdf)
    # 印字ページ → PDF ページ
    pmap: dict[int, int] = {}
    p = 1
    while True:
        try:
            t = pdftext(pdf, p)
        except Exception:  # noqa: BLE001
            break
        if not t.strip() and p > 400:
            break
        pp = printed_page(t)
        if pp is not None:
            pmap.setdefault(pp, p)
        if pp is not None and pp >= parts[-1][1]:
            break
        p += 1
        if p > 400:
            break
    result = []
    skipped: list[str] = []
    for (bname, pstart), (_, pnext) in zip(parts, parts[1:]):
        if pstart not in pmap or pnext not in pmap:
            raise SystemExit(f"印字ページが見つからない: {bname} {pstart}-{pnext}")
        dept = {"部局": bname, "印字ページ": [pstart, pnext - 1], "款": []}
        mode = None  # None / "revenue" / "expense" / "explain"
        cur_kan = None
        # 部局全体を1本の流れとして、款・項の見出しで区切った「表の区間」を作る（ページまたぎの折り返しに対応）
        segs: list[dict] = []
        for pno in range(pmap[pstart], pmap[pnext]):
            for ln in pdftext(pdf, pno).splitlines():
                if not ln.strip():
                    continue
                f = flat(ln)
                if f.startswith("【歳入】"):
                    mode = "revenue"
                    continue
                if f.startswith("【歳出】"):
                    mode = "expense"
                    continue
                if mode == "revenue":
                    continue
                mk = re.match(r"^(\d+)款(.+?)(（Ｐ.*）)?$", f)
                if mode in ("expense", "explain") and mk:
                    mode = "expense"
                    cur_kan = {"no": int(mk.group(1)), "name": mk.group(2), "項集計": [], "項集計の計": None, "項": []}
                    dept["款"].append(cur_kan)
                    segs.append({"kind": "kan", "kan": cur_kan, "lines": [], "pages": []})
                    continue
                mq = re.match(r"^([０-９0-9]+)項(.+)$", f)
                if mode in ("expense", "explain") and mq and cur_kan is not None:
                    mode = "expense"
                    kou = {"no": int(mq.group(1).translate(Z2H)), "name": mq.group(2), "目": [], "計": None}
                    cur_kan["項"].append(kou)
                    segs.append({"kind": "kou", "kan": cur_kan, "kou": kou, "lines": [], "pages": [],
                                 "explain": ExplainReader()})
                    continue
                if f.startswith("説明"):
                    mode = "explain"
                    continue
                if mode == "explain" and segs and segs[-1]["kind"] == "kou":
                    # 項の目の表の下の「（1）決算の内容」「（2）不用額の内容」（目ごとの主な内容の文）
                    segs[-1]["explain"].feed(ln, is_header)
                    continue
                if mode == "expense" and segs and not is_header(ln):
                    segs[-1]["lines"].append(ln)
                    segs[-1]["pages"].append(pno)
        for seg in segs:
            body, pages = seg["lines"], seg["pages"]
            if seg["kind"] == "kan":
                kan = seg["kan"]
                for kind, r in assemble_rows(body, 1, skipped=skipped, label=f"{bname} {kan['no']}款"):
                    if kind == "row":
                        if r.no is None and r.name == "計":
                            kan["項集計の計"] = r.nums[0]
                        elif r.no is not None:
                            kan["項集計"].append({"no": r.no, "name": r.name, "決算額": r.nums[0]})
                continue
            kou = seg["kou"]
            if seg["kan"]["no"] == 14:
                # 予備費だけ列が違う: 当初予算額 / 補正予算額 / 予備費支出及び流用増減額 / 計 / 支出済額 / 不用額
                rows = assemble_rows(body, 6, skipped=skipped, label=f"{bname} 予備費")
                conv = lambda n: {"予算現額": n[3], "支出済額": n[4], "翌年度繰越額": 0, "不用額": n[5],  # noqa: E731
                                  "当初予算額": n[0], "補正予算額": n[1], "予備費支出及び流用増減額": n[2]}
            else:
                rows = assemble_rows(body, 4, skipped=skipped, label=f"{bname} {seg['kan']['no']}款{kou['no']}項",
                                     strip_notes=True)
                conv = lambda n: dict(zip(COLS, n))  # noqa: E731
            for kind, r in rows:
                if kind != "row":
                    continue
                if r.no is None and r.name == "計":
                    kou["計"] = conv(r.nums)
                elif r.no is not None:
                    kou["目"].append({"no": r.no, "name": r.name, "pdf_page": pages[r.line_index], **conv(r.nums), **r.extra})
                else:
                    skipped.append(f"{bname} p{pages[r.line_index]}: 番号のない行 {r.name} {r.nums}")
            attach_explain(kou["目"], seg["explain"].result())
        result.append(dept)
    return result, skipped


def verify(depts, kmk, skipped) -> int:
    fails = 0

    def fail(msg):
        nonlocal fails
        fails += 1
        print("FAIL " + msg, file=sys.stderr)

    agg: dict[tuple, dict] = defaultdict(lambda: {c: 0 for c in COLS})
    names: dict[tuple, set] = defaultdict(set)
    total_spent = 0
    for d in depts:
        for kan in d["款"]:
            s = sum(x["決算額"] for x in kan["項集計"])
            if kan["項集計の計"] is not None and s != kan["項集計の計"]:
                fail(f"{d['部局']} {kan['no']}款: 項集計の合計 {s:,} ≠ 計 {kan['項集計の計']:,}")
            summ = {x["no"]: x["決算額"] for x in kan["項集計"]}
            if len(kan["項集計"]) == 1 and kan["項集計の計"] is None:
                pass
            for kou in kan["項"]:
                ms = {c: sum(m[c] for m in kou["目"]) for c in COLS}
                if kou["計"] is not None:
                    for c in COLS:
                        if ms[c] != kou["計"][c]:
                            fail(f"{d['部局']} {kan['no']}款{kou['no']}項 {c}: 目の合計 {ms[c]:,} ≠ 計 {kou['計'][c]:,}")
                elif len(kou["目"]) != 1:
                    fail(f"{d['部局']} {kan['no']}款{kou['no']}項: 計の行がない（目 {len(kou['目'])} 件）")
                if not summ:
                    # 予備費は項の集計表がない（R6 で確認）。他の款で起きたら要確認
                    level = "WARN" if kan["no"] == 14 else "FAIL"
                    if level == "FAIL":
                        fail(f"{d['部局']} {kan['no']}款: 項の集計表がない")
                    else:
                        print(f"WARN {d['部局']} {kan['no']}款: 項の集計表がない（予備費）", file=sys.stderr)
                elif kou["no"] not in summ:
                    fail(f"{d['部局']} {kan['no']}款{kou['no']}項: 項の集計表にない")
                elif summ[kou["no"]] != ms["支出済額"]:
                    fail(f"{d['部局']} {kan['no']}款{kou['no']}項: 集計表 {summ[kou['no']]:,} ≠ 目の支出済額合計 {ms['支出済額']:,}")
                for m in kou["目"]:
                    key = (kan["no"], kou["no"], m["no"])
                    for c in COLS:
                        agg[key][c] += m[c]
                    names[key].add(m["name"])
                    total_spent += m["支出済額"]
            missing = set(summ) - {k["no"] for k in kan["項"]}
            if missing:
                fail(f"{d['部局']} {kan['no']}款: 集計表にあるが目の表がない項 {sorted(missing)}")
    # 款項目別明細表との突合
    ref = {}
    for kan in kmk["expense"]:
        for kou in kan["children"]:
            for m in kou["children"]:
                ref[(kan["no"], kou["no"], m["no"])] = m
    for key, m in ref.items():
        if key not in agg:
            if any(m[c] for c in COLS):
                fail(f"突合 {key} {m['name']}: 部局別に現れない（支出済額 {m['支出済額']:,}）")
            continue
        for c in COLS:
            if agg[key][c] != m[c]:
                fail(f"突合 {key} {m['name']} {c}: 部局別の合計 {agg[key][c]:,} ≠ 明細表 {m[c]:,}")
        if names[key] != {m["name"]}:
            print(f"WARN 名称 {key}: 部局別 {sorted(names[key])} / 明細表 {m['name']}", file=sys.stderr)
    for key in set(agg) - set(ref):
        fail(f"突合 {key} {sorted(names[key])}: 明細表にない目")
    if total_spent != kmk["totals"]["expense"][1]:
        fail(f"全部局の支出済額 {total_spent:,} ≠ 一般会計 {kmk['totals']['expense'][1]:,}")
    for s in skipped:
        print(f"WARN 読み飛ばした行: {s}", file=sys.stderr)
    print(f"部局 {len(depts)}、部局×目 {sum(len(k['目']) for d in depts for a in d['款'] for k in a['項'])} 行、"
          f"支出済額合計 {total_spent:,}", file=sys.stderr)
    print(f"FAIL={fails}", file=sys.stderr)
    return fails


if __name__ == "__main__":
    depts, sk = parse(sys.argv[1])
    kmk = json.load(open(sys.argv[2], encoding="utf-8"))
    f = verify(depts, kmk, sk)
    json.dump({"source": os.path.basename(sys.argv[1]), "unit": "円", "部局": depts}, sys.stdout, ensure_ascii=False, indent=1)
    sys.exit(1 if f else 0)
