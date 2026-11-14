"""歳入の説明欄の内訳（「○○課所管 金額」など）と、歳出の目の財源内訳「その他」の（財源の名前, 金額）を突き合わせる（調査用）。

歳入の説明欄の内訳は節の中身を課などに分けたもので、歳出の目のその他の欄の金額とちょうど一致することが多い
（R8: 利子及び配当金の 医療指導課所管 65,967 = 医務費、こども未来課所管 113,514 + 子育て支援課所管 8,029 = 児童家庭総務費 121,543）。
同じ財源の名前の中で、歳出の金額 1件 = 歳入の内訳 1〜3件の合計 になる組を、金額の大きい歳出から順に取る。残った歳入の内訳が、
歳出のどの目にも充てられていない（一般財源に数えられた）候補になる。内訳のない歳入の節は、節の金額を1件の内訳として扱う。
調査: docs/local-gov/fukuoka/20261114_0005_財源内訳と歳入の款の差の調査.md 3.4

使い方:
    python3 -I scripts/local-gov/fukuoka-pref/research/funding_other_match.py <setsumeisho-ocr.json> <funding-other.json> [財源の名前…]
    （funding-other.json は funding_other_by_moku.py の出力。財源の名前を省くと 財産収入・諸収入・使用料及び手数料・寄附金）
"""
import itertools
import json
import sys

CATS = ("財産収入", "諸収入", "使用料及び手数料", "寄附金")


def revenue_entries(parsed, cat):
    """その財源の款の歳入の目ごとの内訳（説明欄。なければ節、それもなければ目）。"""
    out = []
    for m in parsed:
        if m.get("kind") != "目" or m["side"] != "歳入" or m.get("款_見出し") != cat:
            continue
        if m["本年度"] is None:
            print(f"WARN 本年度の読めない目（突き合わせから除く）: {m['目名']}", file=sys.stderr)
            continue
        ex = [e for e in (m.get("説明") or []) if e.get("amount")]
        if ex and sum(e["amount"] for e in ex) == m["本年度"]:
            out += [{"目": m["目名"], "name": e["name"], "v": e["amount"]} for e in ex]
            continue
        setsu = [s for s in m.get("節") or [] if s.get("top") and s.get("amount")]
        if setsu and sum(s["amount"] for s in setsu) == m["本年度"]:
            # 説明欄の内訳が節ごとに分かれて載る目（雑入など）は、節の金額で扱う（説明欄は節の中身の一部しか合わないことがある）
            out += [{"目": m["目名"], "name": s["label"], "v": s["amount"]} for s in setsu]
            continue
        out.append({"目": m["目名"], "name": m["目名"], "v": m["本年度"]})
    return out


def main():
    with open(sys.argv[1], encoding="utf-8") as f:
        parsed = json.load(f)
    with open(sys.argv[2], encoding="utf-8") as f:
        other = json.load(f)
    cats = sys.argv[3:] or list(CATS)
    for cat in cats:
        rev = revenue_entries(parsed, cat)
        exp = [{"name": f"{m['款名']}/{m['目名']}", "v": v} for m in other["目"] for lab, v, _ in m["内訳"] if lab == cat]
        pairs = []
        for e in sorted(exp, key=lambda e: -e["v"]):
            free = [r for r in rev if not r.get("used")]
            hit = None
            for n in (1, 2, 3):
                for c in itertools.combinations(free, n):
                    if sum(r["v"] for r in c) == e["v"]:
                        hit = c
                        break
                if hit or len(free) > 160 and n == 2:
                    break
            if hit:
                for r in hit:
                    r["used"] = True
                e["used"] = True
                pairs.append((e, hit))
        rest_r = [r for r in rev if not r.get("used")]
        rest_e = [e for e in exp if not e.get("used")]
        sr, se = sum(r["v"] for r in rest_r), sum(e["v"] for e in rest_e)
        print(f"##### {cat}: 歳入の内訳 {len(rev)} 件 {sum(r['v'] for r in rev):,} / 歳出 {len(exp)} 件 {sum(e['v'] for e in exp):,}"
              f" / 対応した歳出 {len(pairs)} 件 / 残りの歳入 {len(rest_r)} 件 {sr:,} / 残りの歳出 {len(rest_e)} 件 {se:,} / 差 {sr - se:,}")
        for r in sorted(rest_r, key=lambda r: -r["v"])[:30]:
            print(f"   残りの歳入 {r['目']} / {r['name']} {r['v']:,}")
        for e in sorted(rest_e, key=lambda e: -e["v"])[:15]:
            print(f"   残りの歳出 {e['name']} {e['v']:,}")


if __name__ == "__main__":
    main()
