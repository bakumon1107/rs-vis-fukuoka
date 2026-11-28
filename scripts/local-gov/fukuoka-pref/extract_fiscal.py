"""三基金（財源調整分）の推移と見込み、財政の指標を読む。設計: docs/local-gov/tasks/20261128_1646_基金と財政の指標のタブの設計.md

入力（どれも県・総務省の公開資料。原本はコミットしない）:
  --kikin <年度>=<PDF>    基金積立状況（県の「基金の積立状況」の各年度版。文字の PDF）。年度は "R7" など。複数
  --gaiyou <PDF>          当初予算の概要（p.1「財政改革プランの目標達成状況」の三基金の目標と見込み）
  --shihyo <年度>=<xlsx>  総務省「地方公共団体の主要財政指標一覧」の全都道府県の表。年度は "R6" など。複数
  --jokyo <年度>=<xlsx>   総務省「財政状況資料集」の福岡県の表（総括表の本年度・前年度の指標で、主要財政指標一覧を突き合わせる）。複数
出力: 標準出力に JSON（書き出し export_fukuoka_pref.py が fiscal-indicators.json にする）。要約は標準エラー。
確かめ（合わなければ FAIL を出して終了コード 1）:
  - 基金: 内訳（通常分・交付税精算分等・公債管理特別会計分）の計 = 基金の行（前年度末・年度末とも）／前年度の年度末 = 次の年度の前年度末
  - 見込み: 概要の p.1 から目標（下限・上限）と見込みが読める／見込みの年度 = 最後の実績の年度 + 1
  - 指標: 47都道府県がそろう／福岡県の値が財政状況資料集の総括表の値と一致
金額は資料の千円・億円を円に直す。
"""
import argparse
import json
import re
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET

GOV_NAME = "福岡県"
RESERVE_LABEL = "財政調整基金等三基金（財源調整分）"
RESERVE_PARTS = ["財政調整基金（通常分）", "減債基金（通常分）", "公共施設整備基金"]
MAIN_FUNDS = ("財政調整基金", "減債基金", "公共施設整備基金")
# 指標（主要財政指標一覧の列の名前）。good: 良い方の向き（順位を数える向き）。threshold: 早期健全化基準
INDICATORS = [
    {"key": "fiscal_capacity", "label": "財政力指数", "unit": "", "good": "high", "threshold": None},
    {"key": "current_balance", "label": "経常収支比率", "unit": "%", "good": "low", "threshold": None},
    {"key": "debt_service", "label": "実質公債費比率", "unit": "%", "good": "low", "threshold": 25.0},
    {"key": "future_burden", "label": "将来負担比率", "unit": "%", "good": "low", "threshold": 400.0},
]
ZEN = str.maketrans("０１２３４５６７８９", "0123456789")


def era_year(label: str) -> int:
    """「R7」「H29」「令和7年度」「平成29年度」「令和元年度」→ 西暦の年度"""
    s = label.translate(ZEN)
    m = re.match(r"^(?:R|令和)(\d+|元)", s)
    if m:
        return 2018 + (1 if m.group(1) == "元" else int(m.group(1)))
    m = re.match(r"^(?:H|平成)(\d+|元)", s)
    if m:
        return 1988 + (1 if m.group(1) == "元" else int(m.group(1)))
    raise ValueError(f"年度が読めない: {label}")


def short_era(fy: int) -> str:
    return f"R{fy - 2018}" if fy >= 2019 else f"H{fy - 1988}"


# ---------- 基金積立状況 ----------

NUM = re.compile(r"-?[\d,]+")


def _numbers(rest: str) -> list[int]:
    return [int(x.replace(",", "")) for x in NUM.findall(rest) if x.replace(",", "").lstrip("-")]


