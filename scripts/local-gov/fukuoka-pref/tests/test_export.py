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


def test_pick_name_uses_r6_reference_when_close():
    kmk = {"revenue": [], "expense": [{"no": 2, "name": "総務費", "children": [
        {"no": 1, "name": "総務管理費", "children": [{"no": 1, "name": "一般管理費"}, {"no": 3, "name": "広報費"}]}]}]}
    e = ex.Exporter(None, kmk, {}, {}, None)
    assert e.pick_name("一般管理費", "歳出", 2, "moku") == ("一般管理費", "reference")
    assert e.pick_name("維持修善費管理", "歳出", 2, "moku")[1] == "ocr"   # 近い名前がなければ OCR のまま
    # 1文字違いの短い名前（OCR の「店報費」と R6 の「広報費」、近さ 0.67）は、別の目との取り違えを避けるため直さない。
    # 基準（0.75）未満は OCR のまま残し、name_src で区別する
    assert e.pick_name("店報費", "歳出", 2, "moku") == ("店報費", "ocr")
