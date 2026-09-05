# -*- coding: utf-8 -*-
"""演示用户 show 第二批：自动调研（网页抓取）+ 补题目预测 + 完整模拟面试（含复盘报告）。"""
import json
import sys
import time
from datetime import datetime

sys.path.insert(0, r"C:\ai_coding\inter_go\scripts")
import enrich_show  # noqa: E402
from enrich_show import (  # noqa: E402
    LOG, OPPORTUNITIES, call, client, drop_session_token, make_session_token, try_call,
)

TOKEN = make_session_token()
client.cookies.set("session_token", TOKEN)
# import enrich_show 时其模块级代码也创建了一个会话，一并在退出时清理
_LEAKED_TOKENS = [enrich_show.TOKEN]

RESUME_FACTS = {
    "intro": "面试官您好。我叫林亦航，9 年 Java 后端经验，目前在云澈科技支付平台部带 8 人小组，负责统一支付网关和清结算系统。之前在澜途信息做电商交易中台和实时风控。这几年最有代表性的工作是把支付网关从单体重构为多活架构，单机房 QPS 从 3k 做到 2.5w，大促连续三年零资损。对这个岗位的业务方向我很感兴趣，觉得我的高并发交易经验能直接用上。",
    "project": "我拿支付网关重构来讲。背景是老网关单体在日 3000 万笔峰值时频繁超时。我主导了三件事：一是无状态化改造，会话外置到 Redis，服务可以随意扩缩容，单机房 QPS 从 3k 到 2.5w，P99 从 180ms 降到 35ms；二是一致性方案，记账走本地消息表加 Kafka 异步，配 T+1 对账兜底，差异率压到百万分之一以下；三是稳定性，桶算法分布式限流加渠道级熔断，大促时故障渠道自动摘除。结果接入成本从 5 人日降到 0.5 人日，实现零资损。",
    "kafka": "Kafka 我们生产上主要抓三点：不丢靠 producer acks=all 加 broker 端 min.insync.replicas=2，消费端处理完再手动提交；不重靠幂等生产者和消费端业务幂等，我们用「渠道流水号做唯一键加状态机」兜底；顺序性靠按商户号自定义分区保证同商户有序。物流轨迹项目里我还处理过分区扩容导致键到分区映射变化的问题，当时是选在大促低峰扩容并做了消费端缓冲。",
    "redis": "缓存一致性我们的方案是先更新库再删缓存，配合 Canal 订阅 binlog 异步删除加延迟双删兜底，重试走本地消息表。秒杀场景里库存预扣用的是 Redis Lua 脚本保证原子性，热点商品按 16 个分片桶打散，读多写少的商品详情走多级缓存。线上也治理过大 key 和热 key：大 key 用 unlink 异步删除加业务侧拆分，热 key 加本地缓存副本。",
    "jvm": "G1 适合大堆可预测停顿，Region 化整体标记整理；ZGC 着色指针加读屏障，停顿亚毫秒且与堆大小无关。我们网关堆 32G 用 G1 调过 MaxGCPauseMillis 到 50ms；去年升级 JDK21 后核心链路换了 ZGC。排查 Full GC 的套路是先看老年代增长曲线区分泄漏还是容量不足，jmap histo 加 MAT 支配树定位大对象，之前定位过一次是报表服务大分页没做游标化。",
    "mysql": "8 亿数据的表我们按商户维度拆了 16 个库 256 张表，分片键选择考虑了查询路由和数据倾斜，两个超级商户做了二次散列。迁移用双写方案：全量刷库加 binlog 增量同步，灰度切读，保留两周回滚窗口。拆完最棘手的是跨片分页和聚合，列表页改走 ES 冗余索引，运营报表全部挪到 T+1 数仓，分布式事务用本地消息表保证。",
    "design": "这类设计我会先做容量估算再定架构。以秒杀为例：80w QPS 峰值，漏斗设计是前端静态化加按钮防抖挡一层，网关令牌桶限流加验证码再挡 97%，服务端 Redis Lua 预扣库存、MQ 异步落库削峰。库存一致性靠对账任务兜底，热点打散防单分片过热。这个方案我们双 11 实际跑过，零超卖零宕机，机器成本还降了 40%。",
    "weak": "这个问题我们场景里接触不算深，我说下我目前的理解：常规做法一般是先保证核心链路可用，外围用异步和兜底策略。具体细节如果面试官方便，也希望听听贵团队的实践。",
    "askback": "有两个想请教的问题：一是这个岗位所在团队目前最大的技术挑战是什么，是峰值扩容还是业务复杂度；二是团队对新人前三个月的期望是什么，我想评估下怎么快速贡献。",
}

ANSWER_POOL = [
    # (关键词列表, 答案)
    (("介绍", "自我", "开场", "背景"), "intro"),
    (("kafka", "mq", "消息", "队列", "顺序", "丢失"), "kafka"),
    (("redis", "缓存", "秒杀", "热 key", "大 key"), "redis"),
    (("jvm", "gc", "g1", "zgc", "full", "内存", "调优"), "jvm"),
    (("mysql", "索引", "分库", "分表", "mvcc", "事务", "回表"), "mysql"),
    (("设计", "架构", "场景", "秒杀", "限流", "高并发", "容量"), "design"),
    (("反问", "想问", "问你", "有什么想"), "askback"),
    (("支付", "网关", "项目", "重构", "风控", "订单", "库存"), "project"),
]

