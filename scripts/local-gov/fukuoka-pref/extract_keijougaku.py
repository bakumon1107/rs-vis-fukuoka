"""福岡県「当初予算計上額調」（編成概要の一部、Excel から出力したテキスト PDF）を抽出・検証する。

予算に関する説明書（スキャン画像）を OCR したときの**検算の基準値**として使う。

入力（R8 の例。https://www.pref.fukuoka.lg.jp/uploaded/attachment/ 配下）:
    277210.pdf 一般会計歳入予算額調 / 277211.pdf 一般会計歳出予算額調 / 277212.pdf 特別会計予算額調 / 277209.pdf 総括
使い方:
    python3 -P scripts/local-gov/fukuoka-pref/extract_keijougaku.py <歳入.pdf> <歳出.pdf> <特別会計.pdf> <総括.pdf> > keijougaku.json

出力の単位は千円（原資料のまま）。検証（完全一致、FAIL で終了コード 1）:
- 歳入の款の合計 = 歳入合計、歳出の款の合計 = 歳出合計（当年度・前年度・比較の各列）
- 比較 = 当年度 − 前年度
- 歳入合計 = 歳出合計 = 総括の一般会計、特別会計の合計 = 総括の特別会計
"""
import json
import re
import subprocess
import sys

NUM = r"△?\s?[\d,]+"


def text(pdf: str) -> str:
    return subprocess.run(["pdftotext", "-enc", "UTF-8", "-layout", pdf, "-"], capture_output=True, text=True, check=True).stdout


def to_int(s: str) -> int:
    s = s.replace(" ", "").replace(",", "")
    return -int(s[1:]) if s.startswith("△") else int(s)


def parse_kan(pdf: str) -> tuple[list[dict], dict | None]:
    """「１． 県税 830,805,619 36.1 798,923,736 36.5 31,881,883 104.0」の形。名前が2行に折り返す科目がある。"""
    rows, total, pending = [], None, ""
    for ln in text(pdf).splitlines():
        f = re.sub(r"\s", "", ln)
        m = re.match(rf"^\s*(?:(\d+)．)?\s*(.*?)\s+({NUM})\s+([\d.]+)\s+({NUM})\s+([\d.]+)\s+({NUM})\s+([\d.－-]+)\s*$", ln)
        if m:
            own = re.sub(r"\s", "", m.group(2))
            name = pending + own
            pending = ""
            rec = {"款名": name, "当年度": to_int(m.group(3)), "前年度": to_int(m.group(5)), "比較": to_int(m.group(7))}
            if m.group(1):
                # 番号は全角（「６．」）。名前が空なら「上の行／番号と数値の行／下の行」の折り返し
                rows.append({"no": int(m.group(1)), **rec, **({"_tail": True} if not own else {})})
            elif name.startswith("合"):
                total = rec
            continue
        # 「交通安全対策 / ６． 870,606 … / 特別交付金」のように番号と数値が中段に来る折り返し
        m2 = re.match(rf"^\s*(\d+)．\s+({NUM})\s+([\d.]+)\s+({NUM})\s+([\d.]+)\s+({NUM})\s+([\d.－-]+)\s*$", ln)
        if m2:
            rows.append({"no": int(m2.group(1)), "款名": pending, "当年度": to_int(m2.group(2)), "前年度": to_int(m2.group(4)),
                         "比較": to_int(m2.group(6)), "_tail": True})
            pending = ""
            continue
        if f and not re.search(r"\d", f) and len(f) <= 12 and not re.fullmatch(r"[％%]+", f) \
                and not any(k in f for k in ("款名", "単位", "予算", "構成比", "比較", "当初")):
            if rows and rows[-1].get("_tail"):
                rows[-1]["款名"] += f
                del rows[-1]["_tail"]
            else:
                pending += f
    for r in rows:
        r.pop("_tail", None)
    return rows, total


