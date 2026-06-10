from redis import Redis
from rq import Queue
import os

redis_conn = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))

q_stt     = Queue("stt",     connection=redis_conn)
q_voice   = Queue("voice",   connection=redis_conn)
q_lipsync = Queue("lipsync", connection=redis_conn)
q_music   = Queue("music",   connection=redis_conn)
q_dub     = Queue("dub",     connection=redis_conn)

def submit_job(queue: Queue, func_path: str, kwargs: dict, timeout: int = 1800) -> str:
    job = queue.enqueue(
        func_path,
        kwargs=kwargs,
        job_timeout=timeout,
        result_ttl=86400,
        failure_ttl=86400
    )
    return job.id

def get_job_status(job_id: str) -> dict:
    from rq.job import Job
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        return {
            "id": job.id,
            "status": job.get_status().value,
            "result": job.result,
            "error": str(job.exc_info) if job.exc_info else None,
            "created_at": str(job.created_at),
            "ended_at": str(job.ended_at) if job.ended_at else None,
        }
    except Exception as e:
        return {"id": job_id, "status": "not_found", "error": str(e)}