WEAK_EVERY = 5  # 每第 5 个回答故意示弱，让复盘报告有真实感


def pick_answer(question: str, n: int, resume_id: int) -> str:
    """用统一答案生成接口现场作答（贴合简历）；偶尔故意示弱让复盘更真实。"""
    if n > 0 and n % WEAK_EVERY == 0:
        return RESUME_FACTS["weak"]
    if any(k in question for k in ("反问", "想问", "问你")):
        return RESUME_FACTS["askback"]
    try:
        res = call("POST", "/ai/generate-answer", json={
            "content": question[:2000], "resume_id": resume_id,
        })
        ans = (res.get("answer_spoken") or "").strip()
        if ans:
            return ans
    except RuntimeError as e:
        LOG(f"  现场生成答案失败，退回固定答案：{e}")
    ql = question.lower()
    for keywords, key in ANSWER_POOL:
        if any(k.lower() in ql for k in keywords):
            return RESUME_FACTS[key]
    return RESUME_FACTS["project"]


# ---------------------------------------------------------------- 三件事

def auto_research(opp_ids: dict) -> None:
    """自动调研：逐岗位抓公开渠道资料（逐源容错，抓不到的渠道后端会归入 failed）。"""
    for key, oid in opp_ids.items():
        LOG(f"自动调研开始：{key}")
        try:
            r = call("POST", f"/opportunities/{oid}/notes/auto-research", retries=0)
            LOG(f"自动调研 {key}：成功 {len(r['saved'])} 源，失败 {len(r['failed'])}，重复 {len(r['duplicates'])}")
            for f in r["failed"][:3]:
                LOG(f"  · 失败源：{f['source']}（{f['error'][:60]}）")
        except RuntimeError as e:
            LOG(f"自动调研 {key} 失败：{e}")


def gen_predictions(opp_ids: dict) -> None:
    plan = [("byte", "second"), ("tencent", "first"), ("pdd", "first")]
    for key, rt in plan:
        oid = opp_ids.get(key)
        if not oid:
            continue
        try_call("POST", f"/opportunities/{oid}/predictions", f"预测题单+{key}·{rt}", json={"round_type": rt}, retries=1)


def _turns(iv) -> list:
    t = iv.get("transcript") or []
    return json.loads(t) if isinstance(t, str) else t


def run_mock_interview(oid: int, key: str, round_type: str, resume_id: int, max_replies: int = 8) -> None:
    # 幂等：已完成且带报告的跳过；进行中的会话作废（答案策略已变，避免半截对话）
    for row in (call("GET", f"/opportunities/{oid}/mock-interviews") or {}).get("items", []):
        if row.get("status") == "finished" and row.get("analysis"):
            LOG(f"模拟面试已完成，跳过：{key}#{row['id']}")
            return
        if row.get("status") == "ongoing":
            try_call("DELETE", f"/mock-interviews/{row['id']}", f"作废未完成会话 {key}#{row['id']}")
    iv = try_call("POST", f"/opportunities/{oid}/mock-interviews", f"模拟面试创建+{key}·{round_type}", json={"round_type": round_type})
    if not iv:
        return
    LOG(f"模拟面试 {key}#{iv['id']} 开场：{_turns(iv)[-1]['content'][:60]}…")
    for i in range(1, max_replies + 1):
        turns = _turns(iv)
        last_q = next((t["content"] for t in reversed(turns) if t.get("role") == "interviewer"), "")
        answer = pick_answer(last_q, i, resume_id)
        iv = call("POST", f"/mock-interviews/{iv['id']}/reply", json={"content": answer, "kind": "answer"})
        turn = _turns(iv)[-1]
        LOG(f"  回答#{i} → 面试官[{turn.get('action')}]：{turn['content'][:56]}…")
        if turn.get("action") == "finish":
            break
        time.sleep(1)
    iv = try_call("POST", f"/mock-interviews/{iv['id']}/finish", f"模拟面试复盘+{key}#{iv['id']}", retries=1)
    if iv and iv.get("analysis"):
        LOG(f"模拟面试 {key}#{iv['id']} 完成：总分 {iv.get('overall_score')}，报告 {len(iv.get('analysis') or '')} 字")
    else:
        LOG(f"模拟面试 {key}#{iv['id']} 复盘生成失败，稍后可用「重新分析」重试")


# ---------------------------------------------------------------- main

if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    try:
        opps = call("GET", "/opportunities")["items"]
        opp_ids = {}
        for o in opps:
            for spec in OPPORTUNITIES:
                if o["company"] == spec["company"] and o["position"] == spec["position"]:
                    opp_ids[spec["key"]] = o["id"]
                    break
        LOG(f"岗位：{opp_ids}")
        if only in ("all", "research"):
            auto_research(opp_ids)
        if only in ("all", "predict"):
            gen_predictions(opp_ids)
        if only in ("all", "mock"):
            resume_id = call("GET", "/resumes")["items"][0]["id"]
            if opp_ids.get("byte"):
                run_mock_interview(opp_ids["byte"], "byte", "first", resume_id)
            if opp_ids.get("xhs"):
                run_mock_interview(opp_ids["xhs"], "xhs", "second", resume_id)
        LOG("第二批全部完成 ✔")
    finally:
        drop_session_token(TOKEN)
        for t in _LEAKED_TOKENS:
            drop_session_token(t)
        client.close()
