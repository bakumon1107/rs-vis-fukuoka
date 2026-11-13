"""福岡県の決算（R6）の抽出結果を、地方版の共通 JSON 形式（settlement-<年度>.json）に組み立てる。

設計: docs/local-gov/tasks/20261114_0043_R6決算の書き出しと見方の設計.md（3章 正規化データ・8章 特別会計）
型: types/local-gov.ts（LocalBudgetFile・MokuRow の by_department・explanation、revenue_by_kan）
export_fukuoka_pref.py の main から呼ぶ（index.json を1か所で書くため）。

入力（回帰テストの作業ディレクトリ）:
    kessan-kmk.json     … 一般会計の款項目別明細表（extract_kessan_kmk.py）
    kessan-bukyoku.json … 一般会計の部局別の目と「決算の内容」「不用額の内容」（extract_kessan_bukyoku.py）
    kessan-toku.json    … 特別会計の歳入の款・歳出の款項目と説明（extract_kessan_toku.py）
    kessan-setsu.json   … 一般会計・特別会計の目ごとの節（extract_kessan_setsu.py --toku）

行は歳出の目だけ（歳入は図に描かないので、会計 × 款の表 revenue_by_kan にする）。金額は円（資料が円単位）。
名前・金額の出典は text（テキスト PDF）。節の名前は節番号で決まる施行規則の節名（reference）。細節は入れない（名前の 1/4 が文字コードなし）。
"""
import json
import os
import re
from collections import defaultdict

YEAR, YEAR_LABEL = 2024, "令和6年度"
SRC_GAIYOU, SRC_JIKOU = "r6-kessan-gaiyou", "r6-kessan-jikou"
COLS = {"amount": "支出済額", "budget_current": "予算現額", "carried_over": "翌年度繰越額", "unused": "不用額"}

# 節の名前（地方自治法施行規則の歳出の節。番号で決まる）
SETSU_NAMES = {1: "報酬", 2: "給料", 3: "職員手当等", 4: "共済費", 5: "災害補償費", 6: "恩給及び退職年金", 7: "報償費", 8: "旅費",
               9: "交際費", 10: "需用費", 11: "役務費", 12: "委託料", 13: "使用料及び賃借料", 14: "工事請負費", 15: "原材料費",
               16: "公有財産購入費", 17: "備品購入費", 18: "負担金、補助及び交付金", 19: "扶助費", 20: "貸付金",
               21: "補償、補塡及び賠償金", 22: "償還金、利子及び割引料", 23: "投資及び出資金", 24: "積立金", 25: "寄附金",
               26: "公課費", 27: "繰出金"}


def val(v):
    return {"v": int(v), "src": "text"}


def named(no, name):
    return {"no": int(no), "name": name, "name_src": "text"}


def special_name(full: str) -> str:
    """「福岡県国民健康保険特別会計」→「国民健康保険」（予算の書き出しの SPECIAL_SLUGS の鍵）。"""
    return re.sub(r"特別会計$", "", re.sub(r"^福岡県", "", full))


def explanation(d: dict) -> dict | None:
    e = {k: d[s] for k, s in (("content", "決算の内容"), ("unused", "不用額の内容")) if d.get(s)}
    return e or None


def build(work: str, special_slugs: dict[str, str]):
    """決算のファイル（dict）と、検算が全部通ったか、要約の行を返す。"""
    load = lambda name: json.load(open(os.path.join(work, name), encoding="utf-8"))  # noqa: E731
    kmk, bukyoku, toku, setsu = (load(x) for x in ("kessan-kmk.json", "kessan-bukyoku.json", "kessan-toku.json", "kessan-setsu.json"))

    # 節: (会計の名前, 款, 項, 目) → 節の行と事項別明細書のページ
    setsu_of: dict[tuple, dict] = {}
    for m in setsu["目"]:
        key = (special_name(m["会計"]) if "会計" in m else "一般会計", m["款"], m["項"], m["目"])
        setsu_of[key] = m

    def setsu_rows(key):
        m = setsu_of.get(key)
        if not m:
            return [], []
        out = [{"no": s["no"], "name": SETSU_NAMES.get(s["no"], ""), "name_src": "reference", "amount": val(s["支出済額"])}
               for s in m["節"]]
        return out, [{"source": SRC_JIKOU, "page": m["pdf_page"]}]

    # 部局: (款, 項, 目) → 部局ごとの4列と説明
    dept_of: dict[tuple, list] = defaultdict(list)
    for d in bukyoku["部局"]:
        for kan in d["款"]:
            for kou in kan["項"]:
                for mo in kou["目"]:
                    e = {"name": d["部局"], **{k: val(mo[s]) for k, s in COLS.items()}}
                    ex = explanation(mo)
                    if ex:
                        e["explanation"] = ex
                    dept_of[(kan["no"], kou["no"], mo["no"])].append(e)

    accounts = [{"id": "general", "kind": "general", "name": "一般会計"}]
    rows, revenue = [], []
    for kan in kmk["expense"]:
        for kou in kan["children"]:
            for mo in kou["children"]:
                key = (kan["no"], kou["no"], mo["no"])
                ss, spages = setsu_rows(("一般会計", *key))
                row = {"id": "general/expense/{}-{}-{}".format(*key), "account": "general", "side": "expense",
                       "kan": named(kan["no"], kan["name"]), "kou": named(kou["no"], kou["name"]), "moku": named(mo["no"], mo["name"]),
                       **{k: val(mo[s]) for k, s in COLS.items()},
                       "pages": [{"source": SRC_GAIYOU, "page": mo["pdf_page"]}] + spages}
                if dept_of.get(key):
                    row["by_department"] = dept_of[key]
                if ss:
                    row["setsu"] = ss
                rows.append(row)
    for kan in kmk["revenue"]:
        revenue.append(revenue_row("general", kan["no"], kan["name"], kan, kan.get("過誤納金（内数）")))

    for acc in toku["会計"]:
        name = special_name(acc["会計"])
        if name not in special_slugs:
            raise SystemExit(f"特別会計の名前が予算の会計の一覧にない: {acc['会計']}")
        aid = f"special:{special_slugs[name]}"
        accounts.append({"id": aid, "kind": "special", "name": f"{name}特別会計"})
        kan_names = {x["款"]: x["款名"] for x in acc["款項"]}
        for kou in acc["項"]:
            for mo in kou["目"]:
                key = (kou["款"], kou["項"], mo["no"])
                ss, spages = setsu_rows((name, *key))
                row = {"id": f"{aid}/expense/" + "{}-{}-{}".format(*key), "account": aid, "side": "expense",
                       "kan": named(kou["款"], kan_names[kou["款"]]), "kou": named(kou["項"], kou["項名"]),
                       "moku": named(mo["no"], mo["name"]), **{k: val(mo[s]) for k, s in COLS.items()},
                       "pages": [{"source": SRC_GAIYOU, "page": acc["pdf_page"]}] + spages}
                ex = explanation(mo)
                if ex:
                    row["explanation"] = ex
                if ss:
                    row["setsu"] = ss
                rows.append(row)
        for r in acc["歳入"]:
            revenue.append(revenue_row(aid, r["no"], r["name"], r, r.get("過誤納金")))

    checks, ok, lines = check(rows, revenue, kmk, toku)
    file = {"schema_version": 1, "gov_id": "fukuoka-pref", "year": YEAR, "year_label": YEAR_LABEL, "basis": "settlement",
            "unit_source": "円", "accounts": accounts, "rows": rows, "revenue_by_kan": revenue, "checks": checks}
    return file, ok, lines


