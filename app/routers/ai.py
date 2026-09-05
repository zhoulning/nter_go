"""AI / 抓取能力：从职位链接或 JD 文本中提取关键信息。

- 猎聘（liepin.com）：详情页 SSR，服务端直接抓取解析（无需 AI）。
- BOSS直聘（zhipin.com）：通过 CDP 直连用户自己已登录的浏览器提取，未连接时给出引导。
- 其他链接 / 粘贴文本：交给大模型（智谱 GLM，兼容 OpenAI / Anthropic 协议）。
"""
import json
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from html import unescape
from pydantic import BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user
from app.database import get_session
from app.kb import search_knowledge_base
from app.models import User
from app.routers.settings import get_ai_config, get_browser_config, get_kb_path

router = APIRouter()

FETCH_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

EXTRACT_PROMPT = """你是招聘信息解析助手。请从下面的职位信息中提取字段，只输出一个 JSON 对象，不要输出任何解释或其他内容。JSON 结构如下：
{
  "company": "公司名（不含城市/分号等后缀修饰）",
  "position": "岗位名称",
  "department": "部门/业务线，没有则填 null",
  "city": "工作城市，如 南京/北京，没有则填 null",
  "address": "工作地址：详细地址（含区/街道/大厦楼层等），没有则填 null",
  "salary_range": "薪资范围原文，没有则填 null",
  "jd_text": "工作描述：仅包含职位描述本身（工作职责、任职资格、技能要求等），保留原文条目编号与分段；不要包含公司介绍、工商信息、HR 信息、推荐职位等无关内容；无法识别则填 null"
}
所有字段值为字符串或 null。

职位信息来源：{source}
----- 开始 -----
{content}
----- 结束 -----"""


class ExtractRequest(BaseModel):
    url: Optional[str] = None
    text: Optional[str] = None
    active_tab: bool = False  # BOSS：读取专用浏览器当前打开的职位页（不导航、零自动化特征）


# ---------------------------------------------------------------- 通用工具

def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?s)<!--.*?-->", " ", html)
    html = re.sub(r"(?i)<(br|/p|/div|/li|/h[1-6]|/tr)[^>]*>", "\n", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def _fetch_url(url: str) -> str:
    """抓取网页原始 HTML。先走系统代理，连不上再直连。"""
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="链接格式不正确")
    headers = {"User-Agent": FETCH_UA, "Accept-Language": "zh-CN,zh;q=0.9"}
    resp = None
    last_exc: Exception | None = None
    for trust_env in (True, False):
        try:
            with httpx.Client(trust_env=trust_env, timeout=15, follow_redirects=True) as client:
                resp = client.get(url, headers=headers)
            break
        except httpx.HTTPError as e:
            last_exc = e
    if resp is None:
        raise HTTPException(
            status_code=422,
            detail=f"链接无法访问（{type(last_exc).__name__}: {last_exc}），请直接粘贴 JD 文本",
        )
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=422,
            detail=f"链接访问被拒绝（HTTP {resp.status_code}），该站点可能有反爬限制，请直接粘贴 JD 文本",
        )
    return resp.text


def _parse_json_loose(raw: str) -> dict:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no json object found")
    return json.loads(text[start : end + 1])


def _http_post_json(url: str, headers: dict, payload: dict) -> httpx.Response:
    """带代理回退的 POST：先跟随系统代理，连不上再直连重试；429 限流自动退避。"""
    import time

    last_exc: Exception | None = None
    for trust_env in (True, False):
        for attempt in range(3):
            try:
                with httpx.Client(trust_env=trust_env, timeout=300) as client:
                    resp = client.post(url, headers=headers, json=payload)
            except httpx.HTTPError as e:
                last_exc = e
                break  # 连接层失败 → 换直连
            if resp.status_code == 429 and attempt < 2:
                time.sleep(20 * (attempt + 1))
                continue
            return resp
    raise HTTPException(
        status_code=502,
        detail=f"无法连接 AI 接口（可能触发限流 429）：{type(last_exc).__name__}: {last_exc}",
    )


