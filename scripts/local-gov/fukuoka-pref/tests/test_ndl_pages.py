"""名前の欄を NDLOCR-Lite で読み直す（ocr/ndl_pages.py）の単体テスト。切り抜きの範囲と置き換え方（モデルは使わない）。"""
import numpy as np
import pytest

from conftest import load

nd = load("ocr/ndl_pages.py", "ndl_pages")


def box(text, x0, x1, y0=100, y1=140):
    return {"text": text, "x0": x0, "x1": x1, "y0": y0, "y1": y1, "score": 0.9}


class FakeNdl:
    """切り抜きの幅を返す（どの範囲を読んだかを確かめる）"""

    def __init__(self):
        self.crops = []

    def read(self, img):
        self.crops.append(img.shape[1])
        return "|読|"


class TestNameLines:
    def test_extends_about_one_char_and_stops_before_amount(self):
        # 説明欄: 名前の文字枠（x 2850〜3000）の両端から行の高さ×1.2 だけ広げ、同じ行の金額の左で止める
        col = [box("管理事務費", 2850, 3000), box("2,960,581", 3030, 3300)]
        [(row, (x0, y0, x1, y1))] = nd.name_lines(col, 2757, 3330)
        assert [d["text"] for d in row] == ["管理事務費"]
        assert x0 == int(2850 - 40 * nd.EXTEND) and x1 == 3030 - nd.INSET
        # 金額が離れていれば、右も字1個分まで
        [(_, (_, _, x1, _))] = nd.name_lines([box("管理事務費", 2850, 3000), box("1", 3250, 3300)], 2757, 3330)
        assert x1 == int(3000 + 40 * nd.EXTEND)
        # 欄の縦線より外へは広げない
        [(_, (x0, _, _, _))] = nd.name_lines([box("職員費", 2770, 2900)], 2757, 3330)
        assert x0 == 2757 + nd.INSET
        assert (y0, y1) == (100 - nd.PAD_Y, 140 + nd.PAD_Y)

    def test_full_width_for_setsu_labels_and_stays_inside_lines(self):
        # 節の区分の欄は欄の幅いっぱい（字間の広い細節の端の字）。罫線の内側から
        col = [box("耕翻訳料", 2300, 2480)]
        [(_, (x0, _, x1, _))] = nd.name_lines(col, 2149, 2511, full=True)
        assert (x0, x1) == (2149 + nd.INSET, 2511 - nd.INSET)

    def test_number_box_on_the_left_is_not_cropped(self):
        # 節番号・目の番号が名前と別の文字枠（「1」と「県民税」）なら、番号の右から切り抜く（番号は OCR の文字枠のまま残る。
        # 欄の幅いっぱいでも、番号まで読むと「1県民税」になって OCR の名前と一致しない）
        col = [box("1", 2160, 2180), box("県民税", 2300, 2420)]
        [(row, (x0, _, x1, _))] = nd.name_lines(col, 2149, 2511, full=True)
        assert [d["text"] for d in row] == ["県民税"] and x0 == 2180 + nd.INSET and x1 == 2511 - nd.INSET

    def test_amount_boxes_are_not_name_lines(self):
        col = [box("1,234", 3100, 3300), box("職員費", 2770, 2900, 200, 240)]
        lines = nd.name_lines(col, 2757, 3330)
        assert [[d["text"] for d in r] for r, _ in lines] == [["職員費"]]


class TestMergeNumbers:
    def test_numbers_come_from_ocr(self):
        # NDLOCR-Lite の頭の数字は外し、OCR の番号を使う（番号の印字のない目に数字が付かない）
        assert nd.merge_numbers("林業改善資金助成事業", "7林業改善資金助成事業") == "林業改善資金助成事業"
        assert nd.merge_numbers("1 報", "13報酬") == "1報酬"
        # 末尾の数字（右端の罫線の読み）も外す。OCR の行が数字で終わるとき（「人生100」）は残す
        assert nd.merge_numbers("林業改善資金", "林業改善資金1") == "林業改善資金"
        assert nd.merge_numbers("人生100", "人生100") == "人生100"
        # 金額の形の読み（2行目の1字「費」→「19」）は OCR の読みのまま
        assert nd.merge_numbers("費", "19") == "費"
        assert nd.merge_numbers("管理事務費", "") == "管理事務費"


class TestReplaceNames:
    def test_replaces_name_boxes_keeps_amounts_and_left_edge(self):
        # 切り抜きの前処理（squeeze_gaps）が opencv を使う。PYLIB なしの環境では飛ばす
        pytest.importorskip("cv2")
        # 歳入の表（7列）: 0 目 / 4 節の区分 / 6 説明 が名前の欄。金額の文字枠と左端（字下げで細節を見分ける）は変えない
        vlines = [0, 300, 500, 700, 900, 1300, 1500, 2000]
        cols = [[box("1 県民税", 20, 200)], [box("100", 310, 490)], [], [], [box("現年", 950, 1000), box("課税分", 1010, 1100)],
                [box("100", 1310, 1490)], [box("○個人", 1550, 1700), box("100", 1800, 1990)]]
        rec = {"vlines": vlines, "tables": [{"cols": cols}]}
        img = np.zeros((300, 2100, 3), dtype=np.uint8)
        fake = FakeNdl()
        n = nd.replace_names(rec, img, fake)
        t = rec["tables"][0]["cols"]
        assert n == 3
        # 罫線の読み「|」は名前の両端から外す
        assert [d["text"] for d in t[0]] == ["1読"] and t[0][0]["ndl"]  # 目の番号は OCR の「1」
        assert [(d["text"], d["x0"]) for d in t[4]] == [("読", 950)]
        assert [d["text"] for d in t[6]] == ["読", "100"]  # 名前と金額（位置の順）
        assert [d["text"] for d in t[1]] == ["100"]  # 名前の欄でない列はそのまま
        assert rec["source"] == "ndl"

    def test_total_rows_are_kept(self):
        # 目の欄の「計」の行は置き換えない（NDLOCR-Lite が「10」と読むと、解釈が計の行を見分けられず架空の目になる）
        pytest.importorskip("cv2")
        vlines = [0, 300, 500, 700, 900, 1300, 1500, 2000]
        cols = [[box("計", 20, 60)], [box("100", 310, 490)], [], [], [], [], []]
        rec = {"vlines": vlines, "tables": [{"cols": cols}]}
        assert nd.replace_names(rec, np.zeros((300, 2100, 3), dtype=np.uint8), FakeNdl()) == 0
        assert [d["text"] for d in rec["tables"][0]["cols"][0]] == ["計"]
