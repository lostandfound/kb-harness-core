# 考察メモ: 懸念台帳を構造化し、目的外の利用を検証で拒む

2026-09-29 のディスカッションの記録。課題の置き場（ファイルか GitHub Issues か）を検討する中で、導入先の運用ファイル `docs/CONCERNS.md` と `docs/BACKLOG.md` の考え方を整理し直した。問いは「CONCERNS を目的外に使えないよう、構造化と検証で運用を厳密にできないか」。

結論は「**懸念を `kb-domain.yml` の `concerns.root` 配下に 1 件 1 YAML で置き、実在するエンティティか出典 ID を必ず指させ、`kb validate` で検査する。一覧は `kb sync` が生成する**」。契約は [設定リファレンス](../configuration.md) の「懸念台帳」節が正本である。このメモは判断の経緯を残す。

## 二つの台帳の役割

文書上の定義と、導入先（omnibus-kb）での実際の使い方がずれていた。

| | 文書の定義（integration.md §8、雛形の冒頭文） | omnibus-kb での実際 |
|---|---|---|
| CONCERNS | 未整理の懸念や違和感の受信箱。着手を決めたら BACKLOG へ移す | 出典・内容の懸念。ほぼすべてがエンティティか出典に結びつき、`settled-hedged` のように解決しないまま状態として残る |
| BACKLOG | 実施すると判断した将来作業の正本 | 作業の予定と、経緯つきの作業ログ（`[x]` の行）。収録タスク・運用タスク・RAG 評価の欠落・探索候補 |

使い始めた意図は後者であり、定義を実態に合わせる。

- **CONCERNS は、KB の知識の確からしさの台帳である。** 行は特定のエンティティか出典に結びつき、「やること」ではなく知識の状態を表す。決着しない（両論併記で記述側は完了）ことも正常な終わり方である。本文と同じコミットで更新され、evidence-reviewer が読む。
- **BACKLOG は、KB を作る作業の予定と記録である。** 懸念が作業を生んだら、BACKLOG 側は出所に懸念を書くだけにする。「CONCERNS から BACKLOG へ移す」流れは廃し、参照関係にする。

## 観察された問題

omnibus-kb の `docs/CONCERNS.md`（2026-09-29 時点、22 件）を `scripts/concerns_summary.py` で集計し、行頭の対象欄を分類した。

| 状態 | 件数 |
|---|---|
| open | 14 |
| blocked-source | 1 |
| settled-hedged | 5 |
| resolved | 2 |

| 対象欄の書き方 | 件数 |
|---|---|
| エンティティの slug 1 つ（パスではない） | 15 |
| `tidb / cockroachdb` のような複数の slug | 2 |
| `references.yml`（出典 ID は本文の中） | 2 |
| `靴・ブーツのブランド群`（集合の名前） | 2 |
| `prompt-engineering ほか 5 件`（列挙していない） | 1 |

- 対象欄は `:` の前の文字列を切り出しているだけで、実在を確かめていない。エンティティが改名・削除されても懸念は黙って宙に浮く。
- 対象が集合名や「ほか 5 件」のとき、どのエンティティの懸念かを機械的に引けない。evidence-reviewer がエンティティ単位で懸念を拾えない。
- `靴・ブーツのブランド群` の 2 件は、型の選び方（Concept か Organization か）とタグの付け方で、出典や内容の懸念ではない。モデリングの判断が受信箱の定義に乗って入り込んだ。
- ハーネスのスキル自身が目的外の記録を促している。`audit-harness` は「信頼性に関わる未整理の問題」を、`expand-kb` は「解消先がまだ分からない違和感」を CONCERNS に残させる。前者はハーネス文書の不整合を KB の内容の台帳へ入れる。
- 検査は `status:` の語彙だけで、それも `scripts/concerns_summary.py` の中にしかない。`kb validate` は台帳を見ない。

## 対応の選択肢

**形式**

- (a) Markdown の 1 行形式のまま、`<対象>: <本文> kind: <種別> status: <状態>` の文法を厳しくし、`kb validate` で検査する。移行が最も楽。
- (b) 1 件 1 YAML を `concerns.root` 配下に置き、一覧を `kb sync` が生成する。ビュー（`views.root`）と同じ作り。
- (c) エンティティのフロントマターに `concerns:` を持たせる。

**対象の制約**

- (d) 対象を必須にし、実在するエンティティ（content_root 相対の `/dir/file.md`、ビューの member と同じ表記）か `ref: <id>` に限る。
- (e) 対象を任意にし、書いたときだけ実在を確かめる。

**種別**

- (f) 懸念の種別を語彙で固定する: `conflict`（出典どうしの食い違い）、`weak-source`（出典が単一系統しかない、弱い）、`indirect`（孫引きで原典と照合していない）、`unreachable`（出典を取得できない）、`judgment`（値や系統を選んだ判断の根拠）。
- (g) (f) に `modeling`（型・境界・タグの判断）を加える。

## 判断

