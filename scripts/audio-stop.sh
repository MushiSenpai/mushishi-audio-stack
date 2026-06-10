#!/bin/bash
# audio-stop.sh — Cleanly stop all audio services and free VRAM
set -e
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo -e "${YELLOW}Stopping audio stack...${NC}"
AUDIO_COMPOSE="/data/ai/06-configs/audio"
cd "$AUDIO_COMPOSE"
docker compose stop fish-speech lipsync music audio-gateway rq-dashboard
# Keep Redis running — job history is in Redis; stop only if full reset needed
# docker compose stop redis   # uncomment for full reset

echo ""
echo -e "${GREEN}Audio services stopped. Redis + rq-dashboard preserved.${NC}"
nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader
echo ""
echo "Restore: agent-mode.sh (Nemotron) or creative-mode.sh (ComfyUI)"
