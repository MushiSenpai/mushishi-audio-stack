# Lessons Learned — Audio Stack Install

Every entry below is a real failure hit during installation (May 2026), with the
fix that actually worked. The original spec was wrong or incomplete in all of
these places. If you replicate this stack, read this file first — it will save
you days.

## Infrastructure

**The RQ worker needs its own GPU container.** The gateway only enqueues jobs to
Redis; a separate `audio-worker` container consumes the queues. Without it, jobs
sit in `queued` forever. And the worker must have `runtime: nvidia` +
`NVIDIA_VISIBLE_DEVICES=all` + the deploy GPU block — it runs WhisperX inference
directly. Without it: `CUDA driver version is insufficient` from CTranslate2.

**`host.docker.internal` is not auto-resolved on Linux Docker Engine** (only
Docker Desktop sets it). Add `extra_hosts` with the *compose network's* gateway
IP — not `172.17.0.1`, which is the default bridge and may be blocked by
iptables. Find it: `docker network inspect <network> | grep Gateway`.

**Read-only model mounts need a writable override for user data.** Models mount
`:ro`, but cloned voice profiles are user data living under the models tree.
Docker mount ordering: more specific path wins — add a second rw mount for the
`voices/` subdir.

**Docker builds can fill the OS partition.** PyTorch-nightly image builds are
~38GB each; our `/var` hit 98% and the build failed, leaving runtime pip
installs as a fragile stopgap (deps vanish on container restart). Fix: move the
Docker data-root to the big data drive *before* building large images.

## Whisper / WhisperX

**faster-whisper takes a CTranslate2 model, not HuggingFace safetensors.**
Convert inside the container (`ct2-transformers-converter ... --quantization
float16`), then copy `preprocessor_config.json` from the HF cache into the
CTranslate2 dir — large-v3-turbo needs 128 mels and faster-whisper reads that
from `feature_size`; without it you get silently wrong results.

**Word-level alignment fails for some languages.** Wrap `load_align_model` in
try/except and fall back to uniform word timing within each segment. Never let
alignment failure kill a transcription job.

**Test sources must contain actual speech.** WhisperX VAD finds zero segments in
music/tones/noise. Pipeline tests that "fail" on silent media aren't failures.

## Fish Speech

**Pin the repo to v1.5.1 — never latest main.** Main switched to a
`modded_dac_vq` decoder (dim=1024) incompatible with the fish-speech-1.5
checkpoint (dim=512, `firefly_gan_vq`). Code and weights must move together.

**Install with `--no-deps`.** pyaudio fails to build in slim containers (no
portaudio headers) and is only needed for the demo UI, not the API server.

**Always `raise_for_status()` after the TTS call.** Fish Speech returns HTTP 500
JSON for empty text; without the check, the JSON body gets written as a "WAV"
and the real cause surfaces three steps later as a cryptic decode error.

## Lip sync

**MuseTalk's entry point is `scripts/inference.py`** with a YAML config (not CLI
media args) — generate a per-job YAML at runtime.

**LatentSync requires even pixel dimensions.** Its internal libx264 step rejects
odd width/height; the failure surfaces as an empty-tensor stack error far from
the cause. Crop to even W×H first.

**Hallo2 (cinematic tier) took six separate fixes:** xformers must come from the
PyTorch nightly cu130 index (PyPI xformers drags in stable torch → NCCL ABI
crash); `nvidia-nccl-cu12` ≥ 2.30.4; `libGLESv2.so.2` symlink + `libegl1` for
mediapipe; `attn_implementation="eager"` for Wav2Vec2 (SDPA rejects
`output_attentions`); the output lands at `**/merge_video.mp4`, not `save_path`;
and the repo is `fudan-generative-ai/hallo2` (the similarly-named org without
weights costs you an afternoon).

## Music (YuE 7B)

**Real inference lives at `inference/infer.py`** (the root `infer.py` is a stub)
and must run with `cwd=inference/` because xcodec paths are relative.

**`xcodec_mini_infer` is a separate download** — and a plain `git clone` gives
you 133-byte LFS pointer stubs, not the 1.3GB checkpoint. Use the `hf` CLI,
which resolves LFS natively.

**Patch `flash_attention_2` → `sdpa`.** flash-attn has no prebuilt wheels for
PyTorch nightly; SDPA is built into torch 2.x and performs equivalently on
Blackwell.

**Genre and lyrics are two separate input files**, not one prompt file. Output
is **MP3, mono, 44.1kHz** — workers globbing `*.wav` find nothing.