def _call_llm(
    base_url: str,
    model: str,
    api_key: str,
    prompt: str,
    max_tokens: int = 8192,
) -> str:
    """调用大模型。按 base_url 自动识别 OpenAI / Anthropic 协议。

    推理型模型（如 glm-5.3）可能把输出预算耗在思考块上导致正文为空，
    此时自动加倍 max_tokens 重试一次。
    """
    base = base_url.rstrip("/")

    def _build(max_t: int):
        if "anthropic" in base:
            url = base if base.endswith("/messages") else f"{base}/v1/messages"
            headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
            # thinking 型模型（glm-5.3 等）默认开启思考会拖慢且耗尽预算，明确关闭
            payload = {
                "model": model,
                "max_tokens": max_t,
                "temperature": 0.2,
                "thinking": {"type": "disabled"},
                "messages": [{"role": "user", "content": prompt}],
            }

            def parse(resp: httpx.Response) -> tuple[str, str | None]:
                data = resp.json()
                text = "".join(
                    c.get("text", "")
                    for c in data.get("content", [])
                    if c.get("type") == "text"
                )
                return text, data.get("stop_reason")
        else:
            url = f"{base}/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}"}
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": max_t,
            }

            def parse(resp: httpx.Response) -> tuple[str, str | None]:
                return resp.json()["choices"][0]["message"]["content"], None

        return url, headers, payload, parse

    current_max = max_tokens
    for attempt in range(2):  # 最多两次：正文为空时加倍重试
        url, headers, payload, parse = _build(current_max)
        resp = _http_post_json(url, headers, payload)
        if resp.status_code == 400 and "thinking" in payload:
            # 端点不支持 thinking 参数时去掉重试一次
            payload.pop("thinking")
            resp = _http_post_json(url, headers, payload)
        if resp.status_code >= 400:
            hint = {
                401: "API Key 无效或未授权",
                403: "无权限，Key 可能与该 base_url 不匹配",
                404: "端点或模型名可能不对",
                429: "触发限流，已自动等待重试仍失败，请稍等一两分钟再试",
            }.get(resp.status_code, "请检查 API Key / 模型名 / base_url")
            raise HTTPException(
                status_code=502,
                detail=f"AI 接口返回 HTTP {resp.status_code}（{hint}）：{resp.text[:200]}",
            )
        try:
            text, stop_reason = parse(resp)
        except Exception:
            raise HTTPException(
                status_code=502,
                detail=f"AI 返回内容无法解析：{resp.text[:200]}",
            )
        if text.strip():
            return text
        if attempt == 0:
            current_max = min(current_max * 4, 32768)

    raise HTTPException(
        status_code=502,
        detail="模型只输出了思考过程没有正文（推理模型输出预算不足），请重试或更换更快的模型",
    )


FIELD_KEYS = ("company", "position", "department", "city", "address", "salary_range", "jd_text")


def _llm_extract(content: str, source: str, cfg: dict) -> dict:
    """用大模型从文本中提取结构化字段。"""
    if not cfg["api_key"]:
        raise HTTPException(status_code=400, detail="尚未配置 AI API Key，请先到「设置」中填写")
    prompt = EXTRACT_PROMPT.replace("{source}", source).replace("{content}", content)
    raw = _call_llm(cfg["base_url"], cfg["model"], cfg["api_key"], prompt)
    try:
        fields = _parse_json_loose(raw)
    except ValueError:
        raise HTTPException(status_code=502, detail=f"AI 返回内容无法解析：{raw[:200]}")
    fields = {k: (str(v).strip() or None) if v else None for k, v in fields.items() if k in FIELD_KEYS}
    if not fields.get("company") and not fields.get("position"):
        raise HTTPException(
            status_code=422,
            detail="没能从内容中识别出公司/岗位（该链接可能被反爬拦截，抓到的不是职位内容），请直接粘贴 JD 文本",
        )
    return fields


# ---------------------------------------------------------------- 猎聘

