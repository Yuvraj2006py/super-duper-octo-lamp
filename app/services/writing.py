import re
from abc import ABC, abstractmethod
from datetime import date
from typing import Any

import httpx

from app.core.config import Settings

SENIORITY_CLAIM_PATTERN = re.compile(
    r"\b(seasoned|staff-level|principal|veteran|i am a senior|as a senior|senior engineer)\b",
    flags=re.IGNORECASE,
)

WORK_AUTH_PATTERN = re.compile(r"\b(authorized|eligible)\b[^.]{0,60}\bwork\b", re.IGNORECASE)
SPONSORSHIP_PATTERN = re.compile(r"\b(sponsorship|sponsor|visa)\b", re.IGNORECASE)
COUNTRY_US_PATTERN = re.compile(r"\b(us|usa|united states|america)\b", re.IGNORECASE)
COUNTRY_CANADA_PATTERN = re.compile(r"\b(canada|canadian)\b", re.IGNORECASE)
GPA_PATTERN = re.compile(r"\bgpa\b", re.IGNORECASE)
GRADUATION_PATTERN = re.compile(r"\bgraduat(?:e|ion|ing)\b", re.IGNORECASE)
AVAILABILITY_PATTERN = re.compile(r"\b(available|availability|start date|start)\b", re.IGNORECASE)

class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        raise NotImplementedError


class MockLLMProvider(LLMProvider):
    def generate(self, prompt: str) -> str:
        prompt_lines = [line.strip() for line in prompt.splitlines() if line.strip()]
        seed = " ".join(prompt_lines[:5])
        return f"Generated draft (mock provider): {seed[:280]}"


def _display_date(today: date | None = None) -> str:
    current = today or date.today()
    return current.strftime("%B %d, %Y").replace(" 0", " ")


def _first_sentence(text: str, *, max_chars: int = 220) -> str:
    normalized = re.sub(r"\s+", " ", (text or "")).strip(" -")
    if not normalized:
        return ""
    sentence = re.split(r"(?<=[.!?])\s+", normalized)[0]
    return sentence[:max_chars].strip()


def _dedupe_lines(lines: list[str], *, max_items: int) -> list[str]:
    unique: list[str] = []
    seen = set()
    for line in lines:
        cleaned = _first_sentence(line)
        if not cleaned:
            continue
        key = re.sub(r"\s+", " ", cleaned).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(cleaned)
        if len(unique) >= max_items:
            break
    return unique


def _profile_context_lines(user_profile: dict[str, Any], *, max_items: int = 8) -> list[str]:
    context: list[str] = []

    summary = str(user_profile.get("summary") or "").strip()
    if summary:
        context.append(summary)

    for exp in user_profile.get("experience", [])[:4]:
        title = str(exp.get("title") or "").strip()
        company = str(exp.get("company") or "").strip()
        highlights = str(exp.get("highlights") or "").strip()
        bullets = exp.get("bullets") or []
        first_bullet = bullets[0] if isinstance(bullets, list) and bullets else ""
        detail = _first_sentence(first_bullet or highlights)
        if title and company and detail:
            context.append(f"{title} at {company}: {detail}")
        elif detail:
            context.append(detail)

    for project in user_profile.get("projects", [])[:3]:
        name = str(project.get("name") or "").strip()
        description = str(project.get("description") or "").strip()
        highlights = str(project.get("highlights") or "").strip()
        bullets = project.get("bullets") or []
        first_bullet = bullets[0] if isinstance(bullets, list) and bullets else ""
        detail = _first_sentence(first_bullet or highlights or description)
        if name and detail:
            context.append(f"{name}: {detail}")
        elif detail:
            context.append(detail)

    for item in user_profile.get("external_experiences", [])[:3]:
        if isinstance(item, dict):
            label = str(item.get("title") or item.get("name") or "").strip()
            detail = _first_sentence(str(item.get("description") or item.get("highlights") or ""))
            if label and detail:
                context.append(f"{label}: {detail}")
            elif detail:
                context.append(detail)
        else:
            detail = _first_sentence(str(item))
            if detail:
                context.append(detail)

    for edu in user_profile.get("education", [])[:2]:
        school = str(edu.get("school") or "").strip()
        degree = str(edu.get("degree") or "").strip()
        year = str(edu.get("year") or "").strip()
        gpa = str(edu.get("gpa") or "").strip()
        details_blob = " ".join([degree, str(edu.get("details") or "")])
        gpa_match = re.search(r"(\d\.\d{1,2}\s*/\s*4(?:\.0+)?)", details_blob)
        if not gpa and gpa_match:
            gpa = gpa_match.group(1).replace(" ", "")
        parts = [part for part in [degree, school] if part]
        if parts:
            line = "Student Profile: " + ", ".join(parts)
            if gpa:
                line += f", GPA {gpa}"
            if year:
                line += f", expected graduation {year}"
            context.append(line)

    skills = user_profile.get("skills") or []
    if isinstance(skills, list) and skills:
        key_skills = [str(skill).strip() for skill in skills if str(skill).strip()][:12]
        if key_skills:
            context.append("Skills: " + ", ".join(key_skills))

    return _dedupe_lines(context, max_items=max_items)


