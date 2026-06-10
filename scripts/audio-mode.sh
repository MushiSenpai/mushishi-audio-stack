#!/bin/bash
# audio-mode.sh — Start audio stack in creative mode alongside ComfyUI
# Stops vLLM Nemotron first. CPU Nemotron stays up as sovereignty floor.
# Usage: ./audio-mode.sh [light|full]
#   light = Whisper + Fish Speech + MuseTalk only (~10GB)
#   full  = + LatentSync (~16GB) — default
set -e
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

AUDIO_COMPOSE="/data/ai/06-configs/audio"
TIER=${1:-full}

echo -e "${YELLOW}AUDIO MODE — Starting audio stack (tier: $TIER)...${NC}"

# Stop GPU Nemotron if running (audio needs the VRAM)
if docker ps --format '{{.Names}}' | grep -q "vllm-nemotron"; then
  echo -e "${YELLOW}  vllm-nemotron running — stopping to free VRAM for audio stack.${NC}"
  docker stop vllm-nemotron || true
  sleep 5
fi

# Start base audio services (always)
# audio-worker is mandatory: the gateway only enqueues — without the RQ
# worker container every job sits in "queued" forever.
echo "   Starting Redis, gateway, worker, Fish Speech..."
cd "$AUDIO_COMPOSE"
docker compose up -d redis rq-dashboard audio-gateway audio-worker fish-speech

# Start tier-appropriate lipsync service
if [ "$TIER" = "full" ]; then
  echo "   Starting lipsync (LatentSync quality tier)..."
  docker compose up -d lipsync
elif [ "$TIER" = "light" ]; then
  echo "   Starting lipsync (MuseTalk draft tier only)..."
  docker compose up -d lipsync
fi

echo "   Waiting for gateway health check..."
MAX_WAIT=60; WAITED=0
while ! curl -s http://localhost:9000/audio/health > /dev/null 2>&1; do
  sleep 5; WAITED=$((WAITED + 5)); echo -n "."
  if [ $WAITED -ge $MAX_WAIT ]; then
    echo -e "\n${RED}  Gateway timeout. docker logs creative-audio-gateway${NC}" && exit 1
  fi
done

echo ""
echo -e "${GREEN}AUDIO MODE READY${NC}"
echo "   Gateway: http://localhost:9000"
echo "   Jobs:    http://localhost:9010 (rq-dashboard)"
nvidia-smi --query-gpu=memory.used,memory.free,power.draw --format=csv,noheader
echo ""
echo "CPU Nemotron (sovereignty floor): $(systemctl is-active nemotron-cpu 2>/dev/null || echo 'not installed')"
