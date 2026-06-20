# Audio Stack Benchmarks

Measured on: RTX 5090 32GB · Ryzen 9 9900X3D · 128GB DDR5 · Ubuntu 24.04.
Updated weekly as runs are recorded. Empty cells = not yet measured (honesty
over padding — this table fills in public).

Machine-readable version (same numbers, full schema incl. throughput/cost):
[`audio-benchmarks.csv`](audio-benchmarks.csv) — this is what the public
[workflow catalogue](https://theinvalid.me/workflow-catalogue) is generated from.

| Pipeline | Model/tier | Input | Output | Wall clock | Peak VRAM | Notes |
|---|---|---|---|---|---|---|
| TTS | Fish Speech 1.5 full | 75-word ad-read, avatar-v1 clone | 34.5s WAV | **25s** | ~4GB | E2 chain stage 1; ~145 wpm |
| Voice clone | Demucs + Fish Speech | 30s raw sample | voice profile | | | |
| Lipsync draft | MuseTalk 1.5 | portrait + audio | MP4 | — | — | ⚠️ BLOCKED (mmcv/cu130) — the REBUILD TARGET (2026 #1 open model) |
| Lipsync production | LatentSync | portrait + audio | H.264 | — | — | ⚠️ BLOCKED — produces corrupt output (mouth melt + affine seams) in the unified worker (silent diffusers drift) |
| Lipsync cinematic | Hallo2 | portrait + audio | H.264 MP4 | — | — | ⚠️ BLOCKED — diffusers API break in the unified worker; worked in its own container 2026-05-24 |
| Music (song) | YuE 7B | genre + lyrics, 2 short segments | 15s MP3 (mono 44.1kHz, 64kbps) | **2m 56s** | ~16GB | 2026-06-10, fresh rebuilt container, zero manual installs; mono is a YuE vocoder limit |
| Music (instrumental) | ACE-Step 3.5B | genre/mood tags | 30s **stereo 48kHz** WAV | **~10s** | 7.4GB | WORKING via isolated venv; 1.8s diffusion (~30× realtime); stereo, higher-fi than YuE. (Maestro's old "ACE-Step" score was actually YuE.) |
| Transcribe | Whisper V3 Turbo + WhisperX | 60s speech video | JSON + word timings | | ~2GB | |
| Dub (video-locked) | full pipeline | 60s EN video → ES | dubbed MP4 + SRT | | | |

## Quality bench (client-readiness gate)

Three reference jobs, scored against fixed criteria — pass/fail published either way:

1. **Avatar ad-read (30s)** — criteria: no visible lipsync drift in first 10s to a naive viewer; voice not robotic.
2. **Dubbed clip (60s)** — criteria: per-sentence timing within ±0.5s; correct SRT.
3. **Voice clone fidelity** — criteria: blind A/B against source speaker.

Results (E2, 2026-06-12): **PARTIAL PASS.** Full text→clone→TTS→lipsync chain ran end to end (TTS 25s + LatentSync 280s). Gross sync correct, but lip-interior artifacts at full-frame.

## Lip-sync status — REBUILD REQUIRED (re-verified 2026-06-21)

Deeper testing on 2026-06-21 found **all three local lip-sync models are broken** in the
consolidated `creative-audio-worker`, each from a different environment conflict:

- **LatentSync** — runs but emits **structurally corrupt** output (mouth melt + affine
  seams), reproduced on two different portraits (full-frame AND margined). The earlier
  "280s" run produced garbage, not a usable clip. Cause: silent diffusers/version drift.
- **Hallo2** — `UNet2DConditionModel._set_gradient_checkpointing() got an unexpected
  keyword 'enable'` (needs older diffusers than the worker carries). Also needed
  `libGLESv2.so.2` (fixed live). Worked in its **own** container 2026-05-24.
- **MuseTalk 1.5** — still blocked on mmcv/cu130. This is the **2026 #1 open lip-sync
  model** and the chosen **rebuild target**.

**Root cause:** consolidating into one worker env broke models that each need pinned,
isolated environments. **Fix = a dedicated, pinned env per model** — spec:
`~/Documents/audio/musetalk-1.5-rebuild-spec.md` (separate session, ~half day).

**Quality ceiling:** local lip-sync tops out at **social-media / marketing grade**.
**Broadcast-grade is cloud-only** (Kling / Hedra / HeyGen / Sync.so) — develop that
separately. Do not advertise an avatar tile as working until the rebuild passes its
quality gate.

## Samples — pending

A curated, commercial-grade sample pack (copyright/likeness-clean) is in progress and
will be added here before this repo's samples are advertised. The internal benchmark
outputs that produced the numbers above are **not** published, because they used test
assets (a real-person portrait for the avatar, an unverified TTS clip, lo-fi mono music)
that aren't cleared for public/commercial use. Numbers are real; samples ship when clean.
