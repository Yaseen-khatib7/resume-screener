import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Sequence

try:
    from azure.ai.inference import ChatCompletionsClient
    from azure.ai.inference.models import SystemMessage, UserMessage
    from azure.core.credentials import AzureKeyCredential
except ImportError:  # pragma: no cover - optional dependency
    ChatCompletionsClient = None
    SystemMessage = None
    UserMessage = None
    AzureKeyCredential = None


SKILL_QUESTION_BANK = {
    "python": [
        "How do Python generators differ from regular functions, and where have you used them?",
        "Can you explain decorators in Python and give a practical example from your work?",
    ],
    "sql": [
        "How do you decide when to use indexes, and what tradeoffs do they introduce?",
        "Can you walk through the difference between common join types and when you use them?",
    ],
    "fastapi": [
        "How have you structured FastAPI services for maintainability and testing?",
        "What approach do you use for validation, dependency injection, and error handling in FastAPI?",
    ],
    "aws": [
        "Which AWS services have you used most, and how did they fit into your system design?",
        "How do you think about scalability, observability, and cost when deploying on AWS?",
    ],
    "docker": [
        "How have you used Docker to improve development consistency or deployment reliability?",
    ],
    "kubernetes": [
        "What problems did Kubernetes solve for your team, and what operational challenges did it introduce?",
    ],
    "machine learning": [
        "How do you diagnose overfitting, and what steps do you take to improve generalization?",
        "Can you explain the bias-variance tradeoff using a project you worked on?",
    ],
    "mlops": [
        "How have you handled model deployment, monitoring, and rollback in production?",
    ],
    "pytorch": [
        "Why did you choose PyTorch for your project, and how did you structure the training pipeline?",
    ],
    "tensorflow": [
        "How did you manage experimentation, training performance, and model serving with TensorFlow?",
    ],
    "llm": [
        "How would you evaluate whether an LLM feature is actually useful and reliable in production?",
    ],
    "langchain": [
        "What problems did LangChain solve in your project, and what limitations did you run into?",
    ],
    "rag": [
        "How would you design and evaluate a retrieval-augmented generation pipeline?",
    ],
    "react": [
        "How do you structure React components for readability, state flow, and performance?",
    ],
    "node.js": [
        "What patterns do you use in Node.js services to handle concurrency and error management?",
    ],
    "business analysis": [
        "How do you move from a business problem to clear, testable requirements?",
        "Tell me about a time you handled conflicting stakeholder expectations.",
    ],
    "requirement gathering": [
        "What techniques do you use to uncover requirements that stakeholders may not state directly?",
        "How do you validate that documented requirements match the actual business need?",
    ],
    "stakeholder management": [
        "How do you keep stakeholders aligned when priorities or timelines change?",
        "Describe a time you had to influence a decision without direct authority.",
    ],
    "project management": [
        "How do you track delivery risks and communicate them before they become blockers?",
        "Tell me about a project where scope, timeline, or resources changed mid-way.",
    ],
    "management": [
        "How do you prioritize work when multiple stakeholders need different outcomes?",
        "Tell me about a time you improved coordination across people, process, or tools.",
    ],
    "sales": [
        "How do you qualify a prospect and decide where to spend your follow-up time?",
        "Tell me about a difficult objection you handled and what you changed after it.",
    ],
    "crm": [
        "How do you keep CRM data useful for follow-ups, forecasting, and handovers?",
        "Tell me about a time CRM insights changed how you handled an account or pipeline.",
    ],
    "negotiation": [
        "How do you prepare for a negotiation when price, timeline, and relationship all matter?",
        "Describe a negotiation where you protected value while still reaching agreement.",
    ],
    "business development": [
        "How do you identify and prioritize new business opportunities?",
        "Walk me through how you convert an initial lead into a concrete next step.",
    ],
    "customer support": [
        "How do you handle an unhappy customer while still protecting company policy?",
        "Tell me about a recurring customer issue you helped reduce or resolve.",
    ],
    "marketing": [
        "How do you decide whether a campaign is working beyond surface-level metrics?",
        "Describe a campaign or content initiative you improved after reviewing performance data.",
    ],
    "digital marketing": [
        "How do you balance paid, organic, and content channels for a campaign goal?",
        "Which metrics do you monitor first when campaign performance drops?",
    ],
    "content writing": [
        "How do you adapt the same message for different audiences or channels?",
        "Tell me about a piece of content you revised based on feedback or results.",
    ],
    "recruitment": [
        "How do you screen candidates when a hiring manager's requirements are broad or unclear?",
        "Tell me about a difficult role you helped close and how you adjusted your sourcing strategy.",
    ],
    "talent acquisition": [
        "How do you evaluate candidate quality beyond keyword overlap?",
        "How do you keep candidates engaged through a slow hiring process?",
    ],
    "accounting": [
        "How do you ensure accuracy when working with high-volume financial records?",
        "Tell me about a reconciliation or reporting issue you identified and fixed.",
    ],
    "financial analysis": [
        "How do you explain financial insights to a non-finance stakeholder?",
        "Walk me through an analysis where your recommendation affected a business decision.",
    ],
    "reporting": [
        "How do you decide which metrics belong in a recurring report?",
        "Tell me about a report or dashboard you improved so stakeholders could act faster.",
    ],
    "operations management": [
        "How do you identify the root cause of an operational delay or quality issue?",
        "Tell me about a process improvement you implemented and how you measured it.",
    ],
    "procurement": [
        "How do you evaluate vendors beyond price?",
        "Describe a negotiation or supplier issue you handled under time pressure.",
    ],
    "teaching": [
        "How do you adapt your teaching when learners are progressing at different speeds?",
        "Tell me about a lesson or training session you changed after seeing learner outcomes.",
    ],
    "training": [
        "How do you measure whether a training program improved on-the-job performance?",
        "Describe how you design training for learners with different experience levels.",
    ],
    "patient care": [
        "How do you prioritize patient needs during a busy shift or high-pressure situation?",
        "Tell me about a time accurate documentation or communication changed a patient outcome.",
    ],
    "legal research": [
        "How do you verify that your legal research is complete and current?",
        "Tell me about a matter where you had to summarize complex legal information clearly.",
    ],
    "communication": [
        "Tell me about a time you had to explain a complex issue to a non-specialist audience.",
        "How do you adjust your communication style for different stakeholders?",
    ],
    "leadership": [
        "Describe a time you helped a team perform better without simply taking over the work.",
        "How do you handle accountability when a team misses a target?",
    ],
    "problem solving": [
        "Walk me through a complex problem you solved from diagnosis to outcome.",
        "How do you decide between a quick fix and a deeper process change?",
    ],
}

