"""福岡県データの抽出・検算を手元の原本で全部流し、要約（件数・一致数・FAIL の数・総額）を期待値と比べる回帰テスト。

原本（PDF）と OCR 結果はリポジトリに入れないので、置き場所を環境変数で渡す。ない環境ではテストを飛ばす。

    FUKUOKA_DATA=<dir> python3 -P scripts/local-gov/fukuoka-pref/tests/regression.py          # 比べる
    FUKUOKA_DATA=<dir> python3 -P scripts/local-gov/fukuoka-pref/tests/regression.py --update # 期待値を書き換える
    FUKUOKA_DATA=<dir> python3 -P -m pytest scripts/local-gov/fukuoka-pref/tests                # pytest からも流れる

<dir> の中身: pdf/<ファイル名>.pdf（県サイトのファイル名のまま）、ocr/<名前>/p0001.json …（ocr_pages.py の出力）。
  ocr/r8-ippan     … R8 一般会計。PP-OCRv6（OCR_ENGINE=v6）＋ refill_missing.py の読み直し済み
  ocr/r8-ippan-v4  … R8 一般会計。中国語モデル（OCR_ENGINE=v4ch）。突き合わせの3つ目の読み取り
  ocr/r8-toku      … R8 特別会計
OCR 自体は時間がかかる（1ページ約10秒）ので回帰テストでは流さず、保存した OCR 結果を入力にする。
期待値（expected/regression.json）は「各ステップの要約行」。ロジックを直して数字が変わったら、
差分を確かめてから --update で書き換え、コミットの説明に理由を書く（良くなったのか、悪くなったのか）。
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXPECTED = os.path.join(HERE, "expected", "regression.json")

# (名前, スクリプト, 引数, 出力ファイル, 要約として比べる stderr の行の正規表現)
# 引数の {pdf:X} は <dir>/pdf/X.pdf、{ocr:X} は <dir>/ocr/X、{out:X} は前のステップの出力ファイル
STEPS = [
    ("決算 款項目別明細表", "extract_kessan_kmk.py", ["{pdf:272595}"], "kessan-kmk.json", [r"^件数", r"^合計行", r"FAIL="]),
    ("決算 部局別", "extract_kessan_bukyoku.py", ["{pdf:272595}", "{out:kessan-kmk.json}"], "kessan-bukyoku.json",
     [r"FAIL=", r"^部局 \d+"]),
    ("決算 節", "extract_kessan_setsu.py", ["{pdf:272615}", "{out:kessan-kmk.json}"], "kessan-setsu.json", [r"^節", r"FAIL="]),
    # 引数の順: 歳入（277210）・歳出（277211）・特別会計（277212）・総括（277209）・決算の款項目（款名の照合）
    ("計上額調", "extract_keijougaku.py", ["{pdf:277210}", "{pdf:277211}", "{pdf:277212}", "{pdf:277209}",
                                         "{out:kessan-kmk.json}"], "keijougaku.json", [r"FAIL=", r"^総括", r"^(歳入|歳出|特別会計): \d+ 行"]),
    ("予算書の本体", "extract_yosansho.py", ["{pdf:281297}"], "yosansho.json", [r"総額|公営企業", r"FAIL="]),
    ("公営企業 予算実施計画", "extract_kigyo_jisshi.py", ["{pdf:281299}", "{out:yosansho.json}"], "kigyo.json", [r"目 \d+ 件", r"FAIL="]),
    ("施策別資料", "extract_shisaku.py", ["{pdf:277213}", "{pdf:277214}", "{pdf:278133}", "{pdf:277217}", "{pdf:277218}",
                                        "{pdf:277220}"], "shisaku.json", [r"^事項 \d+ 件"]),
    ("主要施策の成果（試作）", "extract_seika.py", ["{pdf:272597}"], "seika.json", [r"^施策 \d+ 件"]),
    ("説明書 一般会計（OCR）", "ocr/parse_setsumeisho.py",
     ["{ocr:r8-ippan}", "9-420", "--keijou", "{out:keijougaku.json}", "--yosansho", "{out:yosansho.json}",
      "--corrections", os.path.join(ROOT, "ocr", "corrections", "r8-ippan.json")], "setsumeisho-ocr.json",
     [r"^\[", r"^計の行", r"^項 \d", r"^(OK|NG)  ", r"^修正表"]),
    ("説明書 一般会計（文字層）", "ocr/textlayer_pages.py", ["{pdf:281298}", "{ocr:r8-ippan}", "{tmp:tl}", "9-420"], None, []),
    ("説明書 一般会計（文字層の解釈）", "ocr/parse_setsumeisho.py",
     ["{tmp:tl}", "9-420", "--keijou", "{out:keijougaku.json}", "--yosansho", "{out:yosansho.json}"], "setsumeisho-tl.json",
     [r"^\[", r"^計の行", r"^項 \d"]),
    # 3つ目の読み取り（旧 OCR = 中国語モデル）。突き合わせで「2つの OCR が同じ値を読んだ箇所」を固定するのに使う
    ("説明書 一般会計（旧 OCR の解釈）", "ocr/parse_setsumeisho.py",
     ["{ocr:r8-ippan-v4}", "9-420", "--keijou", "{out:keijougaku.json}", "--yosansho", "{out:yosansho.json}"],
     "setsumeisho-v4.json", [r"^\[", r"^計の行", r"^項 \d"]),
    ("説明書 一般会計（突き合わせ）", "ocr/cross_check.py",
     ["{out:setsumeisho-ocr.json}", "{out:setsumeisho-tl.json}", "--third", "{out:setsumeisho-v4.json}",
      "--yosansho", "{out:yosansho.json}"], "cross.json",
     [r"^全検算", r"^検算の通らない", r"^救済", r"^残り", r"^差し替え後", r"^全体"]),
    ("説明書 一般会計（多数決）", "ocr/vote.py",
     ["{out:cross.json}", "{out:setsumeisho-ocr.json}", "{out:setsumeisho-v4.json}", "{out:setsumeisho-tl.json}"], "vote.json",
     [r"^全検算", r"^  \d 通り"]),
    ("説明書 特別会計（OCR）", "ocr/parse_setsumeisho.py",
     ["{ocr:r8-toku}", "1-128", "--keijou", "{out:keijougaku.json}", "--tokubetsu", "--yosansho", "{out:yosansho.json}"],
     "setsumeisho-toku.json", [r"^\[", r"^計の行", r"^項 \d", r"^(OK|NG)  "]),
]


def resolve(arg, data, outdir, tmpdir):
    def rep(m):
        kind, name = m.group(1), m.group(2)
        if kind == "pdf":
            return os.path.join(data, "pdf", name + ".pdf")
        if kind == "ocr":
            return os.path.join(data, "ocr", name)
        if kind == "out":
            return os.path.join(outdir, name)
        return os.path.join(tmpdir, name)
    return re.sub(r"\{(pdf|ocr|out|tmp):([^}]+)\}", rep, arg)


def run_all(data):
    results = {}
    with tempfile.TemporaryDirectory() as outdir, tempfile.TemporaryDirectory() as tmpdir:
        for name, script, args, out, pats in STEPS:
            argv = [resolve(a, data, outdir, tmpdir) for a in args]
            missing = [a for a in argv if (a.startswith(data)) and not os.path.exists(a)]
            if missing:
                results[name] = {"skipped": f"入力がない: {', '.join(os.path.relpath(m, data) for m in missing)}"}
                continue
            env = dict(os.environ)
            p = subprocess.run([sys.executable, "-P", os.path.join(ROOT, script), *argv], capture_output=True, text=True,
                               env=env)
            if out:
                with open(os.path.join(outdir, out), "w", encoding="utf-8") as f:
                    f.write(p.stdout)
            lines = [ln for ln in p.stderr.splitlines() if any(re.search(pt, ln) for pt in pats)]
            results[name] = {"exit": p.returncode, "summary": lines}
            print(f"[{name}] exit={p.returncode} 要約 {len(lines)} 行", file=sys.stderr)
    return results


def compare(got, want):
    diffs = []
    for name, w in want.items():
        g = got.get(name)
        if g is None or "skipped" in g:
            continue
        if g.get("exit") != w.get("exit"):
            diffs.append(f"[{name}] 終了コード {w.get('exit')} → {g.get('exit')}")
        gs, ws = g.get("summary", []), w.get("summary", [])
        for line in ws:
            if line not in gs:
                diffs.append(f"[{name}] 消えた行: {line}")
        for line in gs:
            if line not in ws:
                diffs.append(f"[{name}] 増えた行: {line}")
    return diffs


def main():
    data = os.environ.get("FUKUOKA_DATA")
    if not data:
        sys.exit("FUKUOKA_DATA に原本と OCR 結果の置き場所を指定する")
    got = run_all(data)
    if "--update" in sys.argv:
        os.makedirs(os.path.dirname(EXPECTED), exist_ok=True)
        with open(EXPECTED, "w", encoding="utf-8") as f:
            json.dump(got, f, ensure_ascii=False, indent=1)
        print(f"期待値を書き換えた: {EXPECTED}", file=sys.stderr)
        return
    want = json.load(open(EXPECTED, encoding="utf-8"))
    diffs = compare(got, want)
    skipped = [n for n, g in got.items() if "skipped" in g]
    for d in diffs:
        print(d)
    print(f"回帰テスト: {len(want)} ステップ、差分 {len(diffs)} 件、飛ばした {len(skipped)} 件", file=sys.stderr)
    sys.exit(1 if diffs else 0)


if __name__ == "__main__":
    main()
