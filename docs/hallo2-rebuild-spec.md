---
tags: [ai/audio, ai/lip-sync, infra/rebuild, spec/sdd]
status: DONE — 2026-06-22 (G1–G4 passed, cinematic verified e2e via gateway)
created: 2026-06-22
target: Hallo2 (cinematic/half-body lip-sync) as a dedicated pinned container
owner: completed — mushishi-hallo2 image + creative-hallo2:9006 service
result: fix = pin diffusers==0.32.2 ALONE (NOT the spec's transformers/numpy trio — numpy 1.26.4 breaks the base's numpy-2 scipy) + decorator==4.4.2 (moviepy 1.0.3 fps mux); ~13.3GB, ~35x slower than realtime (1197s/34.5s @512²), no melt; head+expression motion
companion: ~/Documents/audio/musetalk-1.5-rebuild-spec.md (the proven pattern); ~/Documents/audio/latentsync-1.6-rebuild-spec.md (the sibling portrait rebuild); mushishi-audio-stack repo
---

# Spec — Hallo2 (cinematic lip-sync) rebuild

> **Why:** MuseTalk 1.5 already gives a working **portrait, social-grade** local avatar.
> **Hallo2** adds the one capability MuseTalk doesn't: the **cinematic / half-body + expression**
> tier (it bundles CodeFormer face enhancement). It broke in the consolidated worker; it's fixable
> in a **dedicated, pinned, isolated image** — the exact pattern that made MuseTalk 1.5 work.
> Broadcast close-ups still go to a cloud path regardless.
>
> **Sibling spec:** LatentSync 1.6 (a stronger *portrait* alternative for an A/B vs MuseTalk) is now
> its own standalone buildable spec — `~/Documents/audio/latentsync-1.6-rebuild-spec.md`. Same
> pattern, independent session. **This file is Hallo2 only.**

## 0. Outcome (2026-06-22) — what actually shipped vs this spec

Built as specified (own `mushishi-hallo2` image `FROM mushishi-audio-base` + tiny FastAPI
`hallo2_server.py` on `:9006`; gateway `cinematic → hallo2` HTTP-calls it). **G1–G4 all
passed**, verified e2e via the gateway. Deviations from the plan below (the spec is a
hypothesis):

- **The fix is `diffusers==0.32.2` ALONE** — not a version bisect to "0.27.x" (§2 guess) and
  not a code patch. Confirmed: Hallo2's own `hallo/models/unet_3d.py` + `transformer_3d.py`
  override `_set_gradient_checkpointing(self, module, value=False)` (old sig); base diffusers
  0.38 calls `enable=` → crash. 0.32.2 (Hallo2's own requirements pin) calls it the old way.
- **Do NOT also pin transformers/numpy.** Porting Hallo2's full requirements trio FAILED:
  `numpy==1.26.4` breaks the base's numpy-2-native `scipy 1.18` (`np.long`) → insightface
  import crash. The base is proven on numpy 2.x; keep it whole. transformers stays at the
  base's 4.57 (the only transformers need — Wav2Vec2 eager attention — is already committed
  in the repo).
- **One trap the spec didn't predict:** base `decorator 5.3.1` breaks moviepy 1.0.3's final
  mp4 mux (`fps=None`) → also pin `decorator==4.4.2`. Every compute step passed; only the
  file write failed.
- **Cost reality:** ~13.3GB peak, ~35× slower than realtime (1197s for a 34.5s 512² clip;
  cinematic diffusion is heavy) — ~15× slower than MuseTalk's 78s. Right tool for
  non-headshot/expressive framing, not bulk social.

## 1. Proven pattern (from the MuseTalk 1.5 rebuild)
A separate image `FROM mushishi-audio-base` (the SM_120 torch/ffmpeg/opencv base) + the model's
OWN pinned deps, behind a tiny FastAPI service the gateway HTTP-calls — so the working
YuE + Fish Speech + MuseTalk stack is **never touched**. Replicate that here.

## 2. Hallo2 — PRIMARY (the cinematic tier)

