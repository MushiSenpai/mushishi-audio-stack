# Lip-sync tiers — every local engine now runs as its OWN dedicated, pinned,
# isolated service that the worker HTTP-calls by name (like voice.py calls
# creative-tts). Each broke a different way inside the consolidated worker env, so
# each was rebuilt as a separate image behind a tiny FastAPI service:
#   museTalk    (draft / social-grade)   -> creative-musetalk:9005
#               env: DWPose via rtmlib/ONNX, no mmcv.
#   latentsync  (production / 512x512)   -> creative-latentsync:9007
#               env: diffusers 0.32.2 (the silent-drift fix for the 1.5 melted
#               mouth) + the 1.6 checkpoint. See audio/latentsync-1.6-rebuild-spec.md.
#   hallo2      (cinematic-grade)        -> creative-hallo2:9006
#               env: diffusers 0.32.2 + decorator<5. See audio/hallo2-rebuild-spec.md.
# Each service loads models per job and frees VRAM on exit — good citizens on the
# shared 5090. The worker holds NO model code for these tiers anymore.

MUSETALK_API   = "http://creative-musetalk:9005"
HALLO2_API     = "http://creative-hallo2:9006"
LATENTSYNC_API = "http://creative-latentsync:9007"

OUTPUT_DIR = "/data/ai/08-portfolio/outputs/audio/lip-sync"


def _call_lipsync_service(api: str, model: str, job_id: str, source: str,
                          audio_file: str, extra: dict = None) -> dict:
    """POST to a dedicated, isolated lip-sync service by name. Each service loads
    models per job and frees VRAM on exit, so a job can take a few minutes — generous
    timeout. `extra` carries per-model knobs (e.g. latentsync guidance_scale)."""
    import requests
    payload = {"job_id": job_id, "source": source, "audio_file": audio_file}
    if extra:
        payload.update(extra)
    try:
        resp = requests.post(f"{api}/lipsync", json=payload, timeout=1900)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"error": f"{model} service call failed: {e}", "model_used": model}
    if "error" in data:
        return {"error": data["error"], "model_used": model}
    return {"job_id": job_id, "output_file": data.get("output_file"),
            "model_used": data.get("model_used", model), "wall_seconds": data.get("wall_seconds")}


def generate(job_id: str, source: str = None, audio_file: str = None,
             model_tier: str = "latentsync", **kwargs) -> dict:
    if not source or not audio_file:
        return {"error": "source (image/video) and audio_file are required for lipsync"}

    if model_tier == "museTalk":
        return _call_lipsync_service(MUSETALK_API, "museTalk", job_id, source, audio_file)
    if model_tier == "hallo2":
        return _call_lipsync_service(HALLO2_API, "hallo2", job_id, source, audio_file)
    if model_tier == "latentsync":
        # draft = lighter guidance, production = 1.5 (LatentSync's recommended default).
        guidance = 1.0 if kwargs.get("quality") == "draft" else 1.5
        return _call_lipsync_service(LATENTSYNC_API, "latentsync", job_id, source,
                                     audio_file, extra={"guidance_scale": guidance})

    return {"error": f"Unknown model_tier: {model_tier}. Use museTalk, latentsync, or hallo2."}