def _extract_liepin(url: str) -> dict:
    """猎聘详情页 SSR，直接从 HTML 解析，无需 AI。"""
    html = _fetch_url(url)
    if "job-intro-container" not in html:
        if "验证" in html[:5000] or "登录" in html[:5000]:
            raise HTTPException(
                status_code=422,
                detail="猎聘页面要求登录/验证（可能未登录过期），请直接粘贴 JD 文本",
            )
        raise HTTPException(
            status_code=422,
            detail="该链接不是有效的猎聘职位详情页（可能已下架），请检查链接或直接粘贴 JD 文本",
        )

    fields = dict.fromkeys(FIELD_KEYS)

    title_m = re.search(r"<title>([^<]+)</title>", html)
    title = title_m.group(1).strip() if title_m else ""
    m = re.search(r"【([^】]+?)招聘】\s*-\s*(.+?)招聘信息", title)
    if m:
        head, fields["company"] = m.group(1).strip(), m.group(2).strip()
        # head 形如 "苏州 江苏省区总经理（地产背景）" 或 "北京-朝阳区 Java开发"
        parts = re.split(r"[ -]", head, maxsplit=1)
        if len(parts) == 2:
            fields["city"], fields["position"] = parts[0].strip(), parts[1].strip()
        else:
            fields["position"] = head

    for pat, key in (
        (r'class="salary"[^>]*>\s*([^<]{1,40})<', "salary_range"),
        (r'"salaryDesc"\s*:\s*"([^"]{1,40})"', "salary_range"),
        (r'job-pay[^>]*>\s*([^<\s][^<]{0,40})<', "salary_range"),
        (r'"city"\s*:\s*"([^"]{1,20})"', "city"),
        (r'job-address[^>]*>\s*([^<]{1,80})<', "address"),
        (r'"jobAddress"\s*:\s*"([^"]{1,80})"', "address"),
        (r'"jobDepartment"\s*:\s*"([^"]{1,40})"', "department"),
    ):
        if not fields[key]:
            sm = re.search(pat, html)
            if sm:
                fields[key] = sm.group(1).strip()

    m = re.search(r"job-intro-container(.*?)(?:</section>|job-detail)", html, re.S)
    if m:
        text = _strip_html(m.group(1))
        text = re.sub(r"^[^一-龥]+", "", text)  # 去掉开头残留的标签符号
        text = re.sub(r"^职位介绍\s*", "", text)
        fields["jd_text"] = text.strip() or None

    if not fields["jd_text"]:
        raise HTTPException(
            status_code=422,
            detail="该页面没有解析到工作描述（可能已下架），请直接粘贴 JD 文本",
        )
    return fields


# ---------------------------------------------------------------- BOSS直聘（CDP）

NOISE_MARKERS = ("看过该职位的人还看了", "精选职位", "更多职位", "页面更新时间", "BOSS 安全提示")


def _sync_pw():
    """优先 Patchright（反检测内核，移除 CDP 泄露信号），未安装则回退官方 Playwright。"""
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        from playwright.sync_api import sync_playwright
    return sync_playwright()


def _bypass_proxy_for_localhost():
    import os

    no_proxy = os.environ.get("NO_PROXY", os.environ.get("no_proxy", ""))
    for host in ("127.0.0.1", "localhost"):
        if host not in no_proxy:
            no_proxy = f"{no_proxy},{host}".lstrip(",")
    os.environ["NO_PROXY"] = no_proxy
    os.environ["no_proxy"] = no_proxy


SUPPORTED_JOB_SITES = ("zhipin.com", "zhaopin.com", "maimai.cn")


def _is_supported_site_url(u: str) -> bool:
    return any(s in u for s in SUPPORTED_JOB_SITES)


def _is_job_detail_url(u: str) -> bool:
    return (
        "job_detail" in u
        or "/job/" in u
        or "recruit_job_detail" in u
        or "jobId=" in u
    )


def _has_jd_marker(text: str) -> bool:
    return any(
        m in text for m in ("职位描述", "岗位职责", "任职要求", "任职资格", "工作职责", "工作描述")
    )


def _validate_zhipin_page(title: str, text: str, allow_redirect_hint: bool = False) -> None:
    if "安全验证" in title or "安全验证" in text[:800]:
        raise HTTPException(
            status_code=422,
            detail="BOSS 弹出了安全验证，请在专用浏览器中手动完成滑块验证后重试",
        )
    if not _has_jd_marker(text):
        if "登录" in text[:400] or "扫码" in text[:400]:
            raise HTTPException(
                status_code=422,
                detail="该浏览器尚未登录目标招聘网站：请在专用浏览器中登录后重试（登录态长期有效）",
            )
        if allow_redirect_hint:
            raise HTTPException(
                status_code=422,
                detail=(
                    "招聘网站把职位页重定向到了其他页面——通常表示该浏览器尚未登录。"
                    "请在专用浏览器右上角登录后重试"
                ),
            )
        raise HTTPException(
            status_code=422,
            detail="页面上没有找到职位描述（请确认打开的是职位详情页），请检查后重试",
        )


