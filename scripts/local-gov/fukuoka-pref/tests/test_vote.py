"""読み取りの一致の数え方（ocr/vote.py）の単体テスト。"""
from conftest import load

vote = load("ocr/vote.py", "vote")


def moku(**kw):
    m = {"kind": "目", "side": "歳出", "款": 2, "項": [1, "総務管理費"], "目番号": 1, "本年度": 100, "前年度": 90, "比較": 10,
         "財源": {"国庫支出金": 0, "地方債": 0, "その他": 30, "一般財源": 70},
         "節": [{"no": 1, "amount": 60, "top": True}, {"no": 2, "amount": 40, "top": True}],
         "説明": [{"name": "○管理事務費", "amount": 100}]}
    m.update(kw)
    return m


def test_corrected_values_are_not_counted_as_readings():
    # OCR の読み取りの結果には修正表（画像で確認した値）が当たっている。その値は「OCR が読んだ値」に数えない
    m = moku(修正=[{"列": "前年度", "値": 90}, {"列": "財源", "区分": "その他", "値": 30}, {"列": "節", "節番号": 2, "値": 40}])
    r = vote.reading_values(m)
    assert "前年度" not in r and "財源 その他" not in r and "節 40#1" not in r
    # 直していない値はそのまま数える
    assert r["本年度"] == 100 and r["節 60#1"] == 60 and r["財源 一般財源"] == 70


def test_without_corrections_same_as_values():
    m = moku()
    assert vote.reading_values(m) == vote.values(m)
