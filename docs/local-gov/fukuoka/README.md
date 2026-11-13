# 福岡県

福岡県版の調査・設計メモ。データの出どころ、資料の癖、取得手順など福岡県固有の情報をまとめる。
調査の一般的な手順は [../knowhow/自治体データ調査の手順.md](../knowhow/自治体データ調査の手順.md)。

- 計画書と公開データの棚卸し（資料ごとの URL・形式・中身の一覧）: [../tasks/20261106_0122_福岡県予算ビュー計画書.md](../tasks/20261106_0122_福岡県予算ビュー計画書.md) の2章
- 行政評価（事務事業評価）の構造化データ: `mirai-gikai-fukuoka-pref` リポジトリの `docs/data/jimu-jigyo/`（抽出ツール `tools/jimu-jigyo-pdf/`）

## 入口ページ早見表

サイト: `https://www.pref.fukuoka.lg.jp`（以下はパスのみ）

| 知りたいこと | 入口 |
|---|---|
| 財政の全体 | `/life/8/54/`（予算 `/life/8/54/243/`・決算 `/life/8/54/244/`・財政改革 `/life/8/54/245/`） |
| 予算議案・予算に関する説明書（H25〜） | `/contents/yosanngiann.html` |
| 当初予算の編成概要・計上額調・施策別資料（H21〜） | `/contents/hennseigaiyou.html`、年度別 `/contents/r8-2026.html` |
| 事務事業の見直し結果 | `/contents/08zimuzigyou.html`（年度で URL が変わる: `07zimuzigyou`・`06jigyouminaoshi`…） |
| 決算書・事項別明細書・決算概要説明書・主要施策の成果 | `/contents/kessan.html` |
| 決算及び財政状況の公表（H19〜） | `/contents/kessan-zaiseijoukyou.html` |
| 財政事情の公表（年2回） | `/contents/zaiseijijou.html` |
| 財政状況資料集（Excel） | `/contents/zaiseijyoukyoushiryou-r6.html` |
| 決算カード（H13〜） | `/contents/kessancard.html` |
| 財務書類 | `/contents/zaimusyorui.html` |
| 固定資産台帳（Excel） | `/contents/koteisisandaityour6nenndo.html` |
| 行政評価（R3〜） | `/contents/gyouseihyouka-01.html`、過年度 `/gyosei-shiryo/gyouseihyoukarepo-to-0N.html` |
| 決算審査意見書（H22〜） | `/contents/kesankansakekka-sochi.html` |
| 包括外部監査（H22〜） | `/contents/houkatugaibukansakekka-sochi.html` |
| 入札結果 | `/life/8/63/277/`（建設工事は四半期ごと `/contents/kohyo...html`） |
| 特命随意契約 | `/life/8/56/256/` → `/contents/tokumei2025.html` 等 |
| 指定管理者 | `/contents/sitei-kanrisya.html`、管理運営状況報告 `/contents/shiteikanrihoukoku06.html`（R2〜R6） |
| 外郭団体・出資法人 | `/contents/kousyatou-gaikaku-danntai2.html`、`/contents/syussihoujin.html` |
| 補助事業（分野別） | 農業 `/life/4/36/157/`・林業 `/life/4/37/164/`・水産業 `/life/4/38/169/`、事業者向けの入口 `/life/9/70/` |
| オープンデータ | `/contents/opendata.html` → BODIK `https://odcs.bodik.jp/400009/`（予算・決算はない） |

## 資料の癖（福岡県固有）

- 添付ファイルの URL は `/uploaded/attachment/<番号>.pdf` と `/uploaded/life/<ページ番号>_<番号>_misc.pdf` の2系統。番号から内容は推測できないので、掲載ページから取る。
- **予算に関する説明書は R8・R7 ともスキャン画像**（R8: 150dpi カラー、R7: 300dpi 白黒）。一般会計は「PDF ページ = 印字ページ + 8」。款の扉ページと白紙ページが挟まる。
  - R8 一般会計の印字ページ: 総括 3〜、歳入 7〜112、歳出 113〜412、給与費明細書 413〜、債務負担行為 437〜、地方債 469〜
  - R8 特別会計・公営企業会計（別ファイル）: 特別会計 475〜600、公営企業会計 601〜770
- **決算（R6）の書類はテキスト PDF**。事項別明細書は1円単位で、見出しの文字が二重に出る。
- 編成概要の施策別資料・計上額調・見直し一覧は Excel から出力したテキスト PDF で、そのまま抜き出せる。
- 指定管理者の報告書は施設ごとに金額の書き方が違う（「指定管理料」「委託料実績額」、円／千円）。評価は「○」が付いた行。
- 部局名は年度で変わる（例: 行政評価の担当課は R8.4 から「行政経営企画課」→「行政マネジメント課」）。

## 調査の記録

| 日付 | 内容 |
|---|---|
| 2026-11-06 | 財政ページ・行政評価・予算説明書・編成概要・決算書類・入札・随意契約・指定管理者・監査・外郭団体・固定資産台帳・決算カード・オープンデータを確認。結果は計画書2章 |
| 2026-11-14 | 歳出の財源内訳と歳入の款の差（R8 一般会計）。物価高騰対応重点支援地方創生臨時交付金・調整債・財政調整基金繰入金・減債基金繰入金・特別会計繰入金などは、財源内訳では一般財源に数えられている。会計ごとの収支・特別会計の財源内訳・会計間の繰出金と繰入金はすべて一致 → [調査](20261114_0005_財源内訳と歳入の款の差の調査.md) |
