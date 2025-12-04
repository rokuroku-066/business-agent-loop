#!/usr/bin/env bash
# gpt-oss-20b + vLLM + Harmony 用 開発環境セットアップスクリプト
# 対象: Ubuntu / Debian 系 Linux + NVIDIA GPU (16GB VRAM 以上推奨)

set -euo pipefail

PROJECT_DIR=${1:-"$HOME/pikarin-gpt-oss-agent"}

echo "=== gpt-oss 開発環境セットアップ開始 ==="
echo "プロジェクトディレクトリ: ${PROJECT_DIR}"
echo

# ------------------------------
# 1. OS チェック
# ------------------------------
if ! command -v apt-get >/dev/null 2>&1; then
  echo "[ERROR] このスクリプトは Ubuntu / Debian 系 (apt-get) 専用です。" >&2
  exit 1
fi

# ------------------------------
# 2. システム依存パッケージ
# ------------------------------
echo "[1/6] システム依存パッケージをインストールします..."

sudo apt-get update
sudo apt-get install -y \
  python3 python3-venv python3-pip python3-dev \
  build-essential git curl

PYTHON_VERSION=$(python3 - << 'PY_EOF'
import sys
print(".".join(map(str, sys.version_info[:3])))
PY_EOF
)

echo "  検出した Python バージョン: ${PYTHON_VERSION}"
echo "  ※ vLLM の gpt-oss 対応版は主に Python 3.10 / 3.11 で検証されています。"
echo "    3.12 だと vLLM の wheel がまだ提供されない場合があるので要注意です (https://wheels.vllm.ai/gpt-oss/ を確認してください)。"
echo

# ------------------------------
# 3. uv のインストール
# ------------------------------
echo "[2/6] uv (高速 Python パッケージマネージャ) をインストールします..."

if ! command -v uv >/dev/null 2>&1; then
  # 公式インストール手順: https://docs.astral.sh/uv/getting-started/installation/
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # 典型的なパスを PATH に追加
  export PATH="$HOME/.local/bin:$PATH"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "[ERROR] uv コマンドが見つかりません。ターミナルを再起動するか、PATH を確認してください。" >&2
  exit 1
fi

echo "  uv バージョン: $(uv --version)"
echo

# ------------------------------
# 4. プロジェクトディレクトリ & venv
# ------------------------------
echo "[3/6] プロジェクトディレクトリと仮想環境を作成します..."

mkdir -p "${PROJECT_DIR}"
cd "${PROJECT_DIR}"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "  仮想環境 .venv を有効化しました。"
echo

# ------------------------------
# 5. Python パッケージのインストール
# ------------------------------
echo "[4/6] vLLM / Harmony / OpenAI SDK / gpt-oss ヘルパーをインストールします..."

# pip を念のため更新
uv pip install --upgrade pip

# gpt-oss 対応版 vLLM をインストール
# gpt-oss 公式 README の vLLM 手順に基づく: https://github.com/openai/gpt-oss#run-locally-with-vllm
uv pip install --pre 'vllm==0.10.1+gptoss' \
  --extra-index-url https://wheels.vllm.ai/gpt-oss/ \
  --extra-index-url https://download.pytorch.org/whl/nightly/cu128 \
  --index-strategy unsafe-best-match

# Harmony / OpenAI SDK / gpt-oss ヘルパーをインストール (PyPI 公開パッケージ)
uv pip install openai-harmony openai gpt-oss

echo
echo "  Python パッケージのインストール完了。"
echo

# ------------------------------
# 6. プロジェクト構造の作成
# ------------------------------
echo "[5/6] プロジェクト用ディレクトリ構造を作成します..."

mkdir -p config state ideas iterations snapshots scripts

# 不変 IP 設定ファイルのプレースホルダ
if [ ! -f config/ip_profile.json ]; then
  cat > config/ip_profile.json << 'IP_EOF'
{
  "ip_name": "Pikarin",
  "essence": "TODO: 光の妖精ぴかりんの世界観・人格・ビジュアル・口調などをここに定義する。",
  "visual_motifs": ["TODO"],
  "core_personality": ["TODO"],
  "taboos": ["TODO"],
  "target_audience": "TODO: 主なファン層",
  "brand_promise": "TODO: 価値提案を記述",
  "canon_examples": ["TODO"]
}
IP_EOF
  echo "  config/ip_profile.json を作成しました。"
fi

# プロジェクト設定ファイルのプレースホルダ
if [ ! -f config/project_config.json ]; then
  cat > config/project_config.json << 'PROJECT_EOF'
{
  "project_name": "Pikarin IP Business",
  "goal_type": "TODO: 例) 3年以内にマネタイズ可能なアイデアを10個策定し、そのうち2つをPoCまで進める",
  "constraints": {
    "budget_range": "TODO",
    "platforms": [],
    "forbidden_areas": []
  },
  "iteration_policy": {
    "max_tokens_per_iteration": 4096,
    "explore_ratio": 0.6,
    "deepening_ratio": 0.4,
    "stagnation_threshold": 0.6,
    "stagnation_runs": 3
  }
}
PROJECT_EOF
  echo "  config/project_config.json を作成しました。"
fi

# ------------------------------
# 7. gpt-oss-20b vLLM サーバ起動スクリプト
# ------------------------------
echo "[6/6] gpt-oss-20b を起動する vLLM サーバスクリプトを作成します..."

cat > scripts/run_vllm_server.sh << 'RUN_EOF'
#!/usr/bin/env bash
# gpt-oss-20b を vLLM でローカル起動するスクリプト

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${SCRIPT_DIR}/.."

# 仮想環境を有効化
# shellcheck disable=SC1091
source "${PROJECT_DIR}/.venv/bin/activate"

# 一部 GPU (特に Ampere 世代など) では Attention backend を明示すると安定することがあります。
# 問題が出た場合は以下を有効化して試してください (vLLM release notes で言及)。
# export VLLM_ATTENTION_BACKEND=TRITON_ATTN_VLLM_V1

# FlashInfer sampler 周りで問題がある場合の回避策。https://docs.vllm.ai/en/latest/serving/compatibility.html#flashinfer
export VLLM_USE_FLASHINFER_SAMPLER=0

# 初回起動時に Hugging Face から openai/gpt-oss-20b を自動ダウンロードします (https://huggingface.co/openai/gpt-oss-20b)。
vllm serve openai/gpt-oss-20b --host 0.0.0.0 --port 8000
RUN_EOF

chmod +x scripts/run_vllm_server.sh

echo

echo "=== セットアップ完了 🎉 ==="
echo "プロジェクトディレクトリ: ${PROJECT_DIR}"
echo

echo "次のコマンドで作業を開始できます:"
echo "  cd \"${PROJECT_DIR}\""
echo "  source .venv/bin/activate"
echo "  ./scripts/run_vllm_server.sh"
echo

echo "gpt-oss-20b のローカル Response API エンドポイント例:"
echo "  http://localhost:8000/v1/responses  (model: \"openai/gpt-oss-20b\")"
echo

echo "※ CUDA / NVIDIA ドライバは別途セットアップ済み前提です。"
