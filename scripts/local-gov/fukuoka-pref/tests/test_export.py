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


def test_pick_name():
    kmk = {"revenue": [], "expense": [{"no": 2, "name": "総務費", "children": [
        {"no": 1, "name": "総務管理費", "children": [{"no": 1, "name": "一般管理費"}, {"no": 3, "name": "広報費"},
                                                {"no": 5, "name": "地域振興費"}]}]}]}
    e = ex.Exporter(None, kmk, {}, {}, None)
    assert e.pick_name("一般管理費", "歳出", 2, "moku") == ("一般管理費", "reference")   # 同じ名前が R6 にある
    assert e.pick_name("店報費", "歳出", 2, "moku") == ("広報費", "reference")         # 1文字の崩れ
    assert e.pick_name("地域振興総務費", "歳出", 2, "moku") == ("地域振興総務費", "ocr")  # R8 の新しい目は OCR のまま
    assert e.replaced == [("moku", "店報費", "広報費")]
