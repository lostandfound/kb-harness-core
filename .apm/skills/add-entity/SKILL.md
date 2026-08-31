---
name: add-entity
description: KB に新規エンティティを追加する確定的手順。「エンティティ追加」「新しいエンティティ（人物・概念等）を追加」で使用。
---

ナレッジベース（ドメイン定義はルートの `kb-domain.yml`）に新規エンティティを追加するときは、以下の手順を順番に実行する。
規約の正本は `CONTRIBUTING.md` と `<content_root>/vocabulary.yml`（content_root は `kb-domain.yml` の `domain.content_root`）であり、本スキルには規約の値（述語の一覧・必須フィールドの詳細・値域など）を書かない。着手前に必ず `kb-domain.yml`・`CONTRIBUTING.md`・`vocabulary.yml` を読むこと。

1. `python3 scripts/new_entity.py <type> <slug>` で雛形ファイルを生成する。`type` に使える値はコマンドのヘルプ（`--help`）が正。`slug` はローマ字ケバブケース。

2. 生成されたファイルの TODO をすべて埋める。雛形にあるフィールドはすべて必須（TODO を残すと検証で落ちる）。`title` は日本語、`description` は 1〜2 文、`tags` は `<content_root>/vocabulary.yml` の一覧から選ぶ（新タグが必要なら一覧を先に更新）。本文はだ・である調で、確定していない史実は「〜とされる」のように諸説がある旨を明示する。人物の生没年など事実データは WebSearch で裏取りし、情報源が食い違う場合は断定表記を避ける（表記方法は CONTRIBUTING.md 参照）。

3. 他エンティティとの `relations` を張る。使える述語とその型制約（domain/range）は `<content_root>/vocabulary.yml` の `predicates` 定義が正。エッジは一方向のみ（逆向き・重複は検証で落ちる）。該当する関係がなければ省略してよい。口碑・伝承・単一系統源のみに基づくエッジには optional key `confidence: C` を付与する（省略時は独立2源以上を意味するため、確度が満たない場合は必須。詳細は CONTRIBUTING.md 7節）。

4. `sources` には実在が確認できた文献のみを記載する。URL を含める場合は WebSearch や WebFetch で実在を確認してから記載し、書誌情報は確実なもののみ書く。争いのある主張（生没年・制定者・師事・系譜の対立や単一源依拠）には、本文の当該箇所に `（出典: <ref-id>）` を付与できる（形式・運用は CONTRIBUTING.md §8「主張単位の出典」が正）。考証（shiryo-kosho）を経た場合は、その結果が示す説ごとの ref-id をそのまま使う。

5. `python3 scripts/generate_index.py` を実行し、対応する `index.md` を更新する（index の一覧は手で編集しない）。

6. `python3 scripts/validate.py` を実行し、エラーがゼロであることを確認する。`sources` に URL を含めた場合は `python3 scripts/validate.py --check-urls` も実行する。エラーが出たら、その内容が現行規約の正であり、本スキルや自分の記憶と食い違う場合は検証側に従う。

7. コミットする。最終検証は pre-commit hook が行う。
