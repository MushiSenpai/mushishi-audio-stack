---
tags:
  - ai/audio
  - ai/voice
  - ai/music
  - ai/lip-sync
  - ai/dubbing
  - hardware/rtx5090
  - linux/ubuntu
  - docker
  - open-source
status: active
version: 1.1
created: 2026-05-23
updated: 2026-06-21
hardware: RTX 5090 · Ryzen 9 9900X3D · 128GB DDR5 · Ubuntu 24.04 · CUDA 13.2
companion: mushishi-sovereign-ai-stack-v1.7.1.md
sovereignty: T1 (all tools local, MIT/Apache 2.0 only)
---

# 🎙️ Mushishi Audio Stack — Voice, Music, Lip Sync & Dubbing

> **Version:** 1.1 | **Updated:** June 21, 2026 | **Status:** ✅ BUILT — Phases A + B1–B5 complete; **see the Working-vs-Broken matrix below.**
>
> **⚠️ AS-BUILT STATUS (v1.1, 2026-06-21):** This spec was a plan on May 23 and is now EXECUTED.
> The install required ~25 deviations (Fish Speech pinned to v1.5.1, a single `audio-worker`
> container with `runtime: nvidia` that delegates to model microservices, WhisperX CTranslate2
> conversion, YuE/Hallo2 patches, and more). **Do NOT re-execute from this document alone** —
> the as-built lessons live in the repo `LESSONS.md` + Claude memory (`feedback_audio_stack.md`).
> Dockerfile.audio now **bakes** the proven torch 2.8.0 set + sentencepiece/pydub + libgles2 +
> torchsde (the old runtime-rot is fixed).
>
> **What actually works today (re-verified 2026-06-21):**
> - ✅ **TTS** (Fish Speech 1.5, 25s) · **Voice clone** (Demucs+Fish, ~5s) · **Transcribe**
>   (Whisper+WhisperX, ~15s/34.5s) · **Dub** (video_locked) · **Music**: YuE 7B songs (~3–9min),
>   **ACE-Step** instrumental (stereo 48kHz, ~10s — via an isolated venv, now wired into the
>   gateway), **Stable Audio** (stereo 44.1kHz, ~18s — via diffusers, not stable_audio_tools).
> - ❌ **Lip-sync / avatar — ALL 3 models broken** in the unified worker (LatentSync emits
>   corrupt output; Hallo2 diffusers-API break; MuseTalk mmcv/cu130). Root cause: one shared env
>   can't satisfy models that need pinned isolated envs. **REBUILD REQUIRED** — dedicated MuseTalk
>   1.5 env (spec: `docs/musetalk-1.5-rebuild-spec.md`). Local lip-sync ceiling =
>   **social-grade**; broadcast = cloud.
>
> This document is a companion to the **Mushishi Sovereign AI Stack v1.6.4**. It follows the same conventions: `/data/ai/` folder structure, Docker Compose services, systemd for always-on daemons, Tailscale-only port exposure, SDD spec-driven execution, and the sovereignty tier model. Do not execute without reading the main stack document first.

---

## ⚡ TL;DR

Audio is a **Creative Mode extension**. It slots into the existing VRAM switching discipline:

```
FORENSIC MODE:    Nemotron vLLM (~28-30GB)  → Audio stack STOPPED
AGENT MODE:       Nemotron vLLM (~22GB)     → Light audio (Whisper/Fish Speech) OK
CREATIVE MODE:    ComfyUI (~14-24GB)        → Full audio stack runs alongside
MUSIC MODE (new): YuE 7B only (~16GB)       → vLLM STOPPED, ComfyUI STOPPED
```

**New mode-switch scripts:** `audio-mode.sh`, `music-mode.sh`
**New Mac aliases:** `beast-audio`, `beast-audio-status`, `beast-music`
**New ports:** 9000 (gateway), 9002 (TTS), 9003 (lipsync), 9004 (music), 9010 (rq-dashboard) — all Tailscale-only

---

## 🛡️ Sovereignty Classification

**All audio tools: T1 Sovereign.** Every model in this stack is MIT or Apache 2.0 licensed, runs entirely on-machine, and routes no data to any external API. This is appropriate for:

- Client voice samples (privacy as a product feature — same principle as the forensic video pipeline)
- Avatar/talking-head content generated from user-submitted images
- Music and voiceover for commercial creative work (Apache 2.0 permits commercial use)

The audio gateway (`:9000`) is exposed only on the Tailscale interface, consistent with every other stack service.

---

## 🛠️ Tool Evaluation (Checklist Applied)

Before adopting each tool, the five-question evaluation was applied:

| Tool | Tier | Overlap? | Hardware fit? | Sovereignty trade-off | Reversible? |
|---|---|---|---|---|---|
| Whisper V3 Turbo | T1 | None | 2GB VRAM — fits in any mode | None — fully local | Docker container |
| WhisperX | T1 | None | +0GB overhead | None | pip package |
| Fish Speech 1.5 | T1 | None | 4–8GB — creative mode only | None | Docker + compose |
| Demucs | T1 | None | 3GB — creative mode | None | pip package |
| RVC v2 | T1 | None | 4GB | None | pip package |
| MuseTalk | T1 | None | 4GB — fits with ComfyUI light | None | Docker + compose |
| LatentSync | T1 | None | 6GB — fits with ComfyUI | None | Docker + compose |
| Hallo2 | T1 | None | 8–12GB — ComfyUI must stop | None | Docker + compose |
| YuE 7B | T1 | None | 16GB — needs dedicated mode | None | Docker + compose |
| ACE-Step 3.5B | T1 | None | 8GB — creative mode | None | Docker + compose |
| Stable Audio Open | T1 | None | 8GB — creative mode | None | Docker + compose |
| DiffSinger | T1 | None | 4GB — advanced, last | None | pip/repo |
| Redis + RQ | T1 | None | CPU only | None | Docker |