GITHUB_MODELS_ENDPOINT = "https://models.github.ai/inference"
logger = logging.getLogger(__name__)
_QUESTION_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="question-gen")
PROJECT_QUESTION_LIMIT = 6
PROJECTS_TO_COVER = 3
_PROJECT_STOPWORDS = {
    "and", "the", "for", "with", "using", "built", "developed", "system", "platform", "project",
    "application", "app", "tool", "service", "analysis", "tracking", "reader", "processing",
    "resume", "screening",
}


def _clean_list(values: Iterable[str] | None) -> List[str]:
    output: List[str] = []
    seen = set()
    for value in values or []:
        item = str(value).strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _project_question(project: str) -> List[str]:
    short_name = project.strip().rstrip(".")
    return [
        f"Can you walk me through '{short_name}' and the problem or goal it addressed?",
        f"What was your specific contribution in '{short_name}', and how did you measure success?",
    ]


def _weakness_question(skill: str) -> List[str]:
    topic = skill.strip()
    return [
        f"What is your current understanding of {topic}, and how would you ramp up quickly if the role required it?",
        f"How would you approach work involving {topic} if you had to deliver it with limited prior experience?",
    ]


def _experience_question(experience_summary: str) -> List[str]:
    if experience_summary and experience_summary.lower() != "not clearly mentioned":
        return [
            f"You mention {experience_summary} of experience. What has been the most challenging work situation during that time?",
            "Tell me about a time you improved a process, outcome, or stakeholder experience.",
            "Describe a situation where you had to collaborate across functions or resolve a difficult delivery constraint.",
        ]
    return [
        "Tell me about a challenging assignment you worked on and your specific contribution.",
        "Describe a time you had to improve an existing process or piece of work under constraints.",
        "How do you approach teamwork, ownership, and tradeoffs during delivery?",
    ]


def _dedupe_limit(values: Sequence[str], limit: int) -> List[str]:
    output: List[str] = []
    seen = set()
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(value.strip())
        if len(output) >= limit:
            break
    return output


