# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

このリポジトリは「**予算ビュー＠福岡県**」（福岡県の予算・決算の非公式ビューア。https://bakumon1107.github.io/yosan-view-fukuoka-pref/ ）。
本家「政府予算ビュー」（team-mirai-volunteer/rs-vis。国の予算）のフォークで、地方版のページだけを静的サイトとして GitHub Pages に公開している。
国版のコードは本家の取り込みのために残しているが、公開していない（下の「国版のコード」）。

## Quick Reference

```bash
npm run dev              # Dev server（localhost:3000。地方版は /local/fukuoka-pref）
npm run lint             # ESLint チェック
npm run typecheck        # TypeScript 型チェック（データ展開不要）
npm test                 # 単体テスト（地方版・国版）

# 福岡県版の静的書き出し（公開と同じ）。npm run build は国のデータを展開するので使わない
NEXT_PUBLIC_SITE_EDITION=local NEXT_PUBLIC_LOCAL_GOV_ID=fukuoka-pref NEXT_PUBLIC_BASE_PATH=/yosan-view-fukuoka-pref npx next build
node scripts/local-gov/assemble-pages.mjs   # 公開物を out/ に組み立てる

# 福岡県のデータの回帰テスト（元の PDF・OCR は Git 管理外の作業フォルダ。FUKUOKA_DATA で指す）
FUKUOKA_DATA=<作業フォルダ> python3 -P scripts/local-gov/fukuoka-pref/tests/regression.py
python3 -m pytest scripts/local-gov/fukuoka-pref/tests
```

## Architecture

**公開ページ（福岡県版）**: `/local/fukuoka-pref`（サンキー図。見方は 一般会計・全会計・公営企業会計、基準は 当初予算・補正後予算・決算）、`/local/fukuoka-pref/funds`（基金）、`/local/fukuoka-pref/about`（データについて）、`/terms`・`/privacy`。トップ `/` はサンキー図へ移るだけ。

**版の切り替え**: `NEXT_PUBLIC_SITE_EDITION=local` のときだけ `next.config.local.ts` が静的書き出し（`output: 'export'`・`pageExtensions: ['local.tsx','local.ts']`・basePath）にする。ページになるのは `*.local.tsx` だけ。本家のファイルで変えているのは `next.config.ts` の末尾 2 行と、この README.md・CLAUDE.md だけ。詳細は `docs/local-gov/README.md`。

### Layer Design Rules

| Layer | Directory | 役割 |
|-------|-----------|------|
| Data Pipeline | `scripts/`（地方版は `scripts/local-gov/`） | データ処理（CSV・PDF・OCR・検算・書き出し）。UIやAPIロジック禁止 |
| Domain Logic | `app/lib/`（地方版は `app/lib/local-gov/`） | Pure なグラフ生成・集計。HTTP・React禁止 |
| API Layer | `app/api/` | HTTPハンドラ（国版のみ。福岡県版は API を使わない） |
| UI Components | `client/components/` / `components/` | 再利用可能UI。直接APIコール禁止 |
| Client State / IO | `client/hooks/` / `client/lib/` | UI状態・ブラウザIO・データ取得 |
| Pages | `app/*/page.tsx`（地方版の入口は `*.local.tsx`） | 状態管理・データ取得・レイアウトのみ |
| Types | `types/`（地方版は `types/local-gov.ts`） | 全レイヤー共通の型定義 |

### Critical Notes（地方版）

- **データ単位**: 公開データ（`public/data/local-gov/<自治体>/*.json`）の金額は **1円単位**。資料の千円単位を ×1000 して持つ
- **推計しない**: 帯の値は資料に印字された数字の合計だけ。按分しない。値・名前には出典の印（`src`・`name_src`）を付ける
- **公営企業会計**は全会計の見方・純計に入れない（`kind: 'enterprise'` を外して数える）。描くのは公営企業会計の見方だけ
- **データの作り方**は `docs/local-gov/fukuoka/`。データを作り直したら回帰テストの差分を確かめてから期待値を書き換える
- **Import alias**: `@/*` はリポジトリルートにマップ（例: `@/types/local-gov`）

## Deployment

**公開先: GitHub Pages**（https://bakumon1107.github.io/yosan-view-fukuoka-pref/ ）。`local-main` への push で `.github/workflows/pages-local.yml` が
型チェック・lint・テスト・静的書き出しをしてデプロイする（PR では確認だけ）。basePath とサイトの URL は Pages の設定から取る。
本家の CI（`.github/workflows/checks.yml`）はこのフォークでは Actions の設定で無効（国版のビルド・e2e は CI で確かめない）。
GA は読み込まない（`NEXT_PUBLIC_GA_MEASUREMENT_ID` を明示したときだけ）。Vercel・Supabase・AI 機能は使わない。

## ブランチ運用

- `main` は本家のミラー（直接変更しない）。本流は `local-main`（既定ブランチ）。作業は `local-main` から worktree（`../rs-vis-fukuoka-<短い名前>`）で切ったブランチで行い、PR でマージする
- 本家の取り込み: `main` を同期 → `main` → `local-main` の PR。`README.md`・`CLAUDE.md` が衝突したらフォーク側を残す。取り込んだら PR の `pages-local.yml` で地方版の書き出しが通るかを確かめる
- 本家（upstream）への push・PR はしない。本家の問題は `docs/local-gov/本家指摘候補.md` に記録する

## Agent の行動ルール

- **PR は必ずユーザーの明示的な許可を得てから作成すること。** 実装・修正が完了しても、ユーザーから「PR を出してください」「PR お願いします」などの指示がない限り、自律的に PR を作成・プッシュしてはならない。
- コミットは実装完了のタイミングで行ってよいが、プッシュ・PR 作成は指示待ちとする。
- 元の PDF・資料・OCR の結果はコミットしない（Git 管理外の作業フォルダに置く）。

## Documentation Standards

- **地方版の Task docs**（設計・調査・実装計画）: `docs/local-gov/tasks/YYYYMMDD_HHMM_タイトル.md`
- **地方版の恒久的な文書**: `docs/local-gov/README.md`（方針・運用）、`docs/local-gov/knowhow/`（自治体をまたぐノウハウ）、`docs/local-gov/<自治体>/`（自治体固有）
- 本家の `docs/tasks/`・`docs/*.md` は国版の文書（地方版の文書は置かない）

## 国版のコード（本家由来。公開しない）

国版のページ（`/budget-sankey`・`/quality` など）・API・データ生成（`scripts/` の国のデータ）・Supabase・AI 機能・`infra/terraform/` は本家のもの。
本家の取り込みで変わるので、地方版の作業では原則として触らない。触るときの約束事（本家の CLAUDE.md より）:

- 国版のデータ単位も **1円単位**。「その他」（支出先名）と「その他の支出先」（TopN以外の集計）は別ノード
- 支出先が同一事業の複数ブロックに出現する場合、`projects.find()` ではなく `projects.filter().reduce()` で金額を合算する
- `.gz` を Git 管理し、`npm run build` の prebuild で展開する
- `.claude/skills/` の `/sankey`・`/pipeline`・`/data-update` は国版用
- 国版の説明・デプロイ（Vercel）は本家の README と CLAUDE.md（https://github.com/team-mirai-volunteer/rs-vis ）を見る
