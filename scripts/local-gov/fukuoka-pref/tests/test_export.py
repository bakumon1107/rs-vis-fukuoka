"""共通 JSON 形式への書き出し（export_fukuoka_pref.py）の単体テスト。"""
from conftest import load

ex = load("export_fukuoka_pref.py", "export_fukuoka_pref")


def test_clean_name_restores_dropped_ichi():
    # 横棒1本の「一」が OCR で落ちる（「般会計繰入金」。説明書の OCR・議案の文字層とも）
    assert ex.clean_name("般会計繰入金") == "一般会計繰入金"
    assert ex.clean_name("○職員費") == "職員費"
    assert ex.clean_name("子ども•子育て支援納付金") == "子ども・子育て支援納付金"
    assert ex.clean_name("一般管理費") == "一般管理費"


def test_yen_converts_thousand_yen():
    assert ex.yen(17854435) == 17_854_435_000
    assert ex.yen(None) is None


import pytest


@pytest.mark.parametrize("ocr, ref", [
    ("物品壳払収入", "物品売払収入"),          # 字形の取り違え
    ("森林環境讓与税", "森林環境譲与税"),
    ("災害救助基金繰人金", "災害救助基金繰入金"),
    ("地方揮発油I讓与税", "地方揮発油譲与税"),  # 余計な英字
    ("廃対策費", "廃棄物対策費"),              # 落ちた文字（3文字以内）
    ("障措置費がい", "障がい措置費"),           # 2行の名前の前後の入れ替わり
    ("ゴ児フ場利用税", "ゴルフ場利用税"),        # 1文字だけ違う
])
def test_ocr_variant_accepted(ocr, ref):
    assert ex.is_ocr_variant(ocr, ref)


@pytest.mark.parametrize("ocr, ref", [
    # 正しい OCR の名前を、近いだけの別の目に変えてしまった実例（2026-11-06 のレビューで発見）
    ("参議院議員通常選挙臨時啓発費", "衆議院議員総選挙臨時啓発費"),
    ("地域振興総務費", "地域振興費"),          # 参照の方が短い
    ("生活衛生指導費", "食品衛生指導費"),        # 2文字違う
    ("一般管理費", "人事管理費"),
])
def test_ocr_variant_rejected(ocr, ref):
    assert not ex.is_ocr_variant(ocr, ref)


def _row(rid, setsu=()):
    return {"id": rid, "kan": {"name": "x", "name_src": "ocr"}, "kou": {"name": "x", "name_src": "ocr"},
            "moku": {"name": "x", "name_src": "ocr"},
            "setsu": [{"no": no, "name": "x", "name_src": "ocr", "amount": {"v": a * 1000}} for no, a in setsu]}


def test_external_checks_count_from_written_rows():
    def r(acc, side, kan, kou, v):
        return {"account": acc, "side": side, "kan": {"no": kan}, "kou": {"no": kou}, "amount": {"v": v * 1000}}
    rows = [r("general", "expense", 1, 1, 30), r("general", "expense", 1, 1, 70), r("general", "expense", 2, 1, 50),
            r("special:zaisei-chosei-kikin", "revenue", 1, 1, 5), r("special:zaisei-chosei-kikin", "expense", 1, 1, 5)]
    yo = {"会計": [
        {"会計": "一般会計", "歳出": [{"no": 1, "項": [{"no": 1, "金額": 100}]}, {"no": 2, "項": [{"no": 1, "金額": 49}]}]},
        {"会計": "財政調整基金特別会計", "歳入": [{"no": 1, "項": [{"no": 1, "金額": 5}]}],
         "歳出": [{"no": 1, "項": [{"no": 1, "金額": 5}]}]}]}
    keijou = {"一般会計歳入": {"款": []}, "一般会計歳出": {"款": [{"no": 1, "当年度": 100}, {"no": 2, "当年度": 50}]},
              "特別会計": {"会計": [{"会計名": "財政調整基金", "当年度": 5}]}}
    totals = [{"kind": "計", "会計": "一般会計", "side": "歳出", "款": 1, "項": [1, "x"], "本年度": 100}]
    summary, ng = ex.external_checks(rows, yo, keijou, totals)
    # 2款1項は予算書 49 に対して目の合計 50（1件 NG）。固定の値ではなく、書き出す行から数える
    assert summary["項_予算書"] == "一般会計 1/2・特別会計 2/2"
    assert summary["款_計上額調"] == "一般会計 2/2" and summary["会計_計上額調"] == "特別会計 2/2"
    assert summary["計の行"] == "一般会計 1/1"
    assert len(ng) == 1 and "('general', 'expense', 2, 1)" in ng[0]


