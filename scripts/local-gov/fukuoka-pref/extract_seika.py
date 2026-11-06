"""福岡県「主要施策の成果に関する説明書」（決算、テキスト PDF）から 部門 → 施策 → 事業（決算額・概要）を抽出・検証する。

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/extract_seika.py <主要施策の成果.pdf> > seika.json

構造（R6 決算で確認）:
    「第１ 総務部門」→「１ 行政改革の推進（決算額 119,327千円）」→ 表「事業名 / 決算額（千円）/ 事業の概要（〇…）」
    見出しの金額は数字の間に空白が入ることがある（「1 19,327」「4 ,245」）。施策の下に「(1)」「(2)」の小見出しと表が複数ある。
検証（stderr。終了コード 1 = FAIL あり）:
    施策の見出しの決算額 = その施策の事業の決算額の合計（見出しに決算額がある施策のみ）
"""
import json
import re
import subprocess
import sys

HEAD_RE = re.compile(r"^\s*(\d{1,2}|[０-９]{1,2})\s+(.+?)\s*[（(]決算額\s*([\d ,]+?)\s*千\s*円\s*[）)]")
BUMON_RE = re.compile(r"^\s*第\s*([０-９\d]+)\s+(.+部\s*門)\s*$")
ROW_RE = re.compile(r"^(?P<name>\s{2,}\S.*?)\s{2,}(?P<amt>\d{1,3}(?:,\d{3})*)\s{2,}(?P<rest>.*)$")
ROW_RE2 = re.compile(r"^(?P<name>\s{2,}\S.*?)\s{2,}(?P<amt>\d{1,3}(?:,\d{3})*)\s*$")
Z2H = str.maketrans("０１２３４５６７８９", "0123456789")


def main():
    pdf = sys.argv[1]
    txt = subprocess.run(["pdftotext", "-enc", "UTF-8", "-layout", pdf, "-"], capture_output=True, text=True, check=True).stdout
    lines = txt.splitlines()
    # 目次を飛ばす: 最初の「施策の成果」以降
    start = next(i for i, ln in enumerate(lines) if re.sub(r"\s", "", ln) == "施策の成果")
    bumon = None
    shisaku: list[dict] = []
    cur = None
    in_table = False
    pending_name = ""
    # 見出しの40行前から読む（部門名が見出しより前に出る）。先頭近くに見出しがあっても負の添字にしない
    for ln in lines[max(0, start - 40):]:
        f = re.sub(r"\s", "", ln)
        mb = BUMON_RE.match(ln)
        if mb:
            bumon = re.sub(r"\s", "", mb.group(2))
            continue
        mh = HEAD_RE.match(ln)
        if mh:
            cur = {"部門": bumon, "no": int(mh.group(1).translate(Z2H)), "施策": re.sub(r"\s", "", mh.group(2)),
                   "決算額": int(re.sub(r"[ ,]", "", mh.group(3))), "事業": []}
            shisaku.append(cur)
            in_table = False
            continue
        if f.startswith("事業名決算額"):
            in_table = True
            pending_name = ""
            continue
        if not in_table or cur is None:
            continue
        if f in ("千円",) or re.fullmatch(r"[―-]\d+[―-]", f):
            continue
        m = ROW_RE.match(ln) or ROW_RE2.match(ln)
        if m and len(m.group("name").strip()) <= 40:
            name = pending_name + re.sub(r"\s", "", m.group("name"))
            if name in ("計", "合計", "小計"):
                # 表の末尾の計の行（事業として数えると合計が見出しの2倍になる）
                cur.setdefault("表の計", []).append(int(m.group("amt").replace(",", "")))
                pending_name = ""
                continue
            cur["事業"].append({"事業名": name, "決算額": int(m.group("amt").replace(",", "")),
                               "概要": (m.group("rest") or "").strip() if "rest" in m.groupdict() else ""})
            pending_name = ""
            continue
        # 表の外に出た（次の小見出し「(2)」や本文）
        if re.match(r"^\s*[（(]\d+[)）]", ln) or re.match(r"^\s*\d+\s+\S", ln):
            in_table = False
            continue
        # 概要の続き、または事業名の折り返し
        if cur["事業"] and re.match(r"^\s{30,}", ln):
            cur["事業"][-1]["概要"] += " " + ln.strip()
        elif re.match(r"^\s{2,20}\S", ln) and len(f) <= 20:
            pending_name += f
    fails = checked = 0
    for s in shisaku:
        tot = sum(j["決算額"] for j in s["事業"])
        if s["事業"]:
            checked += 1
            if tot != s["決算額"]:
                fails += 1
                print(f"FAIL {s['部門']} {s['no']} {s['施策']}: 事業の合計 {tot:,} ≠ 見出し {s['決算額']:,}（事業 {len(s['事業'])} 件）",
                      file=sys.stderr)
        else:
            print(f"WARN {s['部門']} {s['no']} {s['施策']}: 事業の表が取れない", file=sys.stderr)
    n_j = sum(len(s["事業"]) for s in shisaku)
    print(f"施策 {len(shisaku)} 件（照合 {checked} 件）、事業 {n_j} 件、FAIL={fails}", file=sys.stderr)
    json.dump({"unit": "千円", "施策": shisaku}, sys.stdout, ensure_ascii=False, indent=1)
    sys.exit(1 if fails else 0)


main()
