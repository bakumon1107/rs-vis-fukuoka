"""施策別資料の事項（extract_shisaku.py の shisaku.json）を、当初予算のファイル（budget-<年度>-initial.json）の policies に組み立てる。

設計: docs/local-gov/tasks/20261120_1500_地方版バブル図の設計.md（3章 範囲・4章 データ）。型: types/local-gov.ts の LocalPolicies
export_fukuoka_pref.py の main から呼ぶ（予算の行が決まった後）。

- 範囲: 一般会計の事項だけ。特別会計・公営企業会計の事項（科目が「特別会計」「企業会計」）と債務負担行為（事項名に「債務負担行為」。
  予算額の欄は後年度にわたる限度額で、その年度の歳出ではない）は除き、件数と額を excluded に書く
- 科目: 予算の目（一般会計の歳出）に結ぶ。項が決まらない科目（「9 ? 1」）は、予算にある目がちょうど1つならそれに決める。
  予算にない科目は unmatched の印（資料の印字のまま。R8「認知症医療センター事業費」3-2-5）
- 図に載らない経費（outside）: 一般会計の歳出から、施策別資料の事項の合計と、4つの決まった出費（諸支出金・人件費・公債費・制度融資）を
  引いた残りを「その他」にする。その他が負なら止める（重なりの数え方が合っていない）
- 金額は千円 × 1000 の円
"""
import json
import os
import re


def _kamoku(text: str, budget_ids: set[str]):
    """「款 項 目」→ 科目の dict。項が「?」なら予算にある目がちょうど1つのときだけ決める"""
    m = re.fullmatch(r"(\d+) (\d+|\?) (\d+)", text)
    if not m:
        return None
    kan, kou, moku = m.group(1), m.group(2), m.group(3)
    if kou == "?":
        cands = [i for i in budget_ids if re.fullmatch(rf"general/expense/{kan}-\d+-{moku}", i)]
        if len(cands) == 1:
            kou = cands[0].split("/")[-1].split("-")[1]
        else:
            return {"kan": int(kan), "kou": None, "moku": int(moku), "row": None, "kou_unresolved": True}
    row = f"general/expense/{kan}-{kou}-{moku}"
    out = {"kan": int(kan), "kou": int(kou), "moku": int(moku), "row": row if row in budget_ids else None}
    if out["row"] is None:
        out["unmatched"] = True
    return out


def build(work: str, rows: list[dict]) -> tuple[dict | None, list[str], list[str]]:
    """shisaku.json があれば policies を返す（なければ None）。返り値: (policies, 要約の行, 失敗)"""
    path = os.path.join(work, "shisaku.json")
    if not os.path.exists(path):
        return None, ["施策別資料: shisaku.json がない"], []
    items = json.load(open(path, encoding="utf-8"))["items"]
    expense = [r for r in rows if r["account"] == "general" and r["side"] == "expense"]
    budget_ids = {r["id"] for r in expense}
    fails: list[str] = []
    out_items, excluded = [], {"special": [0, 0], "debt_burden": [0, 0]}
    for it in items:
        amount = (it["予算額"] or 0) * 1000
        if "債務負担行為" in it["事項名"]:
            excluded["debt_burden"][0] += 1
            excluded["debt_burden"][1] += amount
            continue
        if any(("特別会計" in k or "企業会計" in k) for k in it["科目"]):
            excluded["special"][0] += 1
            excluded["special"][1] += amount
            continue
        if it["予算額"] is None:
            fails.append(f"施策別資料 {it['事項名']}: 予算額が読めない")
            continue
        kamoku = [k for k in (_kamoku(t, budget_ids) for t in it["科目"]) if k]
        pillar = None
        if it["柱"]:
            mm = re.match(r"^([１-９\d])．(.+)$", it["柱"])
            pillar = int(mm.group(1).translate(str.maketrans("１２３４５６７８９", "123456789"))) if mm else None
        out_items.append({
            "name": it["事項名"], "pillar": pillar, "initiative": it["区分"] or None, "division": it["課名"],
            "kamoku": kamoku, **({"other_kamoku": True} if "外" in it["科目"] else {}),
            "amount": amount, "previous": None if it["前年度"] is None else it["前年度"] * 1000, "is_new": it["新規"],
            "notes": [e["text"] for e in it["説明"] if e.get("text")],
            "source": {"doc": it["source"], "page": it["pdf_page"]},
        })
    pillars = {}
    for it in items:
        mm = re.match(r"^([１-９\d])．(.+)$", it["柱"] or "")
        if mm:
            pillars[int(mm.group(1).translate(str.maketrans("１２３４５６７８９", "123456789")))] = mm.group(2)

    # 図に載らない経費（設計 3章の表）。一般会計の歳出の目・節・事項から数える
    total = sum(r["amount"]["v"] or 0 for r in expense)
    in_policies = sum(i["amount"] for i in out_items)
    kan_sum = lambda name: sum(r["amount"]["v"] or 0 for r in expense if r["kan"]["name"] == name)  # noqa: E731
    personnel = sum(s["amount"]["v"] or 0 for r in expense for s in r.get("setsu", []) if s.get("no") in (1, 2, 3, 4))
    loans = sum(i["amount"]["v"] or 0 for r in expense for i in r.get("items", []) if i["name"] == "中小企業振興資金融資費")
    outside = [
        {"key": "tax_transfers", "label": "地方消費税の清算金・市町村への税交付金（款「諸支出金」）", "amount": kan_sum("諸支出金")},
        {"key": "personnel", "label": "人件費（節 報酬・給料・職員手当等・共済費）", "amount": personnel},
        {"key": "debt_service", "label": "公債費（款「公債費」。借金の返済と利子）", "amount": kan_sum("公債費")},
        {"key": "loans", "label": "中小企業の制度融資の貸付金（中小企業振興資金融資費）", "amount": loans},
    ]
    other = total - in_policies - sum(o["amount"] for o in outside)
    if other < 0:
        fails.append(f"施策別資料: 図に載らない経費の「その他」が負（{other:,} 円。重なりの数え方が合っていない）")
    outside.append({"key": "other", "label": "その他（事務費・施設の管理・施策別資料に載らない事業。人件費と施策の事項の重なりを含む）",
                    "amount": other})
    policies = {
        "pillars": [{"no": n, "name": pillars[n]} for n in sorted(pillars)],
        "items": out_items,
        "excluded": {k: {"count": v[0], "amount": v[1]} for k, v in excluded.items()},
        "outside": outside,
        "expense_total": total,
        "source_docs": sorted({i["source"]["doc"] for i in out_items}),
    }
    n_unmatched = sum(1 for i in out_items for k in i["kamoku"] if k.get("unmatched"))
    n_unresolved = sum(1 for i in out_items for k in i["kamoku"] if k.get("kou_unresolved"))
    lines = [f"施策別資料 事項 {len(out_items)} 件（{in_policies:,} 円）。除いた: 特別会計 {excluded['special'][0]}・"
             f"債務負担行為 {excluded['debt_burden'][0]}。科目: 予算にない {n_unmatched}・項が決まらない {n_unresolved}。"
             f"図に載らない経費のその他 {other:,} 円"]
    return policies, lines, fails
