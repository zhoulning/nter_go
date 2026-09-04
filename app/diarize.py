"""轻量声纹说话人区分：sherpa-onnx 说话人嵌入 + 贪心聚类。

依赖 sherpa-onnx 与声纹嵌入模型（data/models/*.onnx）；
任一不可用时返回空标签列表，由调用方优雅降级为无说话人标注。
"""
import json
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent.parent / "data" / "models"

# 聚类阈值：余弦相似度高于该值视为同一说话人
SIM_THRESHOLD = 0.45
MIN_SEGMENT_SEC = 0.6  # 短于该时长的段不做声纹（样本太少不可靠）


def _load_samples(wav_path: Path) -> tuple[int, "list[float]"]:
    import wave

    with wave.open(str(wav_path), "rb") as w:
        sr = w.getframerate()
        data = w.readframes(w.getnframes())
    import numpy as np

    samples = np.frombuffer(data, dtype=np.int16).astype("float32") / 32768.0
    return sr, samples.tolist()


def _load_extractor():
    try:
        import sherpa_onnx
    except ImportError:
        return None, "未安装 sherpa-onnx（pip install sherpa-onnx）"
    models = sorted(MODEL_DIR.glob("*.onnx"))
    if not models:
        return None, "缺少声纹嵌入模型（data/models/*.onnx）"
    config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(models[0]))
    try:
        return sherpa_onnx.SpeakerEmbeddingExtractor(config), None
    except Exception as e:  # 模型文件损坏等
        return None, f"声纹模型加载失败：{e}"


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def assign_speakers(
    wav_path: Path, segments: list[dict]
) -> tuple[list[dict], str | None]:
    """为转写段分配说话人标签。

    segments: [{start, end, text}]（秒）
    返回 (带 speaker 标签的段列表, 失败原因或 None)。
    speaker 为 1/2（按首次出现顺序），样本不可靠的段为 None。
    """
    extractor, err = _load_extractor()
    if extractor is None:
        return segments, err

    try:
        sr, samples = _load_samples(wav_path)
    except Exception as e:
        return segments, f"音频读取失败：{e}"

    dim = extractor.dim
    embs: list[list[float] | None] = []
    for seg in segments:
        length = seg["end"] - seg["start"]
        if length < MIN_SEGMENT_SEC:
            embs.append(None)
            continue
        s0 = max(0, int(seg["start"] * sr))
        s1 = min(len(samples), int(seg["end"] * sr))
        chunk = samples[s0:s1]
        if len(chunk) < sr // 4:  # 不足 0.25s
            embs.append(None)
            continue
        stream = extractor.create_stream()
        stream.accept_waveform(sr, chunk[: (len(chunk) // dim) * dim or len(chunk)])
        stream.input_finished()
        try:
            embs.append(list(extractor.compute(stream)))
        except Exception:
            embs.append(None)

    valid = [(i, e) for i, e in enumerate(embs) if e is not None]
    if len(valid) < 2:
        return segments, "有效语音段不足，无法做声纹区分"

    # 贪心聚类
    clusters: list[dict] = []  # {emb: 累加向量, count, members: [段下标]}
    for i, emb in valid:
        best, best_sim = None, SIM_THRESHOLD
        for c in clusters:
            sim = _cosine(emb, [x / c["count"] for x in c["emb_sum"]])
            if sim >= best_sim:
                best, best_sim = c, sim
        if best is None:
            clusters.append({"emb_sum": list(emb), "count": 1, "members": [i]})
        else:
            best["members"].append(i)
            best["count"] += 1
            best["emb_sum"] = [x + y for x, y in zip(best["emb_sum"], emb)]

    clusters.sort(key=lambda c: c["members"][0])  # 按首次出现顺序编号
    label_of: dict[int, int] = {}
    for label, c in enumerate(clusters, start=1):
        for i in c["members"]:
            label_of[i] = min(label, 2)  # 超过 2 个聚类一律并入"说话人2"

    out = []
    for i, seg in enumerate(segments):
        out.append({**seg, "speaker": label_of.get(i)})
    return out, None
