"""回帰テスト（regression.py）を pytest から流す。原本の置き場所 FUKUOKA_DATA がなければ飛ばす。"""
import json
import os

import pytest

from conftest import load

reg = load("tests/regression.py", "regression")


def test_keep_dir_stale_outputs_are_not_reused(tmp_path):
    # --keep のディレクトリに前の結果が残っていても、今回飛ばしたステップの古い出力を後のステップが読まない
    data, keep = tmp_path / "data", tmp_path / "keep"
    data.mkdir()
    keep.mkdir()
    (keep / "kessan-kmk.json").write_text("{}", encoding="utf-8")   # 前に流したときの出力
    got = reg.run_all(str(data), str(keep))
    assert not (keep / "kessan-kmk.json").exists()
    # 原本がないので最初のステップが飛び、その出力を読む後のステップも飛ぶ
    assert "skipped" in got["決算 款項目別明細表"] and "skipped" in got["決算 部局別"]
    # 書き出しは引数に出てこない入力（前のステップの出力・資料の PDF）が欠けても飛ばす
    assert "skipped" in got["共通 JSON 形式の書き出し"]


def test_export_deps_cover_work_files_and_sources():
    deps = reg.STEP_DEPS["共通 JSON 形式の書き出し"]
    assert "{out:cross.json}" in deps and "{out:yosansho.json}" in deps
    assert "{pdf:281298}" in deps and "{pdf:272615}" in deps


@pytest.mark.skipif(not os.environ.get("FUKUOKA_DATA"), reason="FUKUOKA_DATA（原本と OCR 結果の置き場所）が未指定")
def test_regression():
    got = reg.run_all(os.environ["FUKUOKA_DATA"])
    want = json.load(open(reg.EXPECTED, encoding="utf-8"))
    assert reg.compare(got, want) == []