def parse_kikin(text: str) -> dict:
    """基金積立状況の文字（pdftotext -layout）から、三基金と内訳の行を読む。
    返り値: {"year": 年度（西暦）, "page": 表のページ, "rows": {名前: (前年度末, 年度末)}}。額は千円。
    名前は 財政調整基金・減債基金・公共施設整備基金 と、内訳は「<基金>/通常分」「<基金>/交付税精算分」「<基金>/公債管理特別会計分」。
    表は「２ 積立状況」の最初の「合計」の行まで（後ろの「活用状況」の表にも同じ名前の行がある）"""
    m = re.search(r"((?:令和|平成)[０-９\d元]+年度)基金の状況", text)
    if not m:
        raise ValueError("見出し「〇〇年度基金の状況」がない")
    year = era_year(m.group(1))
    rows: dict[str, tuple[int, int]] = {}
    page = None
    parent = None
    for pno, ptext in enumerate(text.split("\f"), start=1):
        done = False
        for line in ptext.splitlines():
            s = line.strip()
            if re.match(r"^合\s*計", s) and rows:
                done = True
                break
            name_m = re.match(r"^([^\d,\-（(]+?|（[^）]+）|\([^)]+\))\s+(-?[\d,]+(?:\s+-?[\d,]+)+)\s*$", s)
            if not name_m:
                continue
            name = re.sub(r"\s+", "", name_m.group(1)).strip("（）()")
            nums = _numbers(name_m.group(2))
            # 設置目的の表の行（名前と文）には数がない。積立状況の行は数が4つ以上（前年度末 … 年度末）
            if len(nums) < 4:
                continue
            if name in MAIN_FUNDS:
                parent = name
                rows[name] = (nums[0], nums[-1])
                page = page or pno
            elif parent and name in ("通常分", "交付税精算分", "交付税精算分等", "公債管理特別会計分", "一般会計分"):
                key = "交付税精算分" if name.startswith("交付税精算分") else name
                rows[f"{parent}/{key}"] = (nums[0], nums[-1])
            else:
                parent = None
        if done:
            break
    missing = [n for n in MAIN_FUNDS if n not in rows]
    if missing:
        raise ValueError(f"{short_era(year)}: 行がない: {missing}")
    return {"year": year, "page": page, "rows": rows}


def reserve_parts(parsed: dict) -> tuple[list[tuple[int, int]], list[str]]:
    """三基金（財源調整分）の3つの（前年度末, 年度末）と、確かめの失敗。
    内訳の段: 財政調整基金 = 通常分 + 交付税精算分等（R4〜）。
    減債基金 = 一般会計分 + 公債管理特別会計分、一般会計分 = 通常分 + 交付税精算分等（R3〜）。
    資料によって段の行がない（H29〜R2 は一般会計分だけ・R3 は一般会計分の行がない）。ある段はすべて足し上げを確かめ、
    通常分の行がなければ、ある行から引いて求める"""
    rows, fails = parsed["rows"], []
    era = short_era(parsed["year"])

    def check(fund, what, parts, whole):
        for i, when in ((0, "前年度末"), (1, "年度末")):
            s = sum(p[i] for p in parts)
            if s != whole[i]:
                fails.append(f"{era} {fund}: {what} {s:,} ≠ {whole[i]:,}（{when}・千円）")

    def sub(a, b):
        return tuple(a[i] - b[i] for i in (0, 1))

    zero = (0, 0)
    out = []
    for fund in ("財政調整基金", "減債基金"):
        total = rows[fund]
        s = {k.split("/")[1]: v for k, v in rows.items() if k.startswith(fund + "/")}
        kouhu, kousai = s.get("交付税精算分", zero), s.get("公債管理特別会計分", zero)
        # 一般会計分（公債管理特別会計分を除いた分）。行がなければ基金の行から求める
        general = s.get("一般会計分", sub(total, kousai))
        if "一般会計分" in s:
            check(fund, "一般会計分 + 公債管理特別会計分", [s["一般会計分"], kousai], total)
        if "通常分" in s:
            normal = s["通常分"]
            check(fund, "通常分 + 交付税精算分等 + 公債管理特別会計分", [normal, kouhu, kousai], total)
        else:
            normal = sub(general, kouhu)
        out.append(normal)
    out.append(rows["公共施設整備基金"])
    return out, fails


def reserve_history(kikin: list[tuple[str, str, str]]) -> tuple[list[dict], list[str], dict]:
    """kikin: [(年度, 文字, 資料の id)]。年度順の推移・確かめの失敗・数（要約用）"""
    hist, fails = [], []
    parsed = []
    for label, text, src in kikin:
        p = parse_kikin(text)
        if p["year"] != era_year(label):
            fails.append(f"{label}: 資料の見出しの年度（{short_era(p['year'])}）が引数と違う")
        parsed.append((p, src))
    parsed.sort(key=lambda x: x[0]["year"])
    prev_end = None
    links = 0
    for p, src in parsed:
        parts, f = reserve_parts(p)
        fails += f
        starts = [s for s, _ in parts]
        ends = [e for _, e in parts]
        if prev_end is not None:
            if prev_end[0] == p["year"] - 1:
                links += 1
                for name, a, b in zip(RESERVE_PARTS, prev_end[1], starts):
                    if a != b:
                        fails.append(f"{short_era(p['year'])} {name}: 前年度末 {b:,} ≠ 前の年度の年度末 {a:,}（千円）")
            else:
                fails.append(f"{short_era(p['year'])}: 前の年度（{short_era(p['year'] - 1)}）の資料がない")
        prev_end = (p["year"], ends)
        hist.append({"year": p["year"], "total": sum(ends) * 1000, "parts": [e * 1000 for e in ends], "source": src, "page": p["page"]})
    return hist, fails, {"links": links}


