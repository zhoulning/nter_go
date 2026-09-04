"""语音转写服务：本地 faster-whisper（默认）+ 云端 OpenAI audio 协议，双通道。"""
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

import httpx

# 国内网络直连 HuggingFace 不通，转写模型默认走镜像下载
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

_whisper_models: dict[str, object] = {}  # 模型进程内缓存，避免重复加载

CLOUD_CHUNK_SECONDS = 1200  # 云端通道切片时长（20 分钟）
CLOUD_MAX_BYTES = 24 * 1024 * 1024


def _fmt_ts(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"命令执行失败：{' '.join(cmd[:3])}…\n{proc.stderr[-500:]}")


def probe_duration(path: Path) -> float | None:
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        return float(proc.stdout.strip())
    except Exception:
        return None


def _to_wav16k(src: Path, workdir: Path) -> Path:
    dest = workdir / "audio_16k.wav"
    _run(["ffmpeg", "-y", "-i", str(src), "-vn", "-ar", "16000", "-ac", "1", str(dest)])
    return dest


def transcribe_local(
    media_path: Path,
    model_size: str,
    on_progress: Callable[[int], None] | None = None,
    diarize: bool = True,
) -> tuple[str, str | None]:
    """本地 faster-whisper 转写，输出带 [MM:SS] 时间戳的文字稿。"""
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError(
            "本地转写依赖未安装：请在项目目录执行 pip install faster-whisper 后重试"
        ) from e

    with tempfile.TemporaryDirectory() as tmp:
        wav = _to_wav16k(media_path, Path(tmp))
        model = _whisper_models.get(model_size)
        if model is None:
            model = WhisperModel(model_size, device="cpu", compute_type="int8")
            _whisper_models[model_size] = model

        segments_iter, info = model.transcribe(str(wav), vad_filter=True)
        total = info.duration or 0
        segs: list[dict] = []
        for seg in segments_iter:
            text = seg.text.strip()
            if text:
                segs.append({"start": seg.start, "end": seg.end, "text": text})
            if on_progress and total:
                on_progress(min(99, int(seg.end / total * 100)))

        speaker_err: str | None = None
        if diarize and segs:
            from app.diarize import assign_speakers

            segs, speaker_err = assign_speakers(wav, segs)

        lines: list[str] = []
        for seg in segs:
            who = f" [说话人{seg['speaker']}]" if seg.get("speaker") else ""
            lines.append(f"[{_fmt_ts(seg['start'])}]{who} {seg['text']}")
        return "\n".join(lines).strip(), speaker_err


def _split_audio(src: Path, workdir: Path) -> list[Path]:
    pattern = workdir / "chunk_%03d.mp3"
    _run([
        "ffmpeg", "-y", "-i", str(src), "-f", "segment", "-segment_time",
        str(CLOUD_CHUNK_SECONDS), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "60k",
        str(pattern),
    ])
    return sorted(workdir.glob("chunk_*.mp3"))


def transcribe_cloud(
    media_path: Path,
    cloud_cfg: dict[str, str],
    on_progress: Callable[[int], None] | None = None,
) -> str:
    """云端转写：POST {base}/audio/transcriptions（OpenAI 协议），大文件先切片。"""
    base = cloud_cfg["cloud_base_url"].rstrip("/")
    model = cloud_cfg["cloud_model"]
    key = cloud_cfg["cloud_api_key"]
    if not key:
        raise RuntimeError("未配置云端 ASR 的 API Key，请到「设置」中填写，或切换本地通道")

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        if media_path.stat().st_size > CLOUD_MAX_BYTES:
            chunks = _split_audio(media_path, workdir)
        else:
            chunks = [media_path]

        parts: list[str] = []
        offset = 0.0
        for idx, chunk in enumerate(chunks):
            duration = probe_duration(chunk) or CLOUD_CHUNK_SECONDS
            with open(chunk, "rb") as f:
                resp = None
                last_exc: Exception | None = None
                for trust_env in (True, False):
                    try:
                        with httpx.Client(trust_env=trust_env, timeout=300) as client:
                            resp = client.post(
                                f"{base}/audio/transcriptions",
                                headers={"Authorization": f"Bearer {key}"},
                                files={"file": (chunk.name, f, "audio/mpeg")},
                                data={"model": model},
                            )
                        break
                    except httpx.HTTPError as e:
                        last_exc = e
                if resp is None:
                    raise RuntimeError(f"云端转写请求失败：{type(last_exc).__name__}: {last_exc}")
                if resp.status_code >= 400:
                    raise RuntimeError(f"云端 ASR 返回 HTTP {resp.status_code}：{resp.text[:200]}")
                text = resp.json().get("text", "").strip()
            if text:
                parts.append(f"[{_fmt_ts(offset)}] {text}")
            offset += duration
            if on_progress:
                on_progress(min(99, int((idx + 1) / len(chunks) * 100)))
        return "\n".join(parts).strip()