**Excluded (same as original audit):**
- **MusicGen Stereo** — CC BY-NC 4.0 non-commercial. Incompatible with client/freelance work.
- **SoulX-Singer** — no verified stable HuggingFace repo with clear maintenance signal.
- **CosyVoice2 0.5B** — redundant with Fish Speech 1.5 which does everything plus better cloning.

> **Full-body talking head note:** Broadcast-quality full-body with gestures has no strong open-source local solution as of mid-2026. The existing Wan 2.2 I2V workflow in ComfyUI produces better results than any dedicated tool. Do not add a dependency on a tool that doesn't exist yet — this matches the stack's existing anti-hype discipline.

---

## 🎮 VRAM Budget — Audio in Context

### Available VRAM (RTX 5090 with iGPU display, idle)

```
Total:        32,607 MiB
Display:        ~500 MiB (iGPU — freed from GPU in v1.5)
Available:    ~32,100 MiB
```

### Audio Mode Profiles

| Mode | Active Models | Approx VRAM | What must stop |
|---|---|---|---|
| **Forensic** | Nemotron NVFP4 only | ~28–30GB | ALL audio services |
| **Agent** | Nemotron NVFP4 light | ~22GB | Heavy audio (YuE, Hallo2, LatentSync) |
| **Audio-Light** (new) | Whisper + Fish Speech + MuseTalk | ~8–10GB | vLLM Nemotron |
| **Creative + Audio** | ComfyUI + Fish Speech + MuseTalk | ~18–22GB | vLLM Nemotron |
| **Creative + Avatar** | ComfyUI light + LatentSync | ~20GB | vLLM Nemotron |
| **Music Mode** (new) | YuE 7B only | ~16GB | vLLM + ComfyUI |
| **Cinematic Avatar** | Hallo2 only | ~10–12GB | vLLM + ComfyUI |

> **Key constraint:** YuE 7B (~16GB) and Hallo2 (~12GB) are solo acts — they need most of the VRAM budget and require `music-mode.sh` or stopping creative stack first. This mirrors the existing forensic ↔ creative handoff discipline already in the stack.

### VRAM Handoff Protocol (extends existing pattern)

```
forensic-mode.sh ──── exclusive ──── (28-30GB) 
                │
                └── stop ──────────── creative-mode.sh ──── (14-24GB)
                                              │
                                              ├── + fish-speech (~8GB) ── for voiceover
                                              ├── + museTalk (~4GB)    ── for avatar draft
                                              └── + latentsync (~6GB)  ── for avatar quality

music-mode.sh ─────── exclusive ──── (16GB) ── no ComfyUI, no vLLM
                │
                └── stop ──────────── back to agent-mode.sh or creative-mode.sh
```

---

## 🏗️ Architecture

