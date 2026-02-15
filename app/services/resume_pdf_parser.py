import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader

SECTION_ALIASES: dict[str, str] = {
    "SUMMARY": "summary",
    "PROFESSIONAL SUMMARY": "summary",
    "PROFILE": "summary",
    "EDUCATION": "education",
    "TECHNICAL SKILLS": "skills",
    "SKILLS": "skills",
    "RELEVANT EXPERIENCE": "experience",
    "EXPERIENCE": "experience",
    "WORK EXPERIENCE": "experience",
    "PROJECTS": "projects",
    "ACHIEVEMENTS": "achievements",
    "CERTIFICATIONS": "achievements",
    "AWARDS": "achievements",
}

SECTION_PATTERN = re.compile(
    r"\b(" + "|".join(sorted((re.escape(key) for key in SECTION_ALIASES), key=len, reverse=True)) + r")\b",
)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d{1,2}\s*)?(?:\(\d{3}\)|\d{3})[-\s]?\d{3}[-\s]?\d{4}")
URL_RE = re.compile(r"(?:https?://|www\.)\S+")
METRIC_RE = re.compile(r"\$?\d{1,3}(?:,\d{3})*(?:\.\d+)?\+?%?|\d+\+?%")

MONTH_MAP = {
    "jan": "01",
    "january": "01",
    "feb": "02",
    "february": "02",
    "mar": "03",
    "march": "03",
    "apr": "04",
    "april": "04",
    "may": "05",
    "jun": "06",
    "june": "06",
    "jul": "07",
    "july": "07",
    "aug": "08",
    "august": "08",
    "sep": "09",
    "sept": "09",
    "september": "09",
    "oct": "10",
    "october": "10",
    "nov": "11",
    "november": "11",
    "dec": "12",
    "december": "12",
}

TITLE_HINTS = {
    "engineer",
    "developer",
    "manager",
    "analyst",
    "intern",
    "lead",
    "scientist",
    "consultant",
    "designer",
    "coordinator",
    "specialist",
    "assistant",
    "architect",
    "director",
    "officer",
    "president",
    "founder",
}
TITLE_PREFIXES = {
    "senior",
    "junior",
    "lead",
    "staff",
    "principal",
    "project",
    "operations",
    "software",
    "data",
    "ai",
    "machine",
    "learning",
    "product",
    "research",
    "backend",
    "frontend",
}

LOCATION_PREFIXES = {"san", "new", "los", "fort", "st", "saint"}
COMPANY_WORD_HINTS = {
    "inc",
    "inc.",
    "llc",
    "ltd",
    "ltd.",
    "corp",
    "corporation",
    "company",
    "society",
    "university",
    "technologies",
    "technology",
    "solutions",
    "systems",
    "group",
    "labs",
    "lab",
}
SKILL_CATEGORY_LABELS = [
    "Languages & Frameworks",
    "Data Analysis & Visualization",
    "Tools & Platforms",
]

DATE_RANGE_RE = re.compile(
    r"(((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s*)?\d{4}\s*[-–—‑]\s*"
    r"(?:Present|Current|((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s*)?\d{4}))",
    flags=re.IGNORECASE,
)


def parse_resume_pdf(pdf_path: Path) -> dict[str, Any]:
    raw_text = _extract_pdf_text(pdf_path)
    profile = parse_resume_text(raw_text)
    profile["resume_source"] = {
        **profile.get("resume_source", {}),
        "pdf_path": str(pdf_path),
    }
    return profile


def parse_resume_text(raw_text: str) -> dict[str, Any]:
    normalized = _normalize_text(raw_text)
    if not normalized:
        raise ValueError("Resume text is empty")

    sections = _extract_sections(normalized)

    personal_info = _parse_personal_info(sections.get("header", ""))
    summary = sections.get("summary", "").strip()
    education = _parse_education(sections.get("education", ""))
    skills, skill_categories = _parse_skills(sections.get("skills", ""))
    experience = _parse_experience(sections.get("experience", ""))
    projects = _parse_projects(sections.get("projects", ""))
    achievements = _split_bullets(sections.get("achievements", ""))

    allowed_claims = _derive_allowed_claims(experience, projects, achievements)

    return {
        "personal_info": personal_info,
        "summary": summary,
        "education": education,
        "experience": experience,
        "projects": projects,
        "skills": skills,
        "achievements": achievements,
        "allowed_claims": allowed_claims,
        "skill_categories": skill_categories,
        "raw_resume_sections": sections,
        "resume_source": {
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "char_count": len(normalized),
            "section_names": [name for name in sections if name != "header" and sections[name]],
        },
    }


