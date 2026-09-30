---
name: find-book
description: NDL サーチ（国立国会図書館）API で書籍・資料を検索し、文献レジストリ references.yml に登録する手順。「書籍を探して」「NDLで検索」「書誌を確認して」で使用。論文検索は find-paper（CiNii）を使う。
---

ナレッジベースの出典として書籍・単行資料を探し、文献レジストリに登録するときは以下の手順を実行する。規約の正本は `CONTRIBUTING.md` の sources 節。まずリポジトリルートの `kb-domain.yml` を読み、`domain.content_root` を把握する。

1. `python3 apm_modules/lostandfound/kb-harness-core/scripts/ndl_search.py "<検索語>" --count 5 --format json > <作業用ディレクトリ>/search-result.json` を実行する（作業用ディレクトリはリポジトリ外のスクラッチ領域。`search-result.json`・`reference.yml` はリポジトリに含めない）。API は認証不要。ノイズが多い場合は `--title-only` でタイトル検索に絞る。雑誌は `--mediatype periodicals`。人向けの登録案が必要なら `--format yaml`（既定）を使う。

2. 出力される references.yml 登録案から、対象エンティティの主張を実際に裏付けられそうな文献を選ぶ。タイトルだけで判断できない場合は URL（NDL サーチの書誌ページ）を取得して内容を確認する。

3. 登録前に `kb reference search --url <URL>`（DOI があれば `--doi <DOI>`、書籍はタイトルや著者名の語句）で既存エントリを確認する。同じ資料が既にあればその ID を使い、新規登録はしない。

4. JSON 出力は `kb reference spec --from search-result.json --output reference.yml --dry-run`（いずれも作業用ディレクトリ内のパス）で決定論的な spec に変換し、内容を確認してから `kb reference create --from reference.yml --dry-run` で登録差分を確認する。登録 ID は規約に沿って編集する（著者ローマ字姓-年、例: `miyagi-1934`。仮 ID は必ず直す）。他の資料と由来を共有する資料（同じ流派・学派の伝承、同じ記事の別言語版や転載、当事者の自己発信など）には任意キー `lineage` を付ける。単位の例は `kb-domain.yml` の `domain.lineage_example`、既存ラベルは `kb reference search --field lineage <ラベル>` で確認し綴りを揃える。由来を共有しないと判断できたら `lineage: 系統外`、判断がつかなければ省略する（未記載は未判定の意味）。フィールドは確認できた値のみ書く。`<content_root>/references.yml`（content_root は `kb-domain.yml` の `domain.content_root`）への反映は `kb reference create --from reference.yml` を使う。

5. 出典として使うエンティティの `sources` に `- "ref: <id>"` を追記する。本文の主張は必ず自分の言葉で書く。資料本文・スキャンのファイルは `content_root` 配下に保存しない。パブリックドメインが確認できた資料の翻刻テキストを別途保存する場合は、置き場所・可否とも導入先が独自に定める規約（CONTRIBUTING.md 等）に従う。ハーネスの `kb-domain.yml` はコーパスの置き場所を持たない。

6. `kb validate` でエラーゼロ、URL を登録した場合は `kb validate --check-urls --ref <登録した ID>` も実行する（出典を追記したエンティティがあれば `--for <そのパス>` でもよい）。

7. コミットする。pre-commit hook が最終検証を行う。