def test_setsu_in_print_order():
    # 突き合わせで組み直した目は「節を全部 → 細節を全部」の順になる。印字の順（ページ → 高さ）に戻さないと、
    # 細節がすべて最後の節に付く（R8 6款5項5目 森林環境費）
    m = {"pages": [280, 281], "節": [
        {"label": "職員手当等", "top": True, "page": 280, "y": 1831},
        {"label": "積立金", "top": True, "page": 281, "y": 2165},
        {"label": "勤勉手当", "top": False, "page": 280, "y": 2040},
        {"label": "旅費", "top": True, "page": 281, "y": 793},
        {"label": "普通旅費", "top": False, "page": 281, "y": 910},
    ]}
    assert [s["label"] for s in ex.setsu_in_print_order(m)] == ["職員手当等", "勤勉手当", "旅費", "普通旅費", "積立金"]
    # 位置のない節（修正表で足した節）があれば並べ替えない
    m2 = {"pages": [1], "節": [{"label": "b", "page": 1, "y": 9}, {"label": "a", "page": None, "y": None}]}
    assert [s["label"] for s in ex.setsu_in_print_order(m2)] == ["b", "a"]


def test_name_corrections_apply_and_clear_unresolved():
    rows = [_row("special:a-b/expense/1-1-1", [(1, 30), (2, 30)]), _row("special:a-b/expense/1-1-2"),
            _row("special:a-b/expense/10-1-1")]
    unresolved = [("kan", {"id": "special:a-b/expense/1-1-1"}, "x", [], None),
                  ("setsu", {"id": "special:a-b/expense/1-1-1", "amount": 30}, "x", [], None)]
    fixes = [{"id": "special:a-b/expense/1", "level": "kan", "name": "積立金"},
             {"id": "special:a-b/expense/1-1-1", "level": "setsu", "amount": 30, "no": 2, "name": "雑入"}]
    assert ex.apply_name_corrections(rows, fixes, unresolved) == 2
    # 款は 1款のすべての目の行に当たり、10款には当たらない（id の前方一致で「1」と「10」を取り違えない）
    assert [r["kan"]["name"] for r in rows] == ["積立金", "積立金", "x"]
    assert [s["name"] for s in rows[0]["setsu"]] == ["x", "雑入"]
    # 節番号も画像で確かめた値に直せる（set_no。番号の出典は correction）
    ex.apply_name_corrections(rows, [{"id": "special:a-b/expense/1-1-1", "level": "setsu", "amount": 30, "no": 1,
                                      "set_no": 7, "name": "報酬"}], [])
    assert (rows[0]["setsu"][0]["no"], rows[0]["setsu"][0]["no_src"]) == (7, "correction")
    assert rows[0]["setsu"][1]["name_src"] == "correction"
    assert unresolved == []   # 当てた名前は、画像で確かめる一覧から消える


