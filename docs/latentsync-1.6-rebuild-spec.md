---
tags: [ai/audio, ai/lip-sync, infra/rebuild, spec/sdd]
status: DONE — 2026-06-22 (G1–G4 passed; KEPT as the production portrait tier)
created: 2026-06-22
target: LatentSync 1.6 (portrait lip-sync, the teeth/lip-quality A/B vs MuseTalk) as a dedicated pinned container
owner: completed — mushishi-latentsync image + creative-latentsync:9007 service
result: diffusers==0.32.2 pinned ALONE shadows the base; 1.6 checkpoint on stage2_512.yaml. 1.5 "melt + affine seams" regression CLOSED on both portraits. A/B vs MuseTalk = teeth/lip ~tie (NOT clearly sharper) but cleaner lower-face/beard blending; 242s/34.5s (~0.14x RT), ~20GB. Decision (§6): user KEPT it as production (naturalism edge), draft stays MuseTalk.
companion: ~/Documents/audio/musetalk-1.5-rebuild-spec.md (the proven pattern); ~/Documents/audio/hallo2-rebuild-spec.md (the sibling cinematic rebuild); mushishi-audio-stack repo
---

# Spec — LatentSync 1.6 (portrait lip-sync) rebuild

> **Why:** MuseTalk 1.5 already gives a working **portrait, social-grade** local avatar, so this is
> NOT a new capability — it's a **second portrait engine** whose only reason to exist is **teeth/lip
> fidelity**. The corrupt mouth I saw (melt + affine seams) was the **LatentSync 1.5** limitation;
> **ByteDance trained `ByteDance/LatentSync-1.6` specifically to fix it** — "significantly clearer
> teeth and lip details" at 512×512 ([HF model card](https://huggingface.co/ByteDance/LatentSync-1.6)).
> Build this only if you want an A/B teeth-quality bake-off against MuseTalk, or a fallback portrait
> engine. **Lower priority than Hallo2** (which adds a tier MuseTalk can't reach).
>
> **Sibling specs:** Hallo2 (cinematic/half-body) — `hallo2-rebuild-spec.md`; MuseTalk (the proven
> pattern) — `musetalk-1.5-rebuild-spec.md`. All three are independent; none blocks the others.

## 1. Proven pattern (from the MuseTalk 1.5 rebuild)
A separate image `FROM mushishi-audio-base` (the SM_120 torch / ffmpeg / opencv base) + the model's
OWN pinned deps, behind a tiny FastAPI service the gateway HTTP-calls — so the working
YuE + Fish Speech + MuseTalk stack is **never touched**. Replicate that here. The whole win of the
MuseTalk rebuild was isolation: the failure was *silent version drift in the shared worker env*, and
the cure was a pinned, dedicated env. LatentSync 1.5 failed for the same root cause (below), so the
same cure applies.

## 2. Known failure (1.5, in the consolidated worker)
- **Structurally corrupt output:** mouth **melt + affine seams**, reproduced on **2 different
  portraits** — an earlier ~280s run produced garbage, not a usable take (audio-benchmarks.csv
  `LatentSync` row; queue A-10). Not a tuning problem — a **silent diffusers / version drift** in the
  shared worker, exactly the class of bug that the dedicated-image pattern removes.
- Root cause class = same as MuseTalk: one shared env can't satisfy models that shipped with pinned,
  isolated envs. LatentSync is an audio-conditioned **latent diffusion** lip-sync (Whisper audio
  embeddings → U-Net → SyncNet supervision); it is sensitive to the exact diffusers version.

## 3. Research finding (2026-06-22) — why 1.6, not 1.5
- `ByteDance/LatentSync-1.6` is the **drop-in successor** that explicitly targets the 1.5 blurry/
  unstable-teeth failure: "significantly clearer teeth and lip details," same 512×512 portrait tier.
- So the rebuild is **swap the checkpoint, not patch the artifacts**: take the 1.6 UNet + its
  recommended diffusers pin, run it in a pinned dedicated image. If 1.6 is clean on the same 2
  portraits that broke 1.5, the regression is closed by design rather than by hand-tuning.

## 4. Approach
1. **Get the 1.6 weights.** Download `ByteDance/LatentSync-1.6` (the `latentsync_unet.pt` for 1.6;
   keep the existing `stable_syncnet.pt`, `whisper/tiny.pt`, and `auxiliary/` face-detection assets
   from the 1.5 dir if 1.6 reuses them — verify against the 1.6 repo's `configs/`). Land them beside
   the current weights, e.g. `/data/ai/02-models/audio/latentsync-1.6/` (do NOT overwrite the 1.5
   dir — keep it for the A/B). Use the HF cache at `/data/ai/07-cache/huggingface/` (1.5 is already
   cached there).
2. **`Dockerfile.latentsync`** = `FROM mushishi-audio-base` + LatentSync's OWN pinned deps —
   critically **pin diffusers to the version the 1.6 repo's `requirements.txt` specifies** (LatentSync
   pins a specific diffusers; that pin is the whole point — it shadows the base's newer diffusers
   **inside this image only**, so YuE / Fish / MuseTalk are untouched). Reuse the baked `libgles2` +
   ffmpeg/opencv from the base. Code repo already on disk at
   `/data/ai/01-workspace/audio/latentsync/latentsync`.
3. **Tiny FastAPI service `latentsync_server.py`** on an internal port **`:9007`** (musetalk=9005,
   hallo2=9006, latentsync=9007 — no collision), mounted from the workspace, mirroring
   `musetalk_server.py`. It wraps LatentSync's `scripts/inference.py` (portrait image/video + audio
   → 512×512 talking-head MP4).
