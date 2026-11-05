"""予算に関する説明書（歳出）の OCR 結果（ocr_pages.py の出力）を表として解釈し、目ごとに検算する。

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/ocr/parse_setsumeisho.py <OCR出力ディレクトリ> <PDFページ範囲 例 121-420> \
        [--keijou keijougaku.json] > setsumeisho.json

歳出の表の列（R8 一般会計で確認）:
    0 目 / 1 本年度 / 2 前年度 / 3 比較 / 4 国庫支出金 / 5 地方債 / 6 その他（特定財源） / 7 一般財源 /
    8 節の区分 / 9 節の金額 / 10 説明（○事項 金額）
目どうしは表の幅いっぱいの横線で区切られる。目がページをまたぐときは、次のページの最初の区画に目の名前がない。

検算（目ごと。すべて完全一致を要求。単位は千円）:
    A 説明欄の金額の合計 = 本年度
    B 財源内訳（国庫支出金 + 地方債 + その他 + 一般財源）= 本年度
    C 本年度 − 前年度 = 比較（比較の符号「△」は OCR で落ちることがあるので絶対値で比べ、符号は A〜C から決める）
    D 節の金額の合計（番号付きの節のみ）= 本年度
    款の合計は計上額調（テキスト PDF）と照合する。
結果: 目ごとに checks（A〜D の成否）を付けて出力し、stderr に成功率を出す。
"""
import json
import os
import re
import sys
from collections import defaultdict

AMOUNT_RE = re.compile(r"^[△▲A^\-]?\s*(\d{1,3}(?:[,，.]\d{3})+|\d{1,3})$")

# 中国語モデルが出す簡体字・異体字を日本の字形に直す（名称の表示用。金額の検算には使わない）
SIMP = str.maketrans({
    "费": "費", "务": "務", "厅": "庁", "财": "財", "产": "産", "收": "収", "额": "額", "较": "較", "债": "債",
    "县": "県", "济": "済", "减": "減", "项": "項", "养": "養", "计": "計", "设": "設", "疗": "療", "导": "導",
    "运": "運", "营": "営", "对": "対", "发": "発", "业": "業", "农": "農", "资": "資", "补": "補", "贷": "貸",
    "机": "機", "关": "関", "维": "維", "杂": "雑", "价": "価", "劳": "労", "动": "動", "职": "職", "员": "員",
    "经": "経", "环": "環", "卫": "衛", "药": "薬", "术": "術", "实": "実", "验": "験", "检": "検", "查": "査",
    "规": "規", "护": "護", "儿": "児", "妇": "婦", "进": "進", "选": "選", "举": "挙", "议": "議", "证": "証",
    "书": "書", "图": "図", "馆": "館", "艺": "芸", "东": "東", "应": "応", "报": "報", "给": "給", "处": "処",
    "广": "広", "场": "場", "电": "電", "气": "気", "车": "車", "铁": "鉄", "桥": "橋", "筑": "築", "园": "園",
    "绿": "緑", "渔": "漁", "兽": "獣", "灾": "災", "复": "復", "认": "認", "讲": "講", "习": "習", "训": "訓",
    "练": "練", "观": "観", "线": "線", "网": "網", "络": "絡", "统": "統", "调": "調", "总": "総", "类": "類",
    "别": "別", "划": "画", "单": "単", "独": "独", "乐": "楽", "时": "時", "间": "間", "问": "問", "题": "題",
    "银": "銀", "贸": "貿", "购": "購", "买": "買", "卖": "売", "团": "団", "协": "協", "会": "会", "区": "区",
    "国": "国", "际": "際", "华": "華", "学": "学", "历": "歴", "传": "伝", "统": "統", "开": "開", "达": "達",
    "边": "辺", "这": "這", "种": "種", "积": "積", "极": "極", "临": "臨", "礼": "礼", "仪": "儀", "备": "備",
    "织": "織", "组": "組", "织": "織", "压": "圧", "污": "汚", "染": "染", "废": "廃", "弃": "棄", "环": "環",
    "库": "庫", "补": "補", "贴": "貼", "汇": "彙", "继": "継", "续": "続", "保": "保", "险": "険", "种": "種",
    "医": "医", "疗": "療", "护": "護", "专": "専", "门": "門", "员": "員", "岛": "島", "冈": "岡", "龙": "竜",
    "当": "当", "强": "強", "带": "帯", "让": "譲", "这": "這", "说": "説", "读": "読", "语": "語", "试": "試",
    "请": "請", "诸": "諸", "论": "論", "课": "課", "警": "警", "监": "監", "视": "視", "钢": "鋼", "转": "転",
    "轮": "輪", "输": "輸", "货": "貨", "贵": "貴", "宾": "賓", "宽": "寛", "带": "帯", "确": "確", "认": "認",
    "飞": "飛", "风": "風", "头": "頭", "页": "頁", "顾": "顧", "领": "領", "预": "予", "须": "須", "纳": "納",
    "纪": "紀", "约": "約", "级": "級", "纸": "紙", "细": "細", "终": "終", "经": "経", "给": "給", "绩": "績",
    "姜": "養", "羲": "養", "城": "域", "雜": "維",
    "O": "○", "〇": "○", "0": "○",
})