**`vocos` and `descriptaudiocodec` are bundled inside xcodec** (sys.path
injection) — do NOT pip-install them; but `descript-audiotools` IS required and
is on PyPI under that name, not `audiotools`.

## The June rebuild: nightly wheels are a depreciating asset

Rebuilding this image one month after the original install failed twice from
the same root cause: **"install from the nightly index" instructions have a
shelf life measured in weeks.**

- xformers stopped publishing cu130 nightlies (Dec 2025), so the May
  instruction "xformers from the nightly index" became unbuildable —
  `ResolutionImpossible`, no wheel matches any current torch nightly.
- Putting torch+xformers in one pip invocation (the textbook fix) *also*
  failed: the resolver couldn't bridge a 6-month gap between the two packages'
  newest nightlies.
- The actual fix: the *running* container had quietly ended up on **stable
  torch 2.8.0**, which by June fully supported Blackwell (SM_120) — the entire
  reason for nightlies had expired — and every pipeline had been validated
  against it in daily use. So we pinned the proven stable set
  (`torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 xformers`) and saved a
  `pip freeze` of the working container next to the Dockerfile as ground truth.

Corollary confirmed the hard way: **runtime `docker exec pip install` rots.**
A container recreation silently dropped `sentencepiece`/`pydub` (broke YuE) and
xformers (broke Hallo2's tier) weeks after install. If a dependency matters, it
lives in the Dockerfile — verified here by rebuilding and running a YuE song
job on a fresh container with zero manual installs.

## June 21 update: gateway music, isolated venvs, and the lip-sync env collision

**The "ACE-Step" score was never ACE-Step.** Maestro's music came from
`workers.music.generate(model_tier='yue_7b')` — the gateway's actual `ace_step`
branch pointed `python3` at `/01-workspace/audio/ace-step/inference.py`, which does
not exist (that dir holds the *weights*, not code). ACE-Step's code is the separate
`acestep` package.

**One shared worker env can't host every model — the lip-sync collision.** The
consolidated worker (torch 2.8 + newer diffusers, tuned for YuE + Fish Speech)
silently breaks all three lip-sync models at once: LatentSync emits *structurally
corrupt* output (mouth melt + affine seams — no error, just garbage), Hallo2 throws
`_set_gradient_checkpointing() got an unexpected keyword 'enable'` (needs older
diffusers) plus a missing `libGLESv2.so.2`, and MuseTalk is still mmcv/cu130-blocked.
They worked as *separate* containers. **Lesson: models with conflicting pinned deps
need isolated environments, not one mega-env.** Rebuild target = MuseTalk 1.5 (the
2026 #1 open model). Local lip-sync ceiling = social-grade; broadcast = cloud.

**Isolated venv = the clean way to add a conflicting model without a rebuild.**
`python -m venv --system-site-packages` reuses the image's SM_120 torch, while the
venv's own pinned deps (transformers 4.50, etc.) shadow the system ones *only inside
the venv*. ACE-Step now runs this way (stereo 48kHz, ~10s) and the worker's YuE /
Fish Speech are untouched. The venv lives on a data mount so it survives recreation;
`scripts/setup-acestep-venv.sh` recreates it idempotently.

**Stable Audio: use diffusers, not stable_audio_tools.** `stable_audio_tools`
requires Python <3.11; the worker is 3.12. `diffusers.StableAudioPipeline` works on
3.12 (needs `torchsde` for its scheduler) — stereo 44.1kHz, ~18s.

**`libgles2`, not the nvidia symlink.** The Dockerfile symlinked
`libGLESv2_nvidia.so.2` → `libGLESv2.so.2`, but that target did not resolve on the
as-run worker. `apt install libgles2` ships the real lib (Ubuntu 24.04). Baked.

**The dub is sovereign-isolated from the LLM.** Same-language dub works end-to-end
(~20s). Cross-language needs the translation LLM, but the worker container can't reach
the localhost-bound CPU Nemotron, and LiteLLM needs an API key — which must come from
the worker's *env*, never the public repo. Gated until that networking is wired.

## Meta-lessons

1. **Entry points lie.** Three of five model repos had a different real entry
   point than their README suggested. Always read the code before the docs.
2. **Pin everything.** Two of five repos broke compatibility with their own
   released weights on `main`.
3. **The spec is a hypothesis.** 25+ deviations between plan and working system
   — which is why this file exists and why every phase ended with a verification
   gate, not an assumption.
