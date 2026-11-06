"""回帰テスト（regression.py）を pytest から流す。原本の置き場所 FUKUOKA_DATA がなければ飛ばす。"""
import json
import os

import pytest

from conftest import load

reg = load("tests/regression.py", "regression")


@pytest.mark.skipif(not os.environ.get("FUKUOKA_DATA"), reason="FUKUOKA_DATA（原本と OCR 結果の置き場所）が未指定")
def test_regression():
    got = reg.run_all(os.environ["FUKUOKA_DATA"])
    want = json.load(open(reg.EXPECTED, encoding="utf-8"))
    assert reg.compare(got, want) == []
