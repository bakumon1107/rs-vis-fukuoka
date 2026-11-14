"""補正予算の書き出した公開データを、目の検算とは別の筋で照合する（R8 補正予算の抽出の設計 5章の補い）。

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/verify_hosei.py <budget-2026-initial.json> <work> <公開データのディレクトリ>
（work に hosei-<回>.json、公開データのディレクトリに budget-2026-supplementary-<n>.json。回は export_hosei.ROUNDS の順）

照合（完全一致。FAIL で終了コード 1）:
1. 項: 目の補正額の合計 = 議案の項の補正額（議案のある回。議案には補正のある項だけが載り、載らない項の目の補正額は 0）
2. 目の鎖: 目の補正前の額 = 当初予算の目の額 + それより前の回のその目の補正額の合計（新設の目は 0）。
   目ごとの数字を、当初予算（別の資料）の値から確かめる。計 = 補正前 + 補正額 も見る
3. 財源: 款ごとの財源内訳（国支出金・地方債・その他・一般財源）の合計 = 総括の款の財源内訳（総括に財源のある回）
4. 款: 総括の款の補正前の額 = 当初 + それより前の回の公開データの目の補正額（款ごとに足す）。
   check_hosei_chain.py は総括の補正額どうしをつなぐので、公開データの行が抜けた・余分にある（書き出しで落とした目など）
   ことには気づけない。2 の目の鎖も、公開データにない目は比べないので、ここで款の合計として見る
（目の鎖は export_hosei.py も書き出しのときに見て、状態に反映する。ここは書き出した公開データを読み直して確かめる）
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import export_hosei  # noqa: E402

FUND = {"国支出金": "national", "地方債": "bond", "その他": "other", "一般財源": "general"}
SIDE = {"歳入": "revenue", "歳出": "expense"}


def main():
    initial_path, work, pubdir = sys.argv[1:4]
    initial = json.load(open(initial_path, encoding="utf-8"))
    cur = Counter()  # 目の ID → 当初 + それまでの補正額（円）
    kan_cur = Counter()  # (歳入出, 款) → 当初 + それまでの補正額（円）
    for r in initial["rows"]:
        if r["account"] == "general":
            cur[r["id"]] += r["amount"]["v"] or 0
            kan_cur[(r["side"], r["kan"]["no"])] += r["amount"]["v"] or 0
    fails, n = [], Counter()
    for rd in export_hosei.ROUNDS:
        rid = rd["id"]
        no = int(rid.rsplit("-", 1)[1])
        sp = os.path.join(pubdir, f"budget-2026-supplementary-{no}.json")
        hp = os.path.join(work, f"hosei-{rid}.json")
        if not (os.path.exists(sp) and os.path.exists(hp)):
            fails.append(f"{rid}: 入力がない")
            continue
        sup, gs = json.load(open(sp, encoding="utf-8")), json.load(open(hp, encoding="utf-8"))
        rows = sup["rows"]
        # 2. 目の鎖
        for r in rows:
            b, a, s = r["before"]["v"], r["amount"]["v"], r["after"]["v"]
            want = cur[r["id"]]
            if b != want:
                fails.append(f"{rid} {r['id']} {r['moku']['name']}: 補正前 {b:,} ≠ 当初＋それまでの補正 {want:,}")
            if b + a != s:
                fails.append(f"{rid} {r['id']}: 補正前 + 補正額 ≠ 計")
            n["目の鎖"] += 1
        # 1. 項
        if gs.get("gian"):
            got = Counter()
            for r in rows:
                got[(r["side"], r["kan"]["no"], r["kou"]["no"])] += r["amount"]["v"]
            listed = set()
            for s_ja, s in SIDE.items():
                for k in gs["gian"][s_ja]:
                    for q in k["項"]:
                        key = (s, k["no"], q["no"])
                        listed.add(key)
                        n["項"] += 1
                        if got[key] != q["補正額"] * 1000:
                            fails.append(f"{rid} {s_ja} {k['no']}款{q['no']}項: 目の補正額の合計 {got[key]:,} ≠ 議案 {q['補正額'] * 1000:,}")
            for key, v in got.items():
                if key not in listed and v != 0:
                    fails.append(f"{rid} {key}: 議案に載らない項に目の補正額 {v:,}")
        # 3. 財源（総括に財源のある回）
        for k in gs["総括"]["歳出"]:
            if "財源" not in k:
                continue
            n["財源"] += 1
            for jp, en in FUND.items():
                g = sum(r["funding"][en]["v"] for r in rows if r["side"] == "expense" and r["kan"]["no"] == k["no"])
                if g != k["財源"][jp] * 1000:
                    fails.append(f"{rid} 歳出 {k['no']}款 {jp}: 目の合計 {g:,} ≠ 総括 {k['財源'][jp] * 1000:,}")
        # 4. 総括の款の補正前（公開データの行から足した款の額と比べる）
        for s_ja, s in SIDE.items():
            for k in gs["総括"][s_ja]:
                n["款"] += 1
                if k["補正前"] * 1000 != kan_cur[(s, k["no"])]:
                    fails.append(f"{rid} 総括 {s_ja} {k['no']}款: 補正前 {k['補正前'] * 1000:,} ≠ 当初＋それまでの公開データの補正 {kan_cur[(s, k['no'])]:,}")
        for r in rows:
            cur[r["id"]] += r["amount"]["v"]
            kan_cur[(r["side"], r["kan"]["no"])] += r["amount"]["v"]
    for f in fails:
        print("FAIL " + f, file=sys.stderr)
    print("照合した数: " + "・".join(f"{k} {v}" for k, v in n.items()), file=sys.stderr)
    print(f"FAIL={len(fails)}", file=sys.stderr)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
