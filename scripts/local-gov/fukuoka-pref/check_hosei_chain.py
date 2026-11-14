"""補正予算の回の鎖を照合する（補正の設計書 5章「回をまたぐ照合」）。

当初予算の公開データ（一般会計の款・項の合計）から始め、回の順に補正額を足していき、各回の「補正前の額」と一致することを確かめる。
- 款: 各回の総括の補正前 = 当初 + それより前の回の補正額の合計（総括は全部の款が載る）
- 項: 各回の議案に載った項の補正前 = 当初の項 + それより前の回のその項の補正額の合計
- 最後の回の計 = 当初 + すべての回の補正額

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/check_hosei_chain.py <budget-2026-initial.json> <hosei-第1回.json> <hosei-第2回.json> …
（回は古い順に並べる。金額は補正の出力が千円、公開データが円）
"""
import json
import sys
from collections import Counter


def main():
    pub, *rounds = sys.argv[1:]
    rows = [r for r in json.load(open(pub, encoding="utf-8"))["rows"] if r["account"] == "general"]
    side_of = {"revenue": "歳入", "expense": "歳出"}
    kan, kou = Counter(), Counter()
    for r in rows:
        s = side_of[r["side"]]
        if r["amount"]["v"] % 1000:
            sys.exit(f"千円未満の端数がある目 {r['id']}")
        kan[(s, r["kan"]["no"])] += r["amount"]["v"] // 1000
        kou[(s, r["kan"]["no"], r["kou"]["no"])] += r["amount"]["v"] // 1000
    fails = []
    for path in rounds:
        d = json.load(open(path, encoding="utf-8"))
        rid = d["id"]
        for s in ("歳入", "歳出"):
            for k in d["総括"][s]:
                if k["補正前"] != kan[(s, k["no"])]:
                    fails.append(f"{rid} 総括 {s} {k['no']}款: 補正前 {k['補正前']:,} ≠ 当初＋それまでの補正 {kan[(s, k['no'])]:,}")
            for k in (d["gian"] or {}).get(s, []):
                for q in k["項"]:
                    key = (s, k["no"], q["no"])
                    if q["補正前"] != kou[key]:
                        fails.append(f"{rid} 議案 {s} {k['no']}款{q['no']}項: 補正前 {q['補正前']:,} ≠ 当初＋それまでの補正 {kou[key]:,}")
            # 次の回のために足す（款は総括、項は議案。議案のない専決の回は、項の補正を説明書の目から足す必要がある）
            for k in d["総括"][s]:
                kan[(s, k["no"])] += k["補正額"]
            for k in (d["gian"] or {}).get(s, []):
                for q in k["項"]:
                    kou[(s, k["no"], q["no"])] += q["補正額"]
            if d["gian"] is None:
                for k in d["総括"][s]:
                    if k["補正額"]:
                        kou_known = d.get("項の補正", {}).get(s, {}).get(str(k["no"]))
                        kous = sorted(q for (ss, kk, q) in kou if ss == s and kk == k["no"])
                        if kou_known is None and len(kous) == 1:
                            # 項が1つだけの款（繰越金など）は、款の補正額がそのまま項の補正額
                            kou_known = {str(kous[0]): k["補正額"]}
                        if kou_known is None:
                            print(f"WARN {rid} {s} {k['no']}款: 議案がないので項の補正が分からない（後の回の項の照合が外れうる）",
                                  file=sys.stderr)
                        else:
                            for qn, v in kou_known.items():
                                kou[(s, k["no"], int(qn))] += v
        print(f"{rid}: 補正後の歳出 {sum(v for (s, _), v in kan.items() if s == '歳出'):,} 千円", file=sys.stderr)
    for f in fails:
        print("FAIL " + f, file=sys.stderr)
    print(f"FAIL={len(fails)}", file=sys.stderr)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
