---
tags: [ai/audio, ai/lip-sync, infra/rebuild, spec/sdd]
status: TODO — separate focused session (~half day)
created: 2026-06-21
target: dedicated MuseTalk 1.5 lip-sync environment (best-quality open model, social-grade)
owner: unassigned (spin up as its own Claude session)
companion: ~/Documents/audio/mushishi-audio-stack-v1.0.1.md
---

# Spec — Dedicated MuseTalk 1.5 lip-sync rebuild (social-grade local avatar)

> **Why this exists:** As of 2026-06-21 **all three local lip-sync models are broken**
> inside the consolidated `creative-audio-worker`, each from a different environment
> conflict. This spec rebuilds **one** model in an isolated, pinned environment to get a
> working **social-grade** talking-head. Broadcast-grade stays **cloud** (see §Non-goals).

## 1. Problem (verified 2026-06-21)

The audio stack was consolidated into a single worker env (torch 2.8 + cu130 + newer
diffusers, tuned for YuE + Fish Speech). That env breaks every lip-sync model:

| Model | Failure (observed) | Class |
|---|---|---|
| **LatentSync** (production) | runs without error but output is **structurally corrupt** — glassy/melted mouth, diagonal affine seams across the lower face. Reproduced on two different portraits (full-frame AND margined), so it is **not** a margin/quality issue. | silent diffusers/version drift in the UNet/VAE decode |
| **Hallo2** (cinematic) | `TypeError: UNet2DConditionModel._set_gradient_checkpointing() got an unexpected keyword 'enable'` — needs an **older diffusers** than the worker carries. (Also needed `libGLESv2.so.2`, fixed live via `apt-get install libgles2 libegl1` — bake into the Dockerfile.) | diffusers API break |
| **MuseTalk** (draft) | mmcv build incompatible with cu130 / torch nightly | mmcv/CUDA build block |

**Root cause:** these models each need **pinned, isolated environments** — which is why
they were separate containers originally (Hallo2 produced a clean 512×512 clip in its own
container on 2026-05-24). One shared env cannot satisfy all of them.

## 2. Goal

A **dedicated, pinned, isolated** environment running **MuseTalk 1.5** — the 2026
consensus #1 open-source lip-sync model — that:
1. Takes `portrait image + audio wav` → talking-head MP4.
2. Produces **social-grade** output: a naive viewer can't spot lip drift in the first 10s,
   mouth interior is coherent (no melt/smear).
3. Is reachable behind the existing audio gateway `lipsync` job (`model_tier=museTalk`),
   exactly like `creative-tts` is a separate service the worker calls.
4. Does **not** disturb the working `creative-audio-worker` (YuE + Fish Speech keep running).

## 3. Non-goals

- **Broadcast-grade close-ups.** No local open model reliably hits this in 2026. Use a
  **cloud** path for broadcast (Kling / Hedra / HeyGen / Sync.so). Document this in the
  catalogue + audio doc (done 2026-06-21).
- Fixing LatentSync / Hallo2 (optional later — see §7 fallback).

## 4. Assets already in place (no re-download needed)

- MuseTalk 1.5 weights: `/data/ai/02-models/audio/museTalk/musetalkV15/unet.pth` (+ DWPose).
- MuseTalk repo/code: `/data/ai/01-workspace/audio/museTalk/` (`scripts/inference.py`, `--version v15`).
- Gateway already routes `lipsync` draft tier → `museTalk` (see `gateway/intent_router.py`,
  `workers/lipsync.py` museTalk branch).

So the block is **purely the runtime env (mmcv/CUDA build)**, not weights or wiring.

## 5. Approach — isolated, pinned container

Build a **separate Docker image** (`mushishi-musetalk`) with a pinned stack where mmcv
actually builds for this GPU. Key constraint: **RTX 5090 = SM_120 needs CUDA ≥12.8 kernels**,
so the env must use an SM_120-capable torch AND a matching mmcv.