def norm_name(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^[O〇0]", "○", s)
    return s.translate(SIMP).replace(" ", "")


def amount(text: str):
    t = text.strip().replace(" ", "")
    # 数字の 1・0 が英字として読まれることがある（金額「1」が「l」に）。数字とカンマ以外がそれらだけのときに限り直す。
    # 直し誤りは検算（説明欄・節・款の合計）で必ず検出される
    if t and re.fullmatch(r"[\d,，.lI|Oo]+", t) and re.search(r"[lI|Oo]", t):
        t = t.translate(str.maketrans({"l": "1", "I": "1", "|": "1", "O": "0", "o": "0"}))
    m = AMOUNT_RE.match(t)
    if not m:
        return None
    neg = t[:1] in "△▲-"
    v = int(re.sub(r"[,，.]", "", m.group(1)))
    return -v if neg else v


def lines_of(items, tol=0.6):
    """文字枠を行にまとめる（高さの重なりで判定）。各行は x 順。"""
    rows: list[list[dict]] = []
    for d in sorted(items, key=lambda d: (d["y0"] + d["y1"]) / 2):
        cy = (d["y0"] + d["y1"]) / 2
        if rows:
            last = rows[-1]
            ly0 = min(x["y0"] for x in last)
            ly1 = max(x["y1"] for x in last)
            h = max(ly1 - ly0, d["y1"] - d["y0"], 1)
            if ly0 - h * (1 - tol) <= cy <= ly1 + h * (1 - tol) and abs(cy - (ly0 + ly1) / 2) < h * tol:
                last.append(d)
                continue
        rows.append([d])
    return [sorted(r, key=lambda d: d["x0"]) for r in rows]


def parse_explanations(items):
    """説明欄: 名前の断片を貯め、金額が出たら1件にする。"""
    out, buf, bx = [], [], None
    for row in lines_of(items):
        for d in row:
            a = amount(d["text"])
            if a is not None and (d["x1"] - d["x0"]) < 400:
                out.append({"name": norm_name("".join(buf)), "amount": a, "y": d["y0"], "x": bx})
                buf, bx = [], None
            else:
                if not buf:
                    bx = d["x0"]  # 事項名の書き出し位置（入れ子の内訳は字下げされる）
                buf.append(d["text"])
    rest = norm_name("".join(buf)) if buf else ""
    return out, rest


def parse_setsu(labels, amounts, col_left=None):
    """節: 区分と金額を高さで対応させる。
    節と細節の区別は字下げで行う（細節は内側の枠に入り、列の左端から 30px 以上右に始まる。300dpi・R8 で確認）。
    番号の有無だけで区別すると、名前が2行にわたる節（番号が縦中央に別の文字として読まれる）を細節と誤認する。"""
    lab_lines = lines_of(labels)
    res = []
    for d in sorted(amounts, key=lambda d: d["y0"]):
        a = amount(d["text"])
        if a is None:
            continue
        cy = (d["y0"] + d["y1"]) / 2
        best = min(lab_lines, key=lambda r: abs((min(x["y0"] for x in r) + max(x["y1"] for x in r)) / 2 - cy), default=None)
        label = "".join(x["text"] for x in best) if best else ""
        # 「酬 1報」のように番号の付いた断片が後ろに来ることがあるので、番号はどこにあっても拾う
        mnum = re.search(r"(\d{1,2})", label)
        left = min(x["x0"] for x in best) if best else None
        is_top = (left - col_left < 30) if (col_left is not None and left is not None) else bool(mnum)
        res.append({"label": norm_name(re.sub(r"\d", "", label)), "no": int(mnum.group(1)) if mnum else None,
                    "top": is_top, "amount": a, "y": d["y0"]})
    return res


def cells_of_table(t):
    """表の区画（目の単位）: 表の幅いっぱいの横線で区切る。"""
    x0, top, x1, bottom = t["box"]
    width = x1 - x0
    ys = sorted({d["y"] for d in t["rowlines"] if d["x1"] - d["x0"] > width * 0.9})
    bounds = [t["head"]] + [y for y in ys if y > t["head"] + 10] + [bottom]
    cells = []
    for a, b in zip(bounds, bounds[1:]):
        if b - a < 20:
            continue
        cell = [[d for d in col if a <= (d["y0"] + d["y1"]) / 2 < b] for col in t["cols"]]
        cell_bounds.append((a, b))
        cells.append(cell)
    return cells


cell_bounds: list[tuple[int, int]] = []  # cells_of_table が最後に返した区画の高さの範囲（再 OCR 用）


def first_amount(items):
    for d in sorted(items, key=lambda d: d["y0"]):
        a = amount(d["text"])
        if a is not None:
            return a
    return None


def sum_amounts(items):
    return sum(a for a in (amount(d["text"]) for d in items) if a is not None)


def main():
    ocr_dir, rng = sys.argv[1], sys.argv[2]
    keijou = json.load(open(sys.argv[sys.argv.index("--keijou") + 1], encoding="utf-8")) if "--keijou" in sys.argv else None
    a, b = (int(x) for x in rng.split("-"))
    moku_list: list[dict] = []
    cur_kan = cur_kou = None
    for page in range(a, b + 1):
        path = os.path.join(ocr_dir, f"p{page:04d}.json")
        if not os.path.exists(path):
            print(f"WARN p{page}: OCR 結果がない", file=sys.stderr)
            continue
        page_rec = json.load(open(path, encoding="utf-8"))
        for t in page_rec.get("tables", []):
            rec = page_rec  # 表ごとの補正（縦線の補い）がページの他の表に波及しないよう、毎回ページの元の値から始める
            if len(t["cols"]) == 7:
                # 歳入の表: 0 目 / 1 本年度 / 2 前年度 / 3 比較 / 4 節の区分 / 5 節の金額 / 6 説明
                # 歳出と同じ処理にのせるため、財源の4列を空として差し込む
                t = dict(t)
                c = t["cols"]
                t["cols"] = [c[0], c[1], c[2], c[3], [], [], [], [], c[4], c[5], c[6]]
                t["revenue"] = True
            elif len(t["cols"]) == 10 and len(rec.get("vlines", [])) == 11 and rec["vlines"][9] - rec["vlines"][8] > 500:
                # 節の区分と節の金額の間の縦線が検出できなかった表（R8 p238）。いつもの位置（左端から約 363px）で分ける
                split = rec["vlines"][8] + 363
                t = dict(t)
                c = t["cols"]
                t["cols"] = c[:8] + [[d for d in c[8] if (d["x0"] + d["x1"]) / 2 < split],
                                     [d for d in c[8] if (d["x0"] + d["x1"]) / 2 >= split]] + c[9:]
                rec = dict(rec, vlines=rec["vlines"][:9] + [split] + rec["vlines"][9:])
                print(f"WARN p{page}: 節の列の縦線を補って解釈（x={split}）", file=sys.stderr)
            elif len(t["cols"]) != 11:
                print(f"WARN p{page}: 列数 {len(t['cols'])}（歳出は11列、歳入は7列）", file=sys.stderr)
                continue
            title = "".join(d["text"] for d in t["title"]).replace(" ", "")
            mk = re.search(r"(\d+)款", title)
            if mk:
                cur_kan = int(mk.group(1))
            mq = re.search(r"(\d+)[项項]([^（(]*)", title)
            if mq:
                cur_kou = (int(mq.group(1)), norm_name(mq.group(2)))
            cell_bounds.clear()
            cells = cells_of_table(t)
            for ci, cell in enumerate(cells):
                cy0, cy1 = cell_bounds[ci]
                name_txt = "".join(d["text"] for row in lines_of(cell[0]) for d in row)
                honnen = first_amount(cell[1])
                is_total = norm_name(name_txt) in ("計", "合計") or "計" == norm_name(name_txt)[-1:] and honnen is not None and not re.search(r"\d", name_txt)
                expl, rest = parse_explanations(cell[10])
                vl = rec.get("vlines") or []
                setsu_left = vl[8] if (not t.get("revenue") and len(vl) > 8) else None
                setsu = parse_setsu(cell[8], cell[9], setsu_left)
                if t.get("revenue"):
                    # 歳入の節は列の左端から 45〜52px に印字され、細節はほぼない（R8 で実測）。すべて節として扱う
                    for s in setsu:
                        s["top"] = True
                zaigen = {"国庫支出金": sum_amounts(cell[4]), "地方債": sum_amounts(cell[5]),
                          "その他": sum_amounts(cell[6]), "一般財源": sum_amounts(cell[7])}
                last_moku = next((x for x in reversed(moku_list) if x["kind"] == "目"), None)
                after_total = bool(moku_list) and moku_list[-1]["kind"] == "計"
                if honnen is None and not name_txt.strip() and last_moku is not None and after_total:
                    # 「計」の行の直後なのに目名も本年度も読めない区画＝新しい項の最初の目の読み取り失敗（R8 p239）。
                    # 前の目につなぐと項の合計が狂うので、本年度不明の目として立てる（refill_missing.py の対象になる）
                    print(f"WARN p{page}: 計の行の直後に目名・本年度の読めない区画（新しい目として扱う）", file=sys.stderr)
                elif honnen is None and not name_txt.strip() and last_moku is not None:
                    # 前のページから続く目
                    m = last_moku
                    m["説明"] += expl
                    m["節"] += setsu
                    for k, v in zaigen.items():
                        m["財源"][k] += v
                    m["pages"].append(page)
                    continue
                if is_total:
                    moku_list.append({"kind": "計", "side": "歳入" if t.get("revenue") else "歳出", "款": cur_kan, "項": cur_kou,
                                      "本年度": honnen, "前年度": first_amount(cell[2]), "pages": [page]})
                    continue
                # 目番号は名前の左に縦中央で印字されるので、名前が2行以上だと途中に入る（「市町村連絡2調整費」）
                mno = re.search(r"(\d{1,2})", name_txt)
                moku_list.append({
                    "kind": "目", "side": "歳入" if t.get("revenue") else "歳出",
                    "款": cur_kan, "項": cur_kou, "目番号": int(mno.group(1)) if mno else None,
                    "目名": norm_name(re.sub(r"\d{1,2}", "", name_txt, count=1)),
                    "本年度": honnen, "前年度": first_amount(cell[2]), "比較": first_amount(cell[3]),
                    "財源": zaigen, "節": setsu, "説明": expl, "説明の残り": rest, "pages": [page],
                    "cell": {"page": page, "y0": cy0, "y1": cy1, "x0": (rec.get("vlines") or [0, 0, 0])[1],
                             "x1": (rec.get("vlines") or [0, 0, 0])[2]}})
    # 検算
    for side in ("歳出", "歳入"):
        stat = defaultdict(int)
        for m in moku_list:
            if m["kind"] != "目" or m["side"] != side:
                continue
            h = m["本年度"]
            checks = {}
            if side == "歳出":
                if not m["説明"] and m["説明の残り"] and h is not None:
                    # 説明欄に事項が1つだけで金額の記載がない目（例「○病院事業会計への負担金」、R8 p180 で確認）。
                    # その事項の額は目の額。照合で確かめたものではないので印を付けて別に数える
                    m["説明"] = [{"name": m["説明の残り"], "amount": h, "y": None, "x": None, "金額の記載なし": True}]
                    m["説明の残り"] = ""
                    stat["A金額なし"] += 1
                    checks["A"] = True
                elif not m["説明"] and not m["説明の残り"]:
                    # 説明欄に何も書かれていない目（税交付金・公債費の元金など）。対象外として別に数える
                    m["説明なし"] = True
                    stat["A対象外"] += 1
                    checks["A"] = True
                else:
                    checks["A"] = h is not None and sum(e["amount"] for e in m["説明"]) == h
                    if not checks["A"] and h is not None:
                        # 説明欄は入れ子になることがある（親「中小企業振興資金融資費」の下に字下げした内訳）。
                        # 書き出し位置が最も左の事項から 25px 以内を親とみなし、親だけの合計で照合する
                        xs = [e["x"] for e in m["説明"] if e.get("x") is not None]
                        if xs:
                            left = min(xs)
                            top = [e for e in m["説明"] if e.get("x") is None or e["x"] - left < 25]
                            if sum(e["amount"] for e in top) == h:
                                checks["A"] = True
                                stat["A入れ子"] += 1
                                for e in m["説明"]:
                                    e["内訳"] = not (e.get("x") is None or e["x"] - left < 25)
                checks["B"] = h is not None and sum(m["財源"].values()) == h
            checks["C"] = (h is not None and m["前年度"] is not None and m["比較"] is not None
                           and abs(h - m["前年度"]) == abs(m["比較"]))
            if (h is None and m["前年度"] is not None and not m["説明"] and not m["節"]
                    and m["比較"] is not None and abs(m["比較"]) == m["前年度"]):
                # 本年度の計上がない目（例: 知事選挙費）。「比較 = 前年度」が成り立つときだけ本年度 = 0 とみなす。
                # 成り立たないとき（繰越金: 前年度 34,237・比較 34,236 → 本年度は 1）は読み取り失敗として残す
                h = m["本年度"] = 0
                checks = {k: True for k in checks}
            setsu_top = [s for s in m["節"] if s.get("top", s["no"] is not None)]
            checks["D"] = h is not None and sum(s["amount"] for s in setsu_top) == h
            m["checks"] = checks
            stat["目"] += 1
            for k, v in checks.items():
                stat[k] += int(v)
            if all(checks.values()):
                stat["全部OK"] += 1
        if stat["目"]:
            n = stat["目"]
            print(f"[{side}] 目 {n} 件: " + " / ".join(f"{k} {stat[k]}" for k in ("A", "B", "C", "D") if k in stat or side == "歳出")
                  + (f"（うち A は説明欄が空で対象外 {stat['A対象外']}）" if stat["A対象外"] else "")
                  + (f"（うち A は入れ子の内訳を除いて一致 {stat['A入れ子']}）" if stat["A入れ子"] else "")
                  + (f"（うち A は1事項で金額の記載なし＝目の額を当てた {stat['A金額なし']}）" if stat["A金額なし"] else "")
                  + f" / 全部OK {stat['全部OK']}（{stat['全部OK']/n:.1%}）", file=sys.stderr)
    # 項の「計」の行と目の合計
    acc = defaultdict(int)
    tot_ok = tot_n = 0
    for m in moku_list:
        key = (m.get("side"), m["款"], (m["項"] or (None,))[0])
        if m["kind"] == "目" and m["本年度"] is not None:
            acc[key] += m["本年度"]
        elif m["kind"] == "計":
            tot_n += 1
            ok = acc[key] == m["本年度"]
            tot_ok += int(ok)
            m["check"] = ok
            if not ok:
                print(f"NG  計 {key}: 目の合計 {acc[key]:,} / 計の行 {m['本年度']}", file=sys.stderr)
            acc[key] = 0
    if tot_n:
        print(f"計の行 {tot_n} 件中 {tot_ok} 件一致", file=sys.stderr)
    # 款の合計と計上額調
    if keijou:
        for side, key in (("歳出", "一般会計歳出"), ("歳入", "一般会計歳入")):
            ref = {k["no"]: k for k in keijou[key]["款"]}
            by_kan = defaultdict(int)
            for m in moku_list:
                if m["kind"] == "目" and m["side"] == side and m["本年度"] is not None and m["款"] is not None:
                    by_kan[m["款"]] += m["本年度"]
            for k, v in sorted(by_kan.items()):
                r = ref.get(k)
                ok = r is not None and r["当年度"] == v
                print(f"{'OK  ' if ok else 'NG  '} [{side}] {k}款 {r['款名'] if r else '?'}: 目の合計 {v:,} / 計上額調 "
                      f"{(r['当年度'] if r else 0):,}（差 {((r['当年度'] if r else 0) - v):,}）", file=sys.stderr)
    json.dump(moku_list, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
