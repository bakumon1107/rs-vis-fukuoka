"""施策別資料の事項（extract_shisaku.py の shisaku.json）を、当初予算のファイル（budget-<年度>-initial.json）の policies に組み立てる。

設計: docs/local-gov/tasks/20261120_1500_地方版バブル図の設計.md（3章 範囲・4章 データ）。型: types/local-gov.ts の LocalPolicies
export_fukuoka_pref.py の main から呼ぶ（予算の行が決まった後）。

- 範囲: 一般会計の事項だけ。特別会計・公営企業会計の事項（科目が「特別会計」「企業会計」）と債務負担行為（事項名に「債務負担行為」。
  予算額の欄は後年度にわたる限度額で、その年度の歳出ではない）は除き、件数と額を excluded に書く
- 科目: 予算の目（一般会計の歳出）に結ぶ。項が決まらない科目（「9 ? 4」）は、予算にある目がちょうど1つならそれに決める。
  目が2つあるもの（「9 ? 1」）は、根拠を確かめた表（KOU_FIXES）で決める
  予算にない科目は unmatched の印（資料の印字のまま。R8「認知症医療センター事業費」3-2-5）
- 図に載らない経費（outside）: 一般会計の歳出から、施策別資料の事項の合計と、4つの決まった出費（諸支出金・人件費・公債費・制度融資）を
  引いた残りを「その他」にする。その他が負なら止める（重なりの数え方が合っていない）
- 金額は千円 × 1000 の円
"""
import json
import os
import re

# 4つの柱の後の、番号のない見出し（extract_shisaku.OUTSIDE_PILLAR_HEAD と同じ。柱の外のグループ）
OUTSIDE_PILLAR_HEAD = "計画推進の基盤づくり"

# 項が字の位置で決まらず、予算にある目も2つある科目を、根拠を確かめて決める表。(事項名, 資料の科目) → 科目。
# 字の位置で決まらないのは、目が3行で項の「1」「2」が1・2行目と2・3行目のちょうど真ん中に印字された事項（真ん中の目が
# どちらの項にも同じ近さ）。同じ形の「災害対応力強化費」（9-?-4）は予算の目が 9-1-4 だけで、真ん中の目は上の項だった。
# 「同じ近さなら上の項」を決まりにはしない（確かめた例が2件だけ）
KOU_FIXES = {
    # 説明欄の「少年警察ボランティア協会補助金」9,104 千円は、9-1-1 公安委員会費（節は報酬・旅費・交際費・需用費・委託料だけ）に
    # 入らない。9-2-1 一般警察活動費には節「負担金、補助及び交付金」36,192 千円がある（R8 278133 p40。2026-11-20 確認）
    ("少年補導員等活動費", "9 ? 1"): "9 2 1",
}


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
    """policies を組み立てる。返り値: (policies, 要約の行, 失敗)。
    shisaku.json がなければ失敗にする（施策別資料の抽出のステップを飛ばした作業ディレクトリで書き出すと、公開データから
    policies が黙って消え、バブル図のページが出なくなるため。施策別資料のない年度を書き出すときは、そのときに外す道を作る）"""
    path = os.path.join(work, "shisaku.json")
    if not os.path.exists(path):
        return None, [], ["施策別資料: shisaku.json がない（施策別資料の抽出のステップを飛ばした作業ディレクトリ）"]
    items = json.load(open(path, encoding="utf-8"))["items"]
    expense = [r for r in rows if r["account"] == "general" and r["side"] == "expense"]
    budget_ids = {r["id"] for r in expense}
    fails: list[str] = []
    out_items, excluded = [], {"special": [0, 0], "debt_burden": [0, 0]}
    used_fixes: set[tuple[str, str]] = set()
    for it in items:
        # 予算額が読めない事項は、除く事項（債務負担行為・特別会計）でも止める（除いた額が黙って少なくならないよう）
        if it["予算額"] is None:
            fails.append(f"施策別資料 {it['事項名']}: 予算額が読めない")
            continue
        amount = it["予算額"] * 1000
        if "債務負担行為" in it["事項名"]:
            excluded["debt_burden"][0] += 1
            excluded["debt_burden"][1] += amount
            continue
        # 「外」（ほかの科目にもまたがる印）は会計を示さないので、特別会計かどうかの判定から外す
        special = [("特別会計" in k or "企業会計" in k) for k in it["科目"] if k != "外"]
        if special and all(special):
            excluded["special"][0] += 1
            excluded["special"][1] += amount
            continue
        if any(special):
            # 一般会計と特別会計にまたがる事項: 額が会計ごとに分かれていないので、除いても入れても一般会計の分がずれる。人が決める
            fails.append(f"施策別資料 {it['事項名']}: 一般会計と特別会計の科目にまたがる {it['科目']}（額を分けられない）")
            continue
        if not it["科目"] or it["科目"] == ["外"]:
            # 科目の欄が読めない（目の字が取れず kamoku_lines が科目を返さない）事項を、科目なしで黙って載せない
            fails.append(f"施策別資料 {it['事項名']}: 科目がない {it['科目']}")
            continue
        used_fixes.update(k for k in ((it["事項名"], t) for t in it["科目"]) if k in KOU_FIXES)
        kamoku = []
        for t in it["科目"]:
            k = _kamoku(KOU_FIXES.get((it["事項名"], t), t), budget_ids)
            if k:
                kamoku.append(k)
            elif t != "外":
                # 科目の形（款 項 目）にならない行（款の字が決まらない「? 1 4」など）を黙って落とさない。「外」は other_kamoku で持つ
                fails.append(f"施策別資料 {it['事項名']}: 科目が読めない {t!r}")
        # 事項名・課名・取組（区分）・柱が読めない事項を、名前のない円・「（取組なし）」・柱の外として黙って載せない
        empty = [k for k in ("事項名", "課名", "区分", "柱") if not it[k]]
        if empty:
            fails.append(f"施策別資料 {it['事項名'] or '（名前なし）'} {it['source']} p{it['pdf_page']}: 読めない {empty}")
            continue
        mm = re.match(r"^([１-９\d])．(.+)$", it["柱"])
        if mm:
            pillar = int(mm.group(1).translate(str.maketrans("１２３４５６７８９", "123456789")))
        elif it["柱"] == OUTSIDE_PILLAR_HEAD:
            pillar = None  # 4つの柱の外（計画推進の基盤づくり）
        else:
            fails.append(f"施策別資料 {it['事項名']}: 柱の見出しが分からない {it['柱']!r}")
            continue
        out_items.append({
            "name": it["事項名"], "pillar": pillar, "initiative": it["区分"] or None, "division": it["課名"],
            "kamoku": kamoku, **({"other_kamoku": True} if "外" in it["科目"] else {}),
            "amount": amount, "previous": None if it["前年度"] is None else it["前年度"] * 1000, "is_new": it["新規"],
            "notes": [e["text"] for e in it["説明"] if e.get("text")],
            "source": {"doc": it["source"], "page": it["pdf_page"]},
        })
    # 直しの表の行が使われない（資料の読み取りが変わった）ときは、表を見直すよう止める
    fails += [f"施策別資料: 項の直しの表の行が使われていない {k}" for k in sorted(set(KOU_FIXES) - used_fixes)]
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
    # 4つの決まった出費は名前で数えるので、名前が変わると 0 になり、円が消えて額が「その他」に黙って入る。0 なら止める
    fails += [f"施策別資料: 図に載らない経費「{o['label']}」が 0（款・事項の名前が変わった？）" for o in outside if o["amount"] <= 0]
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
