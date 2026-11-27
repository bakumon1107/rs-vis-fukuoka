"""公営企業会計の予算実施計画の款・項・目の名前を決め、名前の出典の印を付ける。

設計: docs/local-gov/tasks/20261121_0100_公開前のサンキー図の足しと公営企業会計の設計.md 4.2
実施計画（特別会計の説明書の後半）の文字層は発行元が付けたもので、額は正しい（予算書の本体と一致）が名前が崩れている
（「建設改良費」→「建云比又几改良費」など）。名前を次の順で決める:

1. 修正表（ocr/corrections/r8-kigyo-names.json。原本の画像で確かめた名前）にあれば、その名前（出典 correction）
2. 文字層の名前が、同じページの新 OCR（ocr/ocr_lines.py）の行と同じか、款・項なら予算書の本体
   （extract_yosansho.py の条文の款・項を番号で対応させたもの。発行元の本物の文字）と同じなら、そのまま（出典 readings）。
   新 OCR の行は、続く3行までをつないだもののうち、金額のある行をちょうど1つ含むもの（ocr_lines）
3. どちらでもなければ止める（画像で確かめて修正表に足す）

この比べ方は粗いふるいで、名前が正しいことの保証は画像の確認にある:
- 比べる形（norm）は空白・数字・中黒・点を除くので、「償還元金」と「償還金」は別だが、中黒の有無の違いは見逃す
- 2行の名前で金額が上の行にあると、上の行だけ（名前のかけら）も一致に見える
R8 は17ページすべての名前を画像で見比べ、そうしたものも修正表に入れた。別の年度を取り込むときも、ページが少ないので全部を画像で見る。
抽出（extract_kigyo_jisshi.py）の失敗（kigyo.json の fails）はそのまま失敗に引き継ぐ。fails のない kigyo.json（古い出力）は止める。

使い方:
    python3 -P scripts/local-gov/fukuoka-pref/kigyo_names.py <kigyo.json> <yosansho.json> <OCR の行のディレクトリ>... > kigyo-named.json
    （修正表は ocr/corrections/r8-kigyo-names.json）
出力: kigyo.json と同じ形で、款・項・目に name（決めた名前）・name_src・name_read（文字層の読み。直したときだけ）を付けたもの
"""
import glob
import json
import os
import re
import sys
import unicodedata

# 新 OCR が簡体字で読む字を日本の字に寄せる（比べるときだけ。名前そのものは文字層か修正表から取る）
GLYPHS = str.maketrans({"资": "資", "减": "減", "损": "損", "债": "債", "产": "産", "產": "産", "营": "営", "设": "設", "费": "費", "单": "単"})
SECTIONS = {"収益的収入及び支出": 3, "資本的収入及び支出": 4}
# OCR の行の金額（款・項・目の行には予定額がある）。行の頭の款・項・目の番号（1〜2桁）は除いてから探す。
# 金額の後に説明の文字が続く行・金額だけの行もあるので、末尾に限らない
LEAD_NO = re.compile(r"^\s*\d{1,2}(?!\d|,)")
HAS_AMOUNT = re.compile(r"\d")


def norm(s: str) -> str:
    """比べるための形（全角半角・簡体字をそろえ、空白・数字・括弧・中黒・点を除く）"""
    s = unicodedata.normalize("NFKC", s).translate(GLYPHS)
    return re.sub(r"[\s\d,()（）．.・]", "", s)


def ocr_lines(text: str) -> set[str]:
    """OCR のページの文字 → 比べる形にした行の集まり（行は「番号 名前 金額」なので、比べる形にすると名前だけが残る）。
    行に分かれた名前（「支払利息及び／企業債取扱諸費」「流域下水道管理費／負担／金」）のため、続く3行までをつないだものも入れる。
    ただし、金額のある行をちょうど1つ含むものだけ（1つの款・項・目の行。名前だけの行のかけら・2つの目にまたがるつなぎは入れない）"""
    # 名前は金額より前だけ（後ろの説明の文字は名前に付けない）。金額だけの行（名前が空）も、金額の印として残す
    lines = []
    for line in text.splitlines():
        body = LEAD_NO.sub("", line)
        m = HAS_AMOUNT.search(body)
        name = norm(body[:m.start()] if m else body)
        if name or m:
            lines.append((name, bool(m)))
    out = set()
    for k in (1, 2, 3):
        for i in range(len(lines) - k + 1):
            win = lines[i:i + k]
            joined = "".join(n for n, _ in win)
            if joined and sum(has for _, has in win) == 1:
                out.add(joined)
    return out


