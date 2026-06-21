#!/bin/bash
# cross-dub.sh — cross-language dub with the GPU Nemotron loaded JUST for the job, then purged.
# Sovereign translation (LiteLLM 'sovereign-only' -> :8000 GPU Nemotron, fast), honoring the
# sequential-mode discipline. SAME-language dub does NOT need this (no translation step).
#
# GPU etiquette: NEVER stops another session's GPU work — pre-checks free VRAM, aborts if tight.
# It only stops the agent Nemotron IT started. Step 2 briefly RESTARTS the shared LiteLLM proxy
# to clear stale cooldowns so 'sovereign-only' routes to the freshly-loaded :8000 (other LLM
# services reconnect in a few seconds) — run this knowingly. (Alternative: set a 0/short cooldown
# for sovereign-only in litellm config.yaml and drop step 2.)
# Usage: cross-dub.sh <source_video> <target_lang>     e.g.  cross-dub.sh clip.mp4 es
set -e
SRC="$1"; TGT="${2:-es}"
[ -f "$SRC" ] || { echo "usage: cross-dub.sh <source_video> <target_lang>"; exit 1; }
AGENT="/data/ai/06-configs/vllm-nemotron-agent"; AUDIO="/data/ai/06-configs/audio"; GW="http://localhost:9000"

echo "[1/6] Pre-flight: free VRAM for the ~22GB agent Nemotron..."
FREE=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)
if [ "$FREE" -lt 24000 ]; then
  echo "  ❌ Only ${FREE}MiB free; need ~22GB. Free VRAM yourself (stop idle ComfyUI/forensic vLLM"
  echo "     or run agent-mode.sh) — this script will NOT stop another session's GPU work. Re-run after."
  exit 1
fi
echo "  ${FREE}MiB free — loading agent Nemotron (its own container) + light audio..."
cd "$AGENT" && docker compose up -d
cd "$AUDIO" && docker compose up -d redis audio-gateway audio-worker fish-speech
echo -n "  waiting for vLLM :8000 "
for i in $(seq 1 90); do curl -sf http://localhost:8000/v1/models >/dev/null 2>&1 && { echo " ready"; break; }; sleep 10; echo -n "."; done
curl -sf http://localhost:8000/v1/models >/dev/null 2>&1 || { echo " vLLM failed to load"; exit 1; }

echo "[2/6] Clearing LiteLLM cooldowns (brief restart) so 'sovereign-only' routes to the fresh :8000..."
docker restart litellm-proxy >/dev/null 2>&1 || true
for i in $(seq 1 15); do curl -sf http://localhost:4000/health/liveliness >/dev/null 2>&1 && break; sleep 3; done

echo "[3/6] Submitting cross-language dub -> $TGT (translation via 'sovereign-only')..."
JID=$(curl -s -X POST $GW/audio/job -F job_type=dub -F language=$TGT -F approach=video_locked -F "source_file=@$SRC" \
      | python3 -c "import sys,json;print(json.load(sys.stdin)['job_id'])")
echo "  job=$JID"

echo "[4/6] Translating + dubbing..."
OUT=""
for i in $(seq 1 60); do
  S=$(curl -s $GW/audio/status/$JID); st=$(echo "$S"|python3 -c "import sys,json;print(json.load(sys.stdin).get('status'))" 2>/dev/null)
  if [ "$st" = "finished" ]; then OUT=$(echo "$S"|python3 -c "import sys,json;r=json.load(sys.stdin).get('result',{});print(r.get('dubbed_video',''))"); echo "  done"; break; fi
  if [ "$st" = "failed" ]; then echo "  FAILED:"; echo "$S"|python3 -c "import sys,json;print(json.load(sys.stdin).get('error','')[-400:])"; break; fi
  sleep 6
done

echo "[5/6] Purging the agent Nemotron this script loaded (freeing its ~22GB)..."
docker stop vllm-nemotron-agent >/dev/null 2>&1 || true
echo "[6/6] Done."
nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader
[ -n "$OUT" ] && echo "DUBBED: $OUT" || { echo "no output produced"; exit 1; }
