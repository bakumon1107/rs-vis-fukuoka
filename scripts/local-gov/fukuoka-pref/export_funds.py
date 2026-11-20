"""基金の現在高（extract_funds.py の funds.json）を、決算のファイル（settlement-<年度>.json）の funds に組み立てる。

設計: docs/local-gov/tasks/20261120_1200_地方版の基金の設計.md（3章 データ）。型: types/local-gov.ts の LocalFunds
export_settlement.build から呼ぶ。

- items: 決算年度（R6）の基金ごとの区分（現金・有価証券・一般会計貸付金…）と、年度末現在高・出納閉鎖日現在高（円）
- 推移（history）: 年度末現在高。調書のある年度はその年度の「決算年度末現在高」、調書を取り込んでいない年度は
  次の年度の調書の「前年度末現在高」（同じ値。extract_funds.check_chain で続く年度は一致を確かめた）
- totals: 年度ごとの全基金の年度末現在高の合計（廃止した基金を含む）を、財政調整基金・減債基金・その他に分けて
- 金額は千円 × 1000 の円。出典は調書のある年度がテキストなら text、OCR なら ocr
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_funds import RENAMES, YEAR_ORDER  # noqa: E402

KIND = {"積立": "stock", "運用": "operating"}
MAIN = {"福岡県財政調整基金": "fiscal_adjustment", "福岡県減債基金": "debt_reduction"}


def short(name: str) -> str:
    return name.removeprefix("福岡県")


def year_label(fy: int) -> str:
    return f"令和{fy - 2018}年度" if fy >= 2019 else f"平成{fy - 1988}年度"


def build(work: str, fiscal_year: int, source_ids: dict[str, str]) -> tuple[dict | None, list[str]]:
    """funds.json があれば決算のファイルの funds を返す（なければ None）。source_ids: 年度（"R6" など）→ sources.json の id"""
    path = os.path.join(work, "funds.json")
    if not os.path.exists(path):
        return None, ["基金: funds.json がない（基金の抽出のステップを飛ばした）"]
    data = json.load(open(path, encoding="utf-8"))
    years, ocr = data["years"], set(data.get("ocr_years", []))
    fy_of = {y: YEAR_ORDER[y] for y in years}
    latest = max(years, key=fy_of.get)
    if fy_of[latest] != fiscal_year:
        raise SystemExit(f"基金: いちばん新しい調書（{latest}）が決算の年度（{fiscal_year}）でない")
    rename = lambda n: RENAMES.get(n, n)  # noqa: E731

    # 年度末現在高: (今の名前, 年度) → (千円, 出典)
    ends: dict[tuple[str, int], tuple[int, str]] = {}
    for y, funds in years.items():
        src = "ocr" if y in ocr else "text"
        for name, fd in funds.items():
            n = rename(name)
            ends[(n, fy_of[y])] = (sum(v[2] for v in fd["holdings"].values()), src)
            prev = (n, fy_of[y] - 1)
            if prev not in ends:
                ends[prev] = (sum(v[0] for v in fd["holdings"].values()), src)
    # 調書のある年度の値を優先する（前年度末から入れた値を上書き）
    for y, funds in years.items():
        src = "ocr" if y in ocr else "text"
        for name, fd in funds.items():
            ends[(rename(name), fy_of[y])] = (sum(v[2] for v in fd["holdings"].values()), src)
    all_years = sorted({fy for _, fy in ends})

    items = []
    for name, fd in sorted(years[latest].items(), key=lambda kv: (kv[1]["kind"] != "積立", kv[1]["no"])):
        holdings = [{"kind": k, "start": v[0] * 1000, "change": v[1] * 1000, "end": v[2] * 1000,
                     "closing_change": v[3] * 1000, "after_closing": v[4] * 1000} for k, v in fd["holdings"].items()]
        history = [{"year": fy, "end": ends[(name, fy)][0] * 1000, "src": ends[(name, fy)][1]}
                   for fy in all_years if (name, fy) in ends]
        item = {"name": short(name), "kind": KIND[fd["kind"]], "no": fd["no"], "holdings": holdings,
                "end": sum(h["end"] for h in holdings), "after_closing": sum(h["after_closing"] for h in holdings),
                "history": history}
        old = [short(o) for o, n in RENAMES.items() if n == name]
        if old:
            item["renamed_from"] = old
        if fd.get("no_figures"):
            item["no_figures"] = True
        items.append(item)

    totals = []
    for fy in all_years:
        row = {"year": fy, "fiscal_adjustment": 0, "debt_reduction": 0, "other": 0, "srcs": set()}
        for (n, y), (v, src) in ends.items():
            if y == fy:
                row[MAIN.get(n, "other")] += v * 1000
                row["srcs"].add(src)
        row["src"] = "ocr" if "ocr" in row["srcs"] else "text"
        del row["srcs"]
        totals.append(row)

    out = {
        "as_of": {"year": fiscal_year, "label": f"{year_label(fiscal_year)}末"},
        "items": items,
        "totals": totals,
        "statements": [{"year": fy_of[y], "label": year_label(fy_of[y]), "source": source_ids[y], "src": "ocr" if y in ocr else "text"}
                       for y in sorted(years, key=fy_of.get)],
        "notes": [
            "残高は財産に関する調書（決算）の年度末現在高（3月31日）。出納閉鎖日（5月31日）の現在高は、出納整理期間中の増減を足した額",
            "調書を取り込んでいない年度の年度末現在高は、次の年度の調書の前年度末現在高",
            "財政状況資料集・財務書類の附属明細書の基金の額は、定義が違い、財政調整基金・減債基金の額が調書と合わない",
        ],
        "checks": {"signs_fixed": sum(len(v) for v in data.get("signs_fixed", {}).values()),
                   "names_fixed": sum(len(v) for v in data.get("names_fixed", {}).values())},
    }
    lines = [f"基金 {len(items)} 件（{year_label(fiscal_year)}末 {sum(i['end'] for i in items):,} 円）。推移 {all_years[0]}〜{all_years[-1]} 年度"]
    return out, lines
