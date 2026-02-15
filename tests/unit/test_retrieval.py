from app.services.embeddings import MockEmbeddingProvider
from app.services.retrieval import rank_profile_chunks


def test_rank_profile_chunks_returns_top_k_sorted():
    provider = MockEmbeddingProvider(dim=64)
    texts = [
        "Built FastAPI services and PostgreSQL APIs",
        "Designed frontend UI components",
        "Implemented Redis and Celery background workers",
    ]
    vectors = provider.embed_texts(texts)
    chunks = [
        {
            "chunk_key": f"chunk_{idx}",
            "text": text,
            "source_field": f"experience[{idx}]",
            "metadata": {},
            "vector": vector,
        }
        for idx, (text, vector) in enumerate(zip(texts, vectors))
    ]

    ranked = rank_profile_chunks(
        job_text="Need backend engineer with FastAPI and PostgreSQL",
        chunks=chunks,
        embedding_provider=provider,
        top_k=2,
    )

    assert len(ranked) == 2
    assert ranked[0]["score"] >= ranked[1]["score"]
    assert ranked[0]["chunk_key"] in {"chunk_0", "chunk_2"}
