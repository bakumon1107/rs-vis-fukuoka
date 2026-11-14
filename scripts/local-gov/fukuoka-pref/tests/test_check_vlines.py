"""縦線の切り方の比べ方（ocr/check_vlines.py の --same-as）の単体テスト。cv2 を使わない部分だけを試す。"""
import json

from conftest import load

cv = load("ocr/check_vlines.py", "check_vlines")


def _page(d, page, rec):
    d.mkdir(exist_ok=True)
    (d / f"p{page:04d}.json").write_text(json.dumps(rec), encoding="utf-8")


def test_old_format_table_uses_page_vlines(tmp_path, capsys):
    # 表ごとの線を持たない古い形式は、ページ共通の線で切られていた。同じ線の新しい形式とは「同じ」と判定し、止まらない
    a, b = tmp_path / "a", tmp_path / "b"
    _page(a, 1, {"vlines": [1, 2, 3], "tables": [{"box": [0, 0, 9, 9]}]})
    _page(b, 1, {"vlines": [9], "tables": [{"box": [0, 0, 9, 9], "vlines": [1, 2, 3]}]})
    _page(a, 2, {"vlines": [1, 2, 3], "tables": [{"box": [0, 0, 9, 9]}]})
    _page(b, 2, {"vlines": [1, 2, 3], "tables": [{"box": [0, 0, 9, 9], "vlines": [1, 2, 4]}]})
    cv.same_as(str(a), str(b), "1-2")
    assert "differs: [2]" in capsys.readouterr().out
    assert cv.table_vlines({"vlines": []}, {"vlines": [5]}) == [5]
