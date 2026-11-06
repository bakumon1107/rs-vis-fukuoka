"""福岡県サイト /life/ のカテゴリページを巡回し、掲載ページのタイトルと URL を集める（調査用）。

使い方:
    python3 -I scripts/local-gov/fukuoka-pref/research/crawl_life.py <出力.tsv> 2> crawl.log

出力: TSV（カテゴリのパス, カテゴリのタイトル, ページの URL, リンク文字列）
礼儀: 1リクエスト/秒。robots.txt で禁止されていない /life/<n>/... のカテゴリページのみ巡回する。
他の自治体に使うときは BASE と CAT_RE（カテゴリ URL のパターン）、PAGE_PREFIXES を変える。
手順と結果の読み方: docs/local-gov/knowhow/自治体データ調査の手順.md
"""
import html
import re
import sys
import time
import urllib.request

BASE = "https://www.pref.fukuoka.lg.jp"
UA = "Mozilla/5.0 (compatible; budget-research-crawler)"
CAT_RE = re.compile(r"^/life/\d+/(\d+/)*$")
PAGE_PREFIXES = ("/contents/", "/bid-info/", "/site/", "/gyosei-shiryo/", "/uploaded/")

LINK_RE = re.compile(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)


def fetch(path: str) -> str:
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip()


def main(out_path: str) -> None:
    top = fetch("/life/")
    cats = sorted({h for h, _ in LINK_RE.findall(top) if CAT_RE.match(h)})
    seen = set(cats)
    queue = list(cats)
    rows = 0
    failed: dict[str, str] = {}  # 取れなかったカテゴリ → 最後のエラー
    tries: dict[str, int] = {}
    with open(out_path, "w", encoding="utf-8") as out:
        while queue:
            cat = queue.pop(0)
            time.sleep(1.0)
            try:
                page = fetch(cat)
                failed.pop(cat, None)
            except Exception as e:  # noqa: BLE001
                # 一時的な失敗があるので、列の最後に回して 2回まで取り直す。それでも取れなければ記録して最後に失敗で終える
                tries[cat] = tries.get(cat, 0) + 1
                failed[cat] = str(e)
                print(f"ERR {cat} （{tries[cat]}回目） {e}", file=sys.stderr)
                if tries[cat] < 3:
                    queue.append(cat)
                continue
            m = TITLE_RE.search(page)
            ctitle = clean(m.group(1)) if m else ""
            for href, text in LINK_RE.findall(page):
                href = href.split("#")[0]
                if CAT_RE.match(href):
                    # 下位カテゴリだけを追加（上位・兄弟はトップから既に入っている）
                    if href not in seen and href.count("/") > cat.count("/"):
                        seen.add(href)
                        queue.append(href)
                    continue
                if href.startswith(PAGE_PREFIXES):
                    out.write(f"{cat}\t{ctitle}\t{href}\t{clean(text)}\n")
                    rows += 1
            print(f"ok {cat} queue={len(queue)} rows={rows}", file=sys.stderr, flush=True)
    if failed:
        # 一部のカテゴリが取れていない。TSV は取れた分だけ（不完全）なので、失敗で終える
        for cat, err in failed.items():
            print(f"FAIL {cat} {err}", file=sys.stderr)
        sys.exit(f"{len(failed)} カテゴリを取得できなかった（出力は不完全）")


if __name__ == "__main__":
    main(sys.argv[1])
