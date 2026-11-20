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


async def index_sources(state_id, sources: list[dict]) -> int:
    """Embed and upsert unique source excerpts for one project."""
    unique = {}
    for source in sources:
        url = source.get("url")
        text = source.get("content", "").strip()
        if url and text:
            unique[url] = source
    items = list(unique.values())
    if not items:
        return 0

    texts = [f"{item['title']}\n{item['content']}" for item in items]
    vectors = await embed_texts(texts)
    values = [
        {
            "state_id": state_id,
            "source_url": item["url"],
            "source_title": item["title"],
            "source_domain": item.get("domain"),
            "chunk_index": 0,
            "content": item["content"],
            "search_score": item.get("score"),
            "embedding": vector,
        }
        for item, vector in zip(items, vectors)
    ]
    async with SessionLocal() as session:
        statement = insert(ResearchChunk).values(values).on_conflict_do_nothing(
            index_elements=["state_id", "source_url", "chunk_index"]
        )
        result = await session.execute(statement)
        await session.commit()
        return result.rowcount or len(values)


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

    results = []
    for chunk, score in rows:
        distance_value = float(score) if score is not None else 1.0
        results.append({
            "title": chunk.source_title,
            "url": chunk.source_url,
            "domain": chunk.source_domain,
            "excerpt": chunk.content,
            "similarity": max(0.0, min(1.0, 1.0 - distance_value)),
        })
    return results


async def research_count(state_id) -> int:
    from sqlalchemy import func

    async with SessionLocal() as session:
        return int(await session.scalar(
            select(func.count()).select_from(ResearchChunk).where(ResearchChunk.state_id == state_id)
        ) or 0)
