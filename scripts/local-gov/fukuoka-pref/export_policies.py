"""施策別資料の事項（extract_shisaku.py の shisaku.json）を、当初予算のファイル（budget-<年度>-initial.json）の policies に組み立てる。

設計: docs/local-gov/tasks/20261120_1500_地方版バブル図の設計.md（3章 範囲・4章 データ）。型: types/local-gov.ts の LocalPolicies
export_fukuoka_pref.py の main から呼ぶ（予算の行が決まった後）。

- 範囲: 一般会計の事項だけ。特別会計・公営企業会計の事項（科目が「特別会計」「企業会計」）は除き、件数と額を excluded に書く。
  債務負担行為の行は、今年度の額を事項として載せ、限度額（後年度にわたる額で、その年度の歳出ではない）の件数と額だけを excluded に書く。
  制度融資の貸付金（中小企業振興資金融資費）は事項の円にせず、図に載らない経費の灰色の円にする
- 科目: 予算の目（一般会計の歳出）に結ぶ。項が決まらない科目（「9 ? 4」）は、予算にある目がちょうど1つならそれに決める。
  目が2つあるもの（「9 ? 1」）は、根拠を確かめた表（KAMOKU_FIXES）で決める。表になければ止める（項なしで黙って載せない）
  予算にない科目は unmatched の印（資料の印字のまま。R8「認知症医療センター事業費」3-2-5）。
  1つの目だけを科目に持つ事項の合計が目の額を超えれば止める（資料の科目の誤りは KAMOKU_FIXES で直し、直せないものは OVER_MOKU_OK に理由）
- 図に載らない経費（outside）: 一般会計の歳出から、施策別資料の事項の合計と、4つの決まった出費（諸支出金・人件費・公債費・制度融資）を
  引いた残りを「その他」にする。その他が負なら止める（重なりの数え方が合っていない）
- 金額は千円 × 1000 の円
"""
import json
import os
import re

# 4つの柱の後の、番号のない見出し（extract_shisaku.OUTSIDE_PILLAR_HEAD と同じ。柱の外のグループ）
OUTSIDE_PILLAR_HEAD = "計画推進の基盤づくり"
# 中小企業の制度融資の貸付金（金融機関に預けて年度内に戻る）。図に載らない経費の灰色の円で見せる（設計 3章）
LOANS_ITEM = "中小企業振興資金融資費"

# 資料の科目を、根拠を確かめて直す表。(事項名, 資料の科目) → 科目。画面には資料の印字も出す（printed）
KAMOKU_FIXES = {
    # 項が字の位置で決まらず（目が3行で項の「1」「2」が行の間に半行ずれて印字）、予算にある目も2つある。
    # 説明欄の「少年警察ボランティア協会補助金」9,104 千円は、9-1-1 公安委員会費（節は報酬・旅費・交際費・需用費・委託料だけ）に
    # 入らない。9-2-1 一般警察活動費には節「負担金、補助及び交付金」36,192 千円がある（R8 278133 p40。2026-11-20 確認）
    ("少年補導員等活動費", "9 ? 1"): "9 2 1",
    # 資料は結合セルで「10 7 2」（体育振興費 544,641 千円）だが、この2事項（723,323・703,146 千円）は1つでも目の額を超える。
    # ほかの 10-7-2 の事項の合計 533,512 千円で目の額にほぼ届く。10-7-3 体育施設費の事項「県立体育・スポーツ施設運営費」
    # 1,597,974 千円に2事項の合計 1,426,469 千円が収まる（R8 278133 p18。2026-11-20 確認。資料の科目の誤りとみる）
    ("県立体育・スポーツ施設費", "10 7 2"): "10 7 3",
    ("県立体育・スポーツ施設改修費", "10 7 2"): "10 7 3",
}

