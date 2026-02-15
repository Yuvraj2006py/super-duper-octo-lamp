import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import crud
from app.db.models import User
from app.services.embeddings import EmbeddingProvider, cosine_similarity


def chunk_user_profile(user: User) -> list[dict[str, Any]]:
    profile = user.profile_json
    chunks: list[dict[str, Any]] = []

    summary = profile.get("summary", "")
    if summary:
        chunks.append({"chunk_key": "summary", "text": summary, "metadata": {"source_field": "summary"}})

    skills = profile.get("skills", [])
    if skills:
        chunks.append(
            {
                "chunk_key": "skills",
                "text": "Skills: " + ", ".join(skills),
                "metadata": {"source_field": "skills"},
            }
        )

    for idx, exp in enumerate(profile.get("experience", []), start=1):
        text = f"{exp.get('title', '')} at {exp.get('company', '')}: {exp.get('highlights', '')}"
        chunks.append(
            {
                "chunk_key": f"experience_{idx}",
                "text": text,
                "metadata": {
                    "source_field": f"experience[{idx-1}]",
                    "company": exp.get("company"),
                    "title": exp.get("title"),
                    "dates": f"{exp.get('start_date', '')} to {exp.get('end_date', '')}",
                },
            }
        )

    for idx, proj in enumerate(profile.get("projects", []), start=1):
        chunks.append(
            {
                "chunk_key": f"project_{idx}",
                "text": f"{proj.get('name', '')}: {proj.get('description', '')}",
                "metadata": {"source_field": f"projects[{idx-1}]"},
            }
        )

    for idx, edu in enumerate(profile.get("education", []), start=1):
        gpa = str(edu.get("gpa", "")).strip()
        if not gpa:
            details_blob = f"{edu.get('degree', '')} {edu.get('details', '')}"
            gpa_match = re.search(r"(\d\.\d{1,2}\s*/\s*4(?:\.0+)?)", details_blob)
            if gpa_match:
                gpa = gpa_match.group(1).replace(" ", "")

        text = (
            f"{edu.get('school', '')} {edu.get('degree', '')} "
            f"{edu.get('year', '')} {edu.get('details', '')}"
        ).strip()
        if gpa:
            text = f"{text} GPA {gpa}".strip()
        if text:
            chunks.append(
                {
                    "chunk_key": f"education_{idx}",
                    "text": text,
                    "metadata": {"source_field": f"education[{idx-1}]"},
                }
            )

    for idx, achievement in enumerate(profile.get("achievements", []), start=1):
        text = str(achievement).strip()
        if text:
            chunks.append(
                {
                    "chunk_key": f"achievement_{idx}",
                    "text": text,
                    "metadata": {"source_field": f"achievements[{idx-1}]"},
                }
            )

    raw_sections = profile.get("raw_resume_sections", {})
    if isinstance(raw_sections, dict):
        for section_name, section_text in raw_sections.items():
            if section_name == "header":
                continue
            cleaned = str(section_text).strip()
            if cleaned:
                chunks.append(
                    {
                        "chunk_key": f"raw_{section_name}",
                        "text": cleaned,
                        "metadata": {"source_field": f"raw_resume_sections.{section_name}"},
                    }
                )

    for idx, item in enumerate(profile.get("external_experiences", []), start=1):
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("title") or "").strip()
            description = str(item.get("description") or item.get("highlights") or "").strip()
            text = f"{name}: {description}".strip(" :")
        else:
            text = str(item).strip()

        if text:
            chunks.append(
                {
                    "chunk_key": f"external_{idx}",
                    "text": text,
                    "metadata": {"source_field": f"external_experiences[{idx-1}]"},
                }
            )

    return chunks


def embed_user_profile_chunks(db: Session, user: User, embedding_provider: EmbeddingProvider) -> int:
    settings = get_settings()
    chunks = chunk_user_profile(user)
    vectors = embedding_provider.embed_texts([chunk["text"] for chunk in chunks])
    count = 0
    for chunk, vector in zip(chunks, vectors):
        crud.store_embedding(
            db,
            entity_type="profile_chunk",
            entity_id=str(user.id),
            chunk_key=chunk["chunk_key"],
            model_name=settings.embedding_model_name,
            vector=vector,
            metadata={"text": chunk["text"], **chunk["metadata"]},
        )
        count += 1
    return count


def retrieve_profile_chunks_for_job(
    db: Session,
    *,
    user: User,
    job_text: str,
    embedding_provider: EmbeddingProvider,
    top_k: int = 8,
) -> list[dict[str, Any]]:
    settings = get_settings()
    embeddings = [
        emb
        for emb in crud.list_embeddings(db, entity_type="profile_chunk")
        if emb.entity_id == str(user.id) and emb.model_name == settings.embedding_model_name
    ]
    chunks = [
        {
            "chunk_key": emb.chunk_key,
            "text": _embedding_metadata(emb).get("text", ""),
            "source_field": _embedding_metadata(emb).get("source_field", ""),
            "metadata": _embedding_metadata(emb),
            "vector": emb.vector,
        }
        for emb in embeddings
    ]
    return rank_profile_chunks(
        job_text=job_text,
        chunks=chunks,
        embedding_provider=embedding_provider,
        top_k=top_k,
    )


def rank_profile_chunks(
    *,
    job_text: str,
    chunks: list[dict[str, Any]],
    embedding_provider: EmbeddingProvider,
    top_k: int = 8,
) -> list[dict[str, Any]]:
    job_vector = embedding_provider.embed_texts([job_text])[0]
    scored = []
    for chunk in chunks:
        score = cosine_similarity(job_vector, chunk["vector"])
        scored.append(
            {
                "chunk_key": chunk["chunk_key"],
                "score": score,
                "text": chunk.get("text", ""),
                "source_field": chunk.get("source_field", ""),
                "metadata": chunk.get("metadata", {}),
            }
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def _embedding_metadata(embedding_obj: Any) -> dict[str, Any]:
    meta = getattr(embedding_obj, "metadata_json", None)
    if isinstance(meta, dict):
        return meta
    legacy_meta = getattr(embedding_obj, "metadata", None)
    if isinstance(legacy_meta, dict):
        return legacy_meta
    return {}