def test_name_corrections_apply_to_items():
    # 説明欄の事項は目の中の金額で特定する。同じ金額の事項が2つあれば今の名前（was）も合わせる
    row = _row("general/expense/12-1-2")
    row["items"] = [{"name": "一時借入金利子", "name_src": "readings", "amount": {"v": 90_000_000, "src": "ocr"}},
                    {"name": "公債管理特別会計の繰出金", "name_src": "ocr", "amount": {"v": 31_278_351_000, "src": "ocr"}},
                    {"name": "x", "name_src": "ocr", "amount": {"v": 5_000, "src": "ocr"}},
                    {"name": "y", "name_src": "ocr", "amount": {"v": 5_000, "src": "ocr"}}]
    fixes = [{"id": "general/expense/12-1-2", "level": "item", "amount": 31278351, "name": "公債管理特別会計への繰出金"},
             {"id": "general/expense/12-1-2", "level": "item", "amount": 5, "was": "y", "name": "z"}]
    assert ex.apply_name_corrections([row], fixes, []) == 2
    assert [(it["name"], it["name_src"]) for it in row["items"]] == [
        ("一時借入金利子", "readings"), ("公債管理特別会計への繰出金", "correction"), ("x", "ocr"), ("z", "correction")]
    # 今の名前は画像のとおり全角で書いてもよい（行の名前と同じく clean_name でそろえて比べる）
    row["items"][2]["name"] = "A1"
    assert ex.apply_name_corrections([row], [{"id": "general/expense/12-1-2", "level": "item", "amount": 5,
                                               "was": "Ａ１", "name": "v"}], []) == 1
    assert row["items"][2]["name"] == "v"
    with pytest.raises(SystemExit):   # 同じ金額の事項が2つで今の名前の指定なし → 1件に絞れない
        ex.apply_name_corrections([row], [{"id": "general/expense/12-1-2", "level": "item", "amount": 5, "name": "w"}], [])


def test_name_corrections_sub_by_setsu_no_and_amount():
    rows = [_row("general/expense/10-2-1", [(3, 50), (10, 50)])]
    def sub(name, a):
        return {"name": name, "name_src": "ocr", "name_evidence": ["x"], "amount": {"v": a * 1000}}
    rows[0]["setsu"][0]["sub"] = [sub("き地手当", 29), sub("通勤手当", 21)]
    rows[0]["setsu"][1]["sub"] = [sub("光热水費", 29)]
    # 同じ金額の細節が別の節にあっても、節の番号で1件に絞る
    assert ex.apply_name_corrections(rows, [{"id": "general/expense/10-2-1", "level": "sub", "no": 3, "amount": 29,
                                             "name": "へき地手当"}], []) == 1
    s0, s1 = rows[0]["setsu"]
    assert (s0["sub"][0]["name"], s0["sub"][0]["name_src"]) == ("へき地手当", "correction")
    assert "name_evidence" not in s0["sub"][0]
    assert s0["sub"][1]["name"] == "通勤手当" and s1["sub"][0]["name"] == "光热水費"
    with pytest.raises(SystemExit):   # 節の番号が合わない（修正表が古い）
        ex.apply_name_corrections(rows, [{"id": "general/expense/10-2-1", "level": "sub", "no": 4, "amount": 29,
                                          "name": "y"}], [])
    with pytest.raises(SystemExit):   # 節の番号がない（KeyError ではなく、分かる言葉で止める）
        ex.apply_name_corrections(rows, [{"id": "general/expense/10-2-1", "level": "sub", "amount": 29, "name": "y"}], [])
    # 同じ節に同じ金額の細節が2つ: 番号と金額だけでは止まり、今の名前（was）を添えると1件に絞れる
    rows[0]["setsu"][1]["sub"].append(sub("その他役務費", 29))
    with pytest.raises(SystemExit):
        ex.apply_name_corrections(rows, [{"id": "general/expense/10-2-1", "level": "sub", "no": 10, "amount": 29,
                                          "name": "光熱水費"}], [])
    assert ex.apply_name_corrections(rows, [{"id": "general/expense/10-2-1", "level": "sub", "no": 10, "amount": 29,
                                             "was": "光热水費", "name": "光熱水費"}], []) == 1
    assert [x["name"] for x in rows[0]["setsu"][1]["sub"]] == ["光熱水費", "その他役務費"]


