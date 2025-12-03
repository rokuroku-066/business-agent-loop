# Business Agent Loop

本プロジェクトは、gpt-oss-20b と Harmony フォーマットを用いてビジネスアイデアを継続生成・評価するエージェント基盤です。IP プロファイルとプロジェクト設定を読み込み、タスクキューを回しながらアイデアの生成・批評・編集を自動化します。

## 特徴
- **ロール切替型エージェント**: Planner / Ideator / Critic / Editor の役割をモデルプロンプトで切り替え、タスク種別に応じた出力を得ます。
- **テキストベースの永続化**: ベクタDBを使わず、`ideas/` `state/` `iterations/` `snapshots/` などに JSON / Markdown で履歴を保存します。
- **停滞防止ロジック**: 反復が類似しすぎる場合に探索比率を上げたり、新しい方向性を要求するタスクを自動生成します。
- **CLI 最低限対応**: ストレージ初期化やステータス確認、ダミーのイテレーション記録を行うサブコマンドを提供します。

## ディレクトリ構成
- `config/`: `ip_profile.json`（不変のIP設定）と `project_config.json`（テーマごとの制約やポリシー）
- `src/business_agent_loop/`: エージェントの実装と CLI エントリポイント
- `ideas/` `iterations/` `snapshots/` `state/`: ループ実行時に生成される成果物や状態
- `docs/`: システムデザイン (`DESIGN.md`)
- `tests/`: pytest ベースのテスト

## 環境セットアップ
GPU 付き Linux/WSL を想定していますが、CPU 環境でもフォルダ構成やインタフェースは同じです。

1. Python 3.10+ を用意し、リポジトリ直下で仮想環境を作成して有効化します。
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. 依存パッケージをインストールします（`uv` 利用を推奨）。
   ```bash
   uv pip install --upgrade pip
   uv pip install --pre 'vllm==0.10.1+gptoss' \
       --extra-index-url https://wheels.vllm.ai/gpt-oss/ \
       --extra-index-url https://download.pytorch.org/whl/nightly/cu128 \
       --index-strategy unsafe-best-match
   uv pip install openai-harmony openai gpt-oss
   ```
   `scripts/setup_gpt_oss_env.sh` が存在する場合はそちらを優先してください。
3. ローカル推論サーバーを起動する場合は `./scripts/run_vllm_server.sh` を利用します。

## 使い方（CLI）
`src/business_agent_loop/cli.py` に最低限の CLI が用意されています。仮想環境を有効化した状態で以下のように実行してください。

```bash
python -m business_agent_loop.cli --base-dir . --config-dir ./config start
python -m business_agent_loop.cli status
python -m business_agent_loop.cli record-iteration --mode explore
```

## 開発・テストのヒント
- コードスタイル: Black で整形し、ruff の警告を確認してください。
- テスト: 変更後は可能な範囲で `pytest` を実行します。
- モジュール追加や依存変更を行う際は、既存の設定ファイルを更新し、プロジェクト構造を崩さないようにしてください。
