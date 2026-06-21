#!/bin/bash
# cross-dub.sh — cross-language dub with the GPU Nemotron loaded JUST for the job, then purged.
# Sovereign translation (LiteLLM 'sovereign-only' -> :8000 GPU Nemotron). SAME-language dub
# does NOT need this. GPU etiquette: never stops another session's GPU work; pre-checks VRAM;
# only stops the agent it started. 'sovereign-only' has cooldown_time:0 in litellm config.
# Order matters: load the ~22GB agent into FREE VRAM first, THEN warm Fish Speech into the
# remainder (warming both at once races for VRAM -> KV-cache OOM).
# Usage: cross-dub.sh <source_video> <target_lang>
set -e
SRC="$1"; TGT="${2:-es}"
[ -f "$SRC" ] || { echo "usage: cross-dub.sh <source_video> <target_lang>"; exit 1; }
AGENT="/data/ai/06-configs/vllm-nemotron-agent"; AUDIO="/data/ai/06-configs/audio"; GW="http://localhost:9000"

echo "[1/4] Pre-flight + load agent Nemotron FIRST (into free VRAM)..."
FREE=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)
if [ "$FREE" -lt 24000 ]; then
  echo "  ❌ Only ${FREE}MiB free; need ~22GB. Free VRAM yourself — this script won't stop other sessions' GPU work."; exit 1
fi
echo "  ${FREE}MiB free — starting agent Nemotron..."
cd "$AGENT" && docker compose up -d
echo -n "  waiting for vLLM :8000 "
for i in $(seq 1 90); do curl -sf http://localhost:8000/v1/models >/dev/null 2>&1 && { echo " ready"; break; }; sleep 10; echo -n "."; done
curl -sf http://localhost:8000/v1/models >/dev/null 2>&1 || { echo " vLLM failed (KV-cache OOM? lower agent --gpu-memory-utilization)"; exit 1; }
echo "  agent up — now starting light audio (Fish Speech into the remainder)..."
cd "$AUDIO" && docker compose up -d redis audio-gateway audio-worker fish-speech
for i in $(seq 1 12); do curl -sf $GW/audio/health >/dev/null 2>&1 && break; sleep 5; done

echo "[2/4] Submitting cross-language dub -> $TGT ..."
JID=$(curl -s -X POST $GW/audio/job -F job_type=dub -F language=$TGT -F approach=video_locked -F "source_file=@$SRC" \
      | python3 -c "import sys,json;print(json.load(sys.stdin)['job_id'])")
echo "  job=$JID"

echo "[3/4] Translating + dubbing..."
OUT=""
for i in $(seq 1 60); do
  S=$(curl -s $GW/audio/status/$JID); st=$(echo "$S"|python3 -c "import sys,json;print(json.load(sys.stdin).get('status'))" 2>/dev/null)
  if [ "$st" = "finished" ]; then OUT=$(echo "$S"|python3 -c "import sys,json;print(json.load(sys.stdin).get('result',{}).get('dubbed_video',''))"); TR=$(echo "$S"|python3 -c "import sys,json;print(json.load(sys.stdin).get('result',{}).get('translated_text','')[:160])"); echo "  done"; echo "  ES: $TR"; break; fi
  if [ "$st" = "failed" ]; then echo "  FAILED:"; echo "$S"|python3 -c "import sys,json;print(json.load(sys.stdin).get('error','')[-400:])"; break; fi
  sleep 6
done

echo "[4/4] Purging the agent Nemotron this script loaded..."
docker stop vllm-nemotron-agent >/dev/null 2>&1 || true
nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader
[ -n "$OUT" ] && echo "DUBBED: $OUT" || { echo "no output produced"; exit 1; }
