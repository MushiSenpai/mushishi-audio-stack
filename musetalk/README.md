# MuseTalk 1.5 — dedicated lip-sync service (the working local avatar)

The only local lip-sync model that works (social-grade). Runs in its **own** isolated
image so it can't disturb the YuE/Fish-Speech worker. Key trick: **DWPose via rtmlib/ONNX**
instead of mmpose/mmcv (no `mmcv._ext` wheel exists for torch 2.8/cu128 on the RTX 5090).
Full rationale: `../docs/musetalk-1.5-rebuild-spec.md` + repo `LESSONS.md`.

## Files
- `../compose/Dockerfile.musetalk` — `FROM mushishi-audio-base` + `rtmlib` (the only delta).
- `musetalk_server.py` — thin FastAPI service on `:9005` (mounted into the museTalk workspace).
- `preprocessing.rtmlib.patch` — the mmpose→rtmlib swap applied to upstream
  `musetalk/utils/preprocessing.py` (returns the same 133-kpt DWPose output, zero mmcv).

## Deploy (on the box)
1. Clone upstream MuseTalk 1.5 → `/data/ai/01-workspace/audio/museTalk`, stage weights.
2. `patch -p1 < preprocessing.rtmlib.patch` in that tree; drop in `musetalk_server.py`.
3. `docker build -t mushishi-musetalk -f compose/Dockerfile.musetalk .`
4. Bring up the `musetalk` service (compose) → gateway routes `lipsync quality=draft → museTalk`.
