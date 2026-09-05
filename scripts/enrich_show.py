# -*- coding: utf-8 -*-
"""演示用户 show（id=3）数据充实脚本：简历 → 题库 → 岗位 → 调研/匹配度/预测题单 → 轮次 → Offer。

一次性脚本：通过后端 API 以 show 用户身份造数（临时会话 Cookie，不改动账号密码），
AI 相关内容（体检/预测题/调研/匹配度/题单）全部走真实接口生成，失败自动重试一次并跳过。
"""
import hashlib
import io
import json
import secrets
import sqlite3
import sys
import time
from datetime import datetime, timedelta

import httpx

BASE = "http://127.0.0.1:8000/api"
DB_PATH = r"C:\ai_coding\inter_go\data\app.db"
SHOW_USER_ID = 3
LOG = lambda msg: print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# ---------------------------------------------------------------- 会话（临时 Cookie，不动密码）

def make_session_token() -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO usersession (token_hash, user_id, created_at, expires_at) VALUES (?,?,?,?)",
        (token_hash, SHOW_USER_ID, datetime.now(), datetime.now() + timedelta(hours=6)),
    )
    conn.commit()
    conn.close()
    return token


def drop_session_token(token: str) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM usersession WHERE token_hash = ?", (hashlib.sha256(token.encode()).hexdigest(),))
    conn.commit()
    conn.close()


TOKEN = make_session_token()
client = httpx.Client(base_url=BASE, timeout=httpx.Timeout(600, connect=30), cookies={"session_token": TOKEN})


def call(method: str, path: str, *, retries: int = 1, **kw):
    """带重试的 API 调用；非 2xx 抛异常。"""
    last_err = None
    for i in range(retries + 1):
        try:
            r = client.request(method, path, **kw)
            if r.status_code == 200:
                return r.json()
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:  # 网络抖动
            last_err = f"{type(e).__name__}: {e}"
        if i < retries:
            LOG(f"  retry {path} ({last_err})")
            time.sleep(5)
    raise RuntimeError(f"{method} {path} 失败: {last_err}")


def try_call(method: str, path: str, label: str, **kw):
    """失败只记日志不中断（造数允许个别 AI 调用失败）。"""
    try:
        data = call(method, path, **kw)
        LOG(f"OK  {label}")
        return data
    except RuntimeError as e:
        LOG(f"FAIL {label}: {e}")
        return None


# ---------------------------------------------------------------- 1. 复杂简历（DOCX）

RESUME_LINES = [
    "林亦航",
    "资深 Java 后端工程师 | 9 年经验 | 上海",
    "电话：138-0212-6688 | 邮箱：linyihang.dev@example.com | 1992 年生 | 现居上海徐汇",
    "",
    "教育背景",
    "- 华中科技大学 软件工程（本科） 2012.09 - 2016.06",
    "  - 主修课程：数据结构、操作系统、计算机网络、数据库系统、编译原理",
    "  - 校级程序设计竞赛二等奖，ACM 校队队员（区域赛铁牌）",
    "  - CET-6，可阅读英文技术文档与论文",
    "",
    "专业技能",
    "- 语言基础：精通 Java，深入理解 JVM 内存模型、GC 调优（CMS/G1/ZGC）、类加载机制与常用字节码增强手段；熟悉 Kotlin 与 Go",
    "- 并发编程：熟练使用 JUC，深入理解 AQS、线程池原理、ThreadLocal 与内存可见性；有多个万级 QPS 场景的并发改造实战",
    "- 分布式与高可用：熟悉分布式事务（TCC / SAGA / 本地消息表）、分布式锁、幂等设计、限流熔断降级（Sentinel / 自研网关限流）、一致性哈希",
    "- 消息队列：精通 Kafka（分区机制、顺序性、Exactly-Once 语义、跨机房同步），熟悉 RocketMQ 事务消息与延迟消息",
    "- 缓存：精通 Redis（Cluster / 哨兵、缓存一致性方案、热点 Key 治理、大 key 拆分），了解 Dragonfly",
    "- 存储：精通 MySQL（索引原理、事务与 MVCC、锁机制、分库分表），主导过单表 8 亿数据的拆分迁移；熟悉 TiDB、ShardingSphere、Elasticsearch（写入调优与聚合分析）",
    "- 微服务与云原生：精通 Spring Boot / Spring Cloud Alibaba / Dubbo，熟悉 Kubernetes 编排、服务网格 Istio、Helm；主导过 200+ 微服务的治理与容器化迁移",
    "- 可观测性：基于 SkyWalking / Prometheus / Grafana 搭建全链路追踪与告警体系，有 SLA 99.99% 保障经验",
    "",
    "工作经历",
    "- 云澈科技有限公司 高级 Java 工程师（支付平台部） 2021.07 - 至今",
    "  - 负责公司统一支付网关与清结算系统的架构设计，带 8 人小组，支撑全公司 30+ 业务线接入",
    "  - 主导支付核心链路的单元化改造与大促保障，连续三年大促零资损",
    "  - 推动部门微服务治理规范落地：接口契约、容量规划、全链路压测流水线",
    "- 上海澜途信息科技有限公司 资深 Java 工程师（电商平台部） 2018.03 - 2021.06",
    "  - 负责电商交易中台（购物车 / 订单 / 促销）的核心开发与大促备战",
    "  - 从 0 到 1 搭建实时风控引擎，覆盖账号安全与交易反作弊",
    "- 武汉星河网络技术有限公司 Java 工程师 2016.07 - 2018.02",
    "  - 参与 SaaS CRM 后端开发，负责报表模块与消息推送服务",
    "",
    "项目经历",
    "- 统一支付网关重构（2022.03 - 2023.06）",
    "  - 项目描述：原网关单体架构在峰值 3000 万笔/日时频繁超时，重构为插件化、无状态的多活网关",
    "  - 核心工作：",
    "    - 主导无状态化改造与会话外置，单机房 QPS 从 3k 提升至 2.5w，P99 从 180ms 降至 35ms",
    "    - 设计本地消息表 + Kafka 的异步记账与对账链路，保证最终一致性，T+1 对账差异率降到百万分之一以下",
    "    - 基于桶算法实现分布式限流，配合 Sentinel 完成渠道级熔断降级，大促期间自动摘除故障渠道",
    "  - 项目业绩：接入成本从 5 人日降至 0.5 人日，年资损金额从 80 万级降为零资损，获得公司年度技术突破奖",
    "- 大促秒杀与库存中心（2020.05 - 2021.01）",
    "  - 项目描述：支撑双 11 峰值 80w QPS 的商品秒杀与库存扣减",
    "  - 核心工作：",
    "    - 设计 Redis + Lua 预扣库存、MQ 异步落库的两阶段方案，热点商品按分片桶打散",
    "    - 引导请求漏斗：前端限流 → 网关题（验证码 + 令牌）→ 服务端预扣，拦截 97% 无效流量",
    "  - 项目业绩：大促期间零超卖、零宕机，服务器成本较上一届下降 40%",
    "- 实时风控引擎（2019.02 - 2020.04）",
    "  - 项目描述：账号盗用、恶意下单、羊毛党识别的实时决策系统",
    "  - 核心工作：",
    "    - 基于 Flink + Kafka 构建实时特征计算，特征口径 200+，端到端延迟 P99 < 300ms",
    "    - 规则引擎采用 Groovy 脚本热更新 + 决策树编排，策略上线周期从 3 天缩短到 10 分钟",
    "  - 项目业绩：上线后恶意订单占比从 1.8% 降至 0.3%，年挽回损失约 1200 万元",
    "- 物流轨迹搜索平台（2018.03 - 2019.01）",
    "  - 项目描述：全网包裹轨迹的存储与秒级查询服务，日均写入 2 亿条",
    "  - 核心工作：",
    "    - 设计 Elasticsearch 冷热分层索引与滚动扩容方案，写入吞吐提升 3 倍",
    "    - 用 Kafka 分区策略保证轨迹乱序问题的最终一致，补偿任务幂等可重放",
    "  - 项目业绩：轨迹查询 P99 从 2s 降至 200ms，客服进线量下降 18%",
]