def test_name_corrections_stop_when_stale():
    rows = [_row("general/revenue/8-1-3", [(2, 836), (3, 836)])]
    with pytest.raises(SystemExit):   # 同じ金額の節が2つで番号の指定なし → 1件に絞れない
        ex.apply_name_corrections(rows, [{"id": "general/revenue/8-1-3", "level": "setsu", "amount": 836, "name": "y"}], [])
    with pytest.raises(SystemExit):   # 当たる目がない（データが変わった）
        ex.apply_name_corrections(rows, [{"id": "general/revenue/9-9-9", "level": "moku", "name": "y"}], [])


def test_pick_name():
    kmk = {"revenue": [], "expense": [{"no": 2, "name": "総務費", "children": [
        {"no": 1, "name": "総務管理費", "children": [{"no": 1, "name": "一般管理費"}, {"no": 3, "name": "広報費"},
                                                {"no": 5, "name": "地域振興費"}]}]}]}
    e = ex.Exporter(None, kmk, {}, {}, None)
    ref = e.reference("歳出", 2, "moku")

    def pick(name):
        n, src, _ = e.name("moku", [(name, "ocr")], "2-1-1", ref)
        return n, src
    assert pick("一般管理費") == ("一般管理費", "reference")   # 同じ名前が R6 にある
    assert pick("店報費") == ("広報費", "reference")         # 1文字の崩れ
    assert pick("地域振興総務費") == ("地域振興総務費", "ocr")  # R8 の新しい目は（ほかの裏付けがなければ）OCR のまま
    assert e.replaced == [("moku", "店報費", "広報費")]
    assert [u[2] for u in e.unresolved] == ["地域振興総務費"]   # 裏付けのない名前は画像で確かめる一覧に出る


def _moku(h, p, items, fixes=None, setsu=()):
    return {"本年度": h, "前年度": p, "説明": [{"name": "x", "amount": a} for a in items],
            "節": [{"label": "x", "amount": a} for a in setsu], **({"修正": fixes} if fixes else {})}


def test_ndl_mismatches_finds_stale_readings():
    ocr = {"a": _moku(100, 90, [60, 40]), "b": _moku(5, 5, [5])}
    # 同じなら空
    assert ex.ndl_mismatches(ocr, {"a": _moku(100, 90, [60, 40]), "b": _moku(5, 5, [5])}) == []
    # 説明欄の金額が1件違う・本年度が違う・目が欠ける／余る
    assert ex.ndl_mismatches(ocr, {"a": _moku(100, 90, [60, 41]), "b": _moku(5, 5, [5])}) == ["a"]
    assert ex.ndl_mismatches(ocr, {"a": _moku(101, 90, [60, 40]), "b": _moku(5, 5, [5])}) == ["a"]
    assert ex.ndl_mismatches(ocr, {"a": _moku(100, 90, [60, 40]), "c": _moku(5, 5, [5])}) == ["b", "c"]
    # 節の金額が違う（OCR の節の金額を補った後に読み直していない）
    ocr_s = {"a": _moku(100, 90, [100], setsu=[60, 40])}
    assert ex.ndl_mismatches(ocr_s, {"a": _moku(100, 90, [100], setsu=[100])}) == ["a"]


def test_ndl_mismatches_skips_only_corrected_columns():
    # 修正表で本年度を直した目: 本年度は比べないが、説明欄の金額と目の有無は比べる
    ocr = {"a": _moku(100, 90, [100], fixes=[{"列": "本年度"}])}
    assert ex.ndl_mismatches(ocr, {"a": _moku(99, 90, [100])}) == []
    assert ex.ndl_mismatches(ocr, {"a": _moku(99, 90, [99])}) == ["a"]
    assert ex.ndl_mismatches(ocr, {}) == ["a"]


