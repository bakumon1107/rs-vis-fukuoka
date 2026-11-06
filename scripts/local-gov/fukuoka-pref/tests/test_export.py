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
    assert rows[0]["setsu"][1]["name_src"] == "correction"
    assert unresolved == []   # 当てた名前は、画像で確かめる一覧から消える


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
