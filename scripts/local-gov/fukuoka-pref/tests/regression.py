"""福岡県データの抽出・検算を手元の原本で全部流し、要約（件数・一致数・FAIL の数・総額）を期待値と比べる回帰テスト。

原本（PDF）と OCR 結果はリポジトリに入れないので、置き場所を環境変数で渡す。ない環境ではテストを飛ばす。

    FUKUOKA_DATA=<dir> python3 -P scripts/local-gov/fukuoka-pref/tests/regression.py          # 比べる
    FUKUOKA_DATA=<dir> python3 -P scripts/local-gov/fukuoka-pref/tests/regression.py --update # 期待値を書き換える
    … --keep <作業ディレクトリ>  各ステップの出力を残す（共通 JSON 形式の書き出し export_fukuoka_pref.py --work の入力）
    FUKUOKA_DATA=<dir> python3 -P -m pytest scripts/local-gov/fukuoka-pref/tests                # pytest からも流れる

<dir> の中身: pdf/<ファイル名>.pdf（県サイトのファイル名のまま）、ocr/<名前>/p0001.json …（ocr_pages.py の出力）。
  ocr/r8-ippan     … R8 一般会計。PP-OCRv6（OCR_ENGINE=v6）＋ refill_missing.py の読み直し済み
  ocr/r8-ippan-v4  … R8 一般会計。中国語モデル（OCR_ENGINE=v4ch）。突き合わせの3つ目の読み取り
  ocr/r8-toku      … R8 特別会計。PP-OCRv6 ＋ 読み直し済み
  ocr/r8-toku-v4   … R8 特別会計。中国語モデル（突き合わせの3つ目の読み取り）
  ocr/r8-ippan-ndl・ocr/r8-toku-ndl … 名前の欄を NDLOCR-Lite で読み直したもの（名前の3つ目の系統。ocr/ndl_pages.py）
OCR 自体は時間がかかる（1ページ約10秒）ので回帰テストでは流さず、保存した OCR 結果を入力にする。
名前の3つ目の系統（NDLOCR-Lite。ocr/ndl_pages.py で読み直した ocr/r8-ippan-ndl・ocr/r8-toku-ndl）も OCR と同じく保存した結果を入力にする
（1ページ約3秒なので回帰テストでは流さない）。ない環境では NDLOCR-Lite の解釈と書き出し・補正の照合を飛ばす。
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
# 基金の抽出（extract_funds.py）の入力: 年度 → 財産に関する調書（テキストの年度は PDF、画像の年度は OCR の結果）。
# 引数は「年度=パス」の形でパスの頭が原本の置き場所にならないので、入力の有無は STEP_DEPS で確かめる
# 「~」の年度は補助の年度（次の年度の調書にない基金だけを使う。H24・R3 は OCR の質が低く、ほかの基金は次の年度の前年度末で足りる）
FUNDS_INPUTS = [("H23", "{pdf:800079_62749591}"), ("~H24", "{ocr:funds-h24}"), ("H25", "{pdf:800079_62749605}"),
                ("H27", "{ocr:funds-h27}"), ("H28", "{ocr:funds-h28}"), ("H29", "{ocr:funds-h29}"), ("H30", "{pdf:60772}"),
                ("R2", "{pdf:151877}"), ("~R3", "{ocr:funds-r3}"), ("R4", "{ocr:funds-r4}"), ("R5", "{pdf:238290}"), ("R6", "{pdf:272596}")]
# 引数の {pdf:X} は <dir>/pdf/X.pdf、{ocr:X} は <dir>/ocr/X、{out:X} は前のステップの出力ファイル
STEPS = [
    ("決算 款項目別明細表", "extract_kessan_kmk.py", ["{pdf:272595}"], "kessan-kmk.json", [r"^件数", r"^合計行", r"FAIL="]),
    ("決算 部局別", "extract_kessan_bukyoku.py", ["{pdf:272595}", "{out:kessan-kmk.json}"], "kessan-bukyoku.json",
     [r"FAIL=", r"^部局 \d+"]),
    ("決算 特別会計", "extract_kessan_toku.py", ["{pdf:272595}"], "kessan-toku.json", [r"^会計 \d+", r"^WARN", r"FAIL="]),
    ("決算 節", "extract_kessan_setsu.py", ["{pdf:272615}", "{out:kessan-kmk.json}", "--toku", "{out:kessan-toku.json}"],
     "kessan-setsu.json", [r"^節", r"FAIL="]),
    # 引数の順: 歳入（277210）・歳出（277211）・特別会計（277212）・総括（277209）・決算の款項目（款名の照合）
    ("計上額調", "extract_keijougaku.py", ["{pdf:277210}", "{pdf:277211}", "{pdf:277212}", "{pdf:277209}",
                                         "{out:kessan-kmk.json}"], "keijougaku.json", [r"FAIL=", r"^総括", r"^(歳入|歳出|特別会計): \d+ 行"]),
    ("予算書の本体", "extract_yosansho.py", ["{pdf:281297}"], "yosansho.json", [r"総額|公営企業", r"FAIL="]),
    ("公営企業 予算実施計画", "extract_kigyo_jisshi.py", ["{pdf:281299}", "{out:yosansho.json}"], "kigyo.json", [r"目 \d+ 件", r"FAIL="]),
    ("施策別資料", "extract_shisaku.py", ["{pdf:277213}", "{pdf:277214}", "{pdf:278133}", "{pdf:277217}", "{pdf:277218}",
                                        "{pdf:277220}"], "shisaku.json", [r"^事項 \d+ 件"]),
    ("主要施策の成果（試作）", "extract_seika.py", ["{pdf:272597}"], "seika.json", [r"^施策 \d+ 件"]),
    # 基金の現在高（財産に関する調書。画像の年度は ocr/ocr_lines.py の結果。地方版の基金の設計）
    ("基金（財産に関する調書）", "extract_funds.py", [f"{y}={src}" for y, src in FUNDS_INPUTS], "funds.json",
     [r"^[HR]\d+: 基金", r"OCR の読みを検算で直した|名前を寄せた|補助の年度", r"^[HR]\d+→", r"^FAIL"]),
    ("説明書 一般会計（OCR）", "ocr/parse_setsumeisho.py",
     ["{ocr:r8-ippan}", "9-420", "--keijou", "{out:keijougaku.json}", "--yosansho", "{out:yosansho.json}",
      "--corrections", os.path.join(ROOT, "ocr", "corrections", "r8-ippan.json")], "setsumeisho-ocr.json",
     [r"^\[", r"^計の行", r"^項 \d", r"^(OK|NG)  ", r"^修正表"]),
    ("説明書 一般会計（文字層）", "ocr/textlayer_pages.py", ["{pdf:281298}", "{ocr:r8-ippan}", "{tmp:tl}", "9-420"], None, []),
    ("説明書 一般会計（文字層の解釈）", "ocr/parse_setsumeisho.py",
     ["{tmp:tl}", "9-420", "--keijou", "{out:keijougaku.json}", "--yosansho", "{out:yosansho.json}"], "setsumeisho-tl.json",
     [r"^\[", r"^計の行", r"^項 \d"]),
    # 名前の3つ目の系統（NDLOCR-Lite で名前の欄だけを読み直した保存済みの結果 ocr/r8-ippan-ndl。金額は OCR のまま）。書き出しで名前の候補に足す
    ("説明書 一般会計（NDLOCR-Lite の解釈）", "ocr/parse_setsumeisho.py",
     ["{ocr:r8-ippan-ndl}", "9-420", "--keijou", "{out:keijougaku.json}", "--yosansho", "{out:yosansho.json}"],
     "setsumeisho-ndl.json", [r"^\[", r"^計の行", r"^項 \d"]),
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
     ["{ocr:r8-toku}", "1-128", "--keijou", "{out:keijougaku.json}", "--tokubetsu", "--yosansho", "{out:yosansho.json}",
      "--corrections", os.path.join(ROOT, "ocr", "corrections", "r8-toku.json")],
     "setsumeisho-toku.json", [r"^\[", r"^計の行", r"^項 \d", r"^(OK|NG)  ", r"^修正表"]),
    ("説明書 特別会計（文字層）", "ocr/textlayer_pages.py", ["{pdf:281299}", "{ocr:r8-toku}", "{tmp:tl-toku}", "1-128"], None, []),
    ("説明書 特別会計（文字層の解釈）", "ocr/parse_setsumeisho.py",
     ["{tmp:tl-toku}", "1-128", "--keijou", "{out:keijougaku.json}", "--tokubetsu", "--yosansho", "{out:yosansho.json}"],
     "setsumeisho-toku-tl.json", [r"^\[", r"^計の行", r"^項 \d"]),
    ("説明書 特別会計（NDLOCR-Lite の解釈）", "ocr/parse_setsumeisho.py",
     ["{ocr:r8-toku-ndl}", "1-128", "--keijou", "{out:keijougaku.json}", "--tokubetsu", "--yosansho", "{out:yosansho.json}"],
     "setsumeisho-toku-ndl.json", [r"^\[", r"^計の行", r"^項 \d"]),
    ("説明書 特別会計（旧 OCR の解釈）", "ocr/parse_setsumeisho.py",
     ["{ocr:r8-toku-v4}", "1-128", "--keijou", "{out:keijougaku.json}", "--tokubetsu", "--yosansho", "{out:yosansho.json}"],
     "setsumeisho-toku-v4.json", [r"^\[", r"^計の行", r"^項 \d"]),
    ("説明書 特別会計（突き合わせ）", "ocr/cross_check.py",
     ["{out:setsumeisho-toku.json}", "{out:setsumeisho-toku-tl.json}", "--third", "{out:setsumeisho-toku-v4.json}",
      "--yosansho", "{out:yosansho.json}"], "cross-toku.json",
     [r"^全検算", r"^検算の通らない", r"^救済", r"^残り", r"^差し替え後", r"^全体"]),
    ("説明書 特別会計（多数決）", "ocr/vote.py",
     ["{out:cross-toku.json}", "{out:setsumeisho-toku.json}", "{out:setsumeisho-toku-v4.json}", "{out:setsumeisho-toku-tl.json}"],
     "vote-toku.json", [r"^全検算", r"^  \d 通り"]),
    # R8 補正予算（R8 補正予算の抽出の設計）。テキストの3回は ocr_pages の表の線（ocr/r8-hosei-<回>）＋テキストの単語、
    # 画像の9月第3号は OCR（ocr/r8-hosei-09-3）＋文字層の △ で読む。議案・総括（hosei-<回>.json）と目の明細（setsumeisho-hosei-<回>.json）
    *[step for rid, pdf, gian, pages, kind in (("R8-06-1", "289925", "289924", "1-21", "定例"),
                                               ("R8-08-2", "298206", None, "1-14", "専決"),
                                               ("R8-09-4", "298207", "298208", "1-13", "追加提案"))
      for step in (
          (f"補正 {rid}（文字層）", "ocr/textlayer_pages.py",
           [f"{{pdf:{pdf}}}", f"{{ocr:r8-hosei-{rid[3:].lower()}}}", f"{{tmp:tl-{rid}}}", pages], None, []),
          (f"補正 {rid}（目の明細）", "ocr/parse_setsumeisho.py", [f"{{tmp:tl-{rid}}}", pages, "--hosei"],
           f"setsumeisho-hosei-{rid}.json", [r"^\[", r"^計の行"]),
          (f"補正 {rid}（議案・総括）", "extract_hosei.py",
           ["--id", rid, "--kind", kind, *(["--gian", f"{{pdf:{gian}}}"] if gian else []), "--setsumeisho", f"{{pdf:{pdf}}}"],
           f"hosei-{rid}.json", [rf"^{rid}:", r"FAIL="]))],
    ("補正 R8-09-3（△）", "ocr/mark_negatives.py", ["{pdf:298930}", "{ocr:r8-hosei-09-3}", "{tmp:neg-09-3}", "1-44"], None,
     [r"^△ を付けた"]),
    ("補正 R8-09-3（目の明細）", "ocr/parse_setsumeisho.py", ["{tmp:neg-09-3}", "1-44", "--hosei"],
     "setsumeisho-hosei-R8-09-3.json", [r"^\[", r"^計の行"]),
    ("補正 R8-09-3（議案）", "extract_hosei.py",
     ["--id", "R8-09-3", "--kind", "定例", "--gian-scan", "{pdf:298929}", "--prev", "{out:hosei-R8-08-2.json}"],
     "hosei-R8-09-3.json", [r"^R8-09-3:", r"FAIL="]),
    # 共通 JSON 形式（正規化データ）への書き出し。上のステップの出力（{out:...}）を読む
    ("共通 JSON 形式の書き出し", "export_fukuoka_pref.py",
     ["--work", "{outdir}", "--pdf-dir", "{pdfdir}", "--out", "{tmp:export}"], None,
     [r"^目 \d+", r"^一般会計 歳入", r"^名前の出典", r"^一般財源の中身", r"^補正 R8", r"^FAIL 補正"]),
    # 補正の回の鎖（書き出した当初予算から回の順に補正額を足し、各回の補正前の額と款・項で照合）
    ("補正 回の鎖", "check_hosei_chain.py",
     ["{tmp:export}/budget-2026-initial.json", "{out:hosei-R8-06-1.json}", "{out:hosei-R8-08-2.json}",
      "{out:hosei-R8-09-3.json}", "{out:hosei-R8-09-4.json}"], None, [r"^R8-", r"FAIL="]),
    # 書き出した補正のデータの照合（目の補正前 = 当初＋それまでの補正、項 = 議案、款の財源 = 総括）
    ("補正 書き出しの照合", "verify_hosei.py",
     ["{tmp:export}/budget-2026-initial.json", "{outdir}", "{tmp:export}"], None, [r"^照合した数", r"^FAIL"]),
]


def _export_deps():
    """書き出し（export_fukuoka_pref.py）が読む入力: 前のステップの出力と、sources.json の資料の PDF（SHA256 を確かめる）。
    引数は --work <dir> だけなので、ここで並べる（どれかが欠けたら、書き出しのステップを飛ばす）"""
    # 決算の書き出し（export_settlement.build）が読む kessan-bukyoku・kessan-toku・kessan-setsu も入れる
    outs = ["kessan-kmk.json", "kessan-bukyoku.json", "kessan-toku.json", "kessan-setsu.json",
            "keijougaku.json", "yosansho.json", "cross.json", "cross-toku.json",
            "setsumeisho-ocr.json", "setsumeisho-v4.json", "setsumeisho-tl.json", "setsumeisho-ndl.json",
            "setsumeisho-toku.json", "setsumeisho-toku-v4.json", "setsumeisho-toku-tl.json", "setsumeisho-toku-ndl.json"]
    # 基金の抽出の出力（funds.json）は入れない: 基金のステップが飛ばされても（OCR の結果のない環境）、書き出しの回帰は流す。
    # funds.json がなければ export_funds.build が基金を書かず、期待値の要約（「基金 N 件」の行）の差で気づける
    with open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
        pdfs = [s["file"] for s in json.load(f)["sources"]]
    return [f"{{out:{o}}}" for o in outs] + [f"{{pdf:{p}}}" for p in pdfs]


# ステップの、引数に出てこない入力（{out:...}・{pdf:...}・{tmp:...} の形）。
# 補正の目の明細は前のステップ（文字層・△）が作る一時ディレクトリを読むので、前のステップが飛ばされたら飛ばす
# （ないまま解釈すると空の読み取りを終了コード 0 で出す）。補正の照合は書き出しの出力（{tmp:export}）を読むので、
# 書き出しが飛ばされたら飛ばす（NDLOCR-Lite の結果がない環境など）
STEP_DEPS = {"共通 JSON 形式の書き出し": _export_deps(),
             "基金（財産に関する調書）": [src for _, src in FUNDS_INPUTS],
             **{f"補正 {rid}（目の明細）": [f"{{tmp:tl-{rid}}}"] for rid in ("R8-06-1", "R8-08-2", "R8-09-4")},
             "補正 R8-09-3（目の明細）": ["{tmp:neg-09-3}"],
             "補正 回の鎖": ["{tmp:export}/budget-2026-initial.json"],
             "補正 書き出しの照合": ["{tmp:export}/budget-2026-initial.json"]}


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
    arg = arg.replace("{outdir}", outdir).replace("{pdfdir}", os.path.join(data, "pdf"))
    return re.sub(r"\{(pdf|ocr|out|tmp):([^}]+)\}", rep, arg)


def run_all(data, keep=None):
    """全ステップを流す。keep を渡すと、各ステップの出力（JSON）をそのディレクトリに残す（export_fukuoka_pref.py の入力になる）。"""
    results = {}
    with tempfile.TemporaryDirectory() as tmp_out, tempfile.TemporaryDirectory() as tmpdir:
        outdir = keep or tmp_out
        os.makedirs(outdir, exist_ok=True)
        # --keep のディレクトリには前に流した結果が残っている。消しておかないと、今回飛ばしたステップの古い出力を
        # 後のステップが読んでしまう（「前のステップの出力がなければ後のステップも飛ばす」が効かなくなる）
        for _, _, _, out, _ in STEPS:
            if out and os.path.exists(os.path.join(outdir, out)):
                os.remove(os.path.join(outdir, out))
        for name, script, args, out, pats in STEPS:
            argv = [resolve(a, data, outdir, tmpdir) for a in args]
            # 入力がない（原本がない・前のステップの出力ができていない）ステップは飛ばす。
            # 前のステップが飛ばされると出力ファイルができないので、それを入力にする後のステップも飛ぶ
            # 引数に出てこない入力（書き出しが読む前のステップの出力・資料の PDF）は STEP_DEPS で足して確かめる
            deps = [resolve(a, data, outdir, tmpdir) for a in STEP_DEPS.get(name, [])]
            # 引数は原本・前のステップの出力だけを確かめる（{tmp:...} の引数は出力先のこともある）。STEP_DEPS に並べた入力は全部確かめる
            missing = [a for a in argv if (a.startswith(data) or a.startswith(outdir)) and not os.path.exists(a)]
            missing += [a for a in deps if not os.path.exists(a)]
            if missing:
                results[name] = {"skipped": f"入力がない: {', '.join(os.path.basename(m) for m in missing)}"}
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


def missed_steps(got, want):
    """期待値に結果があるのに、今回飛ばした・流さなかったステップ（入力の欠け・ステップの名前の変え忘れ。
    書き出しの回帰テストが黙って抜けないよう失敗にする）"""
    return [n for n, w in want.items() if "skipped" not in w and (n not in got or "skipped" in got[n])]


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
    keep = sys.argv[sys.argv.index("--keep") + 1] if "--keep" in sys.argv else None
    got = run_all(data, keep)
    if "--update" in sys.argv:
        # 入力の欠けた環境で期待値を書き換えると、飛ばしたステップが期待値に「skipped」として入り、以後そのステップを比べなくなる。
        # 前の期待値に結果のあるステップを飛ばしたら止める。--allow-skip のときは、そのステップは前の期待値を残す（「skipped」で上書きしない）
        old = json.load(open(EXPECTED, encoding="utf-8")) if os.path.exists(EXPECTED) else {}
        # 今回飛ばしたステップ（新しく足したステップ・期待値のファイルがないときも含む）があれば、--allow-skip がない限り止める
        skipped_now = [n for n, g in got.items() if "skipped" in g]
        if skipped_now and "--allow-skip" not in sys.argv:
            sys.exit(f"飛ばしたステップがあるので期待値を書き換えない: {', '.join(skipped_now)}（入力を揃えるか --allow-skip）")
        # --allow-skip のとき: 今もあるステップで、前の期待値に結果のあるものは前の期待値を残す（今のステップの一覧にないもの・
        # 名前を変えたものは残さない。残すと以後ずっと「流さなかった」として失敗する）
        for n in skipped_now:
            if n in old and "skipped" not in old[n]:
                got[n] = old[n]
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
    # 飛ばしたステップは差分に数えないので、名前と理由を必ず出す（NDLOCR-Lite の保存した結果がないと書き出しが飛び、
    # 書き出しの回帰テストが抜けたまま通る。気づけるように）
    for n in skipped:
        print(f"WARN 飛ばした: [{n}] {got[n]['skipped']}", file=sys.stderr)
    print(f"回帰テスト: {len(want)} ステップ、差分 {len(diffs)} 件、飛ばした {len(skipped)} 件", file=sys.stderr)
    # 期待値に結果のあるステップを飛ばしたら失敗にする（入力の一部が欠けた環境で、書き出しなどの回帰テストが抜けたまま通らないように）。
    # 原本の一部しかない環境で、分かっていて流すときは --allow-skip
    missed = missed_steps(got, want)
    if missed and "--allow-skip" not in sys.argv:
        print(f"FAIL 期待値のあるステップを飛ばした: {', '.join(missed)}（入力を揃えるか --allow-skip）", file=sys.stderr)
    sys.exit(1 if diffs or (missed and "--allow-skip" not in sys.argv) else 0)


if __name__ == "__main__":
    main()