def test_corrected_columns_use_only_readings_with_same_amounts():
    # 説明欄の事項 A の金額を修正表で 100 → 200 に直した目: 直していない読み取り（NDLOCR-Lite・同じ読み違いの旧 OCR）は
    # A を 100 のまま持つので、金額で対応させると B（100）に A の名前が付く。金額の集まりが直した後と同じ読み取りだけを使う
    m = {"説明": [{"amount": 200}, {"amount": 100}], "修正": [{"列": "説明"}]}
    stale = {"説明": [{"amount": 100}, {"amount": 100}]}
    right = {"説明": [{"amount": 200}, {"amount": 100}]}
    # 金額が入れ替わった読み取り（集まりは同じ）も使わない（金額で対応させると A と B の名前が入れ替わる）
    swapped = {"説明": [{"amount": 100}, {"amount": 200}]}
    others = [("textlayer", right), ("v4", stale), ("ndl", swapped)]
    assert ex.others_for_column(others, m, "説明") == [("textlayer", right)]
    # 修正表で足した位置のない節がある目は、金額の並びが同じでも使わない（並べ替えられず、節の対応が保証されない）
    ms = {"節": [{"amount": 10, "page": 1, "y": 200}, {"amount": 20, "page": None, "y": None}], "修正": [{"列": "節"}]}
    xs = {"節": [{"amount": 10, "page": 1, "y": 100}, {"amount": 20, "page": 1, "y": 200}]}
    assert ex.others_for_column([("textlayer", xs), ("ndl", xs)], ms, "節") == []
    # 直していない欄・修正のない目は全部使う
    assert ex.others_for_column(others, m, "節") == others
    assert ex.others_for_column(others, {"説明": m["説明"]}, "説明") == others


def test_candidate_labels_mark_support_only():
    assert ex.candidate_labels([("用水事業費負担金", "ocr"), ("の用水事業費2負担金", "ndl")]) == \
        ["用水事業費負担金", "の用水事業費2負担金（ndl・支えのみ）"]


def _prev_row(account, side, kan, prev):
    return {"account": account, "side": side, "kan": {"name": kan}, "previous": {"v": prev, "src": "ocr"}}


# R8 の県営埠頭施設整備運営事業特別会計: 総括表（説明書 p.93）にだけ、前年度にだけあった款「財産収入」2,530千円がある
FUTO = "special:kenei-futo-shisetsu"
FUTO_ROWS = [_prev_row(FUTO, "revenue", "県債", 10_000_000), _prev_row(FUTO, "expense", "公債費", 12_530_000)]
FUTO_ENTRY = {"会計": FUTO, "side": "歳入", "款名": "財産収入", "前年度": 2530, "source": "r8-setsumeisho-toku", "page": 93, "根拠": "画像で確認"}
ACCOUNTS = [{"id": FUTO, "kind": "special"}, {"id": "enterprise:x", "kind": "enterprise"}]


def test_previous_only_kan_balances_revenue_and_expense():
    out, fails, checked = ex.previous_only_kan(FUTO_ROWS, ACCOUNTS, [FUTO_ENTRY])
    assert fails == [] and checked == 1
    assert out == [{"account": FUTO, "side": "revenue", "kan": {"name": "財産収入"},
                    "previous": {"v": 2_530_000, "src": "correction", "note": "画像で確認"},
                    "pages": [{"source": "r8-setsumeisho-toku", "page": 93}]}]


def test_previous_only_kan_stops_when_previous_does_not_balance():
    # 修正表に書いていない（前年度にだけあった款を取りこぼした）: 歳入の前年度が足りない
    _, fails, _ = ex.previous_only_kan(FUTO_ROWS, ACCOUNTS, [])
    assert len(fails) == 1 and "差 2,530,000 円" in fails[0]


def test_previous_only_kan_stops_when_stale():
    # 会計がない・本年度にその款の行がある（前年度にだけの款ではない）なら修正表が古い
    _, fails, _ = ex.previous_only_kan(FUTO_ROWS, ACCOUNTS, [{**FUTO_ENTRY, "会計": "special:none"}])
    assert any("会計 special:none がない" in f for f in fails)
    rows = FUTO_ROWS + [_prev_row(FUTO, "revenue", "財産収入", 0)]
    _, fails, _ = ex.previous_only_kan(rows, ACCOUNTS, [FUTO_ENTRY])
    assert any("本年度の行がある" in f for f in fails)
    # side の書き間違い（前後の空白など）は例外でなく、どの款かを書いて止まる
    _, fails, _ = ex.previous_only_kan(FUTO_ROWS, ACCOUNTS, [{**FUTO_ENTRY, "side": "歳入 "}])
    assert any("side が不正" in f and "財産収入" in f for f in fails)


