"""R8 一般会計の歳出の目ごとに、財源内訳「その他」の欄の（財源の名前, 金額）を取り出す（調査用）。

説明書の財源内訳の「その他」の欄には、財源の名前（諸収入・使用料及び手数料など）と金額が組で印字される（名前の下に金額）。
OCR 結果（ocr_pages.py の出力）の列6 から組を取り、解釈の結果（parse_setsumeisho.py の出力）の目の欄の範囲で目に振り分ける。
目の欄の範囲は、目の cell（最初のページ・上端）から次の目の cell の始まりまで（ページをまたぐ）。
R8 では 232目のうち 228目で、名前付きの金額の合計が財源内訳のその他の額と一致する（残り4目も差は千円単位の数件）。
調査: docs/local-gov/fukuoka/20261114_0005_財源内訳と歳入の款の差の調査.md 3.3

使い方:
    python3 -I scripts/local-gov/fukuoka-pref/research/funding_other_by_moku.py <setsumeisho-ocr.json> <ocr/r8-ippan> > funding-other.json
"""
import json
import re
import sys

NORM = {'使用料及': '使用料及び手数料', 'び手数料': None, '分担金及': '分担金及び負担金', 'び負担金': None, 'び负担金': None,
        'U負担金': None, '諸取入': '諸収入', '手数料': '使用料及び手数料'}


def main():
    with open(sys.argv[1], encoding='utf-8') as f:
        parsed = json.load(f)
    ocrdir = sys.argv[2]
    moku = [m for m in parsed if m.get('kind') == '目' and m['side'] == '歳出' and m.get('cell')]
    starts = sorted(((m['cell']['page'], m['cell']['y0']), i) for i, m in enumerate(moku))

    def owner(page, y):
        cur = None
        for (p, y0), i in starts:
            if (p, y0) <= (page, y + 5):
                cur = i
            else:
                break
        return cur

    out = {i: [] for i in range(len(moku))}
    orphan = []
    for p in sorted({p for m in moku for p in m['pages']}):
        with open(f'{ocrdir}/p{p:04d}.json', encoding='utf-8') as f:
            rec = json.load(f)
        for t in rec['tables']:
            if len(t['cols']) != 11:
                continue
            lab = None
            for x in sorted(t['cols'][6], key=lambda x: (x['y0'], x['x0'])):
                s = x['text'].replace(' ', '')
                if re.fullmatch(r'[\d,]+', s):
                    v = int(s.replace(',', ''))
                    i = owner(p, x['y0'])
                    if lab and i is not None:
                        out[i].append((lab, v, p))
                    elif lab:
                        orphan.append((p, lab, v))
                    lab = None
                else:
                    k = NORM.get(s, s)
                    if k:
                        lab = k
    res = [{'款': m['款'], '項': m['項'][0] if m['項'] else None, '目': m['目番号'], '目名': m['目名'], '款名': m['款_見出し'],
            'その他': m['財源']['その他'], '名前付きの合計': sum(v for _, v, _ in out[i]), '内訳': out[i]}
           for i, m in enumerate(moku)]
    json.dump({'目': res, '持ち主なし': orphan}, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
