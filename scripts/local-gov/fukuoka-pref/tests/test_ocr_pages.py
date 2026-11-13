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


def test_continuation_same_count_prefers_page_lines():
    # R8 281298 p367 の実際の線。表ごとの線は節の欄の左端を細節の区切りの線（2180）と取り違えた。本数が同じならページ共通
    tv = [169, 441, 684, 926, 1190, 1418, 1643, 1907, 2180, 2515, 2759, 3329]
    page = [169, 441, 684, 926, 1190, 1418, 1643, 1907, 2153, 2515, 2759, 3329]
    assert op.choose_vlines(tv, page, None, 11) == page
    # 歳入の続き（直前が7列）や直前が分からない表は、本数が同じでも今までどおり表ごと（ページ共通の線が同じページの
    # 別の表の線のことがある）
    rev_tv, rev_page = [0, 100, 200, 300, 400, 500, 600, 700], [0, 120, 240, 360, 480, 600, 650, 700]
    assert op.choose_vlines(rev_tv, rev_page, None, 7) == rev_tv
    assert op.choose_vlines(tv, page, None, None) == tv


def test_union_only_when_each_misses_one_line():
    # 様式の違う表（R8 281299 p7 の総括の表の実際の線: 表ごと 9本・ページ共通 5本）は、足すと 12本になっても合わせない
    tv = [169, 831, 1211, 1594, 1976, 2297, 2621, 2942, 3331]
    page = [169, 1034, 1796, 2561, 3331]
    assert op.choose_vlines(tv, page, "本年度の財源内訳", None) == tv


def test_expense_header_in_simplified_chinese():
    # 旧 OCR（中国語モデル）は財源の見出しを簡体字で読む（R8 281298 p138 の実際の見出し）。歳出の表として 12本を選ぶ
    assert op.choose_vlines(L8, L12, "本年度の财源内節（細節）明比定财本年度前年度源目特一般财源金额分区地方价の他国支出金", None) == L12


def test_revenue_continuation_without_header():
    # 見出しのない続きの表で、直前の表が歳入（7列）なら表ごとの8本（p51）
    assert op.choose_vlines(L8, L12, None, 7) == L8
    # 直前が歳出なら、ページ共通に戻す
    assert op.choose_vlines(L8, L12, None, 11) == L12


def test_long_table_lines_broken():
    # 長い表は行の区切りで縦線が途切れ、表ごとだと本数が減る（281298 p131 で 12→10）→ ページ共通
    assert op.choose_vlines(L10, L12, None, 11) == L12


# R8 281298 p238 の上の表（財源の見出しあり）の実際の線。表ごとは左端の区分の線（439）、ページ共通は節の区分と
# 金額の間の線（2512）を取りこぼした。どちらか一方だと 10列になり「2扶助費30,999,209」が1つのセルにつながる
P238_TV = [165, 681, 922, 1188, 1414, 1640, 1903, 2149, 2512, 2757, 3329]
P238_PAGE = [165, 439, 679, 921, 1187, 1412, 1639, 1902, 2148, 2756, 3328]
P238_WANT = [165, 439, 679, 921, 1187, 1412, 1639, 1902, 2148, 2512, 2756, 3328]  # 近い線はページ共通の位置


def test_expense_header_lines_missing_in_both():
    assert op.choose_vlines(P238_TV, P238_PAGE, "本年度の財源内訳節(細節)本年度前年度", None) == P238_WANT
    # 合わせても 12本にならなければ今までどおり（本数の多い方。同じなら表ごと）
    page_without_439 = [165, 679, 921, 1187, 1412, 1639, 1902, 2148, 2756, 3328]
    assert op.choose_vlines(P238_TV, page_without_439, "財源", None) == P238_TV


def test_expense_continuation_lines_missing_in_both():
    # 見出しのない歳出の続きの表（直前が11列）でも合わせる
    assert op.choose_vlines(P238_TV, P238_PAGE, None, 11) == P238_WANT
    # 直前の列数が分からないときは合わせない（今までどおり表ごと。前のページの結果がないときは ocr_pages.py が
    # 未確定の印を付け、前のページの後に --redo-unknown で読み直す）
    assert op.choose_vlines(P238_TV, P238_PAGE, None, None) == P238_TV


def test_union_prefers_page_position_for_close_lines():
    # 合わせるとき、近い線はページ共通の位置を使う。表ごとの線は細節の区切りの線（p367 の 2180）を拾うことがある
    tv = [169, 441, 684, 926, 1190, 1418, 1643, 1907, 2180, 2515, 3329]          # 11本: 2759 を取りこぼし、2180 は取り違え
    page = [169, 684, 926, 1190, 1418, 1643, 1907, 2153, 2515, 2759, 3329]        # 11本: 441 を取りこぼし
    assert op.choose_vlines(tv, page, "財源", None) == [169, 441, 684, 926, 1190, 1418, 1643, 1907, 2153, 2515, 2759, 3329]


def test_not_a_table():
    assert op.choose_vlines([0, 100], [0, 100], None, None) is None


@pytest.mark.parametrize("tv, page, want", [(L12, L12, L12), (L12, [0, 100], L12)])
def test_expense_normal(tv, page, want):
    assert op.choose_vlines(tv, page, "財源", None) == want


def _page(tmp_path, page, tables):
    import json
    (tmp_path / f"p{page:04d}.json").write_text(json.dumps({"page": page, "tables": tables}), encoding="utf-8")


def test_previous_table_cols_from_previous_page(tmp_path):
    _page(tmp_path, 100, [{"cols": [[]] * 7}])
    assert op.previous_table_cols(str(tmp_path), 101) == (7, False)


def test_previous_table_cols_skips_page_without_tables(tmp_path):
    # 表のないページ（扉など）はとばしてさらに前を見る。未確定にはしない
    _page(tmp_path, 99, [{"cols": [[]] * 11}])
    _page(tmp_path, 100, [])
    assert op.previous_table_cols(str(tmp_path), 101) == (11, False)


def test_previous_table_cols_unknown_when_page_missing(tmp_path):
    # 直前のページの結果がまだない（並べて流した）。さらに前のページで代わりに判定するが、未確定とする
    _page(tmp_path, 99, [{"cols": [[]] * 7}])
    assert op.previous_table_cols(str(tmp_path), 101) == (7, True)
    assert op.previous_table_cols(str(tmp_path), 200) == (None, True)


def test_previous_table_cols_propagates_unknown(tmp_path):
    # 前のページの表そのものが未確定なら、それに頼った判定も未確定（後ろのページへ伝わる）
    _page(tmp_path, 100, [{"cols": [[]] * 7, "prev_cols_unknown": True}])
    assert op.previous_table_cols(str(tmp_path), 101) == (7, True)
