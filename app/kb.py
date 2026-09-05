"""Obsidian 知识库检索：扫描用户在设置里配置的 vault 文件夹，
按与题目的关键词相关度取出若干笔记片段，供 AI 生成答案时注入 prompt。

**硬性规定：本模块对知识库只读——只允许检索与解析，严禁写入、修改、移动或删除知识库中的任何文件。**

这是个人 Markdown 笔记库的轻量关键词检索（非向量 RAG）：
- 跳过 .obsidian / .trash 等配置目录与隐藏文件；
- 按标题 + Markdown 小节切分，笔记标题、章节路径参与相关度计算；
- [[双链]] / ![[嵌入]] 转成普通文本；
- 解析结果按文件 mtime/size 缓存，PDF 不会反复重解析。
"""
from __future__ import annotations

import re
from pathlib import Path

from sqlmodel import Session

from app.routers.settings import get_kb_path

SKIP_DIRS = {".obsidian", ".trash", ".smart-env", ".git"}
SUPPORTED_EXTS = {".md", ".markdown", ".txt", ".pdf", ".docx"}
MAX_FILE_BYTES = 2 * 1024 * 1024   # 单文件超过 2MB 跳过，防超大文件拖慢
MAX_FILES = 800
CHUNK_SIZE = 600                   # 小节内合并段落的目标长度
PIECE_LIMIT = 600                  # 单个片段注入 prompt 时的最大长度
TOTAL_LIMIT = 2400                 # 全部片段注入 prompt 的总长度上限
TOP_K = 4                          # 最多取的相关片段数

# 绝对路径 -> (mtime, size, chunks)；chunk = (检索文本, 注入文本)
_CACHE: dict[str, tuple[float, int, list[tuple[str, str]]]] = {}


def _extract_text(path: Path) -> str | None:
    """按扩展名抽取纯文本；.doc（老格式）等不支持的返回 None。"""
    ext = path.suffix.lower()
    try:
        if ext in (".md", ".markdown", ".txt"):
            return path.read_text("utf-8", errors="ignore")
        if ext == ".pdf":
            from app.routers.resumes import _extract_pdf_text

            return _extract_pdf_text(path)
        if ext == ".docx":
            import docx  # python-docx

            document = docx.Document(str(path))
            text = "\n".join(p.text for p in document.paragraphs if p.text.strip())
            return text.strip() or None
    except Exception:
        return None
    return None


def _clean_markdown(text: str) -> str:
    """Obsidian 语法转普通文本：去 frontmatter、双链转纯文字、去嵌入附件。"""
    text = re.sub(r"\A---\s*\n.*?\n---\s*\n?", "", text, flags=re.S)  # frontmatter
    text = re.sub(r"!\[\[[^\]]*\]\]", " ", text)                      # ![[嵌入]]
    text = re.sub(r"\[\[([^\]|]*)\|([^\]]*)\]\]", r"\2", text)        # [[笔记|别名]]
    text = re.sub(r"\[\[([^\]]*)\]\]", r"\1", text)                   # [[笔记]]
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)              # [文字](链接)
    return text


def _split_sections(text: str, title: str) -> list[tuple[str, str]]:
    """按 Markdown 标题切小节，返回 [(检索文本, 注入文本)]。

    检索文本 = 标题 + 章节路径 + 正文（标题命中也计入相关度）；
    注入文本 = 章节路径 + 正文（给 LLM 看的上下文）。
    无标题的普通笔记整篇作为一节。
    """
    lines = text.split("\n")
    sections: list[tuple[str, list[str]]] = []  # (heading_trail, body_lines)
    trail: list[str] = []
    cur: list[str] = []
    for line in lines:
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if m:
            if any(s.strip() for s in cur):
                sections.append((list(trail), cur))
            level = len(m.group(1))
            trail = trail[: level - 1]
            trail.append(m.group(2).strip())
            cur = []
        else:
            cur.append(line)
    if any(s.strip() for s in cur):
        sections.append((list(trail), cur))

    result: list[tuple[str, str]] = []
    for heads, body in sections:
        body_text = "\n".join(body).strip()
        if not body_text:
            continue
        heading = " › ".join(heads) if heads else ""
        inject = f"{heading}\n{body_text}" if heading else body_text
        search_text = f"{title} {heading} {body_text}"
        result.append((search_text, inject))
    return result


def _split_long(search_text: str, inject: str) -> list[tuple[str, str]]:
    """单节超过约 1.6 倍 CHUNK_SIZE 时按空行二次切。"""
    if len(inject) <= int(CHUNK_SIZE * 1.6):
        return [(search_text, inject)]
    out: list[tuple[str, str]] = []
    buf = ""
    for para in re.split(r"\n\s*\n", inject):
        para = para.strip()
        if not para:
            continue
        if buf and len(buf) + len(para) + 1 > CHUNK_SIZE:
            out.append((f"{search_text[:200]} {buf}", buf))
            buf = para
        else:
            buf = f"{buf}\n{para}" if buf else para
    if buf:
        out.append((f"{search_text[:200]} {buf}", buf))
    return out


def _chunk_note(text: str, title: str) -> list[tuple[str, str]]:
    cleaned = _clean_markdown(text)
    sections = _split_sections(cleaned, title) or [(f"{title}", cleaned)]
    chunks: list[tuple[str, str]] = []
    for search_text, inject in sections:
        chunks.extend(_split_long(search_text, inject))
    return chunks


def _query_terms(query: str) -> set[str]:
    """提取检索词：英文/数字整词 + 中文二字组（bigram），个人笔记库够用。"""
    terms = {w.lower() for w in re.findall(r"[A-Za-z0-9_]{2,}", query)}
    for seg in re.findall(r"[\u4e00-\u9fff]+", query):
        if len(seg) == 1:
            terms.add(seg)
            continue
        terms.update(seg[i : i + 2] for i in range(len(seg) - 1))
    return terms


def search_knowledge_base(session: Session, query: str, top_k: int = TOP_K) -> list[dict]:
    """检索 Obsidian 知识库，返回 [{source, text}]；未配置/目录无效/无相关内容返回空。"""
    root = get_kb_path(session)
    if not root:
        return []
    base = Path(root)
    if not base.is_dir():
        return []
    terms = _query_terms(query)
    if not terms:
        return []

    try:
        files = [
            f
            for f in base.rglob("*")
            if f.is_file()
            and f.suffix.lower() in SUPPORTED_EXTS
            and f.stat().st_size <= MAX_FILE_BYTES
            and not (set(f.parts) & SKIP_DIRS or f.name.startswith("."))
        ][:MAX_FILES]
    except OSError:
        return []

    scored: list[tuple[int, str, str]] = []
    for f in files:
        try:
            stat = f.stat()
        except OSError:
            continue
        key = str(f.resolve())
        cached = _CACHE.get(key)
        if cached and cached[0] == stat.st_mtime and cached[1] == stat.st_size:
            chunks = cached[2]
        else:
            text = _extract_text(f)
            chunks = _chunk_note(text, f.stem) if text else []
            _CACHE[key] = (stat.st_mtime, stat.st_size, chunks)
        for search_text, inject in chunks:
            score = sum(1 for t in terms if t in search_text)
            if score >= 2:
                rel = f.relative_to(base)
                scored.append((score, f"{rel}", inject))

    scored.sort(key=lambda x: x[0], reverse=True)
    results: list[dict] = []
    used = 0
    for _score, source, inject in scored:
        if len(results) >= top_k or used >= TOTAL_LIMIT:
            break
        piece = inject[:PIECE_LIMIT]
        results.append({"source": source, "text": piece})
        used += len(piece)
    return results
