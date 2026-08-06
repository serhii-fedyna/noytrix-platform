from __future__ import annotations

from .config import candidate_resume_path


CANDIDATE = {
    "name": "Serhii Fedyna",
    "headline": "Full-Stack Engineer | AI Engineer | Technical Founder",
    "email": "serhiifedyna@gmail.com",
    "summary": (
        "Full-stack and AI engineer with hands-on experience building production mobile, "
        "backend, SaaS, Web3-risk and LLM-enabled products."
    ),
    "skills": [
        "Python", "FastAPI", "PostgreSQL", "Docker", "REST APIs", "JWT",
        "LLM integration", "Prompt engineering", "SaaS architecture", "Cloud architecture",
        "API design", "Blockchain analysis", "Product strategy",
    ],
    "languages": "Ukrainian (C2), Russian (C2), English (B2)",
    "resume_filename": "Serhii_Fedyna_Resume.pdf",
}


def resume_path():
    return candidate_resume_path()


def resume_is_ready() -> bool:
    return resume_path().is_file() and resume_path().stat().st_size > 10_000
