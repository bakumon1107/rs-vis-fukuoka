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