- **今やる: (b)。** 対象が複数ある懸念と、出典 ID を構造として持てる。1 件 1 ファイルなので並列セッションの追記で衝突しない。ビューと同じ置き方・同じ一覧生成の作法に揃えられ、導入先が覚えることが増えない。
- **今やる: (d)。** 目的外の利用を構造で拒む核である。結びつく先の無いもの（作業、ハーネスの問題、漠然とした違和感）は書けない。改名・削除で宙に浮いた懸念も ERROR で見つかる。`Index` 型は対象にできない。
- **今やる: (f)。** 未知のキーも ERROR にし、作業の予定や議論を載せる余地を残さない。状態ごとに必須の欄を課す（`resolved` と `settled-hedged` は `resolution`、`blocked-source` は待っている資料 `awaiting`、`suspended` は再開条件 `resume_when`）。状態の語彙は既存の 6 値をそのまま使う。
- **仕組みは opt-in にする。** `kb-domain.yml` に `concerns.root` を書いた KB でだけ有効になる。有効な KB に旧来の `docs/CONCERNS.md` が残っていれば WARNING を出す。`scripts/concerns_summary.py` は、`concerns.root` があれば新しい API を呼ぶ互換入口にし、無ければ従来どおり Markdown を集計する。
- **スキルの行き先を直す。** `audit-harness` の不整合は監査結果で報告するだけにする。モデリングの判断は `review-entity-model` の出力とし、作業にするなら BACKLOG に書く。`expand-kb` の「違和感」は、対象が特定できるものだけを懸念にし、それ以外は BACKLOG に書く。
- **見送る: (a)。** 対象が複数ある懸念と出典 ID を行の中で構造として持てず、`tidb / cockroachdb` のような書き方の解釈を検査側に抱えることになる。再開条件は、YAML の手書きが導入先で負担になり、行形式への要望が出たとき。
- **見送る: (c)。** 出典だけに関わる懸念（`lineage` の推定など）の置き場が無い。懸念の更新がエンティティの `updated` を動かし、本文の変更と区別できなくなる。
- **見送る: (e)。** 対象の無い懸念を許すと、受信箱の定義に戻る。
- **見送る: (g)。** モデリングの判断は出典や内容の確からしさではなく、`review-entity-model` の守備範囲である。omnibus-kb の該当 2 件はどちらも解決済みで、移行で困らない。再開条件は、導入先で対象の特定できるモデリングの懸念が繰り返し行き場を失ったとき。
- **見送る: 移行コマンド。** 旧形式の行は種別を持たず、対象欄も解釈が要るので、機械的な変換は不正確になる。omnibus-kb の 22 件は手で移す。

## 実装の記録

2026-09-29 に判断どおり (b)(d)(f) を実装した。

- `src/kb_harness/concerns.py` に読み込み・検査・一覧の描画を置いた。`kb validate` / `kb sync` / 一時 KB での全体検証（`staging.py`）から呼び、`scripts/concerns_summary.py` は `concerns.root` があればこの API を呼ぶ互換入口にした。旧来の Markdown の集計は、未移行の導入先のためにスクリプトに残した。
- `kb-domain.yml` の `views:` 節の解決を `_generated_section()` に切り出し、`concerns:` 節も同じ制約（リポジトリの内側、`content_root` の外、一覧は `.md`）で解決する。加えて、`views` と同じパスを禁じた。ビューの読み込みは `views.root` 直下の `*.yml` を全部拾うので、同じディレクトリに置くと懸念がビューとして読まれる。
- `kb concern list / summary / validate` を足した。`list --for` はメモの未決事項に挙げた evidence-reviewer 向けの入口を兼ねる。エンティティは `/dir/file.md` と、`content_root` 内のファイルパスの両方を受ける（`kb validate --for` / `kb reference show --for` がファイルパスを受けるのに合わせた）。
- 当初の判断から変えた点: 「状態ごとに必須の欄」に加え、その欄を他の状態で書くことも ERROR にした。`resolved` から `open` に戻したときに古い `resolution` が残ると、一覧が「対応済み」と読めてしまうためである。
- 当初の判断から変えた点: 「`Index` 型は対象にできない」は、一覧（`index.md`）がそもそもエンティティとして読まれないため、「存在しない」の ERROR で表れる。専用の検査は置かなかった。
- スキルは audit-harness / expand-kb / explore-kb / ndl-digicolle / review-entity-model の記述を改めた。review-entity-model の分類 `CONCERNS に送る` は `保留（判断材料が足りない）` に替えた。
- 追補: 最初の実装では evidence-reviewer と add-entity が台帳に触れていなかった（evidence-reviewer は説明文で「懸念台帳の確認に使用」とうたうだけだった）。evidence-reviewer は対象の既存の懸念を `kb concern list --for` で読み、確度 C / D のうち本文の修正で解消しないものを懸念の YAML 案として報告するようにした。ファイルは書かせず、反映は依頼元が行う（報告に徹するレビュアーの役割を保つ）。add-entity は、執筆時に残った食い違いや値の選択を、作成したエンティティを対象とする懸念として書くようにした。これで未決事項に置いていた「evidence-reviewer への組み込み」は決着した。
- omnibus-kb の写しで確かめた。`concerns.root` を足すと `docs/CONCERNS.md` について WARNING が出た。対象の無い懸念（`OLAP キューブを追加する`）は `targets` 必須の ERROR で拒まれた。Paxos と グッドイヤーウェルトの 2 件を移すと、`kb validate` と `kb sync --check` が通った。omnibus-kb の 22 件の移行は、ハーネスのリリース後に導入先で行う。

## 未決事項

- **Claim との関係。** `kind: conflict` は Claim の `disputed` と重なって見える。Claim は主張そのもの、懸念は根拠の状態についての注記で層が違うと見て別に置いたが、同じ食い違いを両方に書く運用が生まれたら整理が要る。
- **GitHub Issues との関係。** 懸念は Issues に出さない（本文と同じコミットで更新されるべき）。Issues と重なりうるのは BACKLOG の未着手のうち外から来る要望だけで、その同期ツールは別の論点として残す。