def _trim_zhipin_text(text: str) -> str:
    cut = len(text)
    for marker in NOISE_MARKERS:
        idx = text.find(marker)
        if idx > 200:
            cut = min(cut, idx)
    return text[:cut][:6000]


def _read_zhipin_tab(cdp_endpoint: str) -> dict:
    """被动读取专用浏览器中已打开的 BOSS 职位详情页：不导航、不注入，零自动化特征。"""
    _bypass_proxy_for_localhost()
    try:
        with _sync_pw() as p:
            try:
                browser = p.chromium.connect_over_cdp(cdp_endpoint, timeout=8000)
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"无法连接浏览器调试端口（{cdp_endpoint}）：{str(e)[:120]}。"
                        "请运行项目根目录的 start-boss-browser.bat 启动专用浏览器，或在设置中修改端口"
                    ),
                )
            try:
                target = None
                for ctx in browser.contexts:
                    for page in ctx.pages:
                        u = page.url
                        if _is_supported_site_url(u) and _is_job_detail_url(u):
                            target = page
                            break
                    if target:
                        break
                if target is None:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            "专用浏览器里没有打开的职位详情页：请先在专用浏览器中打开目标职位"
                            "（支持 BOSS直聘 / 猎聘 / 智联 / 脉脉），再回来点「智能提取」"
                        ),
                    )
                prev = ""
                text = ""
                for _ in range(8):
                    try:
                        text = target.evaluate(
                            "() => document.body ? document.body.innerText : ''"
                        ) or ""
                    except Exception:
                        text = ""
                    if text and text == prev:
                        break
                    prev = text
                    target.wait_for_timeout(700)
                try:
                    title = target.title()
                except Exception:
                    title = ""
            finally:
                browser.close()  # 仅断开 CDP 连接，不关闭浏览器、不关用户的标签页
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"浏览器读取失败：{type(e).__name__}: {str(e)[:150]}")
    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="该页面还没加载出内容，请在专用浏览器中等页面打开后再点「智能提取」",
        )
    return {"title": title, "text": text, "url": target.url}