def revenue_row(account, no, name, d, overpaid):
    r = {"account": account, "kan": named(no, name), "amount": val(d["収入済額"]), "budget_current": val(d["予算現額"]),
         "assessed": val(d["調定額"]), "deficit_loss": val(d["不納欠損額"]), "uncollected": val(d["収入未済額"])}
    if overpaid:
        r["overpaid"] = val(overpaid)
    return r


def check(rows, revenue, kmk, toku):
    """目ごとの検算（予算現額の式・節の合計・部局の内訳の合計）と、会計ごとの合計の突き合わせ。"""
    rules = {"予算現額の式": 0, "節の合計": 0, "部局の内訳": 0}
    all_ok, ng = 0, []
    for r in rows:
        v = lambda k: r[k]["v"]  # noqa: E731
        ok1 = v("amount") + v("carried_over") + v("unused") == v("budget_current")
        ok2 = "setsu" not in r or sum(s["amount"]["v"] for s in r["setsu"]) == v("amount")
        ok3 = "by_department" not in r or all(sum(d[k]["v"] for d in r["by_department"]) == v(k) for k in COLS)
        rules["予算現額の式"] += ok1
        rules["節の合計"] += ok2
        rules["部局の内訳"] += ok3
        if ok1 and ok2 and ok3:
            all_ok += 1
        else:
            ng.append(r["id"])
    lines = [f"NG 決算の目 {x}" for x in ng]
    ext = {}
    spent_general = sum(r["amount"]["v"] for r in rows if r["account"] == "general")
    want = kmk["totals"]["expense"][1]
    ext["一般会計の歳出_明細表"] = f"支出済額の合計 {spent_general:,} / 明細表 {want:,}（{'一致' if spent_general == want else '不一致'}）"
    n_acc = n_ok = 0
    for acc in toku["会計"]:
        n_acc += 1
        got = sum(x["決算額"] for x in acc["款項"])
        n_ok += got == (acc["款項の計"] if acc["款項の計"] is not None else got)
    ext["特別会計の歳出_款項の表"] = f"{n_ok}/{n_acc} 会計で一致"
    no_setsu = sum(1 for r in rows if "setsu" not in r and r["budget_current"]["v"])
    ext["節_事項別明細書"] = f"予算現額のある目 {sum(1 for r in rows if r['budget_current']['v'])} のうち節あり " \
                       f"{sum(1 for r in rows if 'setsu' in r)}（節なし {no_setsu}）"
    ok = not ng and spent_general == want and n_ok == n_acc and no_setsu == 0
    rev_ok = sum(1 for x in revenue if x["amount"]["v"] - (x.get("overpaid") or {"v": 0})["v"] + x["deficit_loss"]["v"]
                 + x["uncollected"]["v"] == x["assessed"]["v"])
    ext["歳入の調定額の式"] = f"{rev_ok}/{len(revenue)} 款"
    ok = ok and rev_ok == len(revenue)
    checks = {"rows": len(rows), "all_ok": all_ok, "rules": rules, "external": ext}
    lines.append(f"決算 目 {len(rows)} 件（全検算一致 {all_ok}）。歳入の款 {len(revenue)} 件。" + "・".join(f"{k}: {v}" for k, v in ext.items()))
    return checks, ok, lines