### Integration into Mushishi System Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│       COMPUTE NODE — mushishi (Ubuntu 24.04)  UFW: default-deny     │
│                                                                     │
│  [GPU LAYER — RTX 5090 32GB]                                        │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  FORENSIC MODE (exclusive): vLLM Nemotron ~28-30GB           │  │
│  │  CREATIVE MODE: ComfyUI ~14-24GB                             │  │
│  │  + AUDIO (creative slot): Fish Speech ~8GB, MuseTalk ~4GB    │  │
│  │  + AVATAR (quality tier): LatentSync ~6GB                    │  │
│  │  MUSIC MODE (exclusive): YuE 7B ~16GB                        │  │
│  │  CINEMATIC AVATAR (exclusive): Hallo2 ~10-12GB               │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  [CPU+RAM LAYER — 128GB]                                            │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Nemotron CPU PRISM (llama.cpp, :8001) — always-on           │  │
│  │  Hermes Agent (:8642) — always-on                            │  │
│  │                                                              │  │
│  │  AUDIO LAYER (creative mode only):                           │  │
│  │  ┌────────────────────────────────────────────────────────┐  │  │
│  │  │  Audio Gateway API (:9000) — FastAPI, job router       │  │  │
│  │  │  Redis + RQ (:6379 internal, :9010 dashboard)          │  │  │
│  │  │  Fish Speech 1.5 (:9002) — TTS + voice cloning         │  │  │
│  │  │  Lip Sync Service (:9003) — MuseTalk/LatentSync/Hallo2 │  │  │
│  │  │  Music Service (:9004) — YuE/ACE-Step/Stable Audio     │  │  │
│  │  └────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  [OBSERVABILITY — unchanged]                                        │
│  Netdata :19999 · Arize Phoenix :6006 · rq-dashboard :9010         │
│                                                                     │
│  /data/ai/ (1.6TB NVMe) · All audio ports via Tailscale only       │
└─────────────────────────────────────────────────────────────────────┘
```

### Why a Job Queue

Audio jobs take 10 seconds to 15 minutes. The same reason the forensic pipeline writes JSON to disk and exits before ComfyUI loads — audio jobs must not block. Redis + RQ gives:
- Async job submission with status polling
- Orderly VRAM access (no two heavy jobs at once)
- rq-dashboard at `:9010` for live job monitoring via Tailscale
- One-line scale path if this evolves to a platform service

---

## 📁 Directory Structure (Additions Only)

Follows the existing `/data/ai/` numbering convention exactly.

```
/data/ai/
├── 01-workspace/
│   └── audio/
│       ├── gateway/          ← FastAPI gateway + RQ worker code
│       │   ├── main.py       ← Audio Gateway API (:9000)
│       │   ├── queue_client.py
│       │   ├── intent_router.py
│       │   └── workers/
│       │       ├── stt.py    ← Whisper + WhisperX
│       │       ├── voice.py  ← Fish Speech + Demucs
│       │       ├── lipsync.py← MuseTalk / LatentSync / Hallo2
│       │       ├── music.py  ← YuE / ACE-Step / Stable Audio
│       │       └── dub.py    ← Full auto-dub pipeline
│       ├── fish-speech/      ← Fish Speech repo (git clone)
│       ├── museTalk/         ← MuseTalk repo
│       ├── latentsync/       ← LatentSync repo
│       ├── hallo2/           ← Hallo2 repo
│       └── yue/              ← YuE repo
│
├── 02-models/
│   └── audio/
│       ├── whisper/          ← Whisper Large V3 Turbo  (~2GB VRAM, MIT)
│       ├── fish-speech/      ← Fish Speech 1.5         (~8GB VRAM, Apache 2.0)
│       ├── museTalk/         ← MuseTalk + DWPose        (~4GB VRAM, Apache 2.0)
│       ├── latentsync/       ← LatentSync               (~6GB VRAM, Apache 2.0)
│       ├── hallo2/           ← Hallo2                   (~10GB VRAM, Apache 2.0)
│       ├── demucs/           ← auto-downloads first run (~3GB VRAM, MIT)
│       ├── rvc/              ← RVC v2                   (~4GB VRAM, MIT)
│       ├── yue/
│       │   ├── stage1/       ← YuE 7B stage1            (~13GB)
│       │   └── stage2/       ← YuE 1B stage2            (~3GB)
│       ├── ace-step/         ← ACE-Step 3.5B            (~8GB VRAM, Apache 2.0)
│       ├── stable-audio/     ← Stable Audio Open 1.0    (~8GB VRAM, Apache 2.0)
│       ├── diffsinger/       ← DiffSinger               (~4GB VRAM, Apache 2.0)
│       └── voices/           ← Cloned voice reference .wav files
│
├── 03-data/
│   └── audio/
│       ├── voice-samples/    ← Raw reference recordings (pre-Demucs cleaning)
│       ├── voice-clean/      ← Demucs-cleaned speech-only clips
│       ├── music-prompts/    ← YuE lyrics + genre prompt files
│       └── dub-projects/     ← Per-job dubbing working files + dub_analysis.json
│
├── 04-logs/
│   └── audio/                ← Per-job audio execution logs (mirrors forensic/ pattern)
│
├── 06-configs/
│   └── audio/
│       ├── docker-compose.yml← All audio Docker services
│       └── Dockerfile.audio  ← Shared base image (CUDA 13.2 + PyTorch nightly)
│
└── 08-portfolio/
    └── outputs/
        └── audio/
            ├── music/        ← YuE / ACE-Step / Stable Audio outputs
            ├── voiceover/    ← TTS / cloning outputs
            ├── lip-sync/     ← Talking head video outputs (.mp4)
            ├── dubbing/      ← Auto-dubbed final videos
            └── stems/        ← Demucs separated audio stems
```

---

## 🔌 Port Reservation (Integration with Existing Map)

**Existing ports (unchanged):**

| Port | Service |
|---|---|
| :8000 | Nemotron vLLM (forensic/agent) |
| :8001 | Nemotron CPU llama.cpp |
| :8188 | ComfyUI |
| :8642 | Hermes gateway |
| :9119 | Hermes dashboard |
| :3001 | Hermes workspace PWA |
| :4000 | LiteLLM |
| :2026 | DeerFlow nginx |
| :3100 | Paperclip (Phase 5.5) |
| :6006 | Arize Phoenix |
| :19999 | Netdata |

**New audio ports (all Tailscale-only):**

| Port | Service | Internal only? |
|---|---|---|
| :9000 | Audio Gateway API (FastAPI) | No — Tailscale exposed |
| :9002 | Fish Speech 1.5 TTS | Internal only (gateway proxies) |
| :9003 | Lip Sync service | Internal only |
| :9004 | Music generation service | Internal only |
| :9010 | rq-dashboard (job monitor) | Tailscale exposed |
| :6379 | Redis | Internal only (no UFW rule) |

> **UFW rule additions to harden-firewall.sh:**
> ```bash
> sudo ufw allow in on tailscale0 to any port 9000 proto tcp comment 'Audio Gateway (v1.7)'
> sudo ufw allow in on tailscale0 to any port 9010 proto tcp comment 'Audio rq-dashboard (v1.7)'
> ```
> Internal-only ports (9002, 9003, 9004, 6379) get no UFW rule — Docker inter-container traffic handles them.

---

## 🔀 Mode Integration — Updated Scripts

### audio-mode.sh (NEW)

`/data/ai/01-workspace/scripts/audio-mode.sh`:

```bash
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

echo -e "${YELLOW}🎙️ AUDIO MODE — Starting audio stack (tier: $TIER)...${NC}"

# Stop GPU Nemotron if running (audio needs the VRAM)
if docker ps --format '{{.Names}}' | grep -q "vllm-nemotron"; then
  echo -e "${YELLOW}⚠️  vllm-nemotron running — stopping to free VRAM for audio stack.${NC}"
  docker stop vllm-nemotron || true
  sleep 5
fi

# Start base audio services (always)
echo "   Starting Redis, gateway, Fish Speech..."
cd "$AUDIO_COMPOSE"
docker compose up -d redis rq-dashboard audio-gateway fish-speech

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
    echo -e "\n${RED}❌ Gateway timeout. docker logs creative-audio-gateway${NC}" && exit 1
  fi
