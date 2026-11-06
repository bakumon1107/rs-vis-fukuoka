"""説明書の OCR の縦線の選び方（ocr/ocr_pages.py の choose_vlines）の単体テスト。cv2 を使わない関数だけを試す。"""
import importlib.util
import os
import sys
import types

import pytest

from conftest import ROOT

# ocr_pages.py は import 時に cv2・numpy を読み込む。テストでは選び方の関数だけを使うので、無ければ代わりを入れる
for name in ("cv2", "numpy"):
    if name not in sys.modules:
        try:
            __import__(name)
        except ImportError:
            sys.modules[name] = types.ModuleType(name)
spec = importlib.util.spec_from_file_location("ocr_pages", os.path.join(ROOT, "ocr", "ocr_pages.py"))
op = importlib.util.module_from_spec(spec)
spec.loader.exec_module(op)

L8 = list(range(0, 800, 100))      # 8本（歳入 7列）
L12 = list(range(0, 1200, 100))    # 12本（歳出 11列）
L10 = list(range(0, 1000, 100))    # 10本（長い表で線が途切れた）


def test_revenue_table_with_header_on_mixed_page():
    # 歳入と歳出の表が同じページ（R8 281299 p9）。歳入の見出し（財源の語なし）なら表ごとの8本
    assert op.choose_vlines(L8, L12, "節比較本年度前年度明目金額区分", None) == L8


def test_expense_table_with_broken_lines():
    # 歳出の表でも下端まで届かない線があると表ごとが8本（p45）。財源の見出しならページ共通の12本
    assert op.choose_vlines(L8, L12, "本年度の財源内訳節(細節)本年度前年度", None) == L12


def test_revenue_continuation_without_header():
    # 見出しのない続きの表で、直前の表が歳入（7列）なら表ごとの8本（p51）
    assert op.choose_vlines(L8, L12, None, 7) == L8
    # 直前が歳出なら、ページ共通に戻す
    assert op.choose_vlines(L8, L12, None, 11) == L12


def test_long_table_lines_broken():
    # 長い表は行の区切りで縦線が途切れ、表ごとだと本数が減る（281298 p131 で 12→10）→ ページ共通
    assert op.choose_vlines(L10, L12, None, 11) == L12


def test_not_a_table():
    assert op.choose_vlines([0, 100], [0, 100], None, None) is None


@pytest.mark.parametrize("tv, page, want", [(L12, L12, L12), (L12, [0, 100], L12)])
def test_expense_normal(tv, page, want):
    assert op.choose_vlines(tv, page, "財源", None) == want