def parse_gaiyou(text_p1: str) -> dict:
    """当初予算の概要 p.1 の「財政調整基金等三基金残高（財源調整分）」の行: 目標の年度・下限・上限と見込み（億円）"""
    m = re.search(r"(令和[\d０-９]+)年度末の財政調整基金等三基金残高を\s*([\d,０-９]+)億円\s*[～〜~]\s*([\d,０-９]+)億円確保\s+([\d,０-９]+)億円", text_p1)
    if not m:
        raise ValueError("概要 p.1 に三基金の目標と見込みの行がない")
    num = lambda s: int(s.translate(ZEN).replace(",", "")) * 100_000_000  # noqa: E731
    return {"year": era_year(m.group(1)), "min": num(m.group(2)), "max": num(m.group(3)), "outlook": num(m.group(4))}


# ---------- xlsx（標準ライブラリで読む） ----------

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "rel": "http://schemas.openxmlformats.org/package/2006/relationships"}


def _col(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(path: str) -> dict[str, list[list]]:
    """シート名 → 行の一覧（行は列の位置に値。空は None）。数は float、文字は str"""
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            # 文字は si の直下の t と、書式の区切り r の下の t。ふりがな（rPh の下の t）は読まない
            # （読むと「都道府県名トドウフケンメイ」になる）
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
                ts = si.findall("m:t", NS) + si.findall("m:r/m:t", NS)
                shared.append("".join(t.text or "" for t in ts))
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")).findall("rel:Relationship", NS)}
        out = {}
        for sh in wb.find("m:sheets", NS).findall("m:sheet", NS):
            target = rels[sh.get(f"{{{NS['r']}}}id")].lstrip("/")
            target = target if target.startswith("xl/") else "xl/" + target
            rows = []
            for row in ET.fromstring(z.read(target)).iter(f"{{{NS['m']}}}row"):
                cells: list = []
                for c in row.findall("m:c", NS):
                    v = c.find("m:v", NS)
                    t = c.get("t")
                    if t == "inlineStr":
                        val = "".join(x.text or "" for x in c.iter(f"{{{NS['m']}}}t"))
                    elif v is None:
                        continue
                    elif t == "s":
                        val = shared[int(v.text)]
                    elif t in ("str", "e"):
                        val = v.text
                    elif t == "b":
                        val = v.text == "1"
                    else:
                        val = float(v.text)
                    i = _col(c.get("r"))
                    cells += [None] * (i + 1 - len(cells))
                    cells[i] = val
                rows.append(cells)
            out[sh.get("name")] = rows
    return out


def parse_shihyo(sheets: dict[str, list[list]]) -> dict[str, dict[str, float | None]]:
    """主要財政指標一覧の全都道府県の表: 都道府県名 → {指標の名前: 値（数でなければ None）}"""
    rows = next(iter(sheets.values()))
    # 見出しの行（「都道府県名」のある行。A 列から始まるとは限らない）
    hdr_i, name_j = next((i, r.index("都道府県名")) for i, r in enumerate(rows) if "都道府県名" in r)
    hdr = rows[hdr_i]
    cols = {INDICATORS_BY_LABEL[h]: j for j, h in enumerate(hdr) if h in INDICATORS_BY_LABEL}
    if len(cols) != len(INDICATORS):
        raise ValueError(f"見出しに指標の列がそろわない: {hdr}")
    out = {}
    for r in rows[hdr_i + 1:]:
        name = r[name_j] if name_j < len(r) else None
        if not isinstance(name, str) or not re.search(r"[都道府県]$", name.strip()):
            continue
        out[name.strip()] = {k: _cell(r[j] if j < len(r) else None) for k, j in cols.items()}
    return out


DASH = "dash"


def _cell(v):
    """指標のセル: 数はそのまま、「－」は DASH（比率が算定されない＝負担がない。例: 将来負担比率）、ほかは None"""
    if isinstance(v, float):
        return v
    if isinstance(v, str) and re.fullmatch(r"[-－‐ー―−—–]", v.strip()):
        return DASH
    return None


INDICATORS_BY_LABEL = {x["label"]: x["key"] for x in INDICATORS}


def parse_jokyo(sheets: dict[str, list[list]]) -> tuple[int, dict[str, tuple[float, float]]]:
    """財政状況資料集（都道府県別）の総括表: (本年度の年度, {指標: (本年度, 前年度)})"""
    rows = sheets["総括表"]
    year = None
    found: dict[str, tuple[float, float]] = {}
    for r in rows:
        cells = [c for c in r if c is not None]
        for i, c in enumerate(cells):
            if isinstance(c, str):
                if year is None:
                    m = re.match(r"^((?:令和|平成)[\d元]+年度)\(千円[･・]％\)$", c)
                    if m:
                        year = era_year(m.group(1))
                key = INDICATORS_BY_LABEL.get(c.strip("　 "))
                if key and key not in found and i + 2 < len(cells) and all(isinstance(x, float) for x in cells[i + 1:i + 3]):
                    found[key] = (cells[i + 1], cells[i + 2])
    if year is None or len(found) != len(INDICATORS):
        raise ValueError(f"総括表から年度・指標が読めない（年度 {year}・指標 {sorted(found)}）")
    return year, found


def median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def indicator_series(shihyo: list[tuple[str, dict, str]], jokyo: list[tuple[str, tuple[int, dict]]]) -> tuple[list[dict], list[str], dict]:
    """shihyo: [(年度, 全都道府県の表, 資料の id)]。jokyo: [(年度, 総括表)]。指標の系列・確かめの失敗・数"""
    fails = []
    by_year = {}
    for label, table, src in shihyo:
        fy = era_year(label)
        if len(table) != 47:
            fails.append(f"{label}: 都道府県が {len(table)} 件（47 件のはず）")
        if GOV_NAME not in table:
            fails.append(f"{label}: {GOV_NAME}の行がない")
            continue
        by_year[fy] = (table, src)
    checked = 0
    for label, (fy, vals) in jokyo:
        if fy != era_year(label):
            fails.append(f"{label}: 総括表の年度（{short_era(fy)}）が引数と違う")
        for key, (cur, prev) in vals.items():
            for y, v in ((fy, cur), (fy - 1, prev)):
                if y not in by_year:
                    continue
                got = by_year[y][0][GOV_NAME][key]
                checked += 1
                if not isinstance(got, float) or abs(got - v) > 1e-9:
                    fails.append(f"{short_era(y)} {key}: 主要財政指標一覧 {got} ≠ 財政状況資料集の総括表 {v}")
    series = []
    for ind in INDICATORS:
        values = []
        for fy in sorted(by_year):
            table, src = by_year[fy]
            v = table[GOV_NAME][ind["key"]]
            if not isinstance(v, float):
                fails.append(f"{short_era(fy)} {ind['label']}: {GOV_NAME}の値がない")
                continue
            cells = [t[ind["key"]] for t in table.values()]
            nums = [x for x in cells if isinstance(x, float)]
            dashes = sum(1 for x in cells if x == DASH)
            # 「－」は将来負担比率だけ意味が決まっている（算定されない＝将来負担がない。いちばん良い）。順位では福岡県より良い方に、
            # 中央値では 0 として数える。ほかの指標の「－」は意味が分からないので FAIL
            if dashes and ind["key"] != "future_burden":
                fails.append(f"{short_era(fy)} {ind['label']}: 「－」の団体が {dashes} 件（将来負担比率のほかは扱いを決めていない）")
            if ind["key"] == "future_burden":
                nums_for_median = nums + [0.0] * dashes
                better_dash = dashes
            else:
                nums_for_median, better_dash = nums, 0
            better = sum(1 for x in nums if (x > v if ind["good"] == "high" else x < v)) + better_dash
            unknown = sum(1 for x in cells if x is None)
            if unknown:
                fails.append(f"{short_era(fy)} {ind['label']}: 値の読めない団体が {unknown} 件")
            values.append({"year": fy, "value": v, "median": median(nums_for_median), "rank": better + 1,
                           "of": len(nums) + better_dash, "source": src})
        series.append({"key": ind["key"], "label": ind["label"], "unit": ind["unit"], "good": ind["good"],
                       "threshold": ind["threshold"], "values": values})
    return series, fails, {"checked": checked, "years": sorted(by_year)}


def pdftext(path: str, first: int | None = None, last: int | None = None) -> str:
    cmd = ["pdftotext", "-enc", "UTF-8", "-layout"]
    if first:
        cmd += ["-f", str(first), "-l", str(last or first)]
    return subprocess.run(cmd + [path, "-"], capture_output=True, text=True, check=True).stdout


def pairs(items: list[str]) -> list[tuple[str, str]]:
    out = []
    for it in items:
        k, _, v = it.partition("=")
        if not v:
            raise SystemExit(f"引数は 年度=パス の形: {it}")
        out.append((k, v))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kikin", action="append", default=[])
    ap.add_argument("--gaiyou", required=True)
    ap.add_argument("--gaiyou-source", default="r8-gaiyou")
    ap.add_argument("--shihyo", action="append", default=[])
    ap.add_argument("--jokyo", action="append", default=[])
    a = ap.parse_args()

    kikin = [(y, pdftext(p), f"{y.lower()}-kikin") for y, p in pairs(a.kikin)]
    hist, fails, kn = reserve_history(kikin)
    if not hist:
        fails.append("基金積立状況（--kikin）がない")
    if not a.shihyo:
        fails.append("主要財政指標一覧（--shihyo）がない")
    # 「財政改革プランの目標達成状況」は表紙の次（印刷のページ番号 1 = PDF の 2 ページ目）。最初の数ページから探す
    g = None
    for gpage in range(1, 6):
        try:
            g = parse_gaiyou(pdftext(a.gaiyou, gpage))
            break
        except ValueError:
            continue
    if g is None:
        raise SystemExit("当初予算の概要の最初の5ページに三基金の目標と見込みの行がない")
    last = hist[-1]["year"] if hist else None
    if last is not None and g["year"] != last + 1:
        fails.append(f"見込みの年度（{short_era(g['year'])}）が最後の実績の年度（{short_era(last)}）の次でない")
    shihyo = [(y, parse_shihyo(read_xlsx(p)), f"{y.lower()}-shihyo") for y, p in pairs(a.shihyo)]
    jokyo = [(y, parse_jokyo(read_xlsx(p))) for y, p in pairs(a.jokyo)]
    series, f2, sn = indicator_series(shihyo, jokyo)
    fails += f2

    out = {
        "reserve": {
            "label": RESERVE_LABEL, "parts": RESERVE_PARTS, "history": hist,
            "outlook": {"year": g["year"], "total": g["outlook"], "as_of": f"{short_era(g['year'])}当初予算の時点",
                        "source": a.gaiyou_source, "page": gpage},
            "target": {"year": g["year"], "min": g["min"], "max": g["max"], "plan": "福岡県財政改革プラン2022",
                       "source": a.gaiyou_source, "page": gpage},
        },
        "indicators": series,
        # 確かめの失敗（失敗しても JSON は書くので、書き出しはこれを見て止まる。extract_funds と同じ）
        "fails": fails,
    }
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)
    sys.stdout.write("\n")
    if hist:
        print(f"三基金（財源調整分） {len(hist)} 年分（{short_era(hist[0]['year'])}〜{short_era(last)}）・"
              f"{short_era(last)} 末 {hist[-1]['total']:,} 円・前年度末とのつながり {kn['links']}/{len(hist) - 1}", file=sys.stderr)
    print(f"見込み {short_era(g['year'])} 末 {g['outlook']:,} 円・目標 {g['min']:,}〜{g['max']:,} 円", file=sys.stderr)
    ys = sn["years"]
    if ys:
        print(f"財政の指標 {len(series)} 種 × {len(ys)} 年（{short_era(ys[0])}〜{short_era(ys[-1])}）・"
              f"財政状況資料集の総括表との突き合わせ {sn['checked']} 件", file=sys.stderr)
        for s in series:
            v = s["values"][-1]
            print(f"  {s['label']} {short_era(v['year'])} {v['value']}（中央値 {v['median']}・{v['of']} 団体中 {v['rank']} 位）", file=sys.stderr)
    for f in fails:
        print(f"FAIL {f}", file=sys.stderr)
    print(f"FAIL={len(fails)}", file=sys.stderr)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
