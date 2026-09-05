"""题目来源回溯：把题库题目匹配回模拟面试 / 真实面试录音里的「原问原答」。

题目入库时只有来源类型与岗位关联，没有显式指向某场模拟面试或录音的外键，
这里用「二字组包含度」做轻量文本匹配（题干通常比面试官原话短，算题干覆盖率），
在个人数据量级下足够准，也天然容错 AI 摘述与原话之间的措辞差异。

匹配范围是全部模拟面试 / 录音（个人数据量级小，全量扫描成本低），
这样即使题目没挂来源、或挂错岗位，也照样能找回原回答。
"""
from __future__ import annotations

import json
import re

from sqlmodel import Session, select

from app.models import InterviewRound, MockInterview, Opportunity, Recording

SIM_THRESHOLD = 0.45       # 默认相似度门槛（题干二字组在原话中的覆盖率）
SHORT_THRESHOLD = 0.6      # 很短的题干（泛化问题多）用更高门槛防误匹配
SHORT_LIMIT = 12           # 题干二字组少于此数视为短题干
RAW_WINDOW = 150           # 无角色标注转写稿的滑窗大小
RAW_STEP = 60              # 滑窗步长

# 矫正稿行首角色标注：可带 [MM:SS] 时间戳，标签为「面试官」/「我」
TURN_RE = re.compile(r"^\s*(?:\[(\d{1,2}:\d{2}(?::\d{2})?)\]\s*)?(面试官|我)\s*[:：]\s*")


def _norm(text: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text.lower())


def _bigrams(text: str) -> set[str]:
    t = _norm(text)
    if not t:
        return set()
    if len(t) == 1:
        return {t}
    return {t[i : i + 2] for i in range(len(t) - 1)}


def _containment(content: str, target: str) -> float:
    """题干二字组在目标文本中的覆盖率。"""
    qb = _bigrams(content)
    if not qb:
        return 0.0
    return len(qb & _bigrams(target)) / len(qb)


def _threshold(content: str) -> float:
    return SHORT_THRESHOLD if len(_bigrams(content)) < SHORT_LIMIT else SIM_THRESHOLD


# ---------------------------------------------------------------- 模拟面试

def _mock_origins(session: Session, content: str, user_id: int) -> list[dict]:
    thresh = _threshold(content)
    qb_count = len(_bigrams(content))
    if qb_count == 0:
        return []

    opps = {
        o.id: o for o in session.exec(select(Opportunity).where(Opportunity.user_id == user_id)).all()
    }
    sessions = session.exec(
        select(MockInterview)
        .where(MockInterview.user_id == user_id)
        .order_by(MockInterview.created_at.asc())
    ).all()

    out: list[dict] = []
    for m in sessions:
        try:
            turns = json.loads(m.transcript or "[]")
        except Exception:
            continue
        if not isinstance(turns, list):
            continue

        best_i, best_s = None, 0.0
        for i, t in enumerate(turns):
            if not isinstance(t, dict) or t.get("role") != "interviewer":
                continue
            s = _containment(content, str(t.get("content") or ""))
            if s > best_s:
                best_s, best_i = s, i
        if best_i is None or best_s < thresh:
            continue

        # 收集该问题之后、下一个新问题（action != followup）之前的候选人全部回答
        answers: list[str] = []
        for t in turns[best_i + 1 :]:
            if not isinstance(t, dict):
                continue
            if t.get("role") == "candidate":
                answers.append(str(t.get("content") or "").strip())
            elif t.get("role") == "interviewer" and t.get("action") != "followup":
                break
        my_answer = "\n\n".join(a for a in answers if a).strip()

        opp = opps.get(m.opportunity_id)
        out.append(
            {
                "mock_interview_id": m.id,
                "company": opp.company if opp else None,
                "position": opp.position if opp else None,
                "round_type": m.round_type,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "overall_score": m.overall_score or 0,
                "question": str(turns[best_i].get("content") or "").strip()[:300],
                "my_answer": my_answer[:1500] or None,
            }
        )
    return out