def build_resume_docx() -> bytes:
    import docx

    doc = docx.Document()
    for line in RESUME_LINES:
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def db_scalar(sql: str, *params):
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute(sql, params).fetchone()[0]
    finally:
        conn.close()


def upload_resume() -> int:
    # 幂等：已有同名简历直接复用
    items = call("GET", "/resumes")["items"]
    for r in items:
        if r["name"].startswith("林亦航"):
            LOG(f"简历已存在 id={r['id']}，复用")
            return r["id"]
    content = build_resume_docx()
    r = client.post(
        "/resumes",
        files={"file": ("林亦航-资深Java后端-9年经验.docx", content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    r.raise_for_status()
    resume = r.json()
    LOG(f"简历已上传 id={resume['id']}，抽取 {len(resume.get('text') or '')} 字，自动整理={'有' if resume.get('structured') else '无'}")
    return resume["id"]


# ---------------------------------------------------------------- 2. 题库（手写高质量题 + 简历预测题入库）

HAND_QUESTIONS = [
    # (dimension, difficulty, content, answer_key, source_type, mastery, self_rating)
    ("JUC", "hard", "线程池核心参数有哪些？提交一个任务后线程池的处理流程是怎样的？",
     "1. 核心参数：corePoolSize、maximumPoolSize、keepAliveTime、workQueue、threadFactory、handler；\n2. 流程：核心线程未满则新建；满了先入队；队列满再建非核心线程；达到 maximum 后触发拒绝策略；\n3. 追问点：为什么先入队再扩容（复用优先）、Executors 各工厂方法的风险（无界队列/Integer.MAX）。", "real", "mastered", 4),
    ("JUC", "hard", "AQS 的实现原理？独占模式和共享模式有什么区别？",
     "1. AQS = volatile state + CLH 变体双向队列 + 模板方法；\n2. 独占（tryAcquire 入队 park，release 唤醒后继）；共享（tryAcquireShared 传播唤醒，setPropagate 处理并发释放丢失）；\n3. 结合项目：支付网关用 Semaphore（共享）做渠道并发控制。", "real", "fuzzy", 3),
    ("JVM", "hard", "线上服务频繁 Full GC，你的排查思路是什么？",
     "1. 先看监控：GC 频率与耗时、老年代增长曲线（是内存泄漏还是容量不足）；\n2. jmap histo / mat 分析支配树定位大对象来源；jstat 确认晋升速度；\n3. 常见原因：缓存无界、ThreadLocal 未清理、大分页查询；\n4. 治理：代码修复优先，其次调参（G1 MaxGCPauseMillis / 扩容），给出压测验证口径。", "real", "mastered", 4),
    ("JVM", "medium", "G1 和 CMS 的区别？什么时候会选择 ZGC？",
     "1. CMS 标记-清除有碎片、并发失败退化为 Serial Old；G1 Region 化、整体标记-整理、可预测停顿；\n2. ZGC 着色指针 + 读屏障，停顿 <1ms 且与堆大小无关，适合大堆低延迟；\n3. 代价：吞吐略降、内存 headroom 要求高，JDK 版本和 GC 日志生态要跟上。", "manual", "fuzzy", 3),
    ("MySQL", "hard", "什么是回表？如何减少回表？覆盖索引的代价是什么？",
     "1. 二级索引叶子节点存主键，查非索引列需要回表；\n2. 覆盖索引把查询列都放进索引（联合索引 / 冗余字段）避免回表；\n3. 代价：索引变大、写入放大、维护成本，需结合最左前缀与区分度权衡。", "real", "mastered", 4),
    ("MySQL", "hard", "介绍下 MVCC 的实现？RR 隔离级别下幻读到底解决了没有？",
     "1. MVCC = undo log 版本链 + ReadView（m_ids/min/max/creator）；RR 下首次快照读生成 ReadView 并复用，RC 每次生成；\n2. 快照读靠 MVCC 防幻读，当前读靠临键锁（Next-Key Lock）；\n3. 结论：快照读 + 当前读混用时仍会出现幻读，要结合加锁语义讲。", "real", "fuzzy", 3),
    ("MySQL", "hard", "单表 8 亿数据你是怎么拆的？拆分后哪些问题变得棘手？",
     "1. 分片键选择：按商户维度拆，兼顾查询路由与数据倾斜（热点商户单独再散列）；\n2. 双写迁移：全量刷库 + 增量 binlog 同步 + 灰度切读 + 回滚预案；\n3. 拆分后的难点：跨片分页（ES 冗余或步长跳查）、分布式事务（本地消息表）、聚合统计走 T+1 数仓。", "real", "mastered", 5),
    ("Redis", "hard", "缓存与数据库的一致性怎么保证？先删缓存还是先更新库？",
     "1. 推荐 Cache Aside：先更新库再删缓存 + 延迟双删兜底；\n2. 订阅 binlog（Canal）异步删除更稳，重试队列保证最终一致；\n3. 强一致场景要么加分布式锁串行化，要么干脆不走缓存，讲清业务取舍。", "real", "mastered", 4),
    ("Redis", "medium", "Redis Cluster 的槽位机制是什么？热点 Key 怎么治理？",
     "1. 16384 槽按 CRC16(key) mod 分配，节点负责槽区间，客户端可重定向（MOVED/ASK）；\n2. 热点 Key：本地缓存（多级）、Key 打散（后缀分片聚合读）、读写分离副本；\n3. 大 Key：拆分 ziplist、异步删除 unlink、迁移时注意阻塞。", "manual", "mastered", 4),
    ("消息队列", "hard", "Kafka 如何保证消息不丢不重？顺序性怎么保证？",
     "1. 不丢：producer acks=all + retries、broker 副本 ISR + min.insync.replicas、consumer 手动提交且业务处理完再提交；\n2. 不重：幂等生产者（PID+seq）或事务，消费端业务幂等（唯一键/状态机）；\n3. 顺序：同分区有序，按业务键（订单号）自定义分区，扩容分区会破坏键到分区的映射要评估。", "real", "mastered", 5),
    ("消息队列", "medium", "RocketMQ 事务消息和本地消息表方案怎么选？",
     "1. 事务消息：半消息 + 回查，业务侵入小但依赖 MQ 的回查实现与消息表清理；\n2. 本地消息表：与业务同库同事务，可靠性强但每业务都要建表与扫描任务；\n3. 选型：跨团队链路用事务消息，强一致核心链路倾向本地消息表 + 对账兜底（结合支付项目讲）。", "manual", "fuzzy", 3),
    ("分布式", "hard", "分布式锁有哪些实现？Redis 锁的续期和 Redlock 争议了解吗？",
     "1. Redis：setnx + 过期时间 + 唯一值防误删，看门狗续期（Redisson）；ZK：临时顺序节点 watch 前驱；\n2. Redlock 争议：Martin Kleppmann 质疑时钟跳变下的安全性，fencing token 才是正解；\n3. 实践：单实例 Redis 锁 + 业务幂等兜底已满足大多数场景，强一致用 ZK/etcd。", "real", "fuzzy", 3),
    ("分布式", "hard", "描述一次你处理线上事故的过程：如何定位、恢复和复盘？",
     "1. 案例背景：Kafka 跨机房同步延迟导致对账积压，资损预警；\n2. 定位：链路追踪发现消费组 rebalance 风暴，根因是机房网络抖动触发 session 超时；\n3. 恢复：先扩消费实例 + 调大 session.timeout，追平延迟后恢复；\n4. 复盘：把「超时参数 — 网络分区」写入预案、加 rebalance 告警，推动跨机房同步改为 MirrorMaker2 专用集群。", "manual", "mastered", 5),
    ("微服务", "medium", "微服务拆分的粒度怎么把握？拆过头了有什么症状？",
     "1. 按业务能力/限界上下文拆，结合团队规模（两个披萨）与变更频率；\n2. 拆过头的症状：链路 RT 明显变长、分布式事务泛滥、一个需求改五个服务；\n3. 治理：合并高频同步调用的服务、领域事件解耦、用 API 网关收敛对外语义。", "manual", "mastered", 4),
    ("微服务", "medium", "Sentinel 的限流算法有哪些？和网关层限流怎么配合？",
     "1. 算法：滑动窗口统计、令牌桶（匀速排队）、热点参数限流、集群限流；\n2. 分层：接入层粗粒度挡量（nginx/网关桶限流），应用层按接口/资源细粒度保护；\n3. 结合项目：秒杀场景网关令牌桶挡 97% 流量，Sentinel 兜底保护下游弱依赖。", "manual", "mastered", 4),
    ("计算机网络", "medium", "HTTPS 的握手过程？为什么 TLS 1.3 更快？",
     "1. TLS1.2：ClientHello → 证书校验 → 密钥交换（ECDHE）→ 完成，2-RTT；\n2. TLS1.3：合并握手 1-RTT，支持 0-RTT 恢复，删掉不安全套件；\n3. 追问：会话复用（session ticket）、证书链与 OCSP 装订、SNI。", "manual", "mastered", 4),
    ("计算机网络", "medium", "TCP 粘包拆包怎么处理？长连接的心跳与断线重连怎么设计？",
     "1. 粘包根源是字节流无消息边界：定长、分隔符、长度域（Netty LengthFieldBasedFrameDecoder）；\n2. 心跳：空闲检测（IdleStateHandler）+ 协议层 ping/pong，区分连接死活与业务超时；\n3. 重连：指数退避 + 抖动，重连后状态恢复（订阅关系、token 刷新）。", "manual", "fuzzy", 3),
    ("系统设计", "hard", "设计一个分布式 ID 生成器，要求趋势递增、高可用。",
     "1. 方案对比：UUID（无序）、号段模式（DB 批量发号 + 双 buffer）、雪花算法（时钟回拨问题）；\n2. 雪花优化：回拨等待/借用未来时间、机器位用 ZK/DB 分配；\n3. 容量：64bit 布局，41 位时间戳 + 10 位机器 + 12 位序列，单机 400w/s；\n4. 结合项目：支付网关用号段 + 雪花混合，号段兜底时钟异常。", "real", "mastered", 5),
    ("系统设计", "hard", "如果要你设计一个短链接服务，怎么估算和设计？",
     "1. 估算：写 1w QPS 读 100w QPS、存储年增百 GB 级；\n2. 发号：雪花/号段生成 62 进制 7 位；防重可布隆过滤器；\n3. 读写分离：跳转走缓存 + 302，布隆过滤不存在 key，防攻击限流；\n4. 扩展：自定义域名、过期策略、统计埋点走 Kafka 异步。", "manual", "fuzzy", 3),
    ("场景设计", "hard", "大促前怎么做容量规划与全链路压测？",
     "1. 目标推导：业务目标 GMV → 请求量模型 → 各服务容量（峰值 × 安全系数）；\n2. 压测：影子库表 + 流量标识，从单接口基线到全链路逐步加压，找最短板；\n3. 预案：限流阈值、降级开关、扩容预案演练，值班表与止血 SOP；\n4. 结合支付网关项目讲三年大促零故障的保障体系。", "real", "mastered", 5),
    ("场景设计", "medium", "订单超时未支付自动取消，有哪些实现方案？",
     "1. 延迟消息（RocketMQ 延迟级别 / RabbitMQ 死信）最通用；\n2. 时间轮 / Redis zinv 轮询扫描适合自研场景；\n3. 对账兜底任务必须有；注意取消时与支付回调的并发竞态（状态机 + 分布式锁）。", "manual", "mastered", 4),
    ("软素质", "medium", "你和产品经理对技术方案工期有分歧，怎么处理？",
     "1. 先对齐目标与优先级：这个需求解决什么问题、 deadline 的真实约束；\n2. 给选项而不是给拒绝：MVP 分期 / 降级方案 / 资源互换，附风险与工作量依据；\n3. 事后同步边界：沉淀需求评审机制，避免同类分歧反复。", "manual", "mastered", 4),
    ("算法", "medium", "手写：LRU 缓存（LeetCode 146），说下思路和复杂度。",
     "1. 哈希表 + 双向链表：get/put O(1)，头插尾删；\n2. 追问：LinkedHashMap accessOrder 实现、线程安全版（分桶 + 分段锁/Caffeine W-TinyLFU 对比）；\n3. 落地：本地缓存淘汰策略选型与命中率监控。", "real", "mastered", 4),
    ("语言特性", "medium", "HashMap 在 JDK 7 和 JDK 8 的实现差异？为什么链表转红黑树的阈值是 8？",
     "1. JDK8：数组+链表+红黑树，头插改尾插（解决并发成环），扩容优化（高低位拆分）；\n2. 阈值 8：泊松分布下桶内 8 个元素概率约千万分之一，是退化兜底而非优化目标；\n3. 追问：负载因子 0.625 的折中、树化还需数组容量 ≥ 64。", "real", "mastered", 4),
]


def enrich_bank(resume_id: int, opp_ids: dict[str, int]) -> list[int]:
    """手写题入库（幂等）+ 简历预测题入库；返回新建的题目 id。"""
    ids = []
    # real 来源的题挂到对应公司（只挂公司，轮次留空）
    mapping = [
        ("线程池", "byte"), ("MVCC", "byte"), ("8 亿", "meituan"), ("Kafka 如何保证", "kuaishou"),
        ("分布式 ID", "ali"), ("LRU", "xhs"), ("全链路压测", "byte"), ("处理线上事故", "xhs"),
    ]
    for dim, diff, content, key, source, mastery, rating in HAND_QUESTIONS:
        exists = db_scalar("SELECT COUNT(*) FROM question WHERE content = ?", content.strip())
        if exists:
            LOG(f"跳过（已在题库）[{dim}] {content[:18]}…")
            continue
        payload = {
            "content": content, "dimension": dim, "difficulty": diff, "source": source,
            "opportunity_id": None, "resume_id": None, "sources": None,
            "my_answer": None, "answer_key": key, "answer_spoken": None,
            "self_rating": rating, "mastery": mastery,
        }
        if source == "real":
            for prefix, key2 in mapping:
                if (content.startswith(prefix) or prefix in content) and key2 in opp_ids:
                    oid = opp_ids[key2]
                    payload["opportunity_id"] = oid
                    payload["sources"] = [{"opportunity_id": oid, "round_id": None}]
                    break
        q = try_call("POST", "/questions", f"题库+[{dim}] {content[:18]}…", json=payload)
        if q:
            ids.append(q["id"])
    return ids


def deposit_predicted_questions(resume_id: int) -> None:
    """把简历预测题（含 AI 完整答案）按「题目预测」来源存入题库（幂等）。"""
    resumes = call("GET", "/resumes")
    r = next((x for x in resumes["items"] if x["id"] == resume_id), None)
    if not r or not r.get("questions_json"):
        LOG("跳过预测题入库：无 questions_json")
        return
    for q in json.loads(r["questions_json"]).get("questions", []):
        if db_scalar("SELECT COUNT(*) FROM question WHERE content = ?", (q.get("q") or "").strip()):
            continue
        payload = {
            "content": q.get("q"), "dimension": q.get("tag") or "其他", "difficulty": "medium",
            "source": "predicted", "opportunity_id": None, "resume_id": resume_id, "sources": None,
            "my_answer": None, "answer_key": q.get("a") or None, "answer_spoken": q.get("full") or None,
            "self_rating": None, "mastery": "unknown",
        }
        try_call("POST", "/questions", f"预测题入库 [{q.get('tag')}] {q.get('q','')[:16]}…", json=payload)


# ---------------------------------------------------------------- 3. 岗位（完整字段 + 真实感 JD）

def jd(lead: str, duties: list[str], reqs: list[str], bonus: list[str]) -> str:
    lines = [f"【职位描述】", f"{lead}", "", "职责描述："]
    lines += [f"{i+1}. {d}" for i, d in enumerate(duties)]
    lines += ["", "任职要求："]
    lines += [f"{i+1}. {r}" for i, r in enumerate(reqs)]
    if bonus:
        lines += ["", "加分项："]
        lines += [f"{i+1}. {b}" for i, b in enumerate(bonus)]
    return "\n".join(lines)


OPPORTUNITIES = [
    dict(key="byte", company="字节跳动", position="资深后端开发工程师（抖音电商·交易）", department="抖音电商-交易架构",
         city="上海", address="上海市杨浦区五角场互联宝地", salary_range="40-65K·16薪", channel="BOSS直聘", priority="S",
         status="interviewing",
         jd_text=jd("负责抖音电商交易核心链路的设计与研发，支撑亿级用户的高并发交易场景。",
                    ["负责交易下单、履约、逆向等核心链路的架构设计与稳定性保障；",
                     "参与大促容量规划与全链路压测，建设高可用保障体系；",
                     "主导技术方案评审与疑难问题攻关，带动团队技术成长。"],
                    ["5 年以上后端开发经验，扎实的计算机基础与 Java/Golang 功底；",
                     "深入理解高并发、分布式事务、消息队列等，有电商或交易系统经验优先；",
                     "具备良好的系统抽象能力与故障排查能力，有大促保障经验者优先。"],
                    ["有抖音/电商业务背景；", "熟悉单元化改造、多机房容灾。"]),
         note="HR 反馈节奏快，一面已过，重点准备二面项目深挖"),
    dict(key="ali", company="阿里云", position="高级开发工程师（云原生·容器服务）", department="阿里云-容器平台部",
         city="杭州", address="杭州市西湖区云谷园区", salary_range="35-60K·16薪", channel="官网", priority="S",
         status="applied",
         jd_text=jd("参与阿里云容器服务 ACK / 服务网格 ASM 的核心能力研发，服务百万级容器集群。",
                    ["负责 Kubernetes 控制面性能优化与大规模集群稳定性；",
                     "设计服务网格、灰度发布、多集群调度等云原生解决方案；",
                     "跟踪社区生态（K8s/Istio），推动自研组件与开源协同。"],
                    ["3 年以上 Java/Golang 开发经验，深入理解 Kubernetes 原理（调度/网络/存储）；",
                     "熟悉 Docker、Istio、Prometheus 等云原生技术栈；",
                     "有大规模生产集群运维或云产品研发经验优先。"],
                    ["Kubernetes/Istio 社区 Committer；", "有 SLI/SLO 工程化实践。"]),
         note="官网投递，状态待跟进；岗位与我的 K8s 迁移经验契合"),
    dict(key="meituan", company="美团", position="后端开发专家（到店交易平台）", department="到店事业群-交易平台组",
         city="上海", address="上海市黄浦区中兴路 655 号", salary_range="38-60K·15.5薪", channel="猎聘", priority="A",
         status="applied",
         jd_text=jd("负责到店交易平台的订单、优惠计算等核心模块，支撑高并发本地生活交易。",
                    ["负责交易平台核心域（订单/优惠/结算）的架构演进与性能优化；",
                     "建设交易稳定性体系：限流、降级、对账与资损防控；",
                     "指导团队中级工程师，推动领域建模与代码质量提升。"],
                    ["5 年以上 Java 后端经验，精通 MySQL、Redis、Kafka 等中间件原理；",
                     "有交易、支付、营销等核心系统经验，能驾驭复杂业务建模；",
                     "良好的沟通协作能力，有跨团队项目推进经验。"],
                    ["有本地生活行业背景；", "熟悉领域驱动设计。"]),
         note="猎聘顾问推荐，约了一面"),
    dict(key="xhs", company="小红书", position="资深 Java 开发工程师（社区技术）", department="社区技术部-互动体系",
         city="上海", address="上海市黄浦区马当路 388 号", salary_range="35-55K·15薪", channel="内推", priority="A",
         status="offer",
         jd_text=jd("负责小红书社区互动链路（点赞/评论/关注）的服务端研发，支撑日活过亿的互动体验。",
                    ["负责互动核心服务的架构设计与迭代，保障高并发读写场景的稳定性；",
                     "建设内容安全与风控在互动链路的接入能力；",
                     "参与团队技术规划，推动中间件与基础设施的统一。"],
                    ["4 年以上 Java 开发经验，基础扎实，对 JVM、并发、MySQL 有深入理解；",
                     "有高并发社区/社交类服务经验，熟悉 Redis、Kafka 等中间件；",
                     "有良好的产品意识与业务 owner 意识。"],
                    ["有社区产品相关经验；", "熟悉 Go 语言。"]),
         note="内推效率很高，三轮技术+HR 全过，已发 offer，权衡中"),
    dict(key="tencent", company="腾讯云", position="后台开发高级工程师（云数据库）", department="CSIG-数据库产品线",
         city="深圳", address="深圳市南山区滨海科技大厦", salary_range="35-58K·16薪", channel="BOSS直聘", priority="A",
         status="wishlist",
         jd_text=jd("参与腾讯云数据库（TencentDB）控制面与内核工具链的研发。",
                    ["负责数据库管控平台的架构设计与研发（实例编排、备份恢复、巡检诊断）；",
                     "优化多租户场景下的资源调度与隔离能力；",
                             "建设数据库产品的可观测与自助化运维体系。"],
                    ["3 年以上后端开发经验，熟悉 MySQL 原理，了解 Redis/PG 等产品；",
                     "扎实的 Java/Golang 功底，熟悉 K8s Operator 开发模式优先；",
                     "对云产品商业化与客户体验有感知。"],
                    ["有数据库内核或管控平台经验；", "熟悉华为云/阿里云同类产品。"]),
         note="深圳机会需考虑搬移，先观望"),
    dict(key="kuaishou", company="快手", position="资深服务端开发工程师（商业化）", department="商业化技术部-投放平台",
         city="北京", address="北京市海淀区上地西路 6 号", salary_range="32-55K·15薪", channel="BOSS直聘", priority="B",
         status="rejected",
         jd_text=jd("负责快手商业化投放平台的服务端研发，支撑广告主亿级投放请求。",
                    ["负责广告投放检索与预算控制链路的服务端研发；",
                     "优化高并发低延迟链路，建设投放效果数据体系；"],
                    ["4 年以上服务端经验，Java/C++ 均可，算法与数据结构功底扎实；",
                     "有广告、推荐、检索类高并发系统经验优先；"],
                    ["有计算广告背景。"]),
         note="一面聊广告业务偏少被挂，JD 偏检索方向"),
    dict(key="pdd", company="拼多多", position="服务端研发工程师（主站交易）", department="主站技术部",
         city="上海", address="上海市长宁区娄山关路 533 号", salary_range="45-70K·16薪", channel="脉脉", priority="S",
         status="wishlist",
         jd_text=jd("加入主站交易团队，参与订单与营销链路的研发，用最简架构支撑极致性能。",
                    ["负责交易链路核心模块的研发与优化，追求高吞吐低延迟；",
                     "参与大促备战，建设压测与容量体系；"],
                    ["1-5 年经验均可，技术功底扎实，追求极致性能与工程质量；",
                     "熟悉 Java/C++/Golang 至少一门，熟悉 MySQL、Redis；"],
                    ["有 IOI/ACM 等竞赛经历优先。"]),
         note="脉脉 hr 主动沟通，工作强度传言较大，先评估"),
    dict(key="mihoyo", company="米哈游", position="高级服务端工程师（商业化平台）", department="商业化技术中心",
         city="上海", address="上海市徐汇区宜州路 180 号", salary_range="30-50K·14.5薪", channel="官网", priority="B",
         status="no_response",
         jd_text=jd("负责米哈游旗下游戏商业化平台的服务端研发（支付/商城/活动）。",
                    ["负责游戏内商城、支付订单链路的服务端开发；",
                     "保障活动峰值场景下的稳定性与资损安全；"],
                    ["3 年以上 Java/Golang 经验，熟悉 MySQL、Redis、消息队列；",
                     "有支付、交易相关经验优先；"],
                    ["热爱二次元游戏。"]),
         note="官网投递后两周无响应"),
]


def create_opportunities(resume_id: int) -> dict[str, int]:
    # 幂等：按 公司+岗位 匹配已存在的岗位
    existing = {}
    for o in call("GET", "/opportunities")["items"]:
        existing[(o["company"], o["position"])] = o["id"]
    ids = {}
    for o in OPPORTUNITIES:
        key = o["key"]
        if (o["company"], o["position"]) in existing:
            ids[key] = existing[(o["company"], o["position"])]
            LOG(f"岗位已存在 id={ids[key]}：{o['company']}")
            continue
        payload = {k: v for k, v in o.items() if k not in ("key",)}
        payload["resume_id"] = resume_id
        payload["applied_at"] = None
        if o["status"] in ("applied", "interviewing", "offer", "rejected"):
            payload["applied_at"] = (datetime(2026, 8, 1) + timedelta(days=len(ids) * 3)).strftime("%Y-%m-%dT%H:%M:%S")
        # 创建接口只接受活跃状态：归档状态先建为 applied 再 PATCH
        archived = o["status"] in ARCHIVED
        if archived:
            payload["status"] = "applied"
        opp = try_call("POST", "/opportunities", f"岗位+{o['company']}·{o['position'][:14]}", json=payload)
        if not opp:
            continue
        ids[key] = opp["id"]
        if archived:
            try_call("PATCH", f"/opportunities/{opp['id']}", f"归档+{key}→{o['status']}", json={"status": o["status"]})
    return ids


# ---------------------------------------------------------------- 4. 轮次 / Offer / 调研材料

ARCHIVED = ("rejected", "no_response", "give_up")


def d(day: str, hm: str = "14:00") -> str:
    return f"2026-{day}T{hm}:00"


ROUNDS = [
    # (key, round_type, scheduled_at, result, note)
    ("byte", "first", d("08-22", "14:00"), "passed", "一面：基础 + 项目，问了线程池、MVCC、单表拆分，节奏快"),
    ("byte", "second", d("09-01", "19:30"), "passed", "二面：架构设计（分布式 ID/短链）+ 场景题全链路压测，聊了 70 分钟"),
    ("byte", "third", d("09-09", "19:30"), "pending", "三面（leader 面）：待准备——交易架构演进 + 团队管理"),
    ("meituan", "first", d("09-11", "10:30"), "pending", "一面：约在下周三上午"),
    ("xhs", "first", d("08-12", "15:00"), "passed", "一面：Redis 一致性 + Kafka 语义 + 场景题互动风控"),
    ("xhs", "second", d("08-19", "15:00"), "passed", "二面：项目深挖为主，风控引擎讲得很细"),
    ("xhs", "hr", d("08-26", "16:00"), "passed", "HR 面：薪资沟通、稳定性意向"),
    ("kuaishou", "first", d("08-20", "11:00"), "failed", "一面：广告检索方向不匹配，ELO/CTR 相关答不上"),
]

OFFER_FOR = dict(
    key="xhs",
    payload=dict(
        monthly_salary=46, months=15, signing_bonus="签字费 5 万（分两年发）", stock="字节跳动期权无；小红书有老股回购额度",
        welfare="六险一金 + 免费三餐 + 下午茶 + 租房补贴 1500/月", overtime="大小周已取消，日常 10-8-5，发版周偶尔周末",
        commute="徐汇家中 → 地铁 8 号线转 13 号线约 45 分钟", score_salary=4, score_platform=4, score_growth=4,
        score_worklife=3, score_commute=3, note="与字节三面流程冲突，需在 9 月中旬前给答复",
    ),
)

MANUAL_MATERIALS = {
    "byte": [("抖音电商 2025 发展与交易架构公开分享（摘要）",
              "抖音电商 GMV 连续三年高增长，交易链路强调「内容驱动」：直播、短视频挂车场景下流量脉冲明显，大促峰值 QPS 常态化。\n技术侧公开分享要点：交易核心链路已单元化部署，北上深多机房多活；库存与营销采用分层扣减；稳定性体系以全链路压测 + 自动化预案为核心。面试可结合自身支付网关多活与压测经验呼应。")],
    "xhs": [("小红书技术公开资料摘要（社区互动与架构）",
              "小红书社区日活过亿，点赞/评论等互动峰值明显（爆文效应）。\n公开技术分享：互动服务采用多级缓存 + 异步落库；评论体系引入多层嵌套与审核流；推荐与社区技术共用特征平台。 engineering 博客强调「业务 owner 意识」文化。")],
    "ali": [("阿里云容器服务 ACK 产品页要点",
              "ACK 是国内规模领先的 Kubernetes 托管服务，主打大规模集群（万级节点）、安全隔离与 Cost Optimization。\n服务网格 ASM 基于 Istio 托管控制面。近期重点：Serverless 容器 ACK Serverless、混合云集群注册。")],
    "meituan": [("美团到店业务与交易中台公开信息",
                 "美团到店事业群覆盖到店餐饮/到店综合，交易链路含优惠计算、核销、结算。\n技术博客（美团技术团队）多次分享：优惠计算的规则引擎化、订单系统的分库分表实践、全链路压测影子库方案。")],
}


def add_rounds_and_offer() -> None:
    for key, rt, at, result, note in ROUNDS:
        oid = OPP_IDS.get(key)
        if not oid:
            LOG(f"跳过轮次（无岗位）：{key}·{rt}")
            continue
        day = at.split("T")[0]
        exists = db_scalar(
            "SELECT COUNT(*) FROM interviewround WHERE opportunity_id = ? AND round_type = ? AND date(scheduled_at) = ?",
            oid, rt, day,
        )
        if exists:
            LOG(f"轮次已存在：{key}·{rt}·{day}")
            continue
        try_call("POST", "/rounds", f"轮次+{key}·{rt}", json={
            "opportunity_id": oid, "round_type": rt, "scheduled_at": at,
            "result": result, "note": note,
        })
    offer = OFFER_FOR
    if offer["key"] in OPP_IDS and not db_scalar(
        "SELECT COUNT(*) FROM offer WHERE opportunity_id = ?", OPP_IDS[offer["key"]]
    ):
        try_call("PUT", f"/offers/{OPP_IDS[offer['key']]}", "Offer+小红书", json=offer["payload"])


def add_manual_materials() -> None:
    for key, mats in MANUAL_MATERIALS.items():
        if key not in OPP_IDS:
            continue
        oid = OPP_IDS[key]
        for title, text in mats:
            if db_scalar("SELECT COUNT(*) FROM researchmaterial WHERE title = ? AND opportunity_id = ?", title, oid):
                LOG(f"材料已存在：{key}·{title[:12]}")
                continue
            try_call("POST", f"/opportunities/{oid}/materials", f"调研材料+{key}·{title[:12]}", json={
                "urls": [], "manual_text": text, "manual_title": title,
            })


# ---------------------------------------------------------------- 5. AI 生成：调研 / 匹配度 / 预测题单

NOTE_TYPES_MAIN = ["company", "team", "tech", "self_intro", "ask_back", "employee"]
OUTLINE_PLAN = {
    "byte": NOTE_TYPES_MAIN, "xhs": NOTE_TYPES_MAIN, "ali": NOTE_TYPES_MAIN, "meituan": NOTE_TYPES_MAIN,
    "pdd": ["company", "tech"], "tencent": ["company", "tech"],
    "kuaishou": ["company"], "mihoyo": ["company"],
}
PREDICT_PLAN = [("byte", "first"), ("byte", "second"), ("xhs", "second"), ("meituan", "first"), ("ali", "written")]


def ai_research() -> None:
    for key, types in OUTLINE_PLAN.items():
        oid = OPP_IDS.get(key)
        if not oid:
            continue
        for t in types:
            if db_scalar(
                "SELECT COUNT(*) FROM researchnote WHERE opportunity_id = ? AND note_type = ?", oid, t
            ):
                LOG(f"调研已存在：{key}·{t}")
                continue
            try_call("POST", f"/opportunities/{oid}/notes/{t}/outline", f"调研+{key}·{t}", json={"overwrite": False}, retries=1)


def ai_match() -> None:
    for key, oid in OPP_IDS.items():
        if db_scalar("SELECT COUNT(*) FROM matchreport WHERE opportunity_id = ?", oid):
            LOG(f"匹配度已存在：{key}")
            continue
        try_call("POST", f"/opportunities/{oid}/match-report", f"匹配度+{key}", json={"resume_id": RESUME_ID}, retries=1)


def ai_predictions() -> None:
    for key, rt in PREDICT_PLAN:
        oid = OPP_IDS.get(key)
        if not oid:
            continue
        if db_scalar("SELECT COUNT(*) FROM prediction WHERE opportunity_id = ?", oid):
            LOG(f"预测题单已存在：{key}")
            continue
        try_call("POST", f"/opportunities/{oid}/predictions", f"预测题单+{key}·{rt}", json={"round_type": rt}, retries=1)


# ---------------------------------------------------------------- main

RESUME_ID = None
OPP_IDS: dict[str, int] = {}

if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    try:
        if only in ("all", "resume"):
            RESUME_ID = upload_resume()
            resume_row = next(r for r in call("GET", "/resumes")["items"] if r["id"] == RESUME_ID)
            if resume_row.get("score") is None:
                call("POST", f"/resumes/{RESUME_ID}/review", retries=1)
                LOG("OK  简历 AI 体检")
            else:
                LOG("体检已存在，跳过")
            if not resume_row.get("questions_json"):
                call("POST", f"/resumes/{RESUME_ID}/predict-questions", json={"direction": ""}, retries=1)
                LOG("OK  简历预测题（含完整答案）")
            else:
                LOG("预测题已存在，跳过")
        if only in ("all", "opps"):
            RESUME_ID = RESUME_ID or call("GET", "/resumes")["items"][0]["id"]
            OPP_IDS.update(create_opportunities(RESUME_ID))
            LOG(f"岗位完成：{len(OPP_IDS)} 个 {OPP_IDS}")
            add_rounds_and_offer()
            add_manual_materials()
        if only in ("all", "bank"):
            RESUME_ID = RESUME_ID or call("GET", "/resumes")["items"][0]["id"]
            if not OPP_IDS:
                opps = call("GET", "/opportunities")
                for o in opps["items"]:
                    for spec in OPPORTUNITIES:
                        if o["company"] == spec["company"] and o["position"] == spec["position"]:
                            OPP_IDS[spec["key"]] = o["id"]
                            break
            n = enrich_bank(RESUME_ID, OPP_IDS)
            deposit_predicted_questions(RESUME_ID)
            LOG(f"题库完成：手写 {len(n)} 道 + 预测题入库")
        if only in ("all", "ai"):
            resumes = call("GET", "/resumes")
            RESUME_ID = RESUME_ID or resumes["items"][0]["id"]
            opps = call("GET", "/opportunities")
            for o in opps["items"]:
                for spec in OPPORTUNITIES:
                    if o["company"] == spec["company"] and o["position"] == spec["position"]:
                        OPP_IDS[spec["key"]] = o["id"]
                        break
            LOG(f"恢复上下文：resume={RESUME_ID} opps={OPP_IDS}")
            ai_match()
            ai_predictions()
            ai_research()
        LOG("全部完成 ✔")
    finally:
        drop_session_token(TOKEN)
        client.close()
