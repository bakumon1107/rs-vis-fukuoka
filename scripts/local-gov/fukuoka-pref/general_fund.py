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
    flows = None
    if "歳入の款と財源" in table:
        flows = build_flows(general, out, table, fails)
    if fails:
        return None, fails
    gf = {"rows": out, "total": total, "notes": table["注"], "checked_on": table["確認日"]}
    if flows is not None:
        gf["flows"] = flows
    return gf, []


FUNDING_KEYS = ("national", "bond", "other", "general")


def build_flows(general: list[dict], gf_rows: list[dict], table: dict, fails: list[str]) -> list[dict]:
    """歳入の款 → 財源 の帯（かんたんの図の3列。設計: docs/local-gov/tasks/20261128_1408_かんたんの図に歳入から財源への振り分けを足す設計.md）。
    一般財源へは一般財源の中身の行を元の款へ戻す（款そのもの・組み替えの refs の款・差し引きは款ごとの概算で分ける）。
    残りは表の「歳入の款と財源」の財源へ（書いていない款は other）。
    確かめること（合わなければ fails）: 財源ごとの合計 = 歳出の財源内訳の合計、款ごとの合計 = 歳入の款の額、帯が負でない"""
    revenue = [r for r in general if r["side"] == "revenue"]
    kan_name = {r["kan"]["no"]: r["kan"]["name"] for r in revenue}
    kan_total: dict[int, int] = {}
    for r in revenue:
        kan_total[r["kan"]["no"]] = kan_total.get(r["kan"]["no"], 0) + (r["amount"]["v"] or 0)
    row_kan = {r["id"]: r["kan"]["no"] for r in revenue}
    to_general: dict[int, int] = {}
    estimated: set[int] = set()
    for g in gf_rows:
        if g["basis"] == "revenue_kan":
            to_general[g["kan"]] = to_general.get(g["kan"], 0) + g["amount"]
        elif g["basis"] in ("matched", "summed"):
            kans = {row_kan.get(ref) for ref in g.get("refs", [])}
            if len(kans) != 1 or None in kans:
                fails.append(f"歳入の款 → 財源: {g['label']} の元の目が1つの款にまとまらない（{sorted(map(str, kans))}）")
                continue
            k = kans.pop()
            to_general[k] = to_general.get(k, 0) + g["amount"]
            g["kan"] = k
        else:  # residual: 款ごとの概算（千円）で分ける。実額との差（読み取りの誤差）は一番大きい款で吸収する
            est = {int(k): v * 1000 for k, v in table.get("差し引きの款ごとの概算", {}).items() if k != "説明"}
            if not est:
                fails.append("歳入の款 → 財源: 差し引きの款ごとの概算がない")
                continue
            split = dict(est)
            big = max(split, key=lambda k: split[k])
            split[big] += g["amount"] - sum(est.values())
            neg = [k for k, v in split.items() if v < 0]
            if neg:
                fails.append(f"歳入の款 → 財源: 差し引きの款ごとの分が負になる（{neg}款。概算が負か、差し引き {g['amount']:,} 円が"
                             f"概算の合計 {sum(est.values()):,} 円より小さすぎる。概算を見直す）")
                continue
            g["split"] = [{"kan": k, "amount": v} for k, v in sorted(split.items())]
            for k, v in split.items():
                to_general[k] = to_general.get(k, 0) + v
                estimated.add(k)
    mapping = {k: v for k, v in table["歳入の款と財源"].items() if k != "説明"}
    for name, f in mapping.items():
        if f not in ("national", "bond", "other"):
            fails.append(f"歳入の款 → 財源: {name} の財源が不正（{f}）")
        if name not in kan_name.values():
            fails.append(f"歳入の款 → 財源: 款「{name}」が歳入にない（表が古い）")
    flows = []
    for k in sorted(kan_total):
        gen = to_general.get(k, 0)
        rest = kan_total[k] - gen
        if gen < 0 or rest < 0:
            fails.append(f"歳入の款 → 財源: {k}款 {kan_name[k]} の帯が負（一般財源 {gen:,}・残り {rest:,}）")
            continue
        if gen:
            flows.append({"kan": k, "kan_name": kan_name[k], "funding": "general", "amount": gen,
                          **({"estimated": True} if k in estimated else {})})
        if rest:
            flows.append({"kan": k, "kan_name": kan_name[k], "funding": mapping.get(kan_name[k], "other"), "amount": rest})
    want = {f: 0 for f in FUNDING_KEYS}
    for r in general:
        if r["side"] == "expense":
            for f in FUNDING_KEYS:
                want[f] += ((r.get("funding") or {}).get(f) or {}).get("v") or 0
    got = {f: sum(x["amount"] for x in flows if x["funding"] == f) for f in FUNDING_KEYS}
    for f in FUNDING_KEYS:
        if got[f] != want[f]:
            fails.append(f"歳入の款 → 財源: {f} の合計 {got[f]:,} 円 ≠ 歳出の財源内訳の合計 {want[f]:,} 円（振り分けの定義を見直す）")
    return flows


def build_for(here: str, year: int, basis: str, rows: list[dict]) -> tuple[dict | None, list[str]]:
    """組み替えの表があれば作る。なければ (None, [])"""
    p = table_path(here, year, basis)
    if not os.path.exists(p):
        return None, []
    with open(p, encoding="utf-8") as f:
        return build(rows, json.load(f))