def _project_tokens(project: str) -> List[str]:
    tokens = []
    for token in re.findall(r"[a-z0-9][a-z0-9+#.-]*", (project or "").lower()):
        if len(token) < 4 or token in _PROJECT_STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def _fallback_project_questions(projects: Sequence[str]) -> List[str]:
    project_questions: List[str] = []
    for project in list(projects)[:PROJECTS_TO_COVER]:
        project_questions.extend(_project_question(project))
    return _dedupe_limit(project_questions, PROJECT_QUESTION_LIMIT)


def _rebalance_project_questions(projects: Sequence[str], values: Sequence[str]) -> List[str]:
    cleaned_projects = _clean_list(projects)[:PROJECTS_TO_COVER]
    if len(cleaned_projects) <= 1:
        return _dedupe_limit(values, PROJECT_QUESTION_LIMIT)

    matched_by_project: Dict[str, List[str]] = {project: [] for project in cleaned_projects}
    unmatched: List[str] = []

    for value in _dedupe_limit(values, PROJECT_QUESTION_LIMIT * 2):
        lowered = value.lower()
        matched_project = None
        for project in cleaned_projects:
            tokens = _project_tokens(project)
            if tokens and any(token in lowered for token in tokens):
                matched_project = project
                break
        if matched_project is None:
            unmatched.append(value)
            continue
        bucket = matched_by_project[matched_project]
        if len(bucket) < 2:
            bucket.append(value)

    diverse_projects = [project for project, questions in matched_by_project.items() if questions]
    if len(diverse_projects) < min(2, len(cleaned_projects)):
        return _fallback_project_questions(cleaned_projects)

    ordered: List[str] = []
    for round_idx in range(2):
        for project in cleaned_projects:
            bucket = matched_by_project[project]
            if round_idx < len(bucket):
                ordered.append(bucket[round_idx])
                if len(ordered) >= PROJECT_QUESTION_LIMIT:
                    return ordered

    for value in unmatched:
        if len(ordered) >= PROJECT_QUESTION_LIMIT:
            break
        ordered.append(value)

    return _dedupe_limit(ordered, PROJECT_QUESTION_LIMIT)


def _fallback_questions(candidate_data: Dict[str, Any]) -> Dict[str, List[str]]:
    skills = _clean_list(candidate_data.get("skills") or candidate_data.get("matchedSkills"))
    projects = _clean_list(candidate_data.get("projects"))
    missing_skills = _clean_list(
        list(candidate_data.get("missingRequired") or []) + list(candidate_data.get("missingPreferred") or [])
    )
    experience_summary = str(candidate_data.get("experienceYears") or "").strip()

    skill_questions: List[str] = []
    for skill in skills:
        questions = SKILL_QUESTION_BANK.get(skill.lower())
        if questions:
            skill_questions.extend(questions[:2])
        else:
            skill_questions.append(f"How have you applied {skill} in real work, and what tradeoffs or constraints did you handle?")
        if len(skill_questions) >= 6:
            break

    project_questions = _fallback_project_questions(projects)

    weakness_questions: List[str] = []
    for missing in missing_skills[:3]:
        weakness_questions.extend(_weakness_question(missing))

    experience_questions = _experience_question(experience_summary)

    return {
        "skillQuestions": _dedupe_limit(skill_questions, 6),
        "projectQuestions": project_questions,
        "weaknessQuestions": _dedupe_limit(weakness_questions, 6),
        "experienceQuestions": _dedupe_limit(experience_questions, 4),
    }


def _build_prompt(candidate_data: Dict[str, Any]) -> str:
    payload = {
        "skills": _clean_list(candidate_data.get("skills") or candidate_data.get("matchedSkills")),
        "projects": _clean_list(candidate_data.get("projects")),
        "missingRequired": _clean_list(candidate_data.get("missingRequired")),
        "missingPreferred": _clean_list(candidate_data.get("missingPreferred")),
        "experienceYears": str(candidate_data.get("experienceYears") or "").strip(),
    }
    return (
        "Generate interview questions for this candidate.\n"
        "Return strict JSON only with: skillQuestions, projectQuestions, weaknessQuestions, experienceQuestions.\n"
        "Each value must be an array of strings.\n"
        "Use short, practical questions suitable for the candidate's actual role domain, including non-technical roles.\n"
        "Limits: skillQuestions max 6, projectQuestions 5 or 6 when projects exist, weaknessQuestions max 6, experienceQuestions max 4.\n"
        "Project questions must cover multiple listed projects when possible, with at most two per project.\n"
        "Do not add praise or invent details.\n"
        f"Candidate data:\n{json.dumps(payload, ensure_ascii=True)}"
    )


