import httpx

from family_ai_api.config import Settings


class EmbeddingError(Exception):
    pass


async def embed_texts(
    texts: list[str],
    settings: Settings,
    batch_size: int = 16,
) -> list[list[float]]:
    if not texts:
        return []

    url = f"{settings.ollama_base_url.rstrip('/')}/api/embed"
    results: list[list[float]] = []

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.request_timeout_seconds),
            trust_env=False,
        ) as client:
            for offset in range(0, len(texts), batch_size):
                batch = texts[offset : offset + batch_size]
                response = await client.post(
                    url,
                    json={"model": settings.embedding_model, "input": batch},
                )
                if response.status_code >= 400:
                    raise EmbeddingError(f"embedding request failed: {response.status_code}")
                payload = response.json()
                embeddings = payload.get("embeddings")
                if not isinstance(embeddings, list) or len(embeddings) != len(batch):
                    raise EmbeddingError("invalid embedding response")
                results.extend(embeddings)
    except httpx.HTTPError as exc:
        raise EmbeddingError("embedding service unavailable") from exc
    except ValueError as exc:
        raise EmbeddingError("invalid embedding response") from exc

    return results


async def embed_query(text: str, settings: Settings) -> list[float]:
    embeddings = await embed_texts([text], settings)
    return embeddings[0]