def _evidence_lines(
    *,
    user_profile: dict[str, Any],
    retrieved_chunks: list[dict[str, Any]],
    max_items: int = 8,
) -> list[str]:
    from_retrieval = [str(chunk.get("text") or "").strip() for chunk in retrieved_chunks]
    from_profile = _profile_context_lines(user_profile, max_items=max_items)
    return _dedupe_lines([*from_retrieval, *from_profile], max_items=max_items)


def _extract_cover_letter_body(raw_text: str) -> list[str]:
    if not raw_text.strip():
        return []

    paragraphs = [
        re.sub(r"\s+", " ", paragraph).strip()
        for paragraph in re.split(r"\n\s*\n", raw_text.strip())
        if paragraph.strip()
    ]
    if not paragraphs:
        return []

    skip_prefixes = (
        "here is",
        "certainly",
        "of course",
        "sure",
        "generated draft",
        "dear ",
        "sincerely",
        "best regards",
        "kind regards",
        "regards",
    )
    cleaned: list[str] = []
    for paragraph in paragraphs:
        lowered = paragraph.lower()
        if lowered in {"[your name]", "your name", "[name]"}:
            continue
        if lowered.startswith(skip_prefixes):
            continue
        cleaned.append(paragraph.lstrip("- ").strip())

    if cleaned:
        return cleaned[:3]

    flattened = re.sub(r"\s+", " ", raw_text).strip()
    flattened = re.sub(r"^here is[^:]*:\s*", "", flattened, flags=re.IGNORECASE)
    flattened = re.sub(r"^certainly[,!:]?\s*", "", flattened, flags=re.IGNORECASE)
    return [flattened] if flattened else []


def _is_internship_mode(user_profile: dict[str, Any]) -> bool:
    prefs = user_profile.get("internship_preferences", {}) or {}
    return bool(prefs.get("target_internships_only", False))


def _student_identity_line(user_profile: dict[str, Any]) -> str:
    education = user_profile.get("education", []) or []
    if education:
        first = education[0]
        degree = str(first.get("degree") or "").strip()
        school = str(first.get("school") or "").strip()
        year = str(first.get("year") or "").strip()
        gpa = str(first.get("gpa") or "").strip()
        details_blob = f"{degree} {first.get('details', '')}"
        if not gpa:
            gpa_match = re.search(r"(\d\.\d{1,2}\s*/\s*4(?:\.0+)?)", details_blob)
            if gpa_match:
                gpa = gpa_match.group(1).replace(" ", "")

        clean_degree = re.sub(r"\([^)]*gpa[^)]*\)", "", degree, flags=re.IGNORECASE).strip(" ,")
        if "computer science" in clean_degree.lower():
            clean_degree = "Computer Science"
        if clean_degree and len(clean_degree) > 60:
            clean_degree = "Computer Science"

        if clean_degree and school:
            descriptor = f"I am currently a {clean_degree} student at {school}"
        elif school:
            descriptor = f"I am currently a student at {school}"
        else:
            descriptor = "I am currently a student candidate"

        if year:
            descriptor += f", with expected graduation {year}"
        if gpa:
            descriptor += f" (GPA {gpa})"
        return descriptor + "."

    return "I am currently a student candidate focused on internship opportunities."


