#!/bin/bash
# cross-dub.sh — PHASED cross-language dub. ONE big model in VRAM at a time, so it fits 32GB:
#   transcribe (Whisper) -> free Whisper -> load Nemotron -> translate -> PURGE Nemotron -> TTS (Fish) -> mux.
# (The naive co-load Nemotron+Whisper+Fish ~31.7GB does NOT fit; phasing peaks at ~29GB.)
# GPU etiquette: only touches THIS stack's worker + the agent Nemotron it loads; never other sessions.
# Usage: cross-dub.sh <source_video> <target_language>     e.g.  cross-dub.sh clip.mp4 Spanish
set -e
SRC="$1"; TGT="${2:-Spanish}"
[ -f "$SRC" ] || { echo "usage: cross-dub.sh <source_video> <target_language>"; exit 1; }
AGENT="/data/ai/06-configs/vllm-nemotron-agent"; GW="http://localhost:9000"
KEY=$(cut -d= -f2 /data/ai/06-configs/audio/litellm.env 2>/dev/null)
OUTDIR="/data/ai/08-portfolio/outputs/audio/dubbing"; mkdir -p "$OUTDIR"
DUBOUT="$OUTDIR/$(basename "${SRC%.*}")_dub_${TGT}.mp4"

submit_wait () { # args = curl -F ... ; prints output_file
  local resp jid st; resp=$(curl -s -X POST $GW/audio/job "$@")
  jid=$(echo "$resp"|python3 -c "import sys,json;print(json.load(sys.stdin)['job_id'])")
  for i in $(seq 1 72); do
    st=$(curl -s $GW/audio/status/$jid|python3 -c "import sys,json;print(json.load(sys.stdin).get('status'))" 2>/dev/null)
    [ "$st" = finished ] && { curl -s $GW/audio/status/$jid|python3 -c "import sys,json;print(json.load(sys.stdin).get('result',{}).get('output_file',''))"; return 0; }
    [ "$st" = failed ] && { curl -s $GW/audio/status/$jid|python3 -c "import sys,json;print('JOBFAIL '+json.load(sys.stdin).get('error','')[-300:])" >&2; return 1; }
    sleep 5
  done; return 1
}

echo "[1/6] Transcribe (Whisper; Nemotron NOT loaded)..."
TRANSCRIPT=$(submit_wait -F job_type=transcribe -F quality=production -F "source_file=@$SRC") || { echo "transcribe failed"; exit 1; }
echo "  -> $TRANSCRIPT"

echo "[2/6] Free Whisper (restart this stack's worker) so the Nemotron fits..."
docker restart creative-audio-worker >/dev/null 2>&1 || true
for i in $(seq 1 12); do docker exec creative-audio-worker true 2>/dev/null && break; sleep 2; done; sleep 3

echo "[3/6] Load GPU Nemotron (only Fish resident now; ~29GB peak)..."
cd "$AGENT" && docker compose up -d
for i in $(seq 1 90); do curl -sf http://localhost:8000/v1/models >/dev/null 2>&1 && break; sleep 10; done
curl -sf http://localhost:8000/v1/models >/dev/null 2>&1 || { echo "vLLM failed"; docker stop vllm-nemotron-agent 2>/dev/null; exit 1; }

echo "[4/6] Translate via LiteLLM 'sovereign-only' -> $TGT ..."
TRANSLATED=$(python3 - "$TRANSCRIPT" "$TGT" "$KEY" <<'PY'
import sys,json,requests
tj,tgt,key=sys.argv[1],sys.argv[2],sys.argv[3]
d=json.load(open(tj)); segs=d.get("segments",[])
text=(" ".join(s.get("text","") for s in segs)).strip() or d.get("text","")
dur=segs[-1].get("end",0) if segs else 0
prompt=f"Translate the following to {tgt}. It must be speakable in ~{dur:.0f} seconds; adjust verbosity to fit. Output ONLY the translation.\n\n{text}"
r=requests.post("http://172.17.0.1:4000/v1/chat/completions",headers={"Authorization":f"Bearer {key}"},
  json={"model":"sovereign-only","messages":[{"role":"system","content":"detailed thinking off\nYou are a precise translator. Output ONLY the translation, nothing else."},{"role":"user","content":prompt}],"max_tokens":3000,"temperature":0.2},timeout=300)
m=r.json()["choices"][0]["message"]
out=(m.get("content") or "").strip()
if not out:
    import re as _re
    rc=(m.get("reasoning_content") or "")
    out=_re.sub(r"(?s).*</think>","",rc).strip()
print(out)
PY
)
[ -n "$TRANSLATED" ] || { echo "  translation empty"; docker stop vllm-nemotron-agent 2>/dev/null; exit 1; }
echo "  $TGT: ${TRANSLATED:0:140}"

echo "[5/6] Purge Nemotron, then TTS (Fish) on the translation..."
docker stop vllm-nemotron-agent >/dev/null 2>&1 || true
DUBAUDIO=$(submit_wait -F job_type=tts -F quality=production -F "text=$TRANSLATED") || { echo "tts failed"; exit 1; }
echo "  -> $DUBAUDIO"

echo "[6/6] Mux dubbed audio onto the video..."
ffmpeg -y -loglevel error -i "$SRC" -i "$DUBAUDIO" -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -shortest "$DUBOUT"
nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader
[ -f "$DUBOUT" ] && echo "DUBBED: $DUBOUT" || { echo "mux failed"; exit 1; }
