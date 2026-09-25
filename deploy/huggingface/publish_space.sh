#!/usr/bin/env bash
# Publish the committed LayerToll tree to a Hugging Face Docker Space.
#   deploy/huggingface/publish_space.sh <hf-username> [space-name]
# Needs: git, git-lfs, and an existing Space (SDK: Docker). Authentication is
# handled by your git credential helper (HF username + access token with write
# scope); this script never reads or prints credentials.
set -euo pipefail

HF_USER="${1:?usage: publish_space.sh <hf-username> [space-name]}"
SPACE="${2:-layertoll}"
ROOT="$(git rev-parse --show-toplevel)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

git -C "$ROOT" archive --format=tar HEAD | tar -x -C "$WORK"
cp "$WORK/deploy/huggingface/Dockerfile" "$WORK/Dockerfile"

# Space card: HF front matter + the project README
{
  cat <<'YAML'
---
title: LayerToll
emoji: 🛣️
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: Paid AI-agent services with x402 on X Layer (demo)
---

> Public hackathon demo (OKX Dev Day 2026). Payments run in **TEST MODE on X Layer testnet**:
> x402 signatures are verified, nothing is settled on chain. Source: https://github.com/karaca8640/layertoll

YAML
  cat "$ROOT/README.md"
} > "$WORK/README.md"

cd "$WORK"
git init -q -b main
git lfs install --local >/dev/null
git lfs track "*.png" "*.jpg" "*.jpeg" "*.webp" "*.avif" "*.ico" "*.gif" >/dev/null
git add .gitattributes
git add -A
git -c user.name="$(git -C "$ROOT" config user.name)" -c user.email="$(git -C "$ROOT" config user.email)" \
  commit -q -m "Deploy LayerToll $(git -C "$ROOT" rev-parse --short HEAD)"
git remote add space "https://huggingface.co/spaces/${HF_USER}/${SPACE}"
git push --force space main
echo "Pushed. Build logs: https://huggingface.co/spaces/${HF_USER}/${SPACE}?logs=build"
echo "App URL:         https://${HF_USER}-${SPACE}.hf.space"
