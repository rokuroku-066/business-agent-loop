# Business Agent Loop: System Design

## 1. 前提と非機能要件
- **モデル**: `gpt-oss-20b`（約21Bパラメータ、MXFP4 MoE、16GB VRAM想定）。
- **Harmony フォーマット必須**: `system/developer/user/assistant/tools` と `analysis/final` チャンネルを維持。
- **長期記憶**: 埋め込みやベクタDBは使わず、短いサマリ・メタデータ（タグ/スコア）・関連IDリンクで管理。
- **非機能要件**: 24/7 常時稼働（現実的な duty cycle を自分で設定）。Web アクセスや高度な安全フレームワークは必須でないが、違法・暴力系は自前で線引き。設定ファイル変更だけでテーマ差し替え可能にする。

## 2. 全体アーキテクチャ
1. **モデル実行レイヤ**: gpt-oss-20b（HF/vLLM/Ollama/Triton）と Harmony レンダラ&パーサ（`openai-harmony`）。
2. **エージェント・オーケストレータ**: プランナー/クリエイター/クリティック/エディタの役割を切替えてタスク駆動で動作。
3. **設定＆知識レイヤ**: 不変の IP 設定、プロジェクト設定、テンプレート類。
4. **状態＆ストレージ**: `ideas/` `tasks/` `iterations/` `snapshots/` などのテキストベース保存。
5. **インタフェース＆運用**: CLI を最低限用意（start/stop/pause/status/new-theme/review）。ログや簡易ダッシュボードでモニタリング。

## 3. モデル実行レイヤ設計
### 3.1 バックエンドパターン（ローカル推論前提）
- **vLLM サーバ方式**: `vllm serve openai/gpt-oss-20b` で OpenAI 互換API化。`openai-harmony` でレンダ/パース。
- **Ollama 方式**: `ollama pull gpt-oss:20b` で簡便。Harmony のツール呼び出し対応は実装依存。テキスト生成優先なら手軽。
- **公式 Triton/Torch**: 実装自由度は高いが重い。詳細制御したい場合向け。
- **本プロジェクト指針**: 初期は Ollama か vLLM。ツール呼び出し重視になったら vLLM + Harmony へ寄せる。

### 3.2 Harmony メッセージ設計
- `system`: モデルメタ（役割、知識カットオフ、日付、使用チャネルなど）。
- `developer`: 実質システムプロンプト（役割定義、出力フォーマット、ツール定義）。IP設定とプロジェクト設定を毎回ここに挿入。
- `user`: ユーザー入力またはオーケストレータからのタスク指示。

## 4. 設定＆知識レイヤ
### 4.1 不変 IP 設定ファイル（例: `ip_profile.json`）
- IPの芯を定義するコア設定。読み取り専用。
- 例: `ip_name` / `essence` / `visual_motifs` / `core_personality` / `taboos` / `target_audience` / `brand_promise` / `canon_examples`。
- Developer メッセージに「# IP Spec」として埋め込み、ブレない芯を維持。

### 4.2 プロジェクト設定ファイル（例: `project_config.json`）
- テーマごとに変更する設定。
- 例: `project_name` / `goal_type` / `constraints`（予算、法的制約、外部API禁止など）/ `idea_templates` / `iteration_policy`（トークン上限、探索:深化比率、停滞検知パラメータ）。
- 各ループで読み込み、Developer メッセージに「# Project Config」として埋め込む。

## 5. エージェントロール設計
### 5.1 ロール
- **Planner**: ロードマップとタスクキュー管理。週次タスクと新領域探索の提示。
- **Ideator**: 新規ビジネスアイデア生成（ID、ワンライナー、ターゲット、提供価値、収益モデル、差別化、リスク）。
- **Critic**: 評価・比較・弱点抽出（スコア、ボトルネック、改善提案）。
- **Editor**: 有望アイデアを企画書レベルに整形（概要、リソース、スケジュール骨子）。
- いずれも gpt-oss-20b で、Developer メッセージの役割切替で実現。

### 5.2 1ループの標準フロー
1. **タスク選択（Planner）**: Task Queue から高優先度を選択。なければ新タスク生成。
2. **コンテキスト構築**: タスクに紐づくアイデア要約/メタデータと IP/プロジェクト設定をまとめる。
3. **モデル呼び出し**: タスク種別に応じてロール切替。表形式や構造化テキストで出力を強制。
4. **出力パース & 永続化**: 新規は `ideas/` に追加、更新は差分を `change_log` に記録。
5. **停滞チェック**: 後述ロジックで判定。
6. **次タスク生成/更新**: 結果に応じてキューを更新。

## 6. 状態＆ストレージ設計（非ベクタ）
### 6.1 ディレクトリ構成イメージ
- `config/`: `ip_profile.json`（不変）、`project_config.json`。
- `state/`: `tasks.json`、`iteration_state.json`。
- `ideas/`: `ideas.jsonl`（ID付き）、`ideas_index.json`（タグ・スコア）。
- `iterations/`: `YYYYMMDD_HHMM_iteration.json`（1ループログ）。
- `snapshots/`: `YYYYMMDD_portfolio.md`（レビュー用まとめ）。

### 6.2 アイデアデータ構造（例）
- `id` / `title` / `summary` / `target_audience` / `value_proposition` / `revenue_model`
- `brand_fit_score` / `novelty_score` / `feasibility_score` / `status` / `tags`
- summary, tags, scores を検索キーとし、関連アイデアIDでタスクと紐づける。

### 6.3 タスクデータ構造（例）
- `id` / `type`（generate/refine/compare/snapshot など） / `priority` / `related_idea_ids`
- `status`（ready/running/done/blocked） / `created_at` / `last_run_at` / `meta`

## 7. 停滞・ループ防止
### 7.1 差分チェック
- 埋め込みなしでテキスト類似度を推定（単語集合の共有率など）。
- 類似度が閾値以上（例 0.9）で同じ更新が連続したら `stalled`。代わりに `shake_up_idea` タスクを生成し、「過去と異なる方向性を複数提示」などの制約を付与。

### 7.2 探索 vs 深化モード
- Scheduler がループごとにモード決定。プロジェクト設定の探索:深化比率を使用。
- 停滞時は探索比率を上げ、散漫になったら深化比率を上げる。

### 7.3 メタ自己評価
- 一定ループごとにスナップショット要約を評価。
- 繰り返し・多様性・ブランドぶれを確認し、停滞時は新フレームワーク/視点を提案させる。
- スコアの平均・分散など定量情報は Python 側で計算して提示すると甘さを抑制。

## 8. ユーザーインタフェース＆運用
### 8.1 CLI コマンド例
- `agent start`（24/7 ループ開始、バックグラウンド化）
- `agent stop`（state 保存して終了）
- `agent status`（ループカウンタ、モード、タスク数）
- `agent review`（最新スナップショットを Markdown で表示）
- `agent new-theme --config ...`（プロジェクト設定差し替え）

### 8.2 人間レビュー挿入
- 一定ループごとに `snapshots/` にまとめを生成し、人間がレビュー。
- レビュー済みフラグや手動補正スコアを付け、次フェーズで優先度に反映。
