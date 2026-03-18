from typing import Any, Dict, Iterable, List, Sequence


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
        f"Can you walk me through the project '{short_name}' and the problem it was solving?",
        f"What were the main technical challenges in '{short_name}', and how did you resolve them?",
        f"If you were redesigning '{short_name}' today, what would you change and why?",
    ]


def _weakness_question(skill: str) -> List[str]:
    topic = skill.strip()
    return [
        f"What is your current understanding of {topic}, and how would you ramp up quickly if the role required it?",
        f"How would you approach a task involving {topic} if you had to deliver in a production setting?",
    ]


def _experience_question(experience_summary: str) -> List[str]:
    if experience_summary and experience_summary.lower() != "not clearly mentioned":
        return [
            f"You mention {experience_summary} of experience. What has been the most technically challenging problem during that time?",
            "Tell me about a time you improved performance, reliability, or maintainability in a real project.",
            "Describe a situation where you had to collaborate across functions or resolve a difficult delivery constraint.",
        ]
    return [
        "Tell me about a technically challenging project you worked on and your specific contribution.",
        "Describe a time you had to improve an existing system under constraints.",
        "How do you approach teamwork, ownership, and technical tradeoffs during delivery?",
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


def generate_interview_questions(candidate_data: Dict[str, Any]) -> Dict[str, List[str]]:
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
            skill_questions.append(f"How have you applied {skill} in production or project work, and what tradeoffs did you encounter?")
        if len(skill_questions) >= 6:
            break

    project_questions: List[str] = []
    for project in projects[:2]:
        project_questions.extend(_project_question(project))

    weakness_questions: List[str] = []
    for missing in missing_skills[:3]:
        weakness_questions.extend(_weakness_question(missing))

    experience_questions = _experience_question(experience_summary)

    return {
        "skillQuestions": _dedupe_limit(skill_questions, 6),
        "projectQuestions": _dedupe_limit(project_questions, 6),
        "weaknessQuestions": _dedupe_limit(weakness_questions, 6),
        "experienceQuestions": _dedupe_limit(experience_questions, 4),
    }
