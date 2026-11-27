# 予算ビュー＠福岡県

福岡県の予算・決算を、会計・款・項・目のサンキー図と基金の推移でたどる**非公式**のビューアです。

**サイト: https://bakumon1107.github.io/yosan-view-fukuoka-pref/**

> このサービスは政党チームみらいが運営しているものではありません。
> 数字は福岡県が公開している予算書・決算書等をもとにこのサイトで加工したものです。正確な数字は原資料をご確認ください。

---

## 見られるもの

| 画面 | 内容 |
|---|---|
| サンキー図 | 当初予算（令和8年度）・補正後予算（令和8年度。6月・8月専決・9月の補正を足したもの）・決算（令和6年度）を切り替えて、お金の流れをたどる |
| 　一般会計 | 予算は 財源 → 款 → 項 → 目 → 説明欄の事項、決算は 部局 → 款 → 項 → 目 → 節。「一般財源」の中身、選んだ範囲の人件費の割合 |
| 　全会計 | 歳入の款 → 会計 → 款 → 項 → 目。全会計の純計（会計間の繰入れを除いた額） |
| 　公営企業会計 | 収入 → 会計・条（収益的・資本的） → 支出の項 → 目。資本的収支の不足を埋める補填財源 |
| 基金 | 基金ごとの残高の推移 |
| データについて | 数字の作り方・検算の方法と結果・使った資料の一覧 |

## 数字の作り方

- 福岡県の「予算に関する説明書」（スキャン画像の PDF）を文字認識（OCR）で読み取り、目ごとの本年度・前年度・財源内訳・節・説明欄の事項を取り出しています。決算・基金はテキスト PDF（古い年度の基金は画像の OCR）から取り出しています
- 金額は資料に印字された数字（千円単位）を円に直したもので、**推計や按分はしていません**
- 読み取った数字は、目ごとの合計・財源内訳・節の合計と、予算書の本体（議案）・当初予算計上額調の額との突き合わせで検算しています。結果はサイトの「データについて」に載せています
- 名前の読み誤りは、複数の読み取りの突き合わせと、原本の画像での確認で直しています

### 使っている資料（福岡県）

- 当初予算に関する説明書（一般会計／特別会計・公営企業会計）、一般会計予算及び特別会計予算（議案）、当初予算計上額調
- 補正予算議案・補正予算に関する説明書
- 歳入歳出決算事項別明細書・決算概要説明書
- 実質収支・財産に関する調書（基金の現在高）
- 名前の確かめに: 当初予算の概要・編成概要・施策別資料・決算に係る主要施策の成果に関する説明書 など

資料ごとの URL はサイトの「データについて」と `public/data/local-gov/fukuoka-pref/index.json` にあります。

---

## 開発

本家「[政府予算ビュー](https://github.com/team-mirai-volunteer/rs-vis)」（国の予算の可視化。AGPL-3.0）のフォークです。
地方版のページだけを静的サイトとして書き出し、GitHub Pages に置いています（国版のページ・API は書き出しに含めません）。

```bash
npm ci
npm run dev        # 開発サーバー → http://localhost:3000/local/fukuoka-pref
npm run lint && npm run typecheck && npm test

# 福岡県版の静的書き出し（公開と同じもの）
NEXT_PUBLIC_SITE_EDITION=local NEXT_PUBLIC_LOCAL_GOV_ID=fukuoka-pref NEXT_PUBLIC_BASE_PATH=/yosan-view-fukuoka-pref npx next build
node scripts/local-gov/assemble-pages.mjs   # 公開物を out/ に組み立てる（国のデータなどを外す）
```

`npm run build` は国のデータを展開する（prebuild）ので、福岡県版では使いません。

| 場所 | 中身 |
|---|---|
| `app/local/[gov]/`・`app/lib/local-gov/`・`client/components/local-gov/` | 地方版の画面・グラフの組み立て・部品 |
| `app/*.local.tsx`・`next.config.local.ts` | 福岡県版の静的書き出しの入口（`*.local.tsx` だけがページになる） |
| `app/lib/local-gov/site.ts` | 名前・運営者・連絡先・配色などのサイト設定 |
| `scripts/local-gov/fukuoka-pref/` | 資料の取り出し（PDF・OCR）・名前の確かめ・検算・書き出しと回帰テスト |
| `public/data/local-gov/fukuoka-pref/` | 公開データ（JSON） |
| `.github/workflows/pages-local.yml` | CI（型チェック・lint・テスト・書き出し）と GitHub Pages へのデプロイ |
| `docs/local-gov/` | 方針・ブランチ運用・設計・調査・ノウハウ |

- 地方版の方針・ブランチ運用・版の切り替え: [docs/local-gov/README.md](docs/local-gov/README.md)
- 福岡県の資料の癖とデータの作り方: [docs/local-gov/fukuoka/](docs/local-gov/fukuoka/)
- ブランチは `local-main` が本流です（`main` は本家のミラー）。`local-main` へのマージで公開し直されます

### 本家（国版）のコードについて

本家の改善を取り込み続けるため、国版のコード（`app/` の国版のページ・API、`scripts/` の国のデータの生成など）はそのまま残しています。
福岡県版の書き出しには含まれず、公開もしていません。国版の説明は[本家の README](https://github.com/team-mirai-volunteer/rs-vis#readme) を見てください。

---

## ライセンス・運営

- ライセンス: [GNU Affero General Public License v3.0](LICENSE)（本家と同じ）
- 運営: バクモン（連絡先: [X @bakumon0907](https://x.com/bakumon0907)）
- 利用規約・プライバシーポリシーはサイトのフッターから
