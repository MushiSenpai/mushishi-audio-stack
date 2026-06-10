#!/bin/bash
# music-mode.sh — Dedicated YuE 7B music generation mode
# Requires ~16GB VRAM. Stops vLLM AND ComfyUI first.
# After music generation: restart with agent-mode.sh or creative-mode.sh
set -e
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

AUDIO_COMPOSE="/data/ai/06-configs/audio"

echo -e "${YELLOW}MUSIC MODE — YuE 7B dedicated (needs ~16GB VRAM)${NC}"
echo "   This will stop vLLM Nemotron and ComfyUI."
read -p "   Continue? (y/N): " confirm
[[ "$confirm" != "y" && "$confirm" != "Y" ]] && echo "Aborted." && exit 0

# Stop GPU-heavy services
docker stop vllm-nemotron 2>/dev/null || true
docker stop comfyui 2>/dev/null || true
sleep 5

VRAM_FREE=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)
if [ "$VRAM_FREE" -lt 14000 ]; then
  echo -e "${RED}  Less than 14GB VRAM free ($((VRAM_FREE/1024))GB). Check what's still running.${NC}"
  docker ps
  exit 1
fi

echo "   Starting Redis, gateway, audio-worker (all queues incl. music/YuE)..."
cd "$AUDIO_COMPOSE"
docker compose up -d redis audio-gateway audio-worker

echo ""
echo -e "${GREEN}MUSIC MODE READY${NC}"
echo "   Submit: curl -X POST http://localhost:9000/audio/job -F job_type=music -F quality=song -F text='genre' -F 'lyrics=[verse]...'"
echo "   Jobs:   http://localhost:9010"
nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader
echo ""
echo -e "${YELLOW}When done: agent-mode.sh or creative-mode.sh to restore normal operation${NC}"