def _has_seniority_claim(paragraphs: list[str]) -> bool:
    text = "\n".join(paragraphs)
    return bool(SENIORITY_CLAIM_PATTERN.search(text))


def _normalize_student_tone(text: str, *, internship_mode: bool) -> str:
    if not internship_mode:
        return text
    replacements = [
        (r"\bseasoned\b", "motivated"),
        (r"\bstaff-level\b", "student-level"),
        (r"\bprincipal\b", "student"),
        (r"\bveteran\b", "student"),
        (r"\bi am a senior\b", "I am a student"),
        (r"\bas a senior\b", "as a student"),
        (r"\bsenior engineer\b", "engineering intern candidate"),
    ]
    result = text
    for pattern, value in replacements:
        result = re.sub(pattern, value, result, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", result).strip()


def _candidate_links(personal_info: dict[str, Any], user_profile: dict[str, Any]) -> list[str]:
    links: list[str] = []

    assets = user_profile.get("application_assets", {}) or {}
    for key in ["portfolio_url", "github_url", "linkedin_url", "website_url"]:
        value = str(assets.get(key) or "").strip()
        if value:
            links.append(value)

    raw_links = personal_info.get("links") or []
    if not isinstance(raw_links, list):
        raw_links = [str(raw_links)]
    links.extend([str(link).strip() for link in raw_links if str(link).strip()])

    dedup: list[str] = []
    for link in links:
        if link not in dedup:
            dedup.append(link)
    return dedup


def _profile_gpa(user_profile: dict[str, Any]) -> str:
    education = user_profile.get("education", []) or []
    for item in education:
        gpa = str(item.get("gpa") or "").strip()
        if gpa:
            return gpa
        details = str(item.get("details") or "")
        match = re.search(r"(\d\.\d{1,2}\s*/\s*4(?:\.0+)?)", details)
        if match:
            return match.group(1).replace(" ", "")
    return ""


def _profile_grad(user_profile: dict[str, Any]) -> str:
    education = user_profile.get("education", []) or []
    for item in education:
        year = str(item.get("year") or "").strip()
        if year:
            return year
    return ""


def _deterministic_profile_answer(question: str, user_profile: dict[str, Any]) -> str | None:
    text = str(question or "").strip()
    if not text:
        return None

    prefs = user_profile.get("internship_preferences", {}) or {}
    work_auth = prefs.get("work_authorization", {}) or {}
    lower = text.lower()

    if WORK_AUTH_PATTERN.search(text):
        if COUNTRY_CANADA_PATTERN.search(text):
            can_auth = bool(work_auth.get("canada_authorized", False))
            can_sponsor = bool(work_auth.get("requires_sponsorship_canada", True))
            if can_auth:
                if can_sponsor:
                    return "Yes, I am authorized to work in Canada; sponsorship requirements can be discussed if needed."
                return "Yes, I am authorized to work in Canada and do not require sponsorship."
            return "No, I am not currently authorized to work in Canada."

        if COUNTRY_US_PATTERN.search(text):
            us_auth = bool(work_auth.get("us_authorized", False))
            us_sponsor = bool(work_auth.get("requires_sponsorship_us", True))
            if us_auth:
                if us_sponsor:
                    return "Yes, I am authorized to work in the United States; sponsorship requirements can be discussed if needed."
                return "Yes, I am authorized to work in the United States and do not require sponsorship."
            return "No, I am not currently authorized to work in the United States."

    if SPONSORSHIP_PATTERN.search(text):
        if COUNTRY_CANADA_PATTERN.search(text):
            can_sponsor = bool(work_auth.get("requires_sponsorship_canada", True))
            return "Yes." if can_sponsor else "No."
        if COUNTRY_US_PATTERN.search(text):
            us_sponsor = bool(work_auth.get("requires_sponsorship_us", True))
            return "Yes." if us_sponsor else "No."

    if GPA_PATTERN.search(text):
        gpa = _profile_gpa(user_profile)
        if gpa:
            return f"My current GPA is {gpa}."
        return "I have not provided a GPA in my profile yet."

    if GRADUATION_PATTERN.search(text):
        year = _profile_grad(user_profile)
        if year:
            return f"My expected graduation is {year}."
        return "I have not provided my expected graduation date in my profile yet."

    if AVAILABILITY_PATTERN.search(text) and ("internship" in lower or "term" in lower or "summer" in lower):
        active_term = str(prefs.get("active_term") or "").strip()
        if active_term:
            return f"I am available for {active_term} internship/co-op opportunities."
        return "My internship availability is listed in my profile preferences."

    return None


def _fallback_cover_letter_body(
    company: str,
    role: str,
    evidence_lines: list[str],
    *,
    student_identity: str = "",
) -> list[str]:
    snippets = [_first_sentence(line) for line in evidence_lines if _first_sentence(line)]
    snippets = snippets[:6]

    experience_snippet = next((s for s in snippets if " at " in s.lower()), "")
    project_snippet = next(
        (
            s
            for s in snippets
            if ":" in s
            and " at " not in s.lower()
            and not s.lower().startswith("skills:")
        ),
        "",
    )
    selected = _dedupe_lines(
        [experience_snippet, project_snippet, *snippets],
        max_items=3,
    )

    paragraph_1 = f"I am applying for the {role} position at {company}. "
    if student_identity:
        paragraph_1 += f"{student_identity} "
    paragraph_1 += (
        "My background centers on building reliable software, improving delivery quality, "
        "and shipping measurable outcomes."
    )

    if selected:
        snippet_text = "; ".join(selected)
        paragraph_2 = (
            "Relevant experience includes "
            f"{snippet_text}. "
            "I focus on translating complex requirements into clear execution plans and dependable production results."
        )
    else:
        paragraph_2 = (
            "I have led backend initiatives from architecture through production operations, "
            "with strong emphasis on maintainability, observability, and cross-functional delivery."
        )

    paragraph_3 = (
        f"I would value the opportunity to contribute to {company} and help accelerate outcomes in the {role} scope. "
        "Thank you for your consideration."
    )
    return [paragraph_1, paragraph_2, paragraph_3]


def _compose_cover_letter(
    *,
    candidate_name: str,
    candidate_email: str,
    candidate_links: list[str],
    company: str,
    role: str,
    body_paragraphs: list[str],
) -> str:
    lines = [candidate_name]
    if candidate_email:
        lines.append(candidate_email)
    normalized_links = [str(link).strip() for link in candidate_links if str(link).strip()]
    if normalized_links:
        lines.append(" | ".join(normalized_links[:2]))
    lines.append(_display_date())

    body = "\n\n".join(body_paragraphs[:3]).strip()
    return (
        "\n".join(lines)
        + "\n\n"
        + "Hiring Manager\n"
        + f"{company}\n\n"
        + f"Re: {role}\n\n"
        + "Dear Hiring Manager,\n\n"
        + body
        + "\n\nSincerely,\n"
        + candidate_name
    )


def _build_cover_letter_prompt(
    *,
    candidate_name: str,
    company: str,
    role: str,
    evidence_lines: list[str],
    student_identity: str = "",
) -> str:
    evidence_block = "\n".join([f"- {line}" for line in evidence_lines[:8]]) or "- No evidence provided"
    return (
        "Write exactly three polished business paragraphs for an internship cover letter body.\n"
        "Constraints:\n"
        "- Use only the evidence provided.\n"
        "- Do not invent employers, titles, dates, or metrics.\n"
        "- Position the candidate as a student/intern candidate; never as senior/staff/principal.\n"
        "- Do not include greeting, closing, signature, placeholders, bullet lists, or markdown.\n"
        "- Tone: concise, credible, and professional.\n"
        f"Candidate: {candidate_name}\n"
        f"Candidate student profile: {student_identity}\n"
        f"Target company: {company}\n"
        f"Target role: {role}\n"
        "Evidence:\n"
        f"{evidence_block}"
    )


def _question_key(question: str, idx: int) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", question.lower()).strip("_")
    if not base:
        base = f"question_{idx + 1}"
    if len(base) > 48:
        base = base[:48].rstrip("_")
    return base


def _build_question_answer_prompt(
    *,
    question: str,
    role: str,
    company: str,
    evidence_lines: list[str],
    internship_mode: bool,
    student_identity: str,
) -> str:
    evidence_block = "\n".join([f"- {line}" for line in evidence_lines[:8]]) or "- No evidence provided"
    tone_line = (
        "- Position the candidate as a student/intern candidate.\n"
        if internship_mode
        else "- Keep the answer professional and concise.\n"
    )
    return (
        "Answer the application question in 3-5 concise sentences.\n"
        "Constraints:\n"
        "- Use only the provided evidence.\n"
        "- Do not invent employers, titles, dates, metrics, or technologies.\n"
        f"{tone_line}"
        "- Avoid fluff and generic claims.\n"
        f"Role: {role}\n"
        f"Company: {company}\n"
        f"Student profile: {student_identity}\n"
        f"Question: {question}\n"
        "Evidence:\n"
        f"{evidence_block}"
    )


def _fallback_question_answer(
    *,
    question: str,
    role: str,
    evidence_lines: list[str],
    internship_mode: bool,
    student_identity: str,
) -> str:
    anchor = _first_sentence(evidence_lines[0]).rstrip(".!?") if evidence_lines else "relevant project work"
    prefix = f"{student_identity} " if internship_mode and student_identity else ""
    return (
        f"{prefix}For \"{question}\", I am a strong fit for {role} because my background includes {anchor}. "
        "I focus on building reliable solutions and collaborating effectively to deliver measurable outcomes."
    )


class OpenAICompatibleLLMProvider(LLMProvider):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: int,
    ) -> None:
        if not api_key:
            raise ValueError("LLM_API_KEY is required when LLM_PROVIDER=openai")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds

    def generate(self, prompt: str) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a concise professional writing assistant."},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)

        if response.status_code >= 400:
            raise RuntimeError(
                f"LLM request failed ({response.status_code}): {response.text[:300]}"
            )

        data = response.json()
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        if not content:
            raise RuntimeError("LLM response missing content")
        return str(content).strip()