def parse_tokubetsu(pdf: str) -> tuple[list[dict], dict | None]:
    rows, total = [], None
    for ln in text(pdf).splitlines():
        m = re.match(rf"^\s*(\S.*?)\s+({NUM})\s+({NUM})\s+({NUM})\s*$", ln)
        if not m:
            continue
        name = re.sub(r"\s", "", m.group(1))
        rec = {"会計名": name, "当年度": to_int(m.group(2)), "前年度": to_int(m.group(3)), "比較": to_int(m.group(4))}
        if name.startswith("合"):
            total = rec
        else:
            rows.append(rec)
    return rows, total


def parse_soukatsu(pdf: str) -> dict:
    out = {}
    for ln in text(pdf).splitlines():
        f = re.sub(r"\s", "", ln)
        for key in ("一般会計", "特別会計", "合計"):
            if f.startswith(key):
                nums = re.findall(rf"{NUM}", ln.split(key[-1], 1)[-1] if False else ln)
                vals = [to_int(x) for x in nums if len(x.replace(",", "").replace("△", "").strip()) >= 6]
                if len(vals) >= 2 and key not in out:
                    out[key] = {"当年度": vals[0], "前年度": vals[1]}
    return out


def main():
    rev_pdf, exp_pdf, tok_pdf, sou_pdf = sys.argv[1:5]
    fails = 0

    def fail(msg):
        nonlocal fails
        fails += 1
        print("FAIL " + msg, file=sys.stderr)

    rev, rev_t = parse_kan(rev_pdf)
    exp, exp_t = parse_kan(exp_pdf)
    tok, tok_t = parse_tokubetsu(tok_pdf)
    sou = parse_soukatsu(sou_pdf)
    for label, rows, tot in (("歳入", rev, rev_t), ("歳出", exp, exp_t), ("特別会計", tok, tok_t)):
        if tot is None:
            fail(f"{label}: 合計行がない")
            continue
        for c in ("当年度", "前年度", "比較"):
            s = sum(r[c] for r in rows)
            if s != tot[c]:
                fail(f"{label} {c}: 合計 {s:,} ≠ 合計行 {tot[c]:,}")
        for r in rows:
            if r["比較"] != r["当年度"] - r["前年度"]:
                fail(f"{label} {r}: 比較 ≠ 当年度 − 前年度")
        print(f"{label}: {len(rows)} 行 {[r.get('款名') or r.get('会計名') for r in rows]}", file=sys.stderr)
    if rev_t and exp_t and rev_t["当年度"] != exp_t["当年度"]:
        fail(f"歳入合計 {rev_t['当年度']:,} ≠ 歳出合計 {exp_t['当年度']:,}")
    if "一般会計" in sou and exp_t and sou["一般会計"]["当年度"] != exp_t["当年度"]:
        fail(f"総括の一般会計 {sou['一般会計']['当年度']:,} ≠ 歳出合計 {exp_t['当年度']:,}")
    if "特別会計" in sou and tok_t and sou["特別会計"]["当年度"] != tok_t["当年度"]:
        fail(f"総括の特別会計 {sou['特別会計']['当年度']:,} ≠ 特別会計合計 {tok_t['当年度']:,}")
    # 名称の検査（合計の検証では名前の誤りは分からない）: 決算の款項目別明細表の款名と照合できるなら照合する
    if len(sys.argv) > 5:
        kmk = json.load(open(sys.argv[5], encoding="utf-8"))
        for label, rows, side in (("歳入", rev, "revenue"), ("歳出", exp, "expense")):
            ref = {k["no"]: k["name"] for k in kmk[side]}
            for r in rows:
                if ref.get(r["no"]) != r["款名"]:
                    fail(f"名称 {label} {r['no']}: 「{r['款名']}」≠ 決算の款名「{ref.get(r['no'])}」")
    for r in rev + exp:
        if re.search(r"[％%0-9]", r["款名"]) or not r["款名"]:
            fail(f"名称: 不審な款名「{r['款名']}」")
    print(f"総括: {sou}", file=sys.stderr)
    print(f"FAIL={fails}", file=sys.stderr)
    json.dump({"unit": "千円", "一般会計歳入": {"款": rev, "合計": rev_t}, "一般会計歳出": {"款": exp, "合計": exp_t},
               "特別会計": {"会計": tok, "合計": tok_t}, "総括": sou}, sys.stdout, ensure_ascii=False, indent=1)
    sys.exit(1 if fails else 0)


main()
