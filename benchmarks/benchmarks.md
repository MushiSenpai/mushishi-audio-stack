# Audio Stack Benchmarks

Measured on: RTX 5090 32GB · Ryzen 9 9900X3D · 128GB DDR5 · Ubuntu 24.04.
Updated weekly as runs are recorded. Empty cells = not yet measured (honesty
over padding — this table fills in public).

| Pipeline | Model/tier | Input | Output | Wall clock | Peak VRAM | Notes |
|---|---|---|---|---|---|---|
| TTS | Fish Speech 1.5 full | 60-word narration | 16kHz WAV | | | |
| Voice clone | Demucs + Fish Speech | 30s raw sample | voice profile | | | |
| Lipsync draft | MuseTalk | portrait + 10s audio | MP4 | | | |
| Lipsync production | LatentSync | 626×732 portrait + 9.4s audio | H.264 MP4 | | | first verified output 2026-05-24 |
| Lipsync cinematic | Hallo2 | 512×512 portrait + 9.4s audio | H.264 MP4 | | | first verified output 2026-05-24 |
| Music (song) | YuE 7B | genre + lyrics, 2 short segments | 15s MP3 (mono 44.1kHz, 64kbps) | **2m 56s** | ~16GB | 2026-06-10, fresh rebuilt container, zero manual installs; mono is a YuE vocoder limit |
| Transcribe | Whisper V3 Turbo + WhisperX | 60s speech video | JSON + word timings | | ~2GB | |
| Dub (video-locked) | full pipeline | 60s EN video → ES | dubbed MP4 + SRT | | | |

## Quality bench (client-readiness gate)

Three reference jobs, scored against fixed criteria — pass/fail published either way:

1. **Avatar ad-read (30s)** — criteria: no visible lipsync drift in first 10s to a naive viewer; voice not robotic.
2. **Dubbed clip (60s)** — criteria: per-sentence timing within ±0.5s; correct SRT.
3. **Voice clone fidelity** — criteria: blind A/B against source speaker.

Results: _pending — see repo commits._