def build_llm_provider(settings: Settings) -> LLMProvider:
    raw_provider = (settings.llm_provider or "mock").strip()
    provider = raw_provider.lower()

    if provider.startswith("sk-") or provider.startswith("gsk_"):
        raise ValueError(
            "LLM_PROVIDER appears to contain an API key. Set LLM_PROVIDER to 'openai' or 'groq' "
            "and move the key to LLM_API_KEY."
        )

    if provider == "mock":
        return MockLLMProvider()
    if provider in {"openai", "openai_compatible"}:
        return OpenAICompatibleLLMProvider(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    if provider == "groq":
        base_url = settings.llm_base_url
        if not base_url or base_url == "https://api.openai.com/v1":
            base_url = "https://api.groq.com/openai/v1"
        return OpenAICompatibleLLMProvider(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            base_url=base_url,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    raise ValueError("Unsupported LLM_PROVIDER. Supported values: mock, openai, groq.")


def generate_drafts(
    *,
    user_profile: dict[str, Any],
    job_structured: dict[str, Any],
    retrieved_chunks: list[dict[str, Any]],
    llm_provider: LLMProvider,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    top_chunks = retrieved_chunks[:5]
    personal_info = user_profile.get("personal_info", {})
    candidate_name = str(personal_info.get("name") or "Candidate").strip()
    candidate_email = str(personal_info.get("email") or "").strip()
    internship_mode = _is_internship_mode(user_profile)
    student_identity = _student_identity_line(user_profile) if internship_mode else ""
    candidate_links = _candidate_links(personal_info, user_profile)

    evidence_lines = _evidence_lines(
        user_profile=user_profile,
        retrieved_chunks=top_chunks,
        max_items=8,
    )

    summary_lines = [
        f"{candidate_name} is targeting {job_structured.get('title', 'this role')}.",
        "Relevant evidence:",
    ]
    if student_identity:
        summary_lines.append(f"- {student_identity}")
    for line in evidence_lines[:3]:
        summary_lines.append(f"- {line}")

    resume_summary = "\n".join(summary_lines)
    bullet_ordering = evidence_lines[:5]

    company = job_structured.get("company") or "Hiring Team"
    role = job_structured.get("title") or "this role"
    requires_cover_letter = bool(job_structured.get("requires_cover_letter", False))
    cover_letter = ""
    if requires_cover_letter:
        letter_prompt = _build_cover_letter_prompt(
            candidate_name=candidate_name,
            company=company,
            role=role,
            evidence_lines=evidence_lines,
            student_identity=student_identity,
        )
        try:
            generated_body = llm_provider.generate(letter_prompt)
        except Exception:
            generated_body = ""

        body_paragraphs = _extract_cover_letter_body(generated_body)
        if internship_mode and _has_seniority_claim(body_paragraphs):
            body_paragraphs = []
        if not body_paragraphs:
            body_paragraphs = _fallback_cover_letter_body(
                company,
                role,
                evidence_lines,
                student_identity=student_identity,
            )
        elif internship_mode and student_identity:
            first = _normalize_student_tone(body_paragraphs[0], internship_mode=True)
            if "student" not in first.lower() and "intern" not in first.lower():
                first = f"{student_identity} {first}"
            body_paragraphs[0] = first

        body_paragraphs = [
            _normalize_student_tone(paragraph, internship_mode=internship_mode) for paragraph in body_paragraphs
        ]

        cover_letter = _compose_cover_letter(
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            candidate_links=[str(link) for link in candidate_links],
            company=company,
            role=role,
            body_paragraphs=body_paragraphs,
        )

    short_answers: dict[str, str] = {}
    question_answer_pairs: list[dict[str, str]] = []
    questions = [str(item).strip() for item in job_structured.get("application_questions", []) if str(item).strip()]
    if questions:
        for idx, question in enumerate(questions):
            deterministic_answer = _deterministic_profile_answer(question, user_profile)
            question_prompt = _build_question_answer_prompt(
                question=question,
                role=role,
                company=company,
                evidence_lines=evidence_lines,
                internship_mode=internship_mode,
                student_identity=student_identity,
            )
            answer = deterministic_answer or ""
            if not answer:
                try:
                    answer = llm_provider.generate(question_prompt).strip()
                except Exception:
                    answer = ""
                if not answer:
                    answer = _fallback_question_answer(
                        question=question,
                        role=role,
                        evidence_lines=evidence_lines,
                        internship_mode=internship_mode,
                        student_identity=student_identity,
                    )
            key = _question_key(question, idx)
            short_answers[key] = answer
            question_answer_pairs.append(
                {
                    "key": key,
                    "question": question,
                    "answer": answer,
                }
            )

    claims_table = []
    for chunk in top_chunks:
        claims_table.append(
            {
                "claim": chunk["text"],
                "source_field": chunk.get("source_field", "unknown"),
                "source_chunk_key": chunk.get("chunk_key"),
                "confidence": round(float(chunk.get("score", 0.0)), 4),
            }
        )

    drafts = {
        "resume_summary": resume_summary,
        "bullet_ordering": bullet_ordering,
        "cover_letter": cover_letter,
        "short_answers": short_answers,
        "question_answer_pairs": question_answer_pairs,
    }
    return drafts, claims_table
