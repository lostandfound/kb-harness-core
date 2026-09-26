# 考察メモ: 型（エンティティの種類）を標準化するか

2026-09-26 のディスカッションの記録。[述語を詳細度で層に分ける](jutsugo-kaisou-memo.md)と[フィールドのプリセット化](field-preset-memo.md)の続き。問いは「述語とフィールドは整理したが、`Person` や `Event` という型そのものは標準化されているか。標準エンティティと呼ぶべきものは要るか」。

結論は「**上位 6 型の名前と意味と対応だけを文書で定める。検査もプリセットもしない。併せて、コードに焼き込まれていた特定 KB の `Person` を消す**」。契約は[設定リファレンス](../configuration.md#標準型)が正本で、このメモは判断の経緯を残す。

## 現状

- ハーネスが機構として予約している型名は `Index`（ディレクトリの索引）と `Claim`（`kb-ontology-core` の関係主張）の 2 つだけ。設定リファレンスは「型名は導入先が自由」と言っていた。
- 一方で `entity.py` の `SECTIONS_BY_TYPE` に `Person` / `Style` / `Kata` / `Term` / `HistoricalEvent` / `Note` が章立てごと焼き込まれていた。`Person` の既定は「概要・生涯・系譜（師と弟子）・功績」で、沖縄空手 KB の残滓である。`sections` を書かない `Person` にはこの章立てが降っていた。`born` / `died` を名前で特別扱いする正規表現も同じ系統である。
- 「標準は無い」と言いながらコードには特定ドメインの `Person` が隠れていた。標準化されていない状態の中で最も悪い形である。

## 標準型を置くべきか

述語のときと同じ物差しで判断する。名前を読む消費者が KB をまたいで存在するか。

- 検証器・ビュー・doctor は型名を読まない。ディレクトリ対応と `domain` / `range` は KB の内側で閉じる。ここは[フィールドのメモ](field-preset-memo.md)の再考で述べたとおりで、名前を固定する必要は無い。
- 見落としが一つあった。**標準述語は標準型を暗黙に前提にしている。** `created-by` の range は主体、`located-in` の range は場所であり、KB が束縛を書くには Person / Organization / Place に当たる型を持っていなければならない。名前を定めずに述語だけ標準化したので、束縛の書き方が KB ごとに発散する。
- もう一つの消費者は交換である。`graph.json` と OKF は型名をそのまま通す。二つの KB を突き合わせる側や RDF に落とす側は、同じ名前か対応表を要る。述語に `maps_to` を置いたのと同じ理由が型にもある。

したがって置くものは「上位型の推奨表と標準語彙への対応」であり、「フィールドや章立てまで含むプリセット」ではない。

## 上位 6 型

独立に設計された語彙が同じところに収束している。schema.org の Thing 直下、CIDOC-CRM の主要クラス、Wikidata の上位項目はいずれも「人・集団・場所・出来事・作品・概念」に分かれる。述語の層 1 と同じく、収束していること自体が安定の証拠である。

| 推奨名 | schema.org | CIDOC-CRM | Wikidata |
|---|---|---|---|
| `Person` | Person | E21 Person | Q5 human |
| `Organization` | Organization | E74 Group | Q43229 organization |
| `Place` | Place | E53 Place | Q17334923 geographic location |
| `Event` | Event | E5 Event | Q1190554 occurrence |
| `Work` | CreativeWork | E71 Human-Made Thing | Q386724 work |
| `Concept` | Intangible | E28 Conceptual Object | Q151885 concept |

- `Dish` / `Kata` / `Script` のような細かい型は述語の層 2 に相当し、導入先が任意で足す。ただし型には `broader` を置かない。型の継承は `domain` / `range` の継承を連れてきて検証器が重くなる。推奨型の細分なら（`Kata` は `Work` の細分）`description` に一言書けば足り、どの推奨型にも入らない型（`Dish`）があってもよい。
- 非標準の型名を `kb doctor` が警告することもしない。型は述語より導入先固有になりやすく、`Dish` を `Work` に押し込む方が害が大きい。
- `maps_to` は型にはまだ置かない。読む側（RDF 出力、KB の突合）ができた時点で述語と同じ形で足す。`graph.json` に `predicates` を出しているのと対になる `types` を出せばよい。

## 併せて直したこと

`SECTIONS_BY_TYPE` を消し、`sections` を宣言しない型はすべて 概要 / 詳細 / 関連項目 にした。影響は `kb entity create` と `scripts/new_entity.py` だけで、`kb validate` は章立てを見ない。既定に依存していた導入先は `vocabulary.yml` の `sections` に既存エンティティと同じ章立てを書く。omnibus-kb がまさにそれで、`Person`（概要・生涯・系譜（師と弟子）・功績）と `Note`（概要・本文・関連項目）は既定に乗っていたので、語彙に `sections` を足した。沖縄空手 KB は `Person` / `Style` / `Kata` について同じ移行が要る。

`born` / `died` の名前による特別扱いは残した。フィールドのメモに書いたとおり、次に validation を触るときに外す。

## 未決事項

- 型の `maps_to` を足す時点。OKF 出力に IRI を併記する設計と一緒に決める。
- `Organization` と `Place` を持つ KB がまだ無い。omnibus-kb は `worksFor` を落として本文に書いたが、組織をノードにしたくなった時点で `Organization` を足し、`part-of` の層 2 に `member-of` を吊るす形になる。

## 参照

- schema.org Thing https://schema.org/Thing
- CIDOC CRM class hierarchy https://cidoc-crm.org/
- Wikidata Q5 / Q43229 / Q17334923 / Q1190554 / Q386724 / Q151885