done

echo ""
echo -e "${GREEN}✅ AUDIO MODE READY${NC}"
echo "   Gateway: http://localhost:9000"
echo "   Jobs:    http://localhost:9010 (rq-dashboard)"
nvidia-smi --query-gpu=memory.used,memory.free,power.draw --format=csv,noheader
echo ""
echo "CPU Nemotron (sovereignty floor): $(systemctl is-active nemotron-cpu 2>/dev/null || echo 'not installed')"
```

### music-mode.sh (NEW)

`/data/ai/01-workspace/scripts/music-mode.sh`:

```bash
#!/bin/bash
# music-mode.sh — Dedicated YuE 7B music generation mode
# Requires ~16GB VRAM. Stops vLLM AND ComfyUI first.
# After music generation: restart with agent-mode.sh or creative-mode.sh
set -e
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

AUDIO_COMPOSE="/data/ai/06-configs/audio"

echo -e "${YELLOW}🎵 MUSIC MODE — YuE 7B dedicated (needs ~16GB VRAM)${NC}"
echo "   This will stop vLLM Nemotron and ComfyUI."
read -p "   Continue? (y/N): " confirm
[[ "$confirm" != "y" && "$confirm" != "Y" ]] && echo "Aborted." && exit 0

# Stop GPU-heavy services
docker stop vllm-nemotron 2>/dev/null || true
docker stop comfyui 2>/dev/null || true
sleep 5

VRAM_FREE=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits)
if [ "$VRAM_FREE" -lt 14000 ]; then
  echo -e "${RED}❌ Less than 14GB VRAM free ($((VRAM_FREE/1024))GB). Check what's still running.${NC}"
  docker ps
  exit 1
fi

echo "   Starting Redis, gateway, music service (YuE)..."
cd "$AUDIO_COMPOSE"
docker compose up -d redis audio-gateway music

echo ""
echo -e "${GREEN}✅ MUSIC MODE READY${NC}"
echo "   Submit: curl -X POST http://localhost:9000/audio/job -F job_type=music -F quality=song -F text='genre' -F 'lyrics=[verse]...'"
echo "   Jobs:   http://localhost:9010"
nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader
echo ""
echo -e "${YELLOW}When done: agent-mode.sh or creative-mode.sh to restore normal operation${NC}"
```

### Updated audio-stop.sh (NEW)

`/data/ai/01-workspace/scripts/audio-stop.sh`:

```bash
#!/bin/bash
# audio-stop.sh — Cleanly stop all audio services and free VRAM
set -e
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo -e "${YELLOW}🔇 Stopping audio stack...${NC}"
AUDIO_COMPOSE="/data/ai/06-configs/audio"
cd "$AUDIO_COMPOSE"
docker compose stop fish-speech lipsync music audio-gateway rq-dashboard
# Keep Redis running — job history is in Redis; stop only if full reset needed
# docker compose stop redis   # uncomment for full reset

echo ""
echo -e "${GREEN}✅ Audio services stopped. Redis + rq-dashboard preserved.${NC}"
nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader
echo ""
echo "Restore: agent-mode.sh (Nemotron) or creative-mode.sh (ComfyUI)"
```

---

## 📦 Docker Services

`/data/ai/06-configs/audio/docker-compose.yml`:

```yaml
services:

  # ── Infrastructure ─────────────────────────────────────────────────
  redis:
    image: redis:7-alpine
    container_name: creative-redis
    ports:
      - "127.0.0.1:6379:6379"     # internal only — no external exposure
    volumes:
      - /data/ai/07-cache/redis:/data
    command: redis-server --appendonly yes
    restart: unless-stopped

  rq-dashboard:
    image: eoranged/rq-dashboard
    container_name: creative-rq-dashboard
    ports:
      - "9010:9181"               # Tailscale-exposed — UFW rule required
    environment:
      - RQ_DASHBOARD_REDIS_URL=redis://creative-redis:6379
    depends_on:
      - redis
    restart: unless-stopped

  # ── Audio Gateway API ───────────────────────────────────────────────
  audio-gateway:
    build:
      context: /data/ai/06-configs/audio
      dockerfile: Dockerfile.audio
    container_name: creative-audio-gateway
    ports:
      - "9000:9000"               # Tailscale-exposed — UFW rule required
    volumes:
      - /data/ai/01-workspace/audio/gateway:/app
      - /data/ai/03-data/audio:/data/ai/03-data/audio
      - /data/ai/08-portfolio/outputs/audio:/outputs
    environment:
      - REDIS_URL=redis://creative-redis:6379
    depends_on:
      - redis
    command: uvicorn main:app --host 0.0.0.0 --port 9000 --reload
    restart: unless-stopped

  # ── TTS + Voice Cloning ─────────────────────────────────────────────
  fish-speech:
    build:
      context: /data/ai/06-configs/audio
      dockerfile: Dockerfile.audio
    container_name: creative-tts
    runtime: nvidia
    ports:
      - "127.0.0.1:9002:9002"    # internal only
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=all
    volumes:
      - /data/ai/02-models/audio/fish-speech:/models:ro
      - /data/ai/02-models/audio/voices:/voices
      - /data/ai/08-portfolio/outputs/audio/voiceover:/outputs
      - /data/ai/01-workspace/audio/fish-speech:/app
    working_dir: /app
    command: >
      bash -c "pip install --break-system-packages -e . &&
               python -m fish_speech.webui.launch_api
               --listen 0.0.0.0:9002
               --checkpoint-path /models/fish-speech-1.5"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    restart: unless-stopped

  # ── Lip Sync (multi-tier) ───────────────────────────────────────────
  lipsync:
    build:
      context: /data/ai/06-configs/audio
      dockerfile: Dockerfile.audio
    container_name: creative-lipsync
    runtime: nvidia
    ports:
      - "127.0.0.1:9003:9003"    # internal only
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=all
    volumes:
      - /data/ai/02-models/audio:/models:ro
      - /data/ai/01-workspace/audio:/workspace:ro
      - /data/ai/03-data/audio:/audio-data
      - /data/ai/08-portfolio/outputs/audio/lip-sync:/outputs
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    restart: unless-stopped

  # ── Music Generation (multi-model) ─────────────────────────────────
  music:
    build:
      context: /data/ai/06-configs/audio
      dockerfile: Dockerfile.audio
    container_name: creative-music
    runtime: nvidia
    ports:
      - "127.0.0.1:9004:9004"    # internal only
    environment:
      - NVIDIA_VISIBLE_DEVICES=all
      - NVIDIA_DRIVER_CAPABILITIES=all
    volumes:
      - /data/ai/02-models/audio:/models:ro
      - /data/ai/01-workspace/audio:/workspace:ro
      - /data/ai/08-portfolio/outputs/audio/music:/outputs
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
    restart: unless-stopped
