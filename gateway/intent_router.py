MODEL_TIERS = {
    "lipsync": {
        "draft":      "museTalk",       # social-grade, dedicated creative-musetalk:9005 (rebuilt 2026-06-21)
        "production": "latentsync",
        "cinematic":  "hallo2",
        "fullbody":   "wan22_i2v",
    },
    "tts": {
        "draft":      "fish_speech_fast",
        "production": "fish_speech_full",
    },
    "music": {
        "draft":      "ace_step",
        "production": "stable_audio",
        "song":       "yue_7b",
    }
}

ROUTES = {
    "transcribe": ("q_stt",     "workers.stt.transcribe",     600),
    "clone":      ("q_voice",   "workers.voice.clone_voice",  300),
    "tts":        ("q_voice",   "workers.voice.synthesise",   300),
    "expressive_tts": ("q_voice", "workers.expressive.expressive_tts", 600),
    "lipsync":    ("q_lipsync", "workers.lipsync.generate",   1800),
    "music":      ("q_music",   "workers.music.generate",     1800),
    "dub":        ("q_dub",     "workers.dub.auto_dub",       3600),
}
