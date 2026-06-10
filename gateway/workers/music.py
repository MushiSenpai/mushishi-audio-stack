import subprocess, os, json

WORKSPACE  = "/data/ai/01-workspace/audio"
MODEL_BASE = "/data/ai/02-models/audio"
OUTPUT_DIR = "/data/ai/08-portfolio/outputs/audio/music"
os.environ.setdefault("TORCH_HOME", "/data/ai/07-cache/torch")

def generate(job_id: str, text: str = None, lyrics: str = None,
             model_tier: str = "stable_audio", duration: int = 30, **kwargs) -> dict:

    out_path = f"{OUTPUT_DIR}/{job_id}_music.wav"

    if model_tier == "yue_7b":
        if not lyrics:
            return {"error": "YuE 7B requires lyrics input (use quality=song and provide lyrics parameter)"}
        # YuE outputs auto-named files — use a job-specific temp dir, then rename
        import glob, shutil
        genre_file  = f"/tmp/{job_id}_genre.txt"
        lyrics_file = f"/tmp/{job_id}_lyrics.txt"
        yue_tmp_dir = f"/tmp/{job_id}_yue"
        os.makedirs(yue_tmp_dir, exist_ok=True)
        with open(genre_file, "w") as f:
            f.write(text or "cinematic, electronic, atmospheric")
        with open(lyrics_file, "w") as f:
            f.write(lyrics)
        yue_infer = f"{WORKSPACE}/yue/inference/infer.py"
        yue_cwd   = f"{WORKSPACE}/yue/inference"
        cmd = [
            "python3", yue_infer,
            "--stage1_model", f"{MODEL_BASE}/yue/stage1",
            "--stage2_model", f"{MODEL_BASE}/yue/stage2",
            "--genre_txt",    genre_file,
            "--lyrics_txt",   lyrics_file,
            "--output_dir",   yue_tmp_dir,
            "--cuda_idx",     "0",
            "--run_n_segments", "2",
        ]

    elif model_tier == "ace_step":
        cmd = [
            "python3", f"{WORKSPACE}/ace-step/inference.py",
            "--prompt", text or "cinematic atmospheric music",
            "--duration", str(duration),
            "--output", out_path,
        ]

    elif model_tier == "stable_audio":
        prompt_escaped = (text or "cinematic ambient score").replace("'", "\\'")
        cmd = [
            "python3", "-c", f"""
import torch, soundfile as sf, os
os.environ['TORCH_HOME'] = '/data/ai/07-cache/torch'
from stable_audio_tools import get_pretrained_model
from stable_audio_tools.inference.generation import generate_diffusion_cond
model, config = get_pretrained_model('{MODEL_BASE}/stable-audio')
model = model.to('cuda')
output = generate_diffusion_cond(
    model, steps=100, cfg_scale=7,
    conditioning=[{{'prompt': '{prompt_escaped}',
                   'seconds_start': 0, 'seconds_total': {duration}}}],
    sample_size=config['sample_size'],
    sigma_min=0.3, sigma_max=500,
    sampler_type='dpmpp-3m-sde', device='cuda'
)
sf.write('{out_path}', output.squeeze().cpu().numpy().T, config['sample_rate'])
print('Done: {out_path}')
"""
        ]
    else:
        return {"error": f"Unknown model_tier: {model_tier}. Use ace_step, stable_audio, or yue_7b."}

    run_cwd = locals().get("yue_cwd")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, cwd=run_cwd)
    if result.returncode != 0:
        return {"error": result.stderr[-2000:], "model_used": model_tier}

    # YuE writes auto-named output to yue_tmp_dir root — find and move it
    # Output may be .mp3 (vocoder) or .wav depending on YuE version
    if model_tier == "yue_7b":
        candidates = glob.glob(f"{yue_tmp_dir}/*.wav") + glob.glob(f"{yue_tmp_dir}/*.mp3")
        if not candidates:
            return {"error": "YuE completed but no audio found in output dir", "stdout": result.stdout[-1000:]}
        latest = max(candidates, key=os.path.getmtime)
        ext = os.path.splitext(latest)[1]
        out_path = f"{OUTPUT_DIR}/{job_id}_music{ext}"
        shutil.move(latest, out_path)
        shutil.rmtree(yue_tmp_dir, ignore_errors=True)

    return {"job_id": job_id, "output_file": out_path, "model_used": model_tier}