def load_ocr(dirs: list[str]) -> dict[int, set[str]]:
    """OCR の行のディレクトリ（done.json のあるもの）→ {PDF のページ: 比べる形にした行の集まり}。同じページが2つのディレクトリにあれば止める"""
    pages: dict[int, set[str]] = {}
    for d in dirs:
        if not os.path.exists(os.path.join(d, "done.json")):
            raise SystemExit(f"{d} に done.json がない（OCR が終わっていない）")
        for f in sorted(glob.glob(os.path.join(d, "p*.txt"))):
            page = int(os.path.basename(f)[1:5])
            if page in pages:
                raise SystemExit(f"p{page} の OCR が2つのディレクトリにある（{d}）。ページの範囲が重ならないように OCR し直す")
            pages[page] = ocr_lines(open(f, encoding="utf-8").read())
    return pages


def decide(kigyo: dict, yosansho: dict, fixes: list[dict], pages: dict[int, set[str]]) -> tuple[dict, list[str], dict]:
    """名前を決める。pages は load_ocr の形（ページ → ocr_lines の行の集まり）。返り値: (名前を付けた kigyo, 失敗, 出典の数)"""
    if not isinstance(kigyo.get("fails"), list):
        # 抽出が fails を書くようになる前の kigyo.json は、抽出が失敗していたかが分からない
        return kigyo, ["kigyo.json に fails がない（古い抽出の出力。extract_kigyo_jisshi.py で作り直す）"], {"readings": 0, "correction": 0}
    fails: list[str] = [f"実施計画の抽出: {f}" for f in kigyo["fails"]]
    counts = {"readings": 0, "correction": 0}
    fix_at = {(f["会計"], f["page"], f["段"], f["読み"]): f for f in fixes}
    used: set = set()
    yo = {a["会計"]: a.get("条", {}) for a in yosansho["会計"]}

    def name_of(acc: str, level: str, node: dict, yo_name: str | None):
        read = node["name"]
        key = (acc, node["pdf_page"], level, read)
        if key in fix_at:
            used.add(key)
            node["name"], node["name_src"], node["name_read"] = fix_at[key]["名前"], "correction", read
            counts["correction"] += 1
        elif norm(read) and (norm(read) in pages.get(node["pdf_page"], set()) or (yo_name is not None and norm(read) == norm(yo_name))):
            node["name_src"] = "readings"
            counts["readings"] += 1
        else:
            fails.append(f"{acc} p{node['pdf_page']} {level}「{read}」: 新 OCR の読み・予算書の本体と合わない（画像で確かめて修正表に足す）")

    for a in kigyo["会計"]:
        acc = a["会計"]
        for sec, art in SECTIONS.items():
            for side in ("収入", "支出"):
                yo_kans = {k["no"]: k for k in yo.get(acc, {}).get(str(art), yo.get(acc, {}).get(art, {})).get(side, [])}
                for kan in a.get(sec, {}).get(side, []):
                    yo_kan = yo_kans.get(kan["no"])  # 番号で対応させる（並びの位置では、款が欠けたとき隣の款と比べてしまう）
                    name_of(acc, "款", kan, yo_kan["name"] if yo_kan else None)
                    yo_kous = {k["no"]: k for k in (yo_kan or {}).get("項", [])}
                    for kou in kan.get("項", []):
                        yo_kou = yo_kous.get(kou["no"])
                        name_of(acc, "項", kou, yo_kou["name"] if yo_kou else None)
                        for m in kou.get("目", []):
                            name_of(acc, "目", m, None)
    fails += [f"修正表の行が使われていない {k}" for k in sorted(set(fix_at) - used)]
    return kigyo, fails, counts


def main():
    kigyo_path, yo_path, *ocr_dirs = sys.argv[1:]
    fix_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ocr", "corrections", "r8-kigyo-names.json")
    kigyo = json.load(open(kigyo_path, encoding="utf-8"))
    yosansho = json.load(open(yo_path, encoding="utf-8"))
    fixes = json.load(open(fix_path, encoding="utf-8"))["修正"]
    named, fails, counts = decide(kigyo, yosansho, fixes, load_ocr(ocr_dirs))
    for f in fails:
        print("FAIL " + f, file=sys.stderr)
    print(f"公営企業会計の名前: 2つの読みが一致 {counts['readings']}・修正表 {counts['correction']}。FAIL={len(fails)}", file=sys.stderr)
    named["fails"] = fails
    json.dump(named, sys.stdout, ensure_ascii=False, indent=1)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
