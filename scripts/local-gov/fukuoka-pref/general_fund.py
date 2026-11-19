"""一般財源の中身（一般会計の見方で「一般財源」の箱を押したときの表）を、予算の公開データの行と組み替えの表から作る。

設計: docs/local-gov/tasks/20261114_1320_一般財源の中身の設計.md
組み替えの表: funding/r<令和の年>-<基準>.json（形式は表の「説明」）。表がなければ作らない（None）。

中身の行（金額は円）:
- 款そのもの（basis revenue_kan）: 歳入の款の目の合計。データが変われば自動で追う
- 組み替え（basis matched / summed）: 表の refs（歳入の目、または目の節）の額の合計。表の「額」と一致しなければ止める
  （部分: true の行は refs の合計のうち表の「額」だけ。額 ≦ refs の合計 を確かめる）
- 差し引き（basis residual）: 一般財源の合計 − 上の計。表の「概算」との差が「許す差」を超えたら・負なら止める
合計 = 一般会計の歳出の目の財源内訳の一般財源の合計（差し引きで必ず一致するが、validate.ts でも確かめる）
"""
import json
import os


def table_path(here: str, year: int, basis: str) -> str:
    return os.path.join(here, "funding", f"r{year - 2018}-{basis}.json")


def build(rows: list[dict], table: dict) -> tuple[dict | None, list[str]]:
    """返り値: (general_fund, 失敗の一覧)。失敗があれば general_fund は None"""
    fails: list[str] = []
    general = [r for r in rows if r["account"] == "general"]

    def known(v, where):
        """読めない値（None）を 0 円にせず失敗にする（足りない額の内訳を作らない）"""
        if v is None:
            fails.append(f"{where}: 額が読めない")
            return 0
        return v

    total = sum(known(((r.get("funding") or {}).get("general") or {}).get("v"), f"一般財源の合計 {r['id']}")
                for r in general if r["side"] == "expense")
    revenue = {r["id"]: r for r in general if r["side"] == "revenue"}
    out = []
    for kan in table["款そのもの"]:
        rs = [r for r in revenue.values() if r["kan"]["no"] == kan]
        if not rs:
            fails.append(f"款そのもの {kan}款: 歳入の目がない")
            continue
        out.append({"label": rs[0]["kan"]["name"], "amount": sum(known(r["amount"]["v"], f"{kan}款 {r['id']}") for r in rs),
                    "basis": "revenue_kan", "kan": kan})
    for g in table["組み替え"]:
        got = 0
        for ref in g["refs"]:
            r = revenue.get(ref["id"])
            if r is None:
                fails.append(f"{g['label']}: 歳入の目 {ref['id']} がない")
                continue
            if "setsu" in ref:
                ss = [s for s in r.get("setsu", []) if s.get("no") == ref["setsu"]]
                if len(ss) != 1:
                    fails.append(f"{g['label']}: {ref['id']} の {ref['setsu']}節が {len(ss)} 件")
                    continue
                got += known(ss[0]["amount"]["v"], f"{g['label']}: {ref['id']} の {ref['setsu']}節")
            else:
                got += known(r["amount"]["v"], f"{g['label']}: {ref['id']}")
        want = g["額"] * 1000
        if g.get("部分"):
            if want > got:
                fails.append(f"{g['label']}: 表の額 {want:,} 円が歳入の目の合計 {got:,} 円より大きい")
        elif got != want:
            fails.append(f"{g['label']}: 歳入の目・節の合計 {got:,} 円 ≠ 表の額 {want:,} 円（データが変わったら調べ直す）")
        out.append({"label": g["label"], "amount": want, "basis": g["basis"], "refs": [ref["id"] for ref in g["refs"]]})
    rest = total - sum(x["amount"] for x in out)
    d = table["差し引き"]
    if rest < 0 or abs(rest - d["概算"] * 1000) > d["許す差"] * 1000:
        fails.append(f"差し引き {rest:,} 円が概算 {d['概算'] * 1000:,} 円から許す差（{d['許す差'] * 1000:,} 円）を超えて違う・負")
    out.append({"label": d["label"], "amount": rest, "basis": "residual"})
    if fails:
        return None, fails
    return {"rows": out, "total": total, "notes": table["注"], "checked_on": table["確認日"]}, []


def build_for(here: str, year: int, basis: str, rows: list[dict]) -> tuple[dict | None, list[str]]:
    """組み替えの表があれば作る。なければ (None, [])"""
    p = table_path(here, year, basis)
    if not os.path.exists(p):
        return None, []
    with open(p, encoding="utf-8") as f:
        return build(rows, json.load(f))
