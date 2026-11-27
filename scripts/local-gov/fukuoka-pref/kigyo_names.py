"""公営企業会計の予算実施計画の款・項・目の名前を決め、名前の出典の印を付ける。

設計: docs/local-gov/tasks/20261121_0100_公開前のサンキー図の足しと公営企業会計の設計.md 4.2
実施計画（特別会計の説明書の後半）の文字層は発行元が付けたもので、額は正しい（予算書の本体と一致）が名前が崩れている
（「建設改良費」→「建云比又几改良費」など）。名前を次の順で決める:

1. 修正表（ocr/corrections/r8-kigyo-names.json。原本の画像で確かめた名前）にあれば、その名前（出典 correction）
2. 文字層の名前が、同じページの新 OCR（ocr/ocr_lines.py）の読みに含まれるか、款・項なら予算書の本体（extract_yosansho.py の
   条文の款・項。発行元の本物の文字）と同じなら、そのまま（出典 readings）
3. どちらでもなければ止める（画像で確かめて修正表に足す）

注意: 2 の「含まれる」は、名前の途中で切れた・字の欠けた文字層の名前も一致に見える（「償還元金」の行に「償還金」が含まれる）。
R8 は17ページすべての名前を画像で見比べ、そうしたものも修正表に入れた。別の年度を取り込むときも、ページが少ないので全部を画像で見る。

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
GLYPHS = str.maketrans({"资": "資", "减": "減", "损": "損", "债": "債", "產": "産", "营": "営", "设": "設", "费": "費", "单": "単"})
SECTIONS = {"収益的収入及び支出": 3, "資本的収入及び支出": 4}


def norm(s: str) -> str:
    """比べるための形（全角半角・簡体字をそろえ、空白・数字・括弧・中黒・点を除く）"""
    s = unicodedata.normalize("NFKC", s).translate(GLYPHS)
    return re.sub(r"[\s\d,()（）．.・]", "", s)


def load_ocr(dirs: list[str]) -> dict[int, str]:
    """OCR の行のディレクトリ（done.json のあるもの）→ {PDF のページ: 比べる形にしたページの文字}"""
    pages = {}
    for d in dirs:
        if not os.path.exists(os.path.join(d, "done.json")):
            raise SystemExit(f"{d} に done.json がない（OCR が終わっていない）")
        for f in glob.glob(os.path.join(d, "p*.txt")):
            pages[int(os.path.basename(f)[1:5])] = norm(open(f, encoding="utf-8").read())
    return pages


def decide(kigyo: dict, yosansho: dict, fixes: list[dict], pages: dict[int, str]) -> tuple[dict, list[str], dict]:
    """名前を決める。返り値: (名前を付けた kigyo, 失敗, 出典の数)"""
    fails: list[str] = []
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
        elif norm(read) and (norm(read) in pages.get(node["pdf_page"], "") or (yo_name is not None and norm(read) == norm(yo_name))):
            node["name_src"] = "readings"
            counts["readings"] += 1
        else:
            fails.append(f"{acc} p{node['pdf_page']} {level}「{read}」: 新 OCR の読み・予算書の本体と合わない（画像で確かめて修正表に足す）")

    for a in kigyo["会計"]:
        acc = a["会計"]
        for sec, art in SECTIONS.items():
            for side in ("収入", "支出"):
                yo_kans = yo.get(acc, {}).get(str(art), yo.get(acc, {}).get(art, {})).get(side, [])
                for i, kan in enumerate(a.get(sec, {}).get(side, [])):
                    yo_kan = yo_kans[i] if i < len(yo_kans) else None
                    name_of(acc, "款", kan, yo_kan["name"] if yo_kan else None)
                    for j, kou in enumerate(kan.get("項", [])):
                        yo_kou = yo_kan["項"][j] if yo_kan and j < len(yo_kan["項"]) else None
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