def _normalize_llm_questions(payload: Dict[str, Any]) -> Dict[str, List[str]]:
    projects = _clean_list(payload.get("projects"))
    return {
        "skillQuestions": _dedupe_limit([str(item).strip() for item in payload.get("skillQuestions") or []], 6),
        "projectQuestions": _rebalance_project_questions(
            projects,
            [str(item).strip() for item in payload.get("projectQuestions") or []],
        ),
        "weaknessQuestions": _dedupe_limit([str(item).strip() for item in payload.get("weaknessQuestions") or []], 6),
        "experienceQuestions": _dedupe_limit([str(item).strip() for item in payload.get("experienceQuestions") or []], 4),
    }


def _github_models_chat_model() -> str:
    return os.getenv("GITHUB_MODELS_CHAT_MODEL", "openai/gpt-4.1").strip() or "openai/gpt-4.1"


def _github_models_timeout_seconds() -> float:
    raw = (os.getenv("GITHUB_MODELS_TIMEOUT_SECONDS", "10") or "10").strip()
    try:
        return max(2.0, min(20.0, float(raw)))
    except ValueError:
        return 10.0


def _github_models_fallback_chain() -> List[str]:
    ordered = [
        _github_models_chat_model(),
        "openai/gpt-4.1-mini",
    ]
    unique: List[str] = []
    seen = set()
    for item in ordered:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item.strip())
    return unique


def _message_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: List[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
                continue
            text = getattr(item, "text", None)
            if isinstance(text, str) and text.strip():
                chunks.append(text)
                continue
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                chunks.append(item["text"])
        return "\n".join(part for part in chunks if part).strip()
    return str(content or "").strip()


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("Empty response")

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found")

    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Response JSON was not an object")
    return parsed


@lru_cache(maxsize=2)
def _github_models_client(token: str):
    if ChatCompletionsClient is None or AzureKeyCredential is None:
        return None
    return ChatCompletionsClient(
        endpoint=GITHUB_MODELS_ENDPOINT,
        credential=AzureKeyCredential(token),
    )


def _complete_with_timeout(*, client: Any, model_name: str, candidate_data: Dict[str, Any], timeout_seconds: float):
    future = _QUESTION_EXECUTOR.submit(
        client.complete,
        messages=[
            SystemMessage(
                "You generate targeted role-specific interview questions for recruiters. "
                "Your questions must be realistic, neutral, and easy for an interviewer to ask out loud. "
                "Return strict JSON only."
            ),
            UserMessage(_build_prompt(candidate_data)),
        ],
        model=model_name,
        temperature=0.3,
    )
    try:
        return future.result(timeout=timeout_seconds)
    except FuturesTimeoutError as exc:
        future.cancel()
        raise TimeoutError(f"GitHub Models timed out after {timeout_seconds:.1f}s for {model_name}") from exc


def _generate_with_github_models(candidate_data: Dict[str, Any]) -> Dict[str, List[str]] | None:
    token = os.getenv("GITHUB_OPENAI_KEY", "").strip() or os.getenv("GITHUB_TOKEN", "").strip()
    if not token or ChatCompletionsClient is None:
        return None

    client = _github_models_client(token)
    if client is None:
        return None

    timeout_seconds = _github_models_timeout_seconds()
    last_error: Exception | None = None
    for model_name in _github_models_fallback_chain():
        try:
            response = _complete_with_timeout(
                client=client,
                model_name=model_name,
                candidate_data=candidate_data,
                timeout_seconds=timeout_seconds,
            )
            content = _message_content_text(response.choices[0].message.content) if response.choices else ""
            parsed = _extract_json_object(content)
            normalized = _normalize_llm_questions(parsed)
            if any(normalized.values()):
                return normalized
        except Exception as exc:
            last_error = exc
            logger.warning("GitHub Models call failed for model %s. %s", model_name, exc)
    if last_error is not None:
        raise last_error
    return None


def generate_interview_questions(candidate_data: Dict[str, Any]) -> Dict[str, List[str]]:
    try:
        generated = _generate_with_github_models(candidate_data)
        if generated is not None:
            return generated
    except Exception as exc:
        logger.warning("GitHub Models interview question generation failed; using fallback. %s", exc)
    return _fallback_questions(candidate_data)
