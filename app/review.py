"""AI 复盘报告生成：切题、逐题点评、JD 对照、行动清单。"""
from app.routers.ai import ANSWER_STANDARD, _call_llm, _parse_json_loose

# 超过该长度的文字稿走两阶段 map-reduce，否则单次直出
SINGLE_PASS_LIMIT = 50000

REPORT_SCHEMA_HINT = """{
  "overall": { "score": 82, "summary": "两三句整体表现评价", "highlights": ["亮点"], "weaknesses": ["不足"] },
  "questions": [
    {
      "question": "面试官的原问题",
      "topic": "考察维度（如 项目深挖/MySQL/分布式/系统设计/软素质）",
      "my_answer": "候选人回答的要点摘述",
      "scores": { "structure": 1-5, "depth": 1-5, "clarity": 1-5 },
      "good": ["回答中的亮点"],
      "bad": ["回答中的问题"],
      "reference": "该题的参考答题要点",
      "improved": "结合候选人背景的更好回答示范"
    }
  ],
  "jd_match": { "demonstrated": ["面试中已展示出的 JD 要求"], "gaps": ["JD 要求但未展示或答弱的"] },
  "interviewer_focus": "从提问分布推断的面试官关注点与团队技术侧重",
  "action_items": ["下一步行动建议"],
  "questions_for_bank": [ { "content": "被问到的原题", "dimension": "维度", "difficulty": "easy|medium|hard" } ]
}"""


def extract_qa_from_chunk(base_url: str, model: str, api_key: str, chunk: str) -> str:
    """长稿 map 阶段：从单个分段中提取问答对。"""
    prompt = f"""以下是某场面试转写稿的一个片段。请提取其中面试官提出的问题与候选人的回答要点，只输出一个 JSON 数组，不要输出其他内容：
[ {{ "question": "面试官的问题", "answer": "候选人回答的要点摘述" }} ]
没有问题的片段输出 []。

----- 片段开始 -----
{chunk}
----- 片段结束 -----"""
    raw = _call_llm(base_url, model, api_key, prompt)
    try:
        start, end = raw.find("["), raw.rfind("]")
        return raw[start : end + 1]
    except Exception:
        return "[]"