# ---------------------------------------------------------------- 真实面试录音

def _split_turns(text: str) -> list[dict]:
    """把带「面试官：/我：」标注的矫正稿拆成发言轮次；无标注行并入上一条。"""
    turns: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = TURN_RE.match(line)
        if m:
            turns.append(
                {
                    "speaker": m.group(2),
                    "text": line[m.end() :].strip(),
                    "timestamp": m.group(1),
                }
            )
        elif turns:
            turns[-1]["text"] += f"\n{line}"
        else:
            turns.append({"speaker": "?", "text": line, "timestamp": None})
    return turns


def _recording_origins(session: Session, content: str, user_id: int) -> list[dict]:
    thresh = _threshold(content)
    if len(_bigrams(content)) == 0:
        return []

    opps = {
        o.id: o for o in session.exec(select(Opportunity).where(Opportunity.user_id == user_id)).all()
    }
    rounds = {
        r.id: r for r in session.exec(select(InterviewRound).where(InterviewRound.user_id == user_id)).all()
    }
    recs = session.exec(
        select(Recording).where(Recording.user_id == user_id).order_by(Recording.created_at.asc())
    ).all()

    out: list[dict] = []
    for r in recs:
        clean = (r.transcript_clean or "").strip()
        text = clean or (r.transcript or "").strip()
        if not text:
            continue

        base = {
            "recording_id": r.id,
            "company": opps[r.opportunity_id].company if r.opportunity_id in opps else None,
            "round_type": rounds[r.round_id].round_type
            if r.round_id is not None and r.round_id in rounds
            else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }

        if clean:
            # 矫正稿有角色标注：按发言轮次定位面试官原话，收集「我」的后续回答
            turns = _split_turns(text)
            best_i, best_s = None, 0.0
            for i, t in enumerate(turns):
                if t["speaker"] != "面试官":
                    continue
                s = _containment(content, t["text"])
                if s > best_s:
                    best_s, best_i = s, i
            if best_i is None or best_s < thresh:
                continue

            t = turns[best_i]
            answers = []
            for j in range(best_i + 1, len(turns)):
                if turns[j]["speaker"] == "面试官":
                    break
                if turns[j]["speaker"] == "我":
                    answers.append(turns[j]["text"])
            context_before = None
            if best_i > 0:
                pre = turns[max(0, best_i - 2) : best_i]
                context_before = " ".join(
                    f"（{p['speaker']}）{p['text']}" for p in pre
                )[:240]

            my_answer = "\n\n".join(a for a in answers if a).strip()
            out.append(
                {
                    **base,
                    "question_text": t["text"][:300],
                    "timestamp": t["timestamp"],
                    "context_before": context_before,
                    "my_answer": my_answer[:1800] or None,
                    "excerpt": None,
                }
            )
        else:
            # 原始转写稿没有角色标注：滑窗找最像题干的片段，给出上下文摘录
            best_pos, best_s = None, 0.0
            for pos in range(0, max(1, len(text) - RAW_WINDOW), RAW_STEP):
                s = _containment(content, text[pos : pos + RAW_WINDOW])
                if s > best_s:
                    best_s, best_pos = s, pos
            if best_pos is None or best_s < thresh:
                continue
            out.append(
                {
                    **base,
                    "question_text": text[best_pos : best_pos + 200].strip(),
                    "timestamp": None,
                    "context_before": None,
                    "my_answer": None,
                    "excerpt": text[max(0, best_pos - 200) : best_pos + 1000].strip()[:1200],
                }
            )
    return out


def find_origins(session: Session, content: str, user_id: int) -> dict:
    """回溯一道题在模拟面试 / 真实面试录音中的原问原答，按时间正序返回。"""
    return {
        "mock_answers": _mock_origins(session, content, user_id),
        "recording_answers": _recording_origins(session, content, user_id),
    }
