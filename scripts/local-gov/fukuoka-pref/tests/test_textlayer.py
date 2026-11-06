"""発行元の文字層の書き出し（ocr/textlayer_pages.py）の単体テスト。"""
from conftest import load

tl = load("ocr/textlayer_pages.py", "textlayer_pages")


def w(text, x0, x1, y0):
    return {"text": text, "x0": x0, "x1": x1, "y0": y0, "y1": y0 + 30}


def test_calibrate_shifts_numbers_only():
    # 文字層は画像に対して右に約 14px ずれている（R8 281298 p239 の「452」: OCR 右端 1907・文字層 1921）。
    # 数字だけを戻し、名前は動かさない（名前まで動かすと細節がすべて節と判定された実例）
    # ずれは4文字以上の数字（3組以上）で測る
    rec = {"tables": [{"cols": [[w("103,009", 520, 680, 1937), w("34,763", 2010, 2145, 1937), w("67,793", 1250, 1400, 1937),
                                 w("452", 1834, 1907, 2076)]]}]}
    words = [w("103,009", 534, 694, 1937), w("34,763", 2024, 2159, 1937), w("67,793", 1264, 1414, 1937),
             w("452", 1848, 1921, 2076),
             w("1", 1885, 1925, 1985), w("諸収入", 1660, 1764, 2036)]
    dx, dy = tl.calibrate(words, rec)
    assert dx == 14 and dy == 0
    one = next(x for x in words if x["text"] == "1")
    assert (one["x0"] + one["x1"]) / 2 < 1904   # 「その他」の列（境目の縦線 1904 の左）に戻る
    name = next(x for x in words if x["text"] == "諸収入")
    assert name["x0"] == 1660


def test_calibrate_needs_enough_matches():
    rec = {"tables": [{"cols": [[w("1,234", 100, 200, 10)]]}]}
    words = [w("1,234", 114, 214, 10)]
    assert tl.calibrate(words, rec) == (0.0, 0.0)