```

---

## 🖼️ Dockerfile

`/data/ai/06-configs/audio/Dockerfile.audio`:

```dockerfile
FROM nvidia/cuda:12.8.0-devel-ubuntu24.04
# NOTE: Use 12.8 base, not 13.2 — PyTorch nightly cu130 is compatible
# and more widely tested at this base image version.

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update && apt install -y \
    python3 python3-pip python3-venv \
    git wget curl ffmpeg \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender-dev \
    libsndfile1 libportaudio2 libasound2-dev \
    && rm -rf /var/lib/apt/lists/*

# PyTorch nightly cu130 — required for RTX 5090 SM_120
# Same pattern as the main stack's vLLM container
RUN pip3 install --no-cache-dir --break-system-packages \
    --pre torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/nightly/cu130

# Core audio dependencies
RUN pip3 install --no-cache-dir --break-system-packages \
    fastapi uvicorn python-multipart \
    redis rq \
    whisperx \
    faster-whisper \
    demucs \
    soundfile librosa audioread \
    requests httpx

WORKDIR /app
```

---

## 🧠 Audio Gateway API

`/data/ai/01-workspace/audio/gateway/main.py` — the single entry point.

### Model Tier Routing

```python
MODEL_TIERS = {
    "lipsync": {
        "draft":      "museTalk",       # ~4GB, fast, portrait
        "production": "latentsync",     # ~6GB, quality portrait
        "cinematic":  "hallo2",         # ~10GB, half-body + expression
        "fullbody":   "wan22_i2v",      # ~14GB, use ComfyUI existing workflow
    },
    "tts": {
        "draft":      "fish_speech_fast",
        "production": "fish_speech_full",
    },
    "music": {
        "draft":      "ace_step",       # fast text-to-music
        "production": "stable_audio",   # cinematic/ambient, 30-90s
        "song":       "yue_7b",         # full song with lyrics + vocals
    }
}
```

### Job Types

| job_type | Queue | Worker | Timeout |
|---|---|---|---|
| `transcribe` | stt | workers/stt.py | 600s |
| `clone` | voice | workers/voice.py | 300s |
| `tts` | voice | workers/voice.py | 300s |
| `lipsync` | lipsync | workers/lipsync.py | 1800s |
| `music` | music | workers/music.py | 1800s |
| `dub` | dub | workers/dub.py | 3600s |

### API Endpoints

```bash
# Submit job
POST http://localhost:9000/audio/job
  job_type=lipsync
  quality=production
  language=en
  text="Your narration here"
  source_file=@portrait.jpg
  voice_ref=@voice_sample.wav
  webhook_url=         (optional)

# → { "job_id": "abc123", "status": "queued", "type": "lipsync", "quality": "production" }

# Poll status
GET http://localhost:9000/audio/status/abc123
# → { "status": "finished", "result": { "output_file": "..." } }

# Health
GET http://localhost:9000/audio/health
```

---

## 🗣️ User Intent Router

The router converts three questions into a deterministic `(job_type, model_tier)` pair. No user needs to know which model runs.

```
Q1: What do you need?
  A → Speaking avatar / talking head   → lipsync
  B → Voiceover narration (no video)   → tts
  C → Background / ambient music       → music_ambient
  D → Full song with vocals            → music_song
  E → Transcribe audio or video        → transcribe
  F → Dub video into another language  → dub

Q2: Output priority?
  A → Fast draft                       → draft
  B → Production quality               → production
  C → Cinematic / maximum              → cinematic

Q3: Voice reference available?
  A → Yes — I have a clip to clone     → voice_profile: <upload>
  B → No — use synthetic voice         → voice_profile: null
```

Full routing table:

| Intent | Quality | Job type | Model tier | VRAM needed |
|---|---|---|---|---|
| Speaking avatar | draft | lipsync | MuseTalk | ~4GB |
| Speaking avatar | production | lipsync | LatentSync | ~6GB |
| Speaking avatar | cinematic | lipsync | Hallo2 | ~10GB |
| Voiceover | draft | tts | Fish Speech fast | ~4GB |
| Voiceover | production | tts | Fish Speech full | ~8GB |
| Background music | draft | music | ACE-Step | ~8GB |
| Background music | production | music | Stable Audio Open | ~8GB |
| Full song | any | music | YuE 7B | ~16GB (music-mode.sh) |
| Transcribe | draft | transcribe | Whisper only | ~2GB |
| Transcribe | production | transcribe | Whisper + WhisperX | ~2GB |
| Dub | production | dub | Whisper→vLLM→Fish | ~24GB seq |

---

## 🎬 Avatar Pipeline (Core YouTube Feature)

A user submits a photo and a voice sample → receives a speaking avatar video.

```
portrait.jpg + voice_sample.wav
         │
         ▼
[Demucs]              ← separate speech from music/noise in the sample
         │            ← output: voice-clean/{job_id}/vocals.wav
         ▼
[Fish Speech clone]   ← create reusable voice profile
         │            ← output: voices/{profile_name}.wav
         ▼
[Fish Speech TTS]     ← synthesise narration text in cloned voice
         │            ← quality tier → speed parameter set here
         ▼
[Lip Sync model]      ← draft=MuseTalk / production=LatentSync / cinematic=Hallo2
         │
         ▼
[Output MP4]          ← /outputs/audio/lip-sync/{job_id}_lipsync.mp4
```

**Full-body alternative:** For full-body character animation, use the existing ComfyUI workflow (Wan 2.2 I2V from FLUX.2 keyframe). The avatar pipeline handles portraits; Wan 2.2 handles full-body. These are complementary, not competing.

### Forensic Integration (NEW — audio for client work)

The forensic pipeline (`client-job.sh`) already writes `_final-bundle.json`. The audio stack can extend this:

```
_final-bundle.json contains: scene description, objects, lighting, atmospheric elements
         │
         ▼
[Auto-generate narration prompt]   ← vLLM (Nemotron or CPU floor) drafts narration text
         │                         ← "This scene shows... Rain is present... Vehicle removed..."
         ▼                         ← (This runs AFTER forensic-mode → creative-mode handoff)
[Fish Speech TTS]                  ← narration voice for client preview
         │
         ▼
[Optional: sync to video output]   ← FFmpeg: add narration track to ComfyUI output
```

---

## 🎵 Music Pipeline

### Tool Decision

```
Need full song with lyrics + vocals?    → YuE 7B   (music-mode.sh — exclusive)
Need instrumental / ambient / cinematic?→ Stable Audio Open (creative mode, alongside ComfyUI)
Need fast music iteration for a draft?  → ACE-Step (creative mode, alongside ComfyUI)
Need vocal style conversion?            → RVC on top of any output
```

### YuE Prompt Format

```
Genre tags: dark electronic, cinematic, heavy bass, atmospheric

Lyrics:
[verse]
Your lyrics here — specific imagery, not vague

[chorus]
Chorus content — repeated phrase, emotional anchor

[verse]
Second verse

[outro]
Optional final section
```

> **YuE + RVC:** YuE generates a song with a generic vocal. Run output through RVC with a voice reference to apply a specific cloned voice. Full pipeline: `music-mode.sh` → YuE job → `audio-mode.sh` → RVC worker.

---

## 🌐 Auto-Dubbing Pipeline

### Two approaches

**`video_locked`** — existing video, dub audio onto it:
```
[Input video]
    → [FFmpeg: extract 16kHz WAV]
    → [WhisperX: transcribe + word-level timestamps]
    → [vLLM (Nemotron or CPU): translate with duration guidance]
    → [Fish Speech TTS: dubbed audio at calculated speed]
    → [Generate .srt subtitle file]
    → [FFmpeg: replace audio track]
    → [Dubbed MP4 output]
```

**`audio_first`** — generate new video to match dubbed audio:
```
[Input video]
    → [Same pipeline through Fish Speech]
    → [dub_analysis.json output]
        {
          "dubbed_audio": "...",
          "speech_rate_wpm": 145,
          "total_duration_seconds": 42,
          "word_timings": [...],
          "video_generation_notes": "Generate 42s video. Character speaks 145 wpm. Sync lip movement to dubbed_audio track."
        }
    → Feed to Wan 2.2 / HunyuanVideo as generation guidance
```

> **Translation prompt design:** The vLLM translation call includes the source speech rate (WPM) and total duration. This requests a length-matched translation — the primary mechanism for timing alignment without external TTS rate manipulation. Same local Nemotron or CPU PRISM used for translation — no cloud, no data leaves machine.

---

## 🔧 Demucs — Voice Sample Cleaning

**Must run before any voice clone.** Raw recordings with background music produce robotic clones.

```bash
export TORCH_HOME=/data/ai/07-cache/torch   # keep weights on data drive, not OS

# Extract vocals only (for voice cloning)
demucs --two-stems vocals \
  --out /data/ai/03-data/audio/voice-clean/ \
  /data/ai/03-data/audio/voice-samples/raw_sample.mp3

# Clean vocal at:
# /data/ai/03-data/audio/voice-clean/htdemucs/raw_sample/vocals.wav

# Full stem separation (for music remixing: vocals + drums + bass + other)
demucs --out /data/ai/08-portfolio/outputs/audio/stems/ /path/to/song.mp3
```

---

## 🚀 Build Order

Follow the SDD pattern: `sdd-snapshot.sh` before each phase, `sdd-verify.sh` after.

| Phase | Component | Rationale | Est. Time |
|---|---|---|---|
| A1 | Directory setup | No dependencies | 5 min |
| A2 | Redis + RQ + rq-dashboard | Foundation — nothing works without it | 30 min |
| A3 | Audio Gateway API | Single entry point, health check target | 45 min |
| A4 | Whisper V3 Turbo + WhisperX | Simplest GPU task — validates CUDA in audio containers | 1 hr |
| A5 | Fish Speech 1.5 + Demucs | Core TTS — required by both lipsync and dubbing | 1–2 hr |
| A6a | MuseTalk | Prove avatar pipeline end-to-end before adding quality tiers | 1–2 hr |
| A6b | LatentSync + Hallo2 | Upgrade quality tiers after A6a confirmed | 1–2 hr |
| A7 | ACE-Step + Stable Audio Open + YuE | Music stack — self-contained, no deps on A4–A6 | 2–3 hr |
| A8 | Full dubbing pipeline | Requires A4 + A5 + gateway working | 2 hr |
| A9 | DiffSinger | Optional — only if MIDI singing is needed | 1 hr |

> **Do not install everything at once.** Each phase validates the previous one.

---

## 🖥️ Mac Aliases (Add to ~/.zshrc)

```bash
# === AUDIO STACK ALIASES (v1.7 addition) ===

# Audio mode control
alias beast-audio='ssh mushi@mushishi "/data/ai/01-workspace/scripts/audio-mode.sh"'
alias beast-audio-light='ssh mushi@mushishi "/data/ai/01-workspace/scripts/audio-mode.sh light"'
alias beast-audio-stop='ssh mushi@mushishi "/data/ai/01-workspace/scripts/audio-stop.sh"'
alias beast-music='ssh mushi@mushishi "/data/ai/01-workspace/scripts/music-mode.sh"'

# Audio status
alias beast-audio-status='ssh mushi@mushishi "\
  echo \"=== Audio Services ==\" && \
  docker ps --format \"table {{.Names}}\t{{.Status}}\" | grep -E \"redis|audio|tts|lipsync|music\" && \
  echo \"\" && \
  echo \"=== GPU (Audio VRAM usage) ==\" && \
  nvidia-smi --query-gpu=memory.used,memory.free,power.draw --format=csv,noheader && \
  echo \"\" && \
  echo \"=== Active Jobs ==\" && \
  curl -s http://localhost:9000/audio/health 2>/dev/null || echo 'Gateway not running'\
"'

# Audio job monitoring
alias audio-jobs='open http://mushishi:9010'   # rq-dashboard

# Quick submit examples
alias audio-test='ssh mushi@mushishi "curl -s http://localhost:9000/audio/health | python3 -m json.tool"'
```

### Updated beast-status (add audio section)

Add to the existing `beast-status` alias in `~/.zshrc`:

```bash
alias beast-status='ssh mushi@mushishi "\
  echo \"=== GPU ==\" && \
  nvidia-smi --query-gpu=name,memory.used,memory.free,power.draw,temperature.gpu,clocks.throttle_reasons --format=csv,noheader && \
  echo \"\" && \
  echo \"=== CPU Nemotron ==\" && \
  (systemctl is-active nemotron-cpu 2>/dev/null && echo RUNNING || echo STOPPED) && \
  echo \"\" && \
  echo \"=== Docker ==\" && \
  docker ps --format \"table {{.Names}}\t{{.Status}}\" && \
  echo \"\" && \
  echo \"=== Audio Gateway ==\" && \
  (curl -s http://localhost:9000/audio/health 2>/dev/null | python3 -c \"import sys,json; d=json.load(sys.stdin); print('RUNNING')\" 2>/dev/null || echo 'STOPPED') && \
  echo \"\" && \
  echo \"=== RAM ==\" && \
  free -h | grep Mem && \
  echo \"\" && \
  echo \"=== Groq Usage ==\" && \
  echo \"(check: https://console.groq.com/settings/usage)\"\
"'
```

---

## ⚡ Quick Reference Commands

```bash
# === FROM MAC (Tailscale) ===

beast-audio              # Start audio stack (full tier)
beast-audio-light        # Start audio stack (draft tier only — less VRAM)
beast-audio-stop         # Stop audio services, free VRAM
beast-music              # YuE 7B dedicated music mode
beast-audio-status       # GPU + audio service status
audio-jobs               # Open rq-dashboard in browser

# === FROM MUSHISHI (Linux) ===

# Submit avatar job (portrait + voice clone)
curl -X POST http://localhost:9000/audio/job \
  -F "job_type=lipsync" \
  -F "quality=production" \
  -F "text=Your narration text here" \
  -F "source_file=@/path/to/portrait.jpg" \
  -F "voice_ref=@/path/to/voice_sample.wav"

# Submit full song
curl -X POST http://localhost:9000/audio/job \
  -F "job_type=music" \
  -F "quality=song" \
  -F "text=dark cyberpunk electronic heavy bass" \
  -F "lyrics=[verse]
Your lyrics here
[chorus]
Chorus here"

# Submit ambient music for video scoring
curl -X POST http://localhost:9000/audio/job \
  -F "job_type=music" \
  -F "quality=production" \
  -F "text=cinematic atmospheric tension building underscore"

# Transcribe with word timestamps
curl -X POST http://localhost:9000/audio/job \
  -F "job_type=transcribe" \
  -F "quality=production" \
  -F "source_file=@/path/to/video.mp4"

# Auto-dub video (video_locked approach)
curl -X POST http://localhost:9000/audio/job \
  -F "job_type=dub" \
  -F "language=es" \
  -F "approach=video_locked" \
  -F "source_file=@/path/to/video.mp4"

# Poll job status
curl http://localhost:9000/audio/status/<job_id>

# Clean voice sample before cloning
demucs --two-stems vocals \
  --out /data/ai/03-data/audio/voice-clean/ \
  /data/ai/03-data/audio/voice-samples/raw.mp3
```

---

## 🔑 Key File Locations (Audio)

| File | Purpose |
|---|---|
| `/data/ai/06-configs/audio/docker-compose.yml` | All audio Docker services |
| `/data/ai/06-configs/audio/Dockerfile.audio` | Shared base image |
| `/data/ai/01-workspace/audio/gateway/main.py` | Audio Gateway API |
| `/data/ai/01-workspace/audio/gateway/intent_router.py` | User intent → model tier |
| `/data/ai/01-workspace/audio/gateway/workers/stt.py` | Whisper + WhisperX worker |
| `/data/ai/01-workspace/audio/gateway/workers/voice.py` | Fish Speech + Demucs worker |
| `/data/ai/01-workspace/audio/gateway/workers/lipsync.py` | Lip sync worker (all tiers) |
| `/data/ai/01-workspace/audio/gateway/workers/music.py` | Music generation worker |
| `/data/ai/01-workspace/audio/gateway/workers/dub.py` | Auto-dub pipeline |
| `/data/ai/01-workspace/scripts/audio-mode.sh` | Start audio stack |
| `/data/ai/01-workspace/scripts/audio-stop.sh` | Stop audio stack |
| `/data/ai/01-workspace/scripts/music-mode.sh` | YuE dedicated mode |
| `/data/ai/02-models/audio/voices/` | Cloned voice profiles — do not delete |
| `/data/ai/08-portfolio/outputs/audio/` | All audio outputs |

---

## 🛠️ Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Voice clone sounds robotic | Raw recording has music/noise | Run Demucs first: `--two-stems vocals` on the source |
| Dubbed audio doesn't match lip movement | `video_locked` with long/fast text | Switch to `audio_first` — feed `dub_analysis.json` to Wan 2.2 |
| YuE OOM crash | Running alongside vLLM or ComfyUI | `music-mode.sh` — stops both first |
| MuseTalk: face not detected | Low res / extreme angle | Front-facing portrait, ≥512×512, face fills >30% of frame |
| Hallo2 slow or OOM | Full VRAM from other services | `audio-stop.sh` → then restart only Hallo2 |
| WhisperX alignment fails | Language not in alignment model | Use `quality=draft` (standard Whisper, no word timestamps) |
| Fish Speech multilingual weak | Using pre-1.5 model | Confirm `fish-speech-1.5` checkpoint — earlier versions are English-biased |
| Stable Audio HuggingFace 401 | Licence not accepted on HF portal | Accept licence at huggingface.co/stabilityai/stable-audio-open-1.0 |
| RQ jobs not processing | Workers not started | `docker ps` — confirm `creative-tts`, `creative-lipsync`, `creative-music` running |
| Audio gateway health 503 | Redis not up | `docker start creative-redis`, then restart `creative-audio-gateway` |
| MuseTalk/LatentSync produce no face movement | Wrong audio format | Ensure audio is WAV, 16kHz mono — `ffmpeg -i input.wav -ar 16000 -ac 1 output.wav` |

---

## 📋 SDD Integration

Follow the standard Mushishi SDD pattern for each phase.

```bash
# Before each phase
/data/ai/01-workspace/scripts/sdd-snapshot.sh \
  --spec /data/ai/08-portfolio/specs/2026-05-23-audio-stack-phase-A2.md

# Execute the phase

# After each phase — gates that must pass
/data/ai/01-workspace/scripts/sdd-verify.sh \
  --spec /data/ai/08-portfolio/specs/2026-05-23-audio-stack-phase-A2.md
```

**sdd-verify.sh additions for audio** (add to the check() block):

```bash
check "audio-gw" "Audio gateway health"   "curl -sf http://localhost:9000/audio/health"
check "redis"    "Redis reachable"        "docker exec creative-redis redis-cli ping | grep -q PONG"
check "rq-dash"  "rq-dashboard reachable" "curl -sf -o /dev/null http://localhost:9010/"
```

---

## 🔮 Future Additions (Audio-Specific)

| Tool | Why deferred | When to add |
|---|---|---|
| **DiffSinger** | Requires MIDI. YuE→RVC covers singing without MIDI | Only if MIDI composition workflow exists |
| **CosyVoice2** | Redundant with Fish Speech | If streaming TTS becomes a specific need |
| **Bark** | Expressive TTS but larger, slower than Fish Speech | If fine-grained emotion control is needed |
| **AudioCraft / MusicGen** | Non-commercial licence blocks platform use | Never — unless licence changes |
| **Wav2Lip** | Older lip sync, lower quality than MuseTalk | Never — MuseTalk/LatentSync supersede it |
| **Multi-language dubbing queue** | Complex scheduling, low priority | Phase 7+ when dubbing is daily |
| **Subtitle burn-in workflow** | `.srt` exists; burn-in is FFmpeg one-liner | Add to creative-mode.sh when needed |

---

## 🔄 Update Strategy

Same discipline as the main stack:

1. **Snapshot first** (SDD snapshot before any update)
2. **One component at a time** — never update Fish Speech and LatentSync in the same session
3. **Test the audio gateway health endpoint** after every update
4. **Test a real job** (not just health) — submit a short TTS job and confirm output
5. **Wait 24h before next update**

Model weight updates specifically:
- Download new weights to a versioned subdirectory (e.g., `fish-speech-1.6/`)
- Test new weights against old checkpoint before replacing
- Only update `docker-compose.yml` volume mount after testing passes

---

*Audio Stack v1.0.0 — May 23, 2026 — Mushishi Sovereign AI Stack companion*
*Hardware: RTX 5090 · Ubuntu 24.04 · CUDA 13.2 · 128GB DDR5*
*All tools: T1 Sovereign, MIT or Apache 2.0, fully local*