def _extract_site_page(url: str, cdp_endpoint: str, require_jd: bool = True) -> dict:
    """通过 CDP 直连用户已登录的浏览器，返回页面标题与正文文本（结构化交给 LLM）。

    require_jd=False 时跳过「页面必须是职位详情」的校验（岗位情报等通用抓取场景使用）。
    """
    _bypass_proxy_for_localhost()

    try:
        with _sync_pw() as p:
            try:
                browser = p.chromium.connect_over_cdp(cdp_endpoint, timeout=8000)
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"无法连接浏览器调试端口（{cdp_endpoint}）：{str(e)[:120]}。"
                        "请运行项目根目录的 start-boss-browser.bat 启动专用浏览器，"
                        "或在设置中修改调试端口"
                    ),
                )
            try:
                ctx = browser.contexts[0] if browser.contexts else browser.new_context()
                page = ctx.new_page()
                try:
                    page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    # BOSS 加载后会做客户端跳转（登录/验证），等待 URL 与正文连续数秒稳定
                    prev_url = prev_text = ""
                    text = ""
                    stable = 0
                    for _ in range(25):
                        page.wait_for_timeout(1000)
                        try:
                            text = page.evaluate(
                                "() => document.body ? document.body.innerText : ''"
                            ) or ""
                        except Exception:
                            stable = 0
                            continue  # 正在导航，下一轮再读
                        if page.url == prev_url and text and text == prev_text and len(text) > 300:
                            stable += 1
                            if stable >= 2:
                                break
                        else:
                            stable = 0
                        prev_url, prev_text = page.url, text
                    try:
                        title = page.title()
                    except Exception:
                        title = ""
                    final_url = page.url
                    if final_url in ("about:blank", "") or not text.strip():
                        site = "BOSS 直聘" if "zhipin.com" in url else "目标网站"
                        hint = (
                            "请先在专用浏览器里像真人一样打开一次 zhipin.com 或任意职位页"
                            "（如弹出滑块请完成），几分钟后回到本应用重试"
                            if "zhipin.com" in url
                            else "请在专用浏览器里手动打开一次该站点（如弹出登录/滑块请完成）后重试"
                        )
                        raise HTTPException(
                            status_code=422,
                            detail=f"{site}拦截了这次访问（页面被置空）：{hint}",
                        )
                    if len(text) < 300 and "/web/user/" in final_url:
                        raise HTTPException(
                            status_code=422,
                            detail="该浏览器尚未登录 BOSS 直聘：请在弹出的专用浏览器中登录后重试（登录态长期有效）",
                        )
                    if (
                        require_jd
                        and not _has_jd_marker(text)
                        and not _is_job_detail_url(final_url)
                    ):
                        # 未登录时 BOSS 会把职位详情重定向到分类目录页
                        raise HTTPException(
                            status_code=422,
                            detail=(
                                "BOSS 把职位页重定向到了其他页面——通常表示该浏览器尚未登录。"
                                "请在专用浏览器右上角登录 BOSS 直聘（可手机扫码）后重试"
                            ),
                        )
                finally:
                    page.close()
            finally:
                browser.close()  # 仅断开 CDP 连接，不会关闭用户的浏览器
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"浏览器提取失败：{type(e).__name__}: {str(e)[:150]}")

    if require_jd:
        # 职位提取场景：校验页面确实是职位详情，并裁掉 BOSS 页面的噪音尾巴
        _validate_zhipin_page(title, text, allow_redirect_hint=True)
        return {"title": title, "text": _trim_zhipin_text(text)}
    # 通用抓取（岗位情报等）：不做职位页校验与 BOSS 噪音裁剪
    return {"title": title, "text": text}


# ---------------------------------------------------------------- 路由