### Known failures (from the 2026-06-21 unified-worker test + the original install)
- **diffusers API break:** `UNet2DConditionModel._set_gradient_checkpointing() got an unexpected
  keyword 'enable'` — the worker's newer diffusers changed the signature; Hallo2 expects the old one.
- Plus the **6 original patches** (audio-stack LESSONS / queue A-4): xformers from the nightly index,
  `nvidia-nccl-cu12 ≥ 2.30.4`, `libGLESv2.so.2` (now baked: `libgles2` in `Dockerfile.audio`),
  `attn_implementation="eager"` for Wav2Vec2, output lands at `**/merge_video.mp4`, and the repo is
  `fudan-generative-ai/hallo2` (NOT the similarly-named org). It produced a clean 512×512 9.38s MP4
  in its **own** container on 2026-05-24 — so a pinned env is proven to work.

### Approach
1. `Dockerfile.hallo2` = `FROM mushishi-audio-base` + **pin diffusers to the version with the old
   `_set_gradient_checkpointing(value)` signature** (pre-~0.30; check the 2026-05-24 working
   container's `pip freeze` if it survived, else bisect: 0.27.x is the likely target). This pinned
   diffusers shadows the base's newer one **inside this image only** — YuE/Fish/MuseTalk untouched.
   - If pinning fights other Hallo2 deps, instead **patch** Hallo2's `enable_gradient_checkpointing()`
     call to drop the `enable=` kwarg (it's an inference-time memory opt, safe to no-op) — save as a
     `.patch` like `musetalk/preprocessing.rtmlib.patch`.
2. Tiny FastAPI service `hallo2_server.py` on an internal port (e.g. `:9006`), mounted from the
   workspace (mirrors `musetalk_server.py`). Weights already at `/data/ai/02-models/audio/hallo2/`.
3. Wire gateway: `workers/lipsync.py` **cinematic** branch → HTTP-call `creative-hallo2:9006`
   (like the museTalk branch calls `:9005`); `intent_router.py` lipsync `cinematic → hallo2`.
4. Hallo2 is heavier (~10–12GB) — runs in the audio/creative VRAM budget; bundles CodeFormer for
   face enhancement (its differentiator vs MuseTalk).

### Gates (SDD)
- **G1** image builds; `python -c "import diffusers; from diffusers import UNet2DConditionModel"`
  + a 512² GPU op on the 5090.
- **G2** smoke: `scripts/inference_long.py` on the synthetic margined portrait + `voiceover.wav`
  → `merge_video.mp4` exists, face detected (mediapipe → libgles2 ok), mouth tracks speech/silence.
- **G3** quality: half-body/expression coherent, no melt; **better than MuseTalk for non-headshot framing** (the reason to keep it).
- **G4** e2e via gateway: `lipsync quality=cinematic → hallo2`, finished.
- Then: `audio-benchmarks.csv` Hallo2 row BLOCKED→measured (+ sample), regenerate catalogue, vendor
  the code to the public repo for reproducibility, LESSONS + queue.

## 3. LatentSync 1.6 — split out to its own spec
LatentSync 1.6 is a *portrait* alternative (an A/B vs MuseTalk), not a new capability, so it's a
separate independent rebuild rather than part of this one. Full buildable SDD:
**`~/Documents/audio/latentsync-1.6-rebuild-spec.md`**. Build either in any order; neither blocks
the other (separate images, separate gateway branches).

## 4. Non-goals / rollback
Broadcast close-ups = cloud. This is a new image + compose service; remove it to roll back; the
working worker is never touched. Quality target = the model's tier (cinematic for Hallo2), not broadcast.

## 5. References
- MuseTalk rebuild spec (the proven pattern): `musetalk-1.5-rebuild-spec.md`.
- LatentSync 1.6 rebuild spec (the sibling): `latentsync-1.6-rebuild-spec.md`.
- Hallo2: github.com/fudan-generative-ai/hallo2 ; weights `/data/ai/02-models/audio/hallo2/`.
