# ASSUMPTIONS

## Defaults Chosen
- MVP is single-user but schema/API include `user_id` for future multi-user support.
- If a PDF exists in `resume/`, seed uses deterministic PDF parsing to populate profile sections and writes `data/user_profile.generated.yaml`.
- Embeddings are pluggable; default test path uses deterministic mock vectors, and local runtime can use free BGE (`BAAI/bge-small-en-v1.5`) projected to dimension 256.
- LLM generation defaults to mock provider for reproducibility.
- Retrieval uses in-house embeddings + pgvector storage (no external RAG framework).
- MVP emits `.pdf` artifacts via deterministic text-rendered export; production-grade layout conversion is deferred.
- `SUBMITTED` status is manual-only; no auto-submission path exists.

## Environment Assumptions
- Docker Desktop with WSL integration is available for compose-based demo.
- Node.js/npm are available to run dashboard locally or in container.
- Postgres container supports pgvector extension image.

## Compliance Assumptions
- RSS and manual imports represent allowed sources with compliant automation permissions.
- No source with forbidden automation will be ingested unless `automation_allowed=false` override is intentionally set (and then blocked).

## Open Risks and Deferrals
- Basic auth/session approach is for MVP only; production-grade auth deferred.
- Verification heuristics are deterministic but conservative; may require tuning on broader datasets.
- Rate limiting is lightweight and should be expanded for distributed deployments.

## Swap Points for Real Providers
- Embeddings: replace `MockEmbeddingProvider` with hosted/local transformer provider implementing `EmbeddingProvider`.
- LLM: replace `MockLLMProvider` with provider implementing `LLMProvider.generate()`.
- Retrieval: optionally move to hybrid reranking with external vector DB/services.
