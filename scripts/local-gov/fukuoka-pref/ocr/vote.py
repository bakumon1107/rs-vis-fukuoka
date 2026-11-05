"""複数の読み取り（例: 旧 OCR・新 OCR・発行元の文字層）の解釈結果で、値ごとに何通りの読み取りが同じ値を出したかを数える。

検算が通っていても、ある値を出したのが1つの読み取りだけなら、その値の裏付けは検算の式だけ。
（検算の式は「誤りが打ち消し合う」ことには弱い。2つの値が逆向きに同じだけずれると通ってしまう）
読み取りの癖が違う複数の結果で同じ値が出ていれば、その値は独立に裏付けられている。

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/ocr/vote.py <採用した結果.json> <読み取り1.json> [<読み取り2.json> ...] > vote.json
    採用した結果は cross_check.py の出力（{"目": [...]}）か parse_setsumeisho.py の出力（[...]）。

値の対応: 目は (会計, 歳入/歳出, 款, 項, 目番号)、目の中は 本年度・前年度・比較・財源の各区分・節（番号ごと）・
説明欄の事項（順番。件数が同じ読み取りだけ）。
出力（stderr）: 採用した値のうち、同じ値を出した読み取りの数の分布。1通りだけの値の一覧は JSON に出す。
"""
import json
import sys
from collections import Counter


def load(path):
    d = json.load(open(path, encoding="utf-8"))
    ms = d["目"] if isinstance(d, dict) else d
    return [m for m in ms if m["kind"] == "目"]


def key(m):
    return (m.get("会計"), m["side"], m["款"], (m["項"] or (None,))[0], m["目番号"])


def values(m):
    out = {}
    for f in ("本年度", "前年度", "比較"):
        out[f] = m.get(f)
    for k, v in (m.get("財源") or {}).items():
        if m["side"] == "歳出":
            out[f"財源 {k}"] = v
    # 節と説明欄は番号・順番で対応させない（節番号の読み違い「8」→「80」、説明欄の件数の違いで対応が外れる）。
    # 目の中の金額の集まりとして比べる（同じ金額が複数あれば、その個数まで）
    for kind, items in (("節", [s["amount"] for s in m["節"] if s.get("top", s.get("no") is not None)]),
                        ("説明", [e["amount"] for e in m["説明"] if not e.get("金額の記載なし")])):
        seen = Counter()
        for a in items:
            seen[a] += 1
            out[f"{kind} {a}#{seen[a]}"] = a
    return out


def main():
    adopted = load(sys.argv[1])
    readings = [{key(m): values(m) for m in load(p)} for p in sys.argv[2:]]
    n = len(readings)
    dist = Counter()
    by_kind = Counter()
    weak = []
    for m in adopted:
        if not all(m.get("checks", {}).values()):
            continue
        vs = values(m)
        for f, v in vs.items():
            if v is None:
                continue
            support = sum(1 for r in readings if r.get(key(m), {}).get(f) == v)
            dist[support] += 1
            kind = f.split(" ")[0].rstrip("0123456789")
            by_kind[(kind, support)] += 1
            if support <= 1:
                weak.append({"key": key(m), "目名": m["目名"], "値": f, "採用": v, "pages": m["pages"],
                             "読み取り": [r.get(key(m), {}).get(f) for r in readings]})
    total = sum(dist.values())
    print(f"全検算一致の目の値 {total} 件について、同じ値を出した読み取りの数（{n} 通り中）:", file=sys.stderr)
    for s in sorted(dist, reverse=True):
        print(f"  {s} 通り: {dist[s]} 件（{dist[s] / total:.1%}）", file=sys.stderr)
    kinds = sorted({k for k, _ in by_kind})
    for k in kinds:
        print(f"  {k}: " + " / ".join(f"{s}通り {by_kind[(k, s)]}" for s in range(n, -1, -1) if by_kind[(k, s)]), file=sys.stderr)
    json.dump({"1通り以下": weak}, sys.stdout, ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    main()