def merge_profiles(base: dict[str, Any] | None, parsed: dict[str, Any]) -> dict[str, Any]:
    base = base or {}
    merged = dict(base)

    base_personal = base.get("personal_info", {})
    parsed_personal = parsed.get("personal_info", {})
    merged_personal = dict(base_personal)
    merged_personal.update({k: v for k, v in parsed_personal.items() if v})

    base_links = base_personal.get("links", []) if isinstance(base_personal.get("links", []), list) else []
    parsed_links = parsed_personal.get("links", []) if isinstance(parsed_personal.get("links", []), list) else []
    dedup_links = []
    for link in [*parsed_links, *base_links]:
        if link and link not in dedup_links:
            dedup_links.append(link)
    merged_personal["links"] = dedup_links

    merged["personal_info"] = merged_personal

    for key in ["summary", "education", "experience", "projects", "skills", "achievements"]:
        parsed_value = parsed.get(key)
        if parsed_value:
            merged[key] = parsed_value
        elif key not in merged:
            merged[key] = [] if key != "summary" else ""

    parsed_claims = parsed.get("allowed_claims", [])
    base_claims = base.get("allowed_claims", [])
    merged["allowed_claims"] = parsed_claims or base_claims

    merged["skill_categories"] = parsed.get("skill_categories", base.get("skill_categories", {}))
    merged["raw_resume_sections"] = parsed.get("raw_resume_sections", {})
    merged["resume_source"] = parsed.get("resume_source", {})

    return merged


def _extract_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    chunks = []
    for page in reader.pages:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks)


