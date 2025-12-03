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
