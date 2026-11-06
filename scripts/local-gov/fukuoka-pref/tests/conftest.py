"""福岡県データ抽出スクリプトのテストの共通部品。

スクリプトはパッケージではなく単体のファイルなので、パスから読み込む。
pdfplumber などの重い依存はテスト対象の関数では使わないが、import 時に必要なものはある（pdfplumber は入っている前提）。
"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(rel: str, name: str):
    path = os.path.join(ROOT, rel)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod
