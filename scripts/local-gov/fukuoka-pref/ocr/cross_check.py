"""2通りの読み取り（OCR と発行元の文字層）の解釈結果を目ごとに突き合わせる。

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/ocr/cross_check.py <OCR の setsumeisho.json> <文字層の setsumeisho.json> \
        [--third <別の OCR の setsumeisho.json>] [--yosansho <yosansho.json>] > cross-check.json
    --third: OCR と同じ値を読んでいる箇所を固定し、文字層で書き換えない（打ち消し合う誤りの防止）。財源内訳は
    区分ごと・断片ごとに突き合わせる（parse_setsumeisho.py の「財源の断片」）

やること:
1. 目の対応: 同じ表の構造（ocr_pages.py の縦線・区画）から作っているので、(会計, 歳入/歳出, 款, 項, 目番号) で対応させる
2. 一致率: OCR で全検算が通った目について、本年度・前年度・比較が文字層と一致する割合（2つの読み取りの独立性の確認）
3. 救済: OCR で検算が通らない目について、値の組（本年度・前年度・比較 / 財源内訳 / 節 / 説明欄の金額）を文字層の値に
   差し替えて、全検算（A〜D）が通るかを試す。通れば採用し「出典: 文字層」と記録する。名前は OCR のものを使う
4. 残り: どちらでも通らない目の一覧（画像で確かめて修正表に書く対象）
検算の規則は parse_setsumeisho.py と同じ（説明欄の入れ子・金額なしの1事項・空欄の扱いは解釈済みの値を使う）。
"""
import copy
import json
import sys
from collections import Counter


def key(m):
    return (m.get("会計"), m["side"], m["款"], (m["項"] or (None,))[0], m["目番号"])


def checks_of(m):
    h = m["本年度"]
    c = {}
    if m["side"] == "歳出":
        ex = m["説明"]
        if m.get("説明なし") or not ex:
            c["A"] = bool(m.get("説明なし")) or (not ex and not m.get("説明の残り"))
        else:
            c["A"] = h is not None and (sum(e["amount"] for e in ex) == h
                                        or sum(e["amount"] for e in ex if not e.get("内訳")) == h)
        c["B"] = h is not None and sum(m["財源"].values()) == h
    c["C"] = (h is not None and m["前年度"] is not None and m["比較"] is not None and abs(h - m["前年度"]) == abs(m["比較"]))
    top = [s for s in m["節"] if s.get("top", s.get("no") is not None)]
    c["D"] = (h is not None and sum(s["amount"] for s in top) == h) or bool(m.get("節なし"))
    if h == 0 and not m["説明"] and not m["節"]:
        c = {k: True for k in c}
    return c


def _top_amounts(m):
    return [s["amount"] for s in m["節"] if s.get("top", s.get("no") is not None)]


def _locked_amounts(m, th):
    """OCR と3つ目の読み取りの両方にある金額（多重集合の共通部分）。"""
    if th is None:
        return Counter()
    return Counter(m) & Counter(th)


def _swap_scalars(x, t, th):
    for f in ("本年度", "前年度", "比較"):
        if t[f] != x[f] and th is not None and x[f] is not None and th.get(f) == x[f]:
            return False  # 2つの OCR が同じ値を読んでいる
    x.update({f: t[f] for f in ("本年度", "前年度", "比較")})
    return None


def _swap_setsu(x, t, th):
    locked = _locked_amounts(_top_amounts(x), _top_amounts(th) if th else None)
    if locked - Counter(_top_amounts(t)):
        return False  # 2つの OCR が読んだ節の金額が、文字層の節にない
    x["節"] = copy.deepcopy(t["節"])
    return None


def _apply_funding(x, t, th):
    """財源内訳を区分ごとに突き合わせる。選択肢:
    - 文字層にだけある断片を足す（OCR の取りこぼし。「その他」の「財産収入 1」。R8 p177 を画像で確認）
    - 区分の値を文字層の値にする（その区分を OCR が1つの断片で読み、3つ目の読み取りと一致していないときだけ）
    最小の変更で目の本年度にちょうど合う解が1通りのときだけ採用する。"""
    h = x["本年度"]
    op, tp = x.get("財源の断片"), t.get("財源の断片")
    if h is None or not op or not tp:
        return False
    total = sum(x["財源"].values())
    opts = []
    for k in x["財源"]:
        extra = Counter(tp.get(k, [])) - Counter(op.get(k, []))
        for a, n in extra.items():
            for _ in range(n):
                opts.append((k, "add", a))
        if (len(op.get(k, [])) == 1 and len(tp.get(k, [])) == 1 and op[k][0] != tp[k][0]
                and not (th is not None and th["財源"].get(k) == x["財源"][k])):
            opts.append((k, "replace", tp[k][0] - op[k][0]))
    if not opts or len(opts) > 12:
        return False
    sols = [mask for mask in range(1, 1 << len(opts))
            if total + sum(opts[i][2] for i in range(len(opts)) if mask >> i & 1) == h]
    if not sols:
        return False
    best = min(bin(s).count("1") for s in sols)
    mins = [s for s in sols if bin(s).count("1") == best]
    if len(mins) != 1:
        return False
    notes = []
    for i, (k, kind, a) in enumerate(opts):
        if mins[0] >> i & 1:
            x["財源"][k] += a
            notes.append(f"{k}: 文字層の断片 {a} を足す" if kind == "add" else f"{k}: 文字層の値にする（差 {a}）")
    x["財源の突き合わせ"] = notes
    return None


def main():
    ocr = [m for m in json.load(open(sys.argv[1], encoding="utf-8")) if m["kind"] == "目"]
    tl = {key(m): m for m in json.load(open(sys.argv[2], encoding="utf-8")) if m["kind"] == "目"}
    third = ({key(m): m for m in json.load(open(sys.argv[sys.argv.index("--third") + 1], encoding="utf-8")) if m["kind"] == "目"}
             if "--third" in sys.argv else None)
    stat = Counter()
    rescued, remaining = [], []
    for m in ocr:
        t = tl.get(key(m))
        ok = all(m["checks"].values())
        if t is None:
            stat["文字層に対応する目なし"] += 1
            if not ok:
                remaining.append(m)
            continue
        if ok:
            for f in ("本年度", "前年度", "比較"):
                stat[f"一致率 {f} 対象"] += 1
                stat[f"一致率 {f} 一致"] += int(t[f] == m[f])
            continue
        # 救済: 値の組ごとに差し替えて試す（組み合わせも試す）。
        # 3つ目の読み取り（--third。別の OCR）があれば、OCR と3つ目が同じ値を読んでいる箇所は「固定」して書き換えない。
        # 書き換えると、文字層の誤りと OCR の取りこぼしが打ち消し合って検算を通ってしまう（R8 p239: 一般財源 34,763 を
        # 文字層の 34,764 に、その他の「1」の取りこぼしと相殺。画像で確認）
        th = third.get(key(m)) if third else None
        groups = {
            "本年度・前年度・比較": lambda x, t=t, th=th: _swap_scalars(x, t, th),
            "財源を1件ずつ": lambda x, t=t, th=th: _apply_funding(x, t, th),
            "節": lambda x, t=t, th=th: _swap_setsu(x, t, th),
            "節を1件ずつ": lambda x, t=t, th=th: _apply_resolve(x, t, th),
            "説明欄の金額": lambda x, t=t, th=th: _swap_expl(x, t, th),
        }
        names = list(groups)
        found = None
        # 差し替える組の少ない順に試す（OCR の値をなるべく残す）
        for mask in sorted(range(1, 1 << len(names)), key=lambda v: (bin(v).count("1"), v)):
            sel = [names[i] for i in range(len(names)) if mask >> i & 1]
            x = copy.deepcopy(m)
            if any(groups[g](x) is False for g in sel):
                continue
            if all(checks_of(x).values()):
                found = (sel, x)
                break
        if found:
            sel, x = found
            x["checks"] = checks_of(x)
            x["出典"] = {g: "文字層" for g in sel}
            rescued.append(x)
            stat["救済"] += 1
            print(f"救済 {key(m)} {m['目名']} p{m['pages'][0]}: {sel}", file=sys.stderr)
        else:
            remaining.append(m)
            ng = [k for k, v in m["checks"].items() if not v]
            print(f"残り {key(m)} {m['目名']} p{m['pages'][0]}: NG {ng} / OCR 本年度 {m['本年度']} 前年度 {m['前年度']} "
                  f"比較 {m['比較']} / 文字層 本年度 {t['本年度']} 前年度 {t['前年度']} 比較 {t['比較']}", file=sys.stderr)
    for f in ("本年度", "前年度", "比較"):
        n = stat[f"一致率 {f} 対象"]
        if n:
            print(f"全検算の通った目で {f} が文字層と一致: {stat[f'一致率 {f} 一致']}/{n}", file=sys.stderr)
    print(f"検算の通らない目 {stat['救済'] + len(remaining)} 件のうち、文字層の値で救済 {stat['救済']} 件・残り {len(remaining)} 件",
          file=sys.stderr)
    # 救済した目を差し替えた全体（以後のデータの元）。差し替え後も項の合計が予算書と合うか確かめ直す
    by_key = {key(x): x for x in rescued}
    merged = [by_key.get(key(m), m) for m in ocr]
    if "--yosansho" in sys.argv:
        import re
        from collections import defaultdict
        yo = json.load(open(sys.argv[sys.argv.index("--yosansho") + 1], encoding="utf-8"))
        ref = {}
        for k in yo["会計"]:
            name = "一般会計" if k["会計"] == "一般会計" else re.sub(r"特別会計$", "", k["会計"])
            for side in ("歳入", "歳出"):
                for kan in k.get(side, []):
                    for kou in kan["項"]:
                        ref[(name, side, kan["no"], kou["no"])] = kou["金額"]
        got = defaultdict(int)
        for m in merged:
            got[key(m)[:4]] += m["本年度"] or 0
        here = {m.get("会計") for m in merged}
        bad = [k for k, v in ref.items() if k[0] in here and got.get(k, 0) != v]
        print(f"差し替え後の項の合計: {sum(1 for k in ref if k[0] in here) - len(bad)}/{sum(1 for k in ref if k[0] in here)} が予算書と一致",
              file=sys.stderr)
        for k in bad:
            print(f"NG 項 {k}: {got.get(k, 0):,} / 予算書 {ref[k]:,}", file=sys.stderr)
    n_all = sum(1 for m in merged if all(m["checks"].values()))
    print(f"全体: 目 {len(merged)} 件のうち全検算一致 {n_all} 件", file=sys.stderr)
    json.dump({"目": merged, "救済": [{"key": key(x), "目名": x["目名"], "出典": x["出典"], "節の突き合わせ": x.get("節の突き合わせ")}
                                     for x in rescued],
               "残り": [{"key": key(m), "目名": m["目名"], "pages": m["pages"], "checks": m["checks"]} for m in remaining]},
              sys.stdout, ensure_ascii=False, indent=1, default=str)


def _swap_expl(x, t, th=None):
    """説明欄: 件数が同じなら金額だけ差し替える（名前は OCR のまま）。
    件数が違う（OCR が金額を名前とつないで落とした: p186「職員費45人386:」）ときは文字層の一覧を使い、名前に要補正の印。
    2つの OCR が同じ金額を読んでいる事項が、文字層の一覧になくなるなら採らない。"""
    if not t["説明"]:
        return False
    locked = _locked_amounts([e["amount"] for e in x["説明"]], [e["amount"] for e in th["説明"]] if th else None)
    if locked - Counter(e["amount"] for e in t["説明"]):
        return False
    if len(x["説明"]) == len(t["説明"]):
        for e, f in zip(x["説明"], t["説明"]):
            e["amount"] = f["amount"]
        return None
    x["説明"] = [dict(f, 名前は文字層_要補正=True) for f in t["説明"]]
    x["説明の残り"] = ""
    return None


def _apply_resolve(x, t, th=None):
    r = resolve_setsu(x, t, th)
    if r is None:
        return False
    x["節"], x["節の突き合わせ"] = r
    return None


def resolve_setsu(m, t, th=None):
    """節を1件ずつ突き合わせ、目の本年度にちょうど合う組み合わせが1通りに決まれば返す。
    選択肢: 同じ節番号で金額が違う → OCR か文字層か / 文字層にだけある節 → 足すか / OCR にだけある番号なしの行 → 残すか
    （OCR が細節を節と誤認した行・重複して読んだ行を除くため）。最小の変更で合う解が1通りのときだけ採用する。
    3つ目の読み取り（th）が同じ節番号で同じ金額なら、その節は文字層の値に置き換えない（番号なしの行を除く操作は、
    読み違いではなく節と細節の取り違えなので固定しない）。"""
    h = m["本年度"]
    if h is None:
        return None
    o_top = [s for s in m["節"] if s.get("top", s.get("no") is not None)]
    t_top = [s for s in t["節"] if s.get("top", s.get("no") is not None)]
    t_by = {s["no"]: s for s in t_top if s.get("no") is not None}
    th_by = {s["no"]: s["amount"] for s in (th["節"] if th else []) if s.get("no") is not None and s.get("top", True)}
    o_nos = {s["no"] for s in o_top if s.get("no") is not None}
    base, opts = [], []  # opts: (説明, 採ったときの金額の差, 採ったときの操作)
    for s in o_top:
        if (s.get("no") is not None and s["no"] in t_by and t_by[s["no"]]["amount"] != s["amount"]
                and th_by.get(s["no"]) != s["amount"]):
            opts.append((f"節{s['no']} 文字層 {t_by[s['no']]['amount']}（OCR {s['amount']}）", t_by[s["no"]]["amount"] - s["amount"],
                         ("replace", s, t_by[s["no"]]["amount"])))
        elif s.get("no") is None:
            opts.append((f"番号なしの行 {s['amount']} を除く", -s["amount"], ("drop", s, None)))
        base.append(s)
    for no, s in t_by.items():
        if no not in o_nos:
            opts.append((f"節{no} {s['amount']} を文字層から足す", s["amount"], ("add", s, None)))
    if len(opts) > 12:
        return None
    total = sum(s["amount"] for s in base)
    sols = []
    for mask in range(0, 1 << len(opts)):
        d = sum(opts[i][1] for i in range(len(opts)) if mask >> i & 1)
        if total + d == h:
            sols.append(mask)
    if not sols:
        return None
    best = min(bin(s).count("1") for s in sols)
    mins = [s for s in sols if bin(s).count("1") == best]
    if len(mins) != 1:
        return None
    mask = mins[0]
    new = [dict(s) for s in base]
    notes = []
    for i, (desc, _, (op, s, val)) in enumerate(opts):
        if not mask >> i & 1:
            continue
        notes.append(desc)
        if op == "replace":
            for n in new:
                if n.get("no") == s["no"] and n["amount"] == s["amount"]:
                    n["amount"], n["出典"] = val, "文字層"
                    break
        elif op == "drop":
            for j, n in enumerate(new):
                if n.get("no") is None and n["amount"] == s["amount"]:
                    new.pop(j)
                    break
        elif op == "add":
            new.append(dict(s, 出典="文字層"))
    rest = [s for s in m["節"] if not s.get("top", s.get("no") is not None)]
    return new + rest, notes


if __name__ == "__main__":
    main()