@router.post("/ai/extract-job")
def extract_job(
    body: ExtractRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    cfg = get_ai_config(session)

    # 被动模式：读取专用浏览器当前打开的 BOSS 职位页（推荐，零自动化特征）
    if body.active_tab:
        cdp = get_browser_config(session)["cdp_endpoint"]
        page_data = _read_zhipin_tab(cdp)
        _validate_zhipin_page(page_data["title"], page_data["text"])
        if not cfg["api_key"]:
            raise HTTPException(
                status_code=400,
                detail="BOSS 页面的结构化提取需要 AI 参与，请先在设置中配置 AI，或直接粘贴 JD 文本",
            )
        content = "页面标题：" + page_data["title"] + chr(10) + page_data["text"]
        fields = _llm_extract(content, "BOSS直聘当前页面", cfg)
        tab_url = page_data.get("url", "")
        fields["channel"] = ("BOSS直聘" if "zhipin.com" in tab_url
                             else "猎聘" if "liepin.com" in tab_url
                             else "智联招聘" if "zhaopin.com" in tab_url
                             else "脉脉" if "maimai.cn" in tab_url
                             else None)
        return {"fields": fields, "source": "BOSS直聘当前页面", "llm": True}

    if body.url:
        host = urlparse(body.url).netloc.lower()

        # 猎聘：SSR 直抓直解析，无需 AI
        if "liepin.com" in host:
            fields = _extract_liepin(body.url)
            fields["channel"] = "猎聘"
            return {"fields": fields, "source": "猎聘网页", "llm": False}

        # BOSS / 智联 / 脉脉：网页均为前端渲染，通过专用浏览器打开后读全文，结构化交给 AI
        if _is_supported_site_url(host):
            cdp = get_browser_config(session)["cdp_endpoint"]
            if "zhipin.com" in host:
                # 剥掉追踪参数（sessionId/lid 等校验失败时 BOSS 会把页面置成 about:blank），只保留路径
                parts = urlparse(body.url)
                open_url = f"{parts.scheme}://{parts.netloc}{parts.path}"
            else:
                open_url = body.url
            site_label = ("BOSS直聘网页" if "zhipin.com" in host
                          else "智联网页" if "zhaopin.com" in host
                          else "脉脉网页" if "maimai.cn" in host
                          else "网页")
            channel = ("BOSS直聘" if "zhipin.com" in host
                       else "智联招聘" if "zhaopin.com" in host
                       else "脉脉" if "maimai.cn" in host
                       else None)
            page_data = _extract_site_page(open_url, cdp)
            if not cfg["api_key"]:
                raise HTTPException(
                    status_code=400,
                    detail="BOSS 链接的结构化提取需要 AI 参与，请先在设置中配置 AI，或直接粘贴 JD 文本",
                )
            content = f"页面标题：{page_data['title']}\n{page_data['text']}"
            fields = _llm_extract(content, site_label, cfg)
            fields["channel"] = channel
            return {"fields": fields, "source": site_label, "llm": True}

        # 其他站点：抓 HTML 转文本后走 LLM
        if len(html := _fetch_url(body.url)) < 30:
            raise HTTPException(status_code=422, detail="抓取到的内容太少，请直接粘贴 JD 文本")
        fields = _llm_extract(_strip_html(html)[:8000], "网页", cfg)
        return {"fields": fields, "source": "网页", "llm": True}

    if body.text:
        if len(body.text.strip()) < 30:
            raise HTTPException(status_code=422, detail="文本内容太少，请粘贴完整的职位描述")
        fields = _llm_extract(body.text.strip()[:8000], "文本", cfg)
        return {"fields": fields, "source": "文本", "llm": True}

    raise HTTPException(status_code=400, detail="请提供职位链接或 JD 文本")


# ---- 统一参考答案引擎 ----
# 全站所有面试题答案（题库口述版 / 题目预测题单 / 复盘示范答案）的唯一生成路径：
# 上下文固定为「关联或默认简历 + 目标岗位 JD + Obsidian 知识库检索」，
# 格式统一为下方口述版标准。新增答案场景一律复用本引擎，禁止再另写答案 prompt。

ANSWER_STANDARD = """1. 第一人称、自然口语，像面试现场说出来的话，不要书面腔；
2. 先用一句话给出核心结论，再分 2-4 个要点展开，要点用「1. 2. 3.」编号，每个要点两三句话，结论句与每个编号要点独占一行；
3. 关键词用 **加粗** 标出，方便复习时快速抓重点；
4. 总长 250-400 字，不要寒暄、不要开场白和总结陈词。"""

ANSWER_EXPERIENCE_RULES = """1. 只要题目与项目 / 实习 / 工作经历相关，必须以「我的简历」中的真实项目作答：项目背景、技术选型、量化数据都要与简历一致——面试官手里就是这份简历，答案不能与简历矛盾，更不能凭空捏造简历里没有的项目；
2. 项目相关的回答按 STAR 原则展开（情境-任务-行动-结果），结果要有量化数字：简历里已有的直接用，没有的才可合理假设；
3. 与项目无关的纯知识题直接讲透知识点，不要生硬套项目。"""


def _load_answer_resume(session: Session, user: User, resume_id: Optional[int]):
    """题目单独关联的简历优先，否则默认简历。"""
    from app.models import Resume

    resume = None
    if resume_id is not None:
        resume = session.get(Resume, resume_id)
        if resume is not None and resume.user_id != user.id:
            resume = None
    if resume is None:
        resume = session.exec(
            select(Resume).where(
                Resume.user_id == user.id,
                Resume.is_default == True,  # noqa: E712
            )
        ).first()
    return resume


def collect_answer_context(
    session: Session,
    user: User,
    *,
    resume_id: Optional[int] = None,
    opportunity_id: Optional[int] = None,
    kb_query: str = "",
) -> dict:
    """统一收集答案上下文：简历 + 岗位 JD + 知识库片段，所有答案场景共用。"""
    from app.models import Opportunity

    resume = _load_answer_resume(session, user, resume_id)
    resume_text = ""
    if resume is not None:
        body_text = (resume.structured or resume.text or "").strip()
        if body_text:
            resume_text = f"《{resume.name}》\n{body_text[:3500]}"
    if not resume_text:
        resume_text = "（未设置默认简历）没有简历资料时，不要虚构具体项目细节，按通用最佳实践回答。"

    jd_text = ""
    if opportunity_id is not None:
        opp = session.get(Opportunity, opportunity_id)
        if opp is not None and opp.user_id == user.id:
            jd_text = (opp.jd_text or "").strip()[:3000]
    if not jd_text:
        jd_text = "（未关联目标岗位，忽略本节）"

    try:
        kb_hits = search_knowledge_base(session, kb_query) if kb_query.strip() else []
    except Exception:
        kb_hits = []
    if kb_hits:
        kb_text = "\n".join(f"[{i}] 来源 {h['source']}\n{h['text']}" for i, h in enumerate(kb_hits, 1))
        kb_text = kb_text[:2400]
    else:
        kb_text = "（未配置知识库或未检索到相关笔记，忽略本节）"
    return {"resume_text": resume_text, "jd_text": jd_text, "kb_text": kb_text}


def build_answer_prompt(*, content: str, dimension: str, companies: list[str], ctx: dict) -> str:
    """唯一的答案 prompt：标准来自共享常量，上下文来自 collect_answer_context。"""
    return f"""你是资深后端面试教练。针对下面这道真实面试题，直接给出面试现场的口述版参考答案。

格式要求（严格遵守）：
{ANSWER_STANDARD}

经历要求（严格遵守）：
{ANSWER_EXPERIENCE_RULES}

若下方提供了「知识库笔记」，优先采用其中与题目相关的要点、结论和细节，自然融入答案；与题目无关的笔记直接忽略，不要提及。

只输出答案正文（Markdown 格式），不要 JSON 包装，不要任何解释或前后缀。

考察维度：{dimension or "未指定"}
被问到的公司：{"、".join(companies) if companies else "未提供"}
题目：{content[:2000]}

目标岗位 JD（贴合岗位要求的技术栈与业务场景作答）：
{ctx["jd_text"]}

我的简历（项目经历以此为准）：
{ctx["resume_text"]}

知识库笔记（来自我的 Obsidian 知识库，按题目相关度检索）：
{ctx["kb_text"]}"""


def generate_reference_answer(
    session: Session,
    user: User,
    *,
    content: str,
    dimension: str = "",
    companies: Optional[list[str]] = None,
    opportunity_id: Optional[int] = None,
    resume_id: Optional[int] = None,
) -> str:
    """生成一道面试题的口述版参考答案（全站唯一答案生成入口，线程安全：只用传入的 session）。"""
    cfg = get_ai_config(session)
    if not cfg["api_key"]:
        raise HTTPException(status_code=400, detail="尚未配置 AI API Key，请先到「设置」中填写")
    content = (content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="题干为空，无法生成答案")
    ctx = collect_answer_context(
        session,
        user,
        resume_id=resume_id,
        opportunity_id=opportunity_id,
        kb_query=f"{content} {dimension}",
    )
    prompt = build_answer_prompt(
        content=content, dimension=dimension, companies=companies or [], ctx=ctx
    )
    raw = _call_llm(cfg["base_url"], cfg["model"], cfg["api_key"], prompt)
    answer = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", raw.strip()).strip()
    if not answer:
        raise HTTPException(status_code=502, detail="AI 没有生成有效答案，请重试")
    return answer


class AnswerGenRequest(BaseModel):
    question_id: Optional[int] = None        # 已入库题目：生成后直接落库
    content: Optional[str] = None            # 未入库时直接给题干
    dimension: Optional[str] = None
    companies: list[str] = []
    opportunity_id: Optional[int] = None     # 目标岗位（注入 JD 上下文）；已入库题目可从来源自动推导
    resume_id: Optional[int] = None          # 关联简历（注入简历上下文）；未入库题目直接指定


@router.post("/ai/generate-answer")
def generate_answer(
    body: AnswerGenRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    from app.models import Opportunity, Question, QuestionSource

    question = None
    opportunity_id = body.opportunity_id
    content = (body.content or "").strip()
    dimension = (body.dimension or "").strip()
    companies = [c for c in body.companies if c.strip()]
    resume_id = body.resume_id

    if body.question_id is not None:
        question = session.get(Question, body.question_id)
        if question is None or question.user_id != user.id:
            raise HTTPException(status_code=404, detail="题目不存在")
        content = question.content
        dimension = question.dimension
        resume_id = question.resume_id
        # 来源公司 / 岗位 JD 自动从关联里取
        src_opps = session.exec(
            select(QuestionSource.opportunity_id).where(
                QuestionSource.question_id == question.id
            )
        ).all()
        companies = []
        for oid in src_opps:
            opp = session.get(Opportunity, oid)
            if opp and opp.user_id == user.id:
                companies.append(opp.company)
                if opportunity_id is None:
                    opportunity_id = opp.id

    if opportunity_id is not None:
        opp = session.get(Opportunity, opportunity_id)
        if opp is None or opp.user_id != user.id:
            opportunity_id = None

    if not content:
        raise HTTPException(status_code=400, detail="请先填写题干再生成答案")

    answer = generate_reference_answer(
        session,
        user,
        content=content,
        dimension=dimension,
        companies=companies,
        opportunity_id=opportunity_id,
        resume_id=resume_id,
    )

    if question is not None:
        question.answer_spoken = answer
        question.updated_at = datetime.now()
        session.add(question)
        session.commit()

    return {"answer_spoken": answer, "saved": question is not None}


# ---- 题目录入辅助：题干润色 + 考察维度选择 ----

QUESTION_ASSIST_PROMPT = """你是面试题库整理助手。下面是一段面试官原话或随手记录的题目内容，可能口语化、有错别字或混入无关上下文。

{task_desc}

候选考察维度（只能从中选一个，不许自造）：
{dimensions}

只输出一个 JSON 对象，不要任何解释或前后缀：{json_shape}

----- 题目内容开始 -----
{content}
----- 题目内容结束 -----"""

POLISH_TASK_DESC = """请完成两件事：
1. 把题目内容整理成一道清晰、简洁、完整的面试题题干：保留原意与考察点，去掉口语废词、错别字和与题目无关的铺垫，不要添加原内容没有的信息，长度不超过 120 字；
2. 从候选考察维度中选出这道题最核心的一个维度。"""

DIMENSION_TASK_DESC = "请从候选考察维度中选出这道题最核心的一个维度，不要改写题干。"


class QuestionAssistRequest(BaseModel):
    content: str
    dimensions: list[str] = []
    task: str = "polish"  # polish=润色题干并选维度；dimension=仅选维度


@router.post("/ai/question-assist")
def question_assist(
    body: QuestionAssistRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """题目录入 AI 辅助：润色题干、按题目内容选出考察维度（维度强制落在候选列表内）。"""
    from app.routers.questions import DIMENSION_PRESETS

    cfg = get_ai_config(session)
    if not cfg["api_key"]:
        raise HTTPException(status_code=400, detail="尚未配置 AI API Key，请先到「设置」中填写")
    content = (body.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="题干为空，无法使用 AI 辅助")
    dims = [d.strip() for d in body.dimensions if d.strip()] or list(DIMENSION_PRESETS)
    dimension_only = body.task == "dimension"
    prompt = (
        QUESTION_ASSIST_PROMPT
        .replace("{task_desc}", DIMENSION_TASK_DESC if dimension_only else POLISH_TASK_DESC)
        .replace("{dimensions}", "、".join(dims))
        .replace(
            "{json_shape}",
            '{"dimension": "维度"}'
            if dimension_only
            else '{"content": "整理后的题干", "dimension": "维度"}',
        )
        .replace("{content}", content[:2000])
    )
    raw = _call_llm(cfg["base_url"], cfg["model"], cfg["api_key"], prompt, max_tokens=2048)
    try:
        data = _parse_json_loose(raw)
    except ValueError:
        raise HTTPException(status_code=502, detail=f"AI 返回内容无法解析：{raw[:200]}")
    dimension = str(data.get("dimension") or "").strip()
    if dimension not in dims:
        dimension = "其他" if "其他" in dims else (dims[0] if dims else "其他")
    result: dict = {"dimension": dimension}
    if not dimension_only:
        polished = str(data.get("content") or "").strip()
        if not polished:
            raise HTTPException(status_code=502, detail="AI 没有返回有效题干，请重试")
        result["content"] = polished
    return result
