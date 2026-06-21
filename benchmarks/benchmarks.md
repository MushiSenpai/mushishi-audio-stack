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
| Lipsync draft | MuseTalk 1.5 | portrait + audio (34.5s) | MP4 1024² 25fps | **78s** | ~7.7GB | ✅ WORKING — dedicated `creative-musetalk:9005` (rtmlib ONNX DWPose, no mmcv). Social-grade, no melt. |
| Lipsync production | LatentSync | portrait + audio | H.264 | — | — | ⚠️ BLOCKED — corrupt output (mouth melt + affine seams) in the unified worker; **superseded by MuseTalk** (not rebuilt) |
| Lipsync cinematic | Hallo2 | portrait + audio (34.5s) | MP4 512² 25fps | **1197s** | ~13.3GB | ✅ WORKING — dedicated `creative-hallo2:9006` (diffusers 0.32.2 pin). Head pose + expression + CodeFormer; ~15× slower than MuseTalk → non-headshot/expressive framing. |
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

## Lip-sync status — REBUILT (2026-06-21 / 06-22)

Consolidating into one worker env broke all three local lip-sync models, each from a
different conflict. **Fix = a dedicated, pinned, isolated image+service per model** — the
worker HTTP-calls each by name, so the working YuE+Fish env is never touched. Two were
rebuilt; LatentSync was dropped (MuseTalk supersedes it).

- ✅ **MuseTalk 1.5** (`creative-musetalk:9005`, social/draft) — the mmcv/SM_120 wall is
  unwinnable (no `mmcv._ext` wheel for torch 2.8/cu128); fix = run DWPose via **rtmlib
  ONNX**, no mmcv. 78s / 34.5s @1024², ~7.7GB, coherent mouth, no melt. Spec:
  `docs/musetalk-1.5-rebuild-spec.md`.
- ✅ **Hallo2** (`creative-hallo2:9006`, cinematic) — Hallo2 ships its own UNet overriding
  the OLD `_set_gradient_checkpointing(module, value)` signature, so base diffusers 0.38
  (`enable=`) crashed; fix = pin **`diffusers==0.32.2` alone** (+ `decorator==4.4.2` for
  moviepy's mp4 mux). 1197s / 34.5s @512², ~13.3GB; head pose + expression + CodeFormer.
  ~15× slower than MuseTalk → reserve for non-headshot/expressive framing. Spec:
  `docs/hallo2-rebuild-spec.md`.
- ⚠️ **LatentSync** — corrupt output (mouth melt + affine seams) in the unified worker;
  **not rebuilt** (MuseTalk is the working portrait path).

**Quality ceiling:** local lip-sync tops out at **social / cinematic grade**.
**Broadcast-grade close-ups stay cloud-only** (Kling / Hedra / HeyGen / Sync.so).

## Samples

Curated, copyright/likeness-clean outputs — all generated on the box (synthetic portrait,
LLM-written lyrics, synthetic TTS voice). Hear/see them:

| File | From | What it is |
|---|---|---|
| [`samples/voiceover.wav`](samples/voiceover.wav) | TTS — Fish Speech 1.5 | 34.5s brand voiceover (synthetic voice) |
| [`samples/song-pop-satire.mp3`](samples/song-pop-satire.mp3) | Music — YuE 7B | 58s full song, satirical lyrics |
| [`samples/song-hiphop.mp3`](samples/song-hiphop.mp3) | Music — YuE 7B | 48s conscious-rap, satirical lyrics |
| [`samples/instrumental.mp3`](samples/instrumental.mp3) | Music — ACE-Step | stereo instrumental (source 48kHz; 320k mp3 here) |
| [`samples/portrait.png`](samples/portrait.png) | Image — FLUX.2 | synthetic portrait (the avatar input; owned, no real likeness) |
| [`samples/avatar-musetalk-social.mp4`](samples/avatar-musetalk-social.mp4) | Lip-sync — MuseTalk 1.5 | 34.5s social-grade talking-head, 1024² (synthetic portrait + TTS voice) |
| [`samples/avatar-hallo2-cinematic.mp4`](samples/avatar-hallo2-cinematic.mp4) | Lip-sync — Hallo2 | 34.5s cinematic talking-head, 512², head pose + expression (synthetic portrait + TTS voice) |

Local lip-sync now ships at **social grade (MuseTalk)** and **cinematic grade (Hallo2)** —
both clips above are generated on the box from the synthetic portrait. **Broadcast-grade
close-ups still use a cloud path** (see "Lip-sync status" above).