# 1つの目だけを科目に持つ事項の合計が、その目の予算額を超えてよい目（理由を書く。ここにない目で超えれば止める）
OVER_MOKU_OK = {
    # 「土地区画整理事業費」505,080 千円 > 土地区画整理費 496,800 千円（8,280 千円）。資料の科目はこの目だけで、
    # 超える分の目は資料から決められない（都市計画総務費などにまたがるとみられる）。印字のまま（2026-11-20）
    "general/expense/8-5-2": "資料の科目は1つだが、額が目を 8,280 千円超える（ほかの目にもまたがるとみられる）",
    # 「土木災害復旧事業費」4,897,105 千円 > 河川等災害復旧費 4,672,005 千円（225,100 千円）。同上（土木施設災害復旧総務費など）
    "general/expense/11-2-2": "資料の科目は1つだが、額が目を 225,100 千円超える（ほかの目にもまたがるとみられる）",
}


def _kamoku(text: str, budget_ids: set[str]):
    """「款 項 目」→ 科目の dict。読めない形なら None。項が「?」なら、予算にある目がちょうど1つのときだけ決める。
    予算に目がなければ unmatched の印（項は None）。2つ以上あれば "ambiguous"（呼び出し側が止める。KAMOKU_FIXES に根拠を書いて足す）"""
    m = re.fullmatch(r"(\d+) (\d+|\?) (\d+)", text)
    if not m:
        return None
    kan, kou, moku = m.group(1), m.group(2), m.group(3)
    if kou == "?":
        cands = [i for i in budget_ids if re.fullmatch(rf"general/expense/{kan}-\d+-{moku}", i)]
        if len(cands) > 1:
            return "ambiguous"
        if not cands:
            return {"kan": int(kan), "kou": None, "moku": int(moku), "row": None, "unmatched": True}
        # 予算にある目が1つなので決まる。資料の読み（「9 ? 4」）を printed に、決め方を resolved に残す（画面に出す）
        return {"kan": int(kan), "kou": int(cands[0].split("/")[-1].split("-")[1]), "moku": int(moku), "row": cands[0],
                "printed": text, "resolved": "budget"}
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
    data = json.load(open(path, encoding="utf-8"))
    # 抽出の検算（説明の内訳の合計 = 予算額・額の欄の読み）が通っていなければ止める。fails のない古い shisaku.json も止める
    if "fails" not in data:
        return None, [], ["施策別資料: shisaku.json に fails がない（古い抽出の出力。extract_shisaku.py を流し直す）"]
    if data["fails"]:
        return None, [], [f"施策別資料の抽出の検算が通っていない: {f}" for f in data["fails"]]
    items = data["items"]
    expense = [r for r in rows if r["account"] == "general" and r["side"] == "expense"]
    budget_ids = {r["id"] for r in expense}
    fails: list[str] = []
    out_items, excluded = [], {"special": [0, 0], "debt_burden": [0, 0]}
    used_fixes: set[tuple[str, str]] = set()
    loans_in_policies = None
    for it in items:
        # 予算額が読めない事項は、除く事項（債務負担行為・特別会計）でも止める（除いた額が黙って少なくならないよう）
        if it["予算額"] is None:
            fails.append(f"施策別資料 {it['事項名']}: 予算額が読めない")
            continue
        amount = it["予算額"] * 1000
        if it["事項名"] == LOANS_ITEM:
            # 制度融資の貸付金は、施策の円の外の灰色の円（loans）で見せる（設計 3章）。事項の円に重ねて数えない
            if loans_in_policies is not None:
                fails.append(f"施策別資料: {LOANS_ITEM} が2度ある（片方が黙って消える）")
            loans_in_policies = amount
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
        used_fixes.update(k for k in ((it["事項名"], t) for t in it["科目"]) if k in KAMOKU_FIXES)
        kamoku = []
        for t in it["科目"]:
            fixed = KAMOKU_FIXES.get((it["事項名"], t))
            k = _kamoku(fixed or t, budget_ids)
            if k == "ambiguous":
                # 項が読み分けられず、予算にその款・目の目が2つ以上ある: 黙って項なしで載せない
                fails.append(f"施策別資料 {it['事項名']}: 科目 {t!r} の項が決まらない（予算に候補が2つ以上。根拠を確かめて KAMOKU_FIXES に足す）")
            elif k:
                if fixed and k.get("unmatched"):
                    # 直しの表の行き先が予算の目にない（表の書き誤り）: 「印字のまま」と「直した」を並べて出さないよう止める
                    fails.append(f"施策別資料 {it['事項名']}: 直しの表の科目 {fixed!r} が予算の目にない")
                # 直した科目には資料の印字と、根拠を確かめた直しの表で決めたこと（resolved: fix）を残す（画面に出す）
                kamoku.append({**k, "printed": t, "resolved": "fix"} if fixed else k)
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
        if it.get("債務負担行為") is not None:
            # 一般会計の事項の債務負担行為の限度額（後年度にわたる額で、この年度の歳出ではない）は数えるだけ。事項の今年度の額は載せる
            # （同じセルに今年度の額と限度額が並ぶ。extract_shisaku.amounts_of）。特別会計の事項・制度融資は上で外したので数えない
            excluded["debt_burden"][0] += 1
            excluded["debt_burden"][1] += it["債務負担行為"] * 1000
        if amount == 0:
            # 今年度の額が 0（限度額だけの債務負担行為。R8「国際園芸博覧会出展事業費」）: 円がないので事項に入れない（件数と円の数をそろえる）。
            # 名前・科目・柱の確かめの後で外す（読めない事項の限度額を黙って数えない）
            continue
        out_items.append({
            "name": it["事項名"], "pillar": pillar, "initiative": it["区分"] or None, "division": it["課名"],
            "kamoku": kamoku, **({"other_kamoku": True} if "外" in it["科目"] else {}),
            "amount": amount, "previous": None if it["前年度"] is None else it["前年度"] * 1000, "is_new": it["新規"],
            "notes": [e["text"] for e in it["説明"] if e.get("text")],
            "source": {"doc": it["source"], "page": it["pdf_page"]},
        })
    # 直しの表の行が使われない（資料の読み取りが変わった）ときは、表を見直すよう止める
    fails += [f"施策別資料: 科目の直しの表の行が使われていない {k}" for k in sorted(set(KAMOKU_FIXES) - used_fixes)]
    # 1つの目だけを科目に持つ事項の合計が、その目の予算額を超えないこと（超えれば科目の読み違いか資料の科目の誤り。設計 4章）
    by_row: dict[str, int] = {}
    for i in out_items:
        if len(i["kamoku"]) == 1 and not i.get("other_kamoku") and i["kamoku"][0]["row"]:
            by_row[i["kamoku"][0]["row"]] = by_row.get(i["kamoku"][0]["row"], 0) + i["amount"]
    row_amount = {r["id"]: r["amount"]["v"] or 0 for r in expense}
    # 制度融資の事項は施策の円から外したので、その目（商業総務費）の確かめでは制度融資の額を引いた額と比べる
    for r in expense:
        if loans_in_policies and any(i["name"] == LOANS_ITEM for i in r.get("items", [])):
            row_amount[r["id"]] -= loans_in_policies
    for rid, s in sorted(by_row.items()):
        if s > row_amount[rid] and rid not in OVER_MOKU_OK:
            fails.append(f"施策別資料: 目 {rid} の事項の合計 {s:,} 円が目の額 {row_amount[rid]:,} 円を超える（科目を確かめて KAMOKU_FIXES か OVER_MOKU_OK に足す）")
    fails += [f"施策別資料: OVER_MOKU_OK の目 {rid} はもう超えていない（表を見直す）" for rid in sorted(OVER_MOKU_OK)
              if by_row.get(rid, 0) <= row_amount.get(rid, 0)]
    # 例外の目の事項には印を付ける（画面に「額が目を超える」と出す）
    for i in out_items:
        if (len(i["kamoku"]) == 1 and not i.get("other_kamoku") and i["kamoku"][0]["row"] in OVER_MOKU_OK
                and i["amount"] > row_amount[i["kamoku"][0]["row"]]):
            i["exceeds_moku"] = True  # その事項だけで目の額を超える（同じ目のほかの小さな事項には付けない）
    # 複数の目にまたがる事項: その目の組の中だけに科目を持つ事項の合計が、組の目の額の合計を超えないこと
    # （1つの目だけの確かめでは、またがる事項の科目の読み違いに気づけない。「外」の事項はほかの目にもまたがるので外す）
    multi = {frozenset(k["row"] for k in i["kamoku"]) for i in out_items
             if len(i["kamoku"]) > 1 and not i.get("other_kamoku") and all(k["row"] for k in i["kamoku"])}
    for rows_set in sorted(multi, key=sorted):
        if rows_set & set(OVER_MOKU_OK):
            continue
        s = sum(i["amount"] for i in out_items if i["kamoku"] and not i.get("other_kamoku")
                and all(k["row"] in rows_set for k in i["kamoku"]))
        cap = sum(row_amount[r] for r in rows_set)
        if s > cap:
            fails.append(f"施策別資料: 目の組 {sorted(rows_set)} の事項の合計 {s:,} 円が目の額の合計 {cap:,} 円を超える（科目を確かめる）")
    pillars: dict[int, str] = {}
    for it in items:
        mm = re.match(r"^([１-９\d])．(.+)$", it["柱"] or "")
        if mm:
            no = int(mm.group(1).translate(str.maketrans("１２３４５６７８９", "123456789")))
            if pillars.get(no, mm.group(2)) != mm.group(2):
                # 同じ番号の柱の名前がページで違う（折り返しの2行目を読み落とした、など）: 黙って後の名前にしない
                fails.append(f"施策別資料: 柱 {no} の名前が2通り {pillars[no]!r} / {mm.group(2)!r}")
            pillars.setdefault(no, mm.group(2))

    # 図に載らない経費（設計 3章の表）。一般会計の歳出の目・節・事項から数える
    total = sum(r["amount"]["v"] or 0 for r in expense)
    in_policies = sum(i["amount"] for i in out_items)
    kan_sum = lambda name: sum(r["amount"]["v"] or 0 for r in expense if r["kan"]["name"] == name)  # noqa: E731
    personnel = sum(s["amount"]["v"] or 0 for r in expense for s in r.get("setsu", []) if s.get("no") in (1, 2, 3, 4))
    loans = sum(i["amount"]["v"] or 0 for r in expense for i in r.get("items", []) if i["name"] == LOANS_ITEM)
    # 施策別資料の制度融資の事項（円に載せず灰色の円で見せる）の額が、説明書の事項の額と同じであること（違えば二重・漏れになる）
    if loans_in_policies is None:
        # 施策別資料に制度融資の事項がない（名前が変わった）: その事項が施策の円になり、灰色の円とで二重に数える。止める
        fails.append(f"施策別資料: {LOANS_ITEM} の事項がない（名前が変わった？ 施策の円と灰色の円で二重に数える）")
    elif loans_in_policies != loans:
        fails.append(f"施策別資料: {LOANS_ITEM} の額 {loans_in_policies:,} 円が説明書の事項 {loans:,} 円と違う")
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
    # 人件費（節で数える）と施策の事項は一部重なりうる（事項の額に人件費が入っている）。重なりの分は2度引かれるので、その他はその分小さい
    outside.append({"key": "other", "label": "その他（事務費・施設の管理・施策別資料に載らない事業。人件費と施策の事項が重なる分だけ小さい）",
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
    # 項が決まらない科目は止めるので、要約には直しの表で項を決めた数を出す
    lines = [f"施策別資料 事項 {len(out_items)} 件（{in_policies:,} 円）。除いた: 特別会計 {excluded['special'][0]}・"
             f"債務負担行為 {excluded['debt_burden'][0]}。科目: 予算にない {n_unmatched}・直しの表で直した {len(used_fixes)}・"
             f"目の額を超えてよい目 {len(OVER_MOKU_OK)}。"
             f"図に載らない経費のその他 {other:,} 円"]
    return policies, lines, fails
