"""施策別資料の抽出（extract_shisaku.py）の単体テスト。"""
import pytest

from conftest import load

sh = load("extract_shisaku.py", "extract_shisaku")


@pytest.mark.parametrize("name, want", [
    ("事項事新項規表示予算表示", True),     # 列見出し（R8 278133 の各ページ）
    ("新規表示予算表示", True),
    ("食品表示適正化推進費", False),         # 事項名に「表示」が入るだけ
    ("原産地表示監視指導費", False),
])
def test_is_header_row(name, want):
    assert sh.is_header_row(name) is want


def _w(x, top, text):
    return {"x0": x, "x1": x + 6, "top": top, "text": text}


def test_kamoku_centered_kan_kou():
    # 款・項は結合セルで、またがる目の行の縦の真ん中に1回だけ（R8 277214 p3「ワンヘルス教育推進費」）
    ws = [_w(107, 279.8, "５"), _w(120, 279.8, "３"), _w(133, 279.8, "１"),
          _w(120, 298.5, "１"), _w(133, 298.5, "４"),
          _w(105, 307.8, "10"), _w(120, 307.8, "８"), _w(133, 307.8, "１"),
          _w(120, 317.2, "９"), _w(133, 317.2, "２")]
    assert sh.kamoku_lines(ws) == ["5 3 1", "10 1 4", "10 8 1", "10 9 2"]
    # 款が全部の目の真ん中、項が2つずつの真ん中（278133 p1「中小企業成長投資・賃上げ応援費」）
    ws = [_w(133, 282.0, "１"), _w(120, 286.2, "１"), _w(133, 291.4, "３"), _w(107, 309.6, "７"), _w(133, 310.1, "５"),
          _w(120, 314.3, "２"), _w(133, 319.5, "６"), _w(120, 338.2, "３"), _w(133, 338.2, "１")]
    assert sh.kamoku_lines(ws) == ["7 1 1", "7 1 3", "7 2 5", "7 2 6", "7 3 1"]
    # 目のない字の並び（特別会計など）はそのまま
    assert sh.kamoku_lines([_w(110, 100, "特別"), _w(125, 100, "会計")]) == ["特別会計"]