Decision tree (resolve in the session, in this order):
1. **Preferred:** torch 2.8 + CUDA 12.8/13 (SM_120) + **mmcv built from source** against it
   (`MMCV_WITH_OPS=1 pip install mmcv==<ver> --no-binary mmcv`). Time-boxed; if the build
   fights for >2h, fall to (2).
2. **Fallback A:** MuseTalk 1.5 may need only **mmpose/DWPose**, not full mmcv-ops. Check if
   `mmcv-lite` (no compiled ops) + a prebuilt DWPose ONNX satisfies inference → avoids the
   source build entirely.
3. **Fallback B:** pin to the newest torch that has **prebuilt mmcv wheels** AND SM_120
   kernels; verify `torch.cuda.is_available()` + a real GPU op on the 5090.

Container shape (mirror `creative-tts`): `runtime: nvidia`, internal port (e.g. `:9005`),
mount `02-models/audio/museTalk` ro + `03-data/audio` + `08-portfolio/outputs/audio/lip-sync`,
exposes a tiny FastAPI `/lipsync` (portrait+audio → mp4 path). Worker's `lipsync.py` museTalk
branch calls it by service name (like it calls `creative-tts:9002`).

## 6. Tasks (SDD — snapshot before, verify after)

1. `sdd-snapshot.sh` for this spec.
2. New `Dockerfile.musetalk` (CUDA 12.8 base; pinned torch; mmcv per §5 decision tree; MuseTalk 1.5 deps: mmpose, mmdet/DWPose, ffmpeg, face parsing).
3. Build image; **gate G1:** `python -c "import mmcv; import torch; assert torch.cuda.is_available()"` + a 256×256 GPU matmul on the 5090.
4. Smoke test: `scripts/inference.py --version v15` on the margined portrait
   (`03-data/audio/sample-pack/portrait_margined.png`) + `voiceover.wav` →
   **gate G2:** output mp4 exists, face detected, mouth opens/closes vs `silencedetect`.
5. **Quality gate G3 (the real one):** extract mid-speech frames; confirm **no melt/smear**,
   coherent mouth interior. Pass/fail published either way (honesty convention).
6. Add `musetalk` service to `06-configs/audio/docker-compose.yml`; point `workers/lipsync.py`
   museTalk branch at it; **gate G4:** end-to-end via gateway `POST :9000/audio/job
   job_type=lipsync quality=draft`.
7. Update `audio-benchmarks.csv` (MuseTalk row: real wall-clock + VRAM + sample), regenerate
   the catalogue, mark the avatar tile **measured (social-grade)**.
8. Bake the `libgles2/libegl1` fix + the pinned env into the Dockerfile (no runtime rot).
9. `sdd-verify.sh`; append lessons to `theinvalid-site/pipeline/queue.md §B` + audio repo `LESSONS.md`.

## 7. Fallback if MuseTalk 1.5 won't reach social-grade

Restore the **dedicated Hallo2 container** with its proven pinned env (it worked
2026-05-24 — pin the diffusers version that has the old `_set_gradient_checkpointing`
signature + the 6 documented Hallo2 patches incl. `libGLESv2`). Hallo2 was cinematic-tier
and bundles CodeFormer, so it is the strongest local fallback.

## 8. Quality target & catalogue language

- **Local lip-sync = "Social Media & Marketing" grade only.** Catalogue + audio doc must say
  this explicitly, and that **broadcast-grade uses a cloud path**.
- Do **not** advertise an avatar tile as working until **G3** passes.

## 9. Rollback

Everything is a new image + a new compose service. If it fails: `docker compose rm musetalk`,
revert the `lipsync.py` museTalk branch. The working `creative-audio-worker` (YuE + Fish
Speech) is never touched.

## 10. References

- MuseTalk 1.5 — github.com/TMElyralab/MuseTalk (perceptual + GAN + sync loss; "real-time high quality").
- 2026 lip-sync comparisons consistently rank MuseTalk #1 among open models (LatentSync/Wav2Lip lower).
- Broadcast (cloud): Kling, Hedra, HeyGen, Sync.so.