4. **Wire the gateway:** `workers/lipsync.py` **production** branch → HTTP-call
   `creative-latentsync:9007` (like the museTalk branch calls `:9005`); `intent_router.py` lipsync
   `production → latentsync`. Leave `draft → musetalk` as-is so both portrait engines are reachable
   and directly A/B-comparable through the same gateway.
5. **VRAM:** LatentSync portrait diffusion is light/moderate (~one model in the audio/creative
   budget); loads per job, frees on idle, like MuseTalk. Confirm the actual peak at G2 and record it.

## 5. Gates (SDD)
- **G1** image builds; `python -c "import diffusers, torch; print(diffusers.__version__)"` reports the
  **pinned** version (not the base's), and a 512² GPU op runs on the 5090 (SM_120 OK).
- **G2** smoke: `scripts/inference.py` on the **same synthetic margined portrait + `voiceover.wav`**
  used for MuseTalk → an MP4 exists, face detected, mouth tracks speech/silence. Record wall-clock +
  peak VRAM.
- **G3** quality — **the reason this rebuild exists**: on the 2 portraits that broke 1.5, teeth/lip
  interior is **clean (no melt, no affine seams)** and visibly **sharper than MuseTalk** on a
  side-by-side. If 1.6 is NOT clearly better than the already-working MuseTalk, **stop and drop the
  tile** — there's no point maintaining a second portrait engine that doesn't win on its one job.
- **G4** e2e via gateway: `lipsync quality=production → latentsync`, finished, sample saved.
- Then: `audio-benchmarks.csv` LatentSync row BLOCKED→measured (+ sample + the A/B note vs MuseTalk),
  regenerate the catalogue, vendor the integration code to the public repo for reproducibility,
  append LESSONS + queue.

## 6. Decision rule (keep it honest)
This is the one rebuild that is allowed to **end in "drop it."** MuseTalk already does the job; 1.6
earns its keep ONLY by a clear teeth/lip-quality win at G3. If it wins → ship it as the `production`
portrait path. If it ties or loses → drop the LatentSync tile (don't leave a "blocked" tile whose
only value was the benchmark-honesty record, now superseded by MuseTalk + this note) and record the
A/B result so the question is closed.

## 7. Non-goals / rollback
Broadcast close-ups = cloud, regardless. This is a new image + compose service + one gateway branch;
remove the three to roll back; the working worker is never touched. Quality target = portrait tier
(512×512 social-grade), not broadcast.

## 8. References
- MuseTalk rebuild spec (the proven pattern): `musetalk-1.5-rebuild-spec.md`.
- Hallo2 rebuild spec (the sibling cinematic tier): `hallo2-rebuild-spec.md`.
- LatentSync 1.6: huggingface.co/ByteDance/LatentSync-1.6 (fixes the 1.5 blurry teeth/lips).
- Code on disk: `/data/ai/01-workspace/audio/latentsync/latentsync`. 1.5 weights (keep for A/B):
  `/data/ai/02-models/audio/latentsync/`. HF cache: `/data/ai/07-cache/huggingface/`.
