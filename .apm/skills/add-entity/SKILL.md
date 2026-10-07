---
name: add-entity
description: KB に新規エンティティを追加する確定的手順。「エンティティ追加」「新しいエンティティ（人物・概念等）を追加」で使用。
---

ナレッジベース（ドメイン定義はルートの `kb-domain.yml`）に新規エンティティを追加するときは、以下の手順を順番に実行する。
規約の正本は `CONTRIBUTING.md` と `<content_root>/vocabulary.yml`（content_root は `kb-domain.yml` の `domain.content_root`）であり、本スキルには規約の値（述語の一覧・必須フィールドの詳細・値域など）を書かない。着手前に必ず `kb-domain.yml`・`CONTRIBUTING.md`・`vocabulary.yml` を読むこと。

反映は `kb entity create` で行う。エンティティ本体・各型の `index.md`・ルートの `graph.json` を一度に原子的に更新し、事前検証に失敗すればファイルを書き換えずに停止する（`kb` が未導入なら CONTRIBUTING.md の導入手順で入れる）。雛形を手で編集する旧手順（`python3 apm_modules/lostandfound/kb-harness-core/scripts/new_entity.py`）を使う場合は、手順 7 の `kb sync` を必ず実行する。`graph.json` はチェックイン済みで CI が `kb sync --check` で陳腐化を検出するため、index だけ更新して graph を忘れると CI が落ちる。

1. 追加する型と slug を決める。`type` に使える値と各型の必須・任意フィールド（`extra_fields` / `optional_fields`）・本文セクション（`sections`）は `<content_root>/vocabulary.yml` の `types` 定義が正。`slug` はローマ字ケバブケース。

2. 作業用ディレクトリ（リポジトリ外のスクラッチ領域）に spec ファイル `entity.yml` を書く。書式は手順 3 の規則に先に目を通してから書く。必須キーは `type` / `slug` / `title` / `description` / `tags` / `sources` / `sections`、任意キーは `aliases` / `relations` / `fields`（型固有フィールド。例: born / died / founded_year）/ `timestamp`。`sections` は「見出し → 本文」のマッピングで、その型に定義された見出しを過不足なく含める。spec のキー・必須条件の契約は `apm_modules/lostandfound/kb-harness-core/docs/configuration.md` の「エンティティ spec」節が正。失敗時は診断メッセージが個々の違反を示す。

3. 作り直しの典型原因になる書式を次の規則で、書く前に避ける（`kb entity create` / `kb validate` が拒否する書式。正本は `apm_modules/lostandfound/kb-harness-core/docs/configuration.md` の「エンティティ spec」節）。
   - `title` に括弧 `(` `)` `（` `）` を入れない。「ジャガイモ（馬鈴薯）」「Python（言語）」のような曖昧さ回避・読み仮名・原綴り・別名は title から外し、別名は `aliases`、区別の説明は `description` か本文に書く。同名で衝突するときも括弧で逃げず、`〜の人物` のように語を足して別の名前にする。`slug` は小文字 ASCII のケバブケースのみ。
   - `title` / `description` / `aliases` / `tags` / `sources` / `fields` の文字列値は、すべて二重引用符で囲む（`title: "Re:ゼロから始める異世界生活"`）。コロン＋空白（`: `）、` #`、先頭の `-` `?` `[` `{` `&` `*` `!` `|` `>` `'` `"` `%` `@` `` ` ``、`yes` / `no` / `null` / 数字だけの値は、引用符が無いと YAML が構文エラーにするか別の型に解釈する。値の中に `"` を含めるときは `\"` とする。`sections` の本文は `|` のブロックで書き、引用符を使わない。
   - spec を書いたら、`--dry-run` の前に `python3 -c 'import yaml,sys; yaml.safe_load(open(sys.argv[1]))' entity.yml` で構文だけ確かめてもよい。実際の検査は手順 7 の `--dry-run` が全項目を行うので、エラーが出たら診断のとおり spec を直して `--dry-run` からやり直す（slug や他ファイルは作り直さない）。

4. spec の中身を埋める。`title` は日本語、`description` は 1〜2 文、`tags` は `<content_root>/vocabulary.yml` の一覧から選ぶ（新タグが必要なら一覧を先に更新）。本文の文体は CONTRIBUTING.md に従い、確定していない事実は諸説がある旨を明示する。日付・数値・帰属など事実データは Web 検索で裏取りし、情報源が食い違う場合は断定表記を避ける（表記方法は CONTRIBUTING.md 参照）。導入先に懸念台帳（`kb-domain.yml` の `concerns.root`）があり、食い違い・単一系統の出典・孫引き・値の選択（どちらの年を `fields` に書いたか等）が残った場合は、手順 7 でエンティティを作った後、それを懸念として `<concerns.root>/<slug>-<要点>.yml` に書く。`targets` には作ったエンティティ（`/dir/file.md`）と関わる出典（`ref: <id>`）を、`kind` と `status` は `apm_modules/lostandfound/kb-harness-core/docs/configuration.md` の「懸念台帳」節の語彙から選ぶ（本文で両論を併記したなら `settled-hedged` と `resolution`）。書いた後に `kb sync` を実行する。作業の予定（関連エンティティの追加など）は懸念にしない。

5. 他エンティティとの `relations` を張る。使える述語とその型制約（domain/range）は `<content_root>/vocabulary.yml` の `predicates` 定義が正。エッジは一方向のみ（逆向き・重複は検証で落ちる）。該当する関係がなければ省略してよい。単一源や同一系統の資料のみに基づくエッジには optional key `confidence: C` を付与する（省略時は独立2源以上を意味するため、確度が満たない場合は必須。詳細は CONTRIBUTING.md の確度の規定）。

6. `sources` には実在が確認できた文献のみを記載する。`references.yml` に新規登録する出典は、登録前に `kb reference search --url <URL>`（語句でも可）で既存エントリを確認し、同じ由来の資料（同じ記事の別言語版・転載、当事者の自己発信など。単位の例は `kb-domain.yml` の `domain.lineage_example`）には既存ラベルに揃えた `lineage` を付ける。URL を含める場合は Web 検索やページの取得で実在を確認してから記載し、書誌情報は確実なもののみ書く。争いのある主張（説の対立や単一源依拠）には、本文の当該箇所に `（出典: <ref-id>）` を付与できる（形式・運用は CONTRIBUTING.md の「主張単位の出典」が正）。導入先のドメイン固有の考証を経た場合は、その結果が示す説ごとの ref-id をそのまま使う。

7. `kb entity create --from entity.yml --dry-run` で生成される差分（エンティティ本体・index.md・graph.json）を確認し、問題がなければ `kb entity create --from entity.yml` で反映する。既存 slug と衝突する場合は上書きせず停止するので、slug を見直す。旧手順で雛形を手編集した場合は、代わりに `kb sync` を実行して index と graph を更新する（index の一覧は手で編集しない）。

8. `kb validate` を実行し、エラーがゼロであることを確認する。`sources` に URL を含めた場合は `kb validate --check-urls --for <追加したエンティティのパス>` も実行する（KB 全体の URL を確かめると時間がかかり、無関係な既存出典の ERROR が混ざる）。エラーが出たら、その内容が現行規約の正であり、本スキルや自分の記憶と食い違う場合は検証側に従う。続けて `kb sync --check` が差分なし（終了コード 0）であることを確認する。

9. コミットする。最終検証は pre-commit hook が行う。spec ファイルはリポジトリに含めない。