def test_previous_only_kan_skips_unread_previous_and_enterprise():
    # 前年度の読めない目（null）がある会計は比べない。公営企業会計は前年度の額を持たないので比べない
    rows = [_prev_row(FUTO, "revenue", "県債", None), _prev_row(FUTO, "expense", "公債費", 12_530_000),
            _prev_row("enterprise:x", "expense", "営業費用", 5)]
    _, fails, checked = ex.previous_only_kan(rows, ACCOUNTS, [])
    assert fails == [] and checked == 0


def _fiscal(**over):
    ind = lambda k: {"key": k, "threshold": 25.0 if k in ex.FISCAL_THRESHOLD_KEYS else None,  # noqa: E731
                     "values": [{"year": 2024, "value": 1.0, "median": 1.0, "rank": 1, "of": 47, "source": "r6-shihyo"}]}
    base = {"fails": [],
            "reserve": {"parts": ["a", "b"], "history": [{"year": 2024, "total": 3, "parts": [1, 2], "source": "r7-kikin"},
                                    {"year": 2025, "total": 4, "parts": [2, 2], "source": "r7-kikin"}],
                        "outlook": {"year": 2026, "total": 5, "source": "r8-gaiyou"},
                        "target": {"min": 1, "max": 2, "source": "r8-gaiyou"}},
            "indicators": [ind(k) for k in ex.FISCAL_KEYS]}
    return {**base, **over}


def test_fiscal_problem_accepts_a_complete_output_and_names_each_problem():
    ids = {"r7-kikin", "r8-gaiyou", "r6-shihyo"}
    assert ex.fiscal_problem(_fiscal(), ids) is None
    assert "形でない" in ex.fiscal_problem([], ids)
    assert "形でない" in ex.fiscal_problem(None, ids)
    assert "fails がない" in ex.fiscal_problem({}, ids)
    assert "確かめが通っていない" in ex.fiscal_problem(_fiscal(fails=["x"]), ids)
    assert "reserve" in ex.fiscal_problem({"fails": []}, ids)
    assert "指標の種類" in ex.fiscal_problem(_fiscal(indicators=[]), ids)
    assert "sources.json にない" in ex.fiscal_problem(_fiscal(), {"r7-kikin"})
    # 形の崩れは落ちずに理由を返す
    bad = _fiscal()
    bad["reserve"] = {**bad["reserve"], "outlook": "n/a"}
    assert "形が崩れている" in ex.fiscal_problem(bad, ids)
    bad = _fiscal()
    bad["reserve"] = {**bad["reserve"], "outlook": {"year": 2027, "total": 5, "source": "r8-gaiyou"}}
    assert "見込み" in ex.fiscal_problem(bad, ids)
    bad = _fiscal()
    bad["reserve"]["history"][1] = {"year": 2025, "total": 5, "parts": [2, 2], "source": "r7-kikin"}
    assert "内訳" in ex.fiscal_problem(bad, ids)
    # NaN・順位の範囲・年度の重複・基準の値・出典の型の混ざり
    bad = _fiscal()
    bad["indicators"][0]["values"][0]["median"] = float("nan")
    assert "数でない" in ex.fiscal_problem(bad, ids)
    bad = _fiscal()
    bad["indicators"][0]["values"][0]["rank"] = 48
    assert "順位" in ex.fiscal_problem(bad, ids)
    bad = _fiscal()
    bad["indicators"][0]["values"].append(dict(bad["indicators"][0]["values"][0]))
    assert "重複" in ex.fiscal_problem(bad, ids)
    bad = _fiscal()
    bad["indicators"][0]["threshold"] = 1.0
    assert "threshold" in ex.fiscal_problem(bad, ids)
    bad = _fiscal()
    bad["indicators"][0]["values"][0]["source"] = None
    bad["indicators"][1]["values"][0]["source"] = "r9-x"
    assert "sources.json にない" in ex.fiscal_problem(bad, ids)