def build_review(
    base_url: str,
    model: str,
    api_key: str,
    *,
    company: str,
    position: str,
    round_label: str,
    jd_text: str,
    resume_text: str,
    transcript: str,
    kb_text: str = "",
) -> dict:
    """生成结构化复盘报告；超长文字稿自动走两阶段 map-reduce。"""
    jd = jd_text.strip() or "（未填写工作描述）"
    resume = resume_text.strip() or "（未关联简历，请仅依据文字稿评价）"
    if len(resume) > 6000:
        resume = resume[:6000] + "…（已截断）"

    qa_note = ""
    if len(transcript) > SINGLE_PASS_LIMIT:
        # map 阶段：分块切问答对
        chunks: list[str] = []
        lines = transcript.splitlines()
        buf: list[str] = []
        size = 0
        for line in lines:
            buf.append(line)
            size += len(line)
            if size >= 18000:
                chunks.append("\n".join(buf))
                buf, size = [], 0
        if buf:
            chunks.append("\n".join(buf))

        qa_parts = []
        for chunk in chunks:
            qa_parts.append(
                extract_qa_from_chunk(base_url, model, api_key, chunk[:22000])
            )
        merged = "[" + ",".join(p.strip().strip("[]") for p in qa_parts if p.strip().strip("[]")) + "]"
        transcript_body = merged
        qa_note = "注意：文字稿很长，下面是已经按顺序提取好的问答对列表，请基于它完成复盘，并可通过开头的原文节选补充语气细节。"
        transcript_head = transcript[:10000]
        body = f"{qa_note}\n\n【问答对列表】\n{merged}\n\n【文字稿开头节选】\n{transcript_head}"
    else:
        body = transcript

    prompt = f"""你是一位资深的面试教练。请根据下面这场面试的转写文字稿，结合岗位 JD 与候选人简历，产出深度复盘报告。

【岗位】{position} @ {company}
【轮次】{round_label}
【岗位 JD】
{jd}

【候选人简历要点】
{resume}

【知识库笔记】（候选人自己的复习笔记，点评与 improved 优先参考其中与题目相关的要点）
{kb_text}

【面试转写文字稿】
{body}

要求：
1. 文字稿中面试官与候选人交替发言，请按语言特征准确区分，只把「面试官提出的实际问题」收入 questions，按出现顺序完整覆盖，不要遗漏闲聊寒暄。
2. 逐题点评要具体到候选人原话，评分严格 1-5；reference 给出该题的标准答题要点；improved 给出结合候选人经历的更好回答示范，格式遵守全站统一的口述版答案标准（纯知识题直接给知识要点与答题结构，不生硬套项目）：
{ANSWER_STANDARD}
3. jd_match 对照上面的 JD 逐条判断展示情况。
4. questions_for_bank 收录值得沉淀的真实面试题（含维度与难度）。
5. 只输出一个 JSON 对象，不要输出任何其他文字。结构如下：
{REPORT_SCHEMA_HINT}"""

    raw = _call_llm(base_url, model, api_key, prompt)
    report = _parse_json_loose(raw)
    if not isinstance(report, dict) or "questions" not in report:
        raise ValueError("报告缺少 questions 字段")
    # 兜底规范
    report.setdefault("overall", {})
    report.setdefault("jd_match", {"demonstrated": [], "gaps": []})
    report.setdefault("interviewer_focus", "")
    report.setdefault("action_items", [])
    report.setdefault("questions_for_bank", [])
    overall = report["overall"]
    overall.setdefault("score", 0)
    overall.setdefault("summary", "")
    overall.setdefault("highlights", [])
    overall.setdefault("weaknesses", [])
    for q in report["questions"]:
        q.setdefault("scores", {"structure": 3, "depth": 3, "clarity": 3})
        q.setdefault("good", [])
        q.setdefault("bad", [])
        q.setdefault("topic", "")
        q.setdefault("reference", "")
        q.setdefault("improved", "")
        q.setdefault("my_answer", "")
    return report


POLISH_PROMPT = """你是转写稿整理助手。请对下面的面试转写稿做「整理」而不是「改写」：
1. 修正错别字与技术名词拼写（例如：radis→Redis、麦ysql→MySQL、springboot→Spring Boot、dubble→Dubbo、卡夫卡→Kafka、布拉格→Pulsar 等）
2. 去除口语填充词与结巴重复（嗯、呃、那个、就是说），但不删除任何实质内容、不改变观点与事实、不修改任何数字
3. 每个发言整理为独立段落，统一格式：[原始时间戳 MM:SS] 说话人：内容
4. 说话人识别：若行内已有 [说话人1]/[说话人2] 标记，请根据内容判断谁是面试官、谁是候选人，统一写为「面试官」和「我」；没有标记的请根据语义标注
5. 保留所有时间戳，不合并、不删减时间戳

只输出整理后的文字稿正文，不要输出任何解释。

----- 转写稿开始 -----
{transcript}
----- 转写稿结束 -----"""


def polish_transcript(base_url: str, model: str, api_key: str, transcript: str) -> str:
    """AI 矫正转写稿；长稿按行分块逐段整理后拼接。"""
    sep = chr(10)
    dsep = chr(10) * 2
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for line in transcript.splitlines():
        buf.append(line)
        size += len(line)
        if size >= 14000:
            chunks.append(sep.join(buf))
            buf, size = [], 0
    if buf:
        chunks.append(sep.join(buf))

    out: list[str] = []
    for chunk in chunks:
        prompt = POLISH_PROMPT.replace("{transcript}", chunk)
        out.append(_call_llm(base_url, model, api_key, prompt).strip())
    return dsep.join(out)
