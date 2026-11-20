"""Project-scoped web research, vector indexing, and retrieval helpers."""
import asyncio
import logging
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

import memory
from config import TAVILY_API_KEY
from database.initialization import SessionLocal
from database.models import ResearchChunk

log = logging.getLogger("aiagent.research")
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


def _search_sync(query: str) -> list[dict]:
    """Search the live web through Tavily. Its SDK also supports rate-limited keyless mode."""
    from tavily import TavilyClient

    client = TavilyClient(api_key=TAVILY_API_KEY) if TAVILY_API_KEY else TavilyClient()
    response = client.search(
        query=query[:380],
        search_depth="basic",
        topic="general",
        max_results=5,
        include_answer=False,
    )
    results = []
    for item in response.get("results", []):
        url = (item.get("url") or "").strip()
        content = (item.get("content") or "").strip()
        if not url.startswith("https://") or not content:
            continue
        parsed = urlparse(url)
        if not parsed.hostname:
            continue
        results.append({
            "url": url,
            "title": (item.get("title") or parsed.hostname).strip()[:300],
            "domain": parsed.hostname.lower(),
            "content": content[:2600],
            "score": float(item.get("score") or 0.0),
        })
    return results


async def search_sources(query: str) -> list[dict]:
    try:
        return await asyncio.to_thread(_search_sync, query)
    except Exception as exc:
        log.warning("web search unavailable for %r: %s", query[:100], exc)
        return []


def _embed_sync(texts: list[str]) -> list[list[float]]:
    from fastembed import TextEmbedding

    model = TextEmbedding(EMBEDDING_MODEL)
    try:
        vectors = [vector.tolist() for vector in model.embed(texts)]
        memory.report("research embedder loaded")
        return vectors
    finally:
        del model
        memory.free()


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    async with memory.heavy:
        return await asyncio.to_thread(_embed_sync, texts)


def _split_into_chunks(text: str, size: int = 1100, overlap: int = 160) -> list[str]:
    """Split search snippets into short overlapping passages without breaking words."""
    clean = " ".join(text.split())
    chunks = []
    start = 0
    while start < len(clean):
        end = min(start + size, len(clean))
        if end < len(clean):
            boundary = clean.rfind(" ", start + size // 2, end)
            if boundary > start:
                end = boundary
        chunk = clean[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(clean):
            break
        start = max(end - overlap, start + 1)
    return chunks


async def index_sources(state_id, sources: list[dict]) -> int:
    """Chunk, embed, and index source passages for one project."""
    unique = {}
    for source in sources:
        url = source.get("url")
        content = source.get("content", "").strip()
        if url and content:
            unique[url] = source
    if not unique:
        return 0

    passages = []
    for source in unique.values():
        for index, chunk in enumerate(_split_into_chunks(source["content"])):
            passages.append((source, index, chunk))

    texts = [f"{source['title']}\n{chunk}" for source, _, chunk in passages]
    vectors = await embed_texts(texts)
    values = [
        {
            "state_id": state_id,
            "source_url": source["url"],
            "source_title": source["title"],
            "source_domain": source.get("domain"),
            "chunk_index": chunk_index,
            "content": chunk,
            "search_score": source.get("score"),
            "embedding": vector,
        }
        for (source, chunk_index, chunk), vector in zip(passages, vectors)
    ]
    async with SessionLocal() as session:
        statement = insert(ResearchChunk).values(values).on_conflict_do_nothing(
            index_elements=["state_id", "source_url", "chunk_index"]
        )
        await session.execute(statement)
        await session.commit()

    return await research_count(state_id)


async def retrieve_sources(state_id, query: str, limit: int = 8) -> list[dict]:
    """Semantic retrieval over this project's research snippets."""
    vector = (await embed_texts([query]))[0]
    distance = ResearchChunk.embedding.cosine_distance(vector).label("distance")
    statement = (
        select(ResearchChunk, distance)
        .where(ResearchChunk.state_id == state_id)
        .order_by(distance)
        .limit(limit)
    )
    async with SessionLocal() as session:
        rows = (await session.execute(statement)).all()

    grouped = {}
    for chunk, score in rows:
        distance_value = float(score) if score is not None else 1.0
        similarity = max(0.0, min(1.0, 1.0 - distance_value))
        source = grouped.setdefault(chunk.source_url, {
            "title": chunk.source_title,
            "url": chunk.source_url,
            "domain": chunk.source_domain,
            "excerpt": "",
            "similarity": similarity,
        })
        if chunk.content not in source["excerpt"]:
            source["excerpt"] = (source["excerpt"] + "\n\n" + chunk.content).strip()
        source["similarity"] = max(source["similarity"], similarity)
    return sorted(grouped.values(), key=lambda item: item["similarity"], reverse=True)


async def research_count(state_id) -> int:
    from sqlalchemy import func

    async with SessionLocal() as session:
        return int(await session.scalar(
            select(func.count()).select_from(ResearchChunk).where(ResearchChunk.state_id == state_id)
        ) or 0)
