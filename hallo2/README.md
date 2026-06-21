# Hallo2 — dedicated cinematic lip-sync service

The **cinematic** tier: head pose + expression + CodeFormer face enhancement — the one
capability MuseTalk doesn't have (MuseTalk pastes a mouth; Hallo2 animates the whole
face). Runs in its **own** isolated image so it can't disturb the YuE/Fish-Speech worker.
Key trick: **pin `diffusers==0.32.2`** (Hallo2's authored version) over the base's newer
diffusers. Full rationale: `../docs/hallo2-rebuild-spec.md` + repo `LESSONS.md`.

## The bug this fixes
Hallo2 ships its own UNet/Transformer classes (`hallo/models/unet_3d.py`,
`transformer_3d.py`) that override `_set_gradient_checkpointing(self, module, value=False)`
— the **old** diffusers signature. The base image carries diffusers 0.38, whose
`enable_gradient_checkpointing()` calls `_set_gradient_checkpointing(enable=...)` →
`TypeError: ... unexpected keyword 'enable'`. diffusers 0.32.2 calls it the old way, so
the override matches. That is the entire fix — **no transformers/numpy downgrade**
(downgrading numpy breaks the base's numpy-2-native scipy/opencv).

## Files
- `../compose/Dockerfile.hallo2` — `FROM mushishi-audio-base` + `diffusers==0.32.2` and
  `decorator==4.4.2` (moviepy 1.0.3 needs decorator<5 or the final mp4 mux gets `fps=None`).
- `hallo2_server.py` — thin FastAPI service on `:9006` (mounted into the hallo2 workspace);
  each job runs `scripts/inference_long.py` with a per-job OmegaConf config, frees VRAM on exit.

## Deploy (on the box)
1. Clone upstream `fudan-generative-ai/hallo2` → `/data/ai/01-workspace/audio/hallo2`,
   stage weights to `/data/ai/02-models/audio/hallo2/` (`pretrained_models` symlink).
   Keep the committed `attn_implementation="eager"` AudioProcessor fix (Wav2Vec2 output_attentions).
2. Drop in `hallo2_server.py`.
3. `docker build -t mushishi-hallo2 -f compose/Dockerfile.hallo2 .`
4. Bring up the `hallo2` service (compose) → gateway routes `lipsync quality=cinematic → hallo2`.