def _normalize_text(text: str) -> str:
    text = text.replace("\r", "\n")
    text = text.replace("\xa0", " ").replace("\u2022", " ● ")
    # Collapse the PDF extractor's repeated whitespace/newline artifacts.
    text = re.sub(r"\s*\n\s*", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_sections(text: str) -> dict[str, str]:
    matches = list(SECTION_PATTERN.finditer(text))
    sections = {
        "header": "",
        "summary": "",
        "education": "",
        "skills": "",
        "experience": "",
        "projects": "",
        "achievements": "",
    }

    if not matches:
        sections["header"] = text
        return sections

    first = matches[0]
    sections["header"] = text[: first.start()].strip()

    for idx, match in enumerate(matches):
        section_name = SECTION_ALIASES[match.group(1).upper()]
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        if not chunk:
            continue
        if sections[section_name]:
            sections[section_name] = f"{sections[section_name]} {chunk}".strip()
        else:
            sections[section_name] = chunk

    return sections


def _parse_personal_info(header_text: str) -> dict[str, Any]:
    email_match = EMAIL_RE.search(header_text)
    phone_match = PHONE_RE.search(header_text)
    links = URL_RE.findall(header_text)

    name_source = header_text
    for match in [email_match.group(0) if email_match else "", phone_match.group(0) if phone_match else "", "|"]:
        if match:
            name_source = name_source.split(match)[0]
    name = re.sub(r"\s+", " ", name_source).strip(" -|")

    if not links:
        for label in ["Portfolio", "GitHub", "LinkedIn"]:
            if re.search(label, header_text, flags=re.IGNORECASE):
                links.append(label)

    personal_info: dict[str, Any] = {
        "name": name,
        "email": email_match.group(0) if email_match else "",
        "links": links,
    }
    if phone_match:
        personal_info["phone"] = phone_match.group(0)
    return personal_info


def _parse_education(section_text: str) -> list[dict[str, Any]]:
    if not section_text:
        return []

    entries = []
    for segment in [seg.strip() for seg in section_text.split(" ● ") if seg.strip()]:
        details = segment
        coursework = []
        if "Relevant Coursework:" in segment:
            main, coursework_blob = segment.split("Relevant Coursework:", 1)
            details = main.strip(" |")
            coursework = [item.strip() for item in coursework_blob.split(",") if item.strip()]
            if not details and entries:
                existing = entries[-1].get("coursework", [])
                entries[-1]["coursework"] = [*existing, *coursework]
                continue

        school = details
        location = ""
        details_for_parse = details
        if "|" in details:
            left, right = [part.strip() for part in details.split("|", 1)]
            school = left
            details_for_parse = right
            location_match = re.search(r"([A-Za-z]+(?:\s+[A-Za-z]+){0,2},\s*[A-Z]{2})", right)
            if location_match:
                location = location_match.group(1).strip()
                details_for_parse = (right[: location_match.start()] + " " + right[location_match.end() :]).strip()

        year_match = re.search(r"(\d{4}(?:\s*\(Expected\))?)", details)
        year = year_match.group(1) if year_match else ""

        degree = ""
        degree_match = re.search(
            r"(Bachelor|Master|B\.Sc|M\.Sc|Honours|Specialization|Minor)[^|]*",
            details_for_parse,
            flags=re.IGNORECASE,
        )
        if degree_match:
            degree = degree_match.group(0).strip()

        entries.append(
            {
                "school": school,
                "location": location,
                "degree": degree,
                "year": year,
                "details": details,
                "coursework": coursework,
            }
        )

    return entries


def _parse_skills(section_text: str) -> tuple[list[str], dict[str, list[str]]]:
    if not section_text:
        return [], {}

    marked = section_text
    for label in SKILL_CATEGORY_LABELS:
        marked = re.sub(rf"\s*{re.escape(label)}\s*:", f" || {label}: ", marked, flags=re.IGNORECASE)

    categories: dict[str, list[str]] = {}
    for part in [chunk.strip() for chunk in marked.split("||") if chunk.strip()]:
        if ":" not in part:
            continue
        category, blob = [item.strip() for item in part.split(":", 1)]
        parsed = _expand_skill_tokens(blob)
        if parsed:
            categories[category] = parsed

    all_skills: list[str] = []
    if categories:
        for items in categories.values():
            for item in items:
                if item not in all_skills:
                    all_skills.append(item)
    else:
        all_skills = _expand_skill_tokens(section_text)

    return all_skills, categories


def _expand_skill_tokens(blob: str) -> list[str]:
    tokens = []
    for piece in _split_on_delimiters(blob):
        piece = piece.strip(" .")
        if not piece:
            continue

        # Expand parenthetical technologies while retaining the parent label.
        if "(" in piece and ")" in piece:
            prefix, suffix = piece.split("(", 1)
            prefix = prefix.strip()
            inside = suffix.rsplit(")", 1)[0]
            if prefix:
                tokens.append(prefix)
            for sub in _split_on_delimiters(inside):
                sub = sub.strip()
                if sub:
                    tokens.append(sub)
        else:
            tokens.append(piece)

    dedup = []
    for token in tokens:
        token = re.sub(r"\s+", " ", token).strip()
        if token and token not in dedup:
            dedup.append(token)
    return dedup


def _parse_experience(section_text: str) -> list[dict[str, Any]]:
    if not section_text:
        return []

    entries: list[dict[str, Any]] = []
    current_entry: dict[str, Any] | None = None
    tokens = [token.strip() for token in section_text.split("●") if token.strip()]

    for token in tokens:
        date_match = DATE_RANGE_RE.search(token)
        if date_match:
            if current_entry:
                current_entry["highlights"] = " ".join(current_entry.get("bullets", [])).strip()
                entries.append(current_entry)

            date_range = date_match.group(1)
            prefix = token[: date_match.start()].strip()
            suffix = token[date_match.end() :].strip()
            header_prefix, leading_noise = _split_header_from_noise(prefix)
            if leading_noise and entries:
                entries[-1].setdefault("bullets", []).append(leading_noise)
                entries[-1]["highlights"] = " ".join(entries[-1].get("bullets", [])).strip()

            header_blob = f"{header_prefix} {date_range}".strip()
            header_wo_date = re.sub(re.escape(date_range), "", header_blob, flags=re.IGNORECASE).strip(" |,-")
            company, title, location = _parse_experience_header(header_wo_date)
            start_date_raw, end_date_raw = _split_date_range(date_range)

            current_entry = {
                "company": company,
                "title": title,
                "location": location,
                "start_date": _normalize_date_token(start_date_raw),
                "end_date": _normalize_date_token(end_date_raw),
                "highlights": "",
                "bullets": [],
            }
            if suffix:
                current_entry["bullets"].append(suffix)
            continue

        if current_entry:
            current_entry.setdefault("bullets", []).append(token.strip(" -"))

    if current_entry:
        current_entry["highlights"] = " ".join(current_entry.get("bullets", [])).strip()
        entries.append(current_entry)

    return entries


def _parse_projects(section_text: str) -> list[dict[str, Any]]:
    if not section_text:
        return []

    entries = []
    project_markers = list(re.finditer(r"([A-Z][A-Za-z0-9 .&+'-]{1,90})\s*\|", section_text))

    if not project_markers:
        bullets = _split_bullets(section_text)
        if bullets:
            entries.append({"name": "Project", "description": bullets[0], "tech_stack": [], "highlights": " ".join(bullets), "bullets": bullets})
        return entries

    for idx, marker in enumerate(project_markers):
        segment_start = marker.start()
        segment_end = project_markers[idx + 1].start() if idx + 1 < len(project_markers) else len(section_text)
        segment = section_text[segment_start:segment_end].strip()

        name = marker.group(1).strip()
        remainder = segment[marker.end() - segment_start :].strip()
        parts = [part.strip() for part in remainder.split("●") if part.strip()]

        header_blob = parts[0] if parts else ""
        bullets = [bullet.strip(" -") for bullet in parts[1:] if bullet.strip()]

        tech_stack = []
        description = header_blob
        tech_match = re.match(r"(.+?)\s+(Built|Developed|Created|Implemented|Launched)\b(.+)", header_blob, flags=re.IGNORECASE)
        if tech_match:
            tech_stack = [item.strip() for item in tech_match.group(1).split(",") if item.strip()]
            description = f"{tech_match.group(2)}{tech_match.group(3)}".strip()
        elif "," in header_blob:
            maybe_stack, _, maybe_desc = header_blob.partition(" ")
            if maybe_stack:
                tech_stack = [item.strip() for item in header_blob.split(",") if item.strip()]
            description = header_blob

        entries.append(
            {
                "name": name,
                "description": description,
                "tech_stack": tech_stack,
                "highlights": " ".join(bullets).strip(),
                "bullets": bullets,
            }
        )

    return entries


def _derive_allowed_claims(
    experience: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    achievements: list[str],
) -> list[dict[str, str]]:
    claims: list[dict[str, str]] = []

    def collect(text: str, source: str) -> None:
        if not text:
            return
        metrics = [match.strip(" .,") for match in METRIC_RE.findall(text)]
        if not metrics:
            return
        claims.append({"claim": text, "metric": metrics[0], "source": source})

    for idx, exp in enumerate(experience):
        for bullet in exp.get("bullets", []):
            collect(bullet, f"experience[{idx}]")

    for idx, proj in enumerate(projects):
        for bullet in proj.get("bullets", []):
            collect(bullet, f"projects[{idx}]")

    for idx, item in enumerate(achievements):
        collect(item, f"achievements[{idx}]")

    dedup: list[dict[str, str]] = []
    seen = set()
    for claim in claims:
        key = claim["claim"]
        if key not in seen:
            dedup.append(claim)
            seen.add(key)
    return dedup


def _split_bullets(text: str) -> list[str]:
    if not text:
        return []
    pieces = [piece.strip(" -") for piece in text.split("●")]
    return [piece for piece in pieces if piece]


def _extract_location(text: str) -> tuple[str, str]:
    candidates = list(_location_candidates(text))
    if not candidates:
        return "", text

    def score(candidate: tuple[str, int, int, int]) -> tuple[float, int]:
        location, start, end, words = candidate
        before = text[:start].strip()
        after = text[end:].strip()
        city_words = location.split(",")[0].split()
        first_word = city_words[0].lower() if city_words else ""
        prev_word = before.split()[-1].lower() if before.split() else ""

        weight = 0.0
        if re.search(rf"\b({'|'.join(TITLE_HINTS)})\b", after, flags=re.IGNORECASE):
            weight -= 2.0
        if first_word in COMPANY_WORD_HINTS:
            weight += 3.0
        if words == 1 and prev_word in LOCATION_PREFIXES:
            weight += 2.0
        if words == 2 and first_word in LOCATION_PREFIXES:
            weight -= 1.0
        weight += 0.3 * words
        return weight, -start

    location, start, end, _words = min(candidates, key=score)
    remaining = (text[:start] + " " + text[end:]).strip()
    remaining = re.sub(r"\s+", " ", remaining)
    return location, remaining


def _location_candidates(text: str) -> list[tuple[str, int, int, int]]:
    candidates: list[tuple[str, int, int, int]] = []
    for word_count in (1, 2, 3):
        pattern = re.compile(rf"([A-Za-z]+(?:\s+[A-Za-z]+){{{word_count - 1}}},\s*[A-Z]{{2}})")
        for match in pattern.finditer(text):
            location = match.group(1).strip()
            candidates.append((location, match.start(), match.end(), word_count))
    return candidates


def _parse_experience_header(header: str) -> tuple[str, str, str]:
    if not header:
        return "", "", ""

    location, stripped = _extract_location(header)
    if not location:
        company, title = _split_company_title(header)
        return company, title, ""

    prefix = header.split(location, 1)[0].strip(" |,-")
    suffix = header.split(location, 1)[1].strip(" |,-")
    suffix_has_title = bool(re.search(rf"\b({'|'.join(TITLE_HINTS)})\b", suffix, flags=re.IGNORECASE))

    if suffix_has_title and prefix:
        company = prefix
        title = suffix
    else:
        company, title = _split_company_title(stripped)
    return company, title, location


def _split_company_title(header: str) -> tuple[str, str]:
    header = re.sub(r"\s+", " ", header).strip(" |")
    if not header:
        return "", ""

    if "|" in header:
        left, right = [part.strip() for part in header.split("|", 1)]
        return left, right

    tokens = header.split()
    if len(tokens) <= 2:
        return header, ""

    first_hint_index = None
    for idx, token in enumerate(tokens):
        if token.lower().strip(".,") in TITLE_HINTS:
            first_hint_index = idx
            break

    if first_hint_index is None:
        midpoint = max(1, len(tokens) // 2)
        return " ".join(tokens[:midpoint]), " ".join(tokens[midpoint:])

    title_start = first_hint_index
    while title_start > 0 and tokens[title_start - 1].lower().strip(".,") in TITLE_PREFIXES:
        title_start -= 1

    company = " ".join(tokens[:title_start]).strip()
    title = " ".join(tokens[title_start:]).strip()
    return company, title


def _split_date_range(date_range: str) -> tuple[str, str]:
    if re.search(r"[-–—‑]", date_range):
        start_raw, end_raw = [piece.strip() for piece in re.split(r"[-–—‑]", date_range, maxsplit=1)]
        return start_raw, end_raw
    return date_range.strip(), ""


def _normalize_date_token(token: str) -> str:
    token = token.strip()
    lowered = token.lower()
    if lowered in {"present", "current"}:
        return "Present"

    year_match = re.search(r"(\d{4})", token)
    if not year_match:
        return token
    year = year_match.group(1)

    month = "01"
    for key, value in MONTH_MAP.items():
        if re.search(rf"\b{key}\b", lowered):
            month = value
            break

    return f"{year}-{month}"


def _split_header_from_noise(prefix: str) -> tuple[str, str]:
    if not prefix:
        return "", ""

    candidate_pattern = re.compile(
        r"([A-Z][A-Za-z0-9&.'-]*(?:\s+[A-Z][A-Za-z0-9&.'-]*){0,8}\s+"
        r"[A-Za-z]+,\s*[A-Z]{2}\s+[A-Za-z][A-Za-z/&' -]+)$"
    )
    match = candidate_pattern.search(prefix)
    if not match:
        return prefix, ""

    header = match.group(1).strip()
    noise = prefix[: match.start()].strip(" .")
    return header, noise


def _split_on_delimiters(blob: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0

    for char in blob:
        if char == "(":
            depth += 1
        elif char == ")" and depth > 0:
            depth -= 1

        if char in {",", ";", "|"} and depth == 0:
            piece = "".join(current).strip()
            if piece:
                parts.append(piece)
            current = []
            continue

        current.append(char)

    tail = "".join(current).strip()
    if tail:
        parts.append(tail)

    return parts
