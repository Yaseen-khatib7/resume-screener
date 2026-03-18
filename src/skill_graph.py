from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Mapping, Set, Tuple

from src.skills import extract_skills


SKILL_GRAPH_PATH = Path(__file__).with_name("skill_graph_data.json")


@dataclass(frozen=True)
class SkillNode:
    label: str
    aliases: Tuple[str, ...] = ()
    parents: Tuple[str, ...] = ()
    related: Tuple[str, ...] = ()


def _build_skill_graph(raw: Mapping[str, Any]) -> Dict[str, SkillNode]:
    graph: Dict[str, SkillNode] = {}
    for concept, payload in raw.items():
        graph[concept] = SkillNode(
            label=str(payload.get("label") or concept),
            aliases=tuple(str(item) for item in payload.get("aliases", [])),
            parents=tuple(str(item) for item in payload.get("parents", [])),
            related=tuple(str(item) for item in payload.get("related", [])),
        )
    return graph


def _load_skill_graph(path: Path = SKILL_GRAPH_PATH) -> Dict[str, SkillNode]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return _build_skill_graph(raw)


def _build_indexes(graph: Mapping[str, SkillNode]) -> Tuple[Dict[str, str], Dict[str, Set[str]]]:
    alias_to_concept: Dict[str, str] = {}
    children: Dict[str, Set[str]] = {}

    for concept, node in graph.items():
        terms = {concept, *node.aliases}
        for term in terms:
            alias_to_concept[re.sub(r"\s+", " ", term.strip().lower())] = concept
        for parent in node.parents:
            children.setdefault(parent, set()).add(concept)

    return alias_to_concept, children


SKILL_GRAPH = _load_skill_graph()
_ALIAS_TO_CONCEPT, _CHILDREN = _build_indexes(SKILL_GRAPH)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _concept_display(concept: str) -> str:
    node = SKILL_GRAPH.get(concept)
    return node.label if node else concept.strip().title()


@lru_cache(maxsize=4096)
def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    escaped = re.escape(phrase)
    return re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])")


def normalize_skill(term: str, graph_data: Mapping[str, SkillNode] | None = None) -> str | None:
    cleaned = _clean(term)
    if not cleaned:
        return None
    alias_to_concept = _ALIAS_TO_CONCEPT if graph_data is None else _build_indexes(graph_data)[0]
    return alias_to_concept.get(cleaned)


def _contains_phrase(text: str, phrase: str) -> bool:
    return _phrase_pattern(phrase).search(text) is not None


def extract_graph_skills(
    text: str,
    seed_terms: Iterable[str] | None = None,
    graph_data: Mapping[str, SkillNode] | None = None,
) -> Dict[str, Any]:
    graph = graph_data or SKILL_GRAPH
    alias_to_concept = _ALIAS_TO_CONCEPT if graph_data is None else _build_indexes(graph)[0]
    lowered = _clean(text)
    concepts: Set[str] = set()
    labels: Dict[str, str] = {}

    for term in seed_terms or []:
        concept = alias_to_concept.get(_clean(term))
        if concept:
            concepts.add(concept)
            labels.setdefault(concept, term)

    base_skills, _ = extract_skills(text)
    for skill in base_skills:
        concept = alias_to_concept.get(_clean(skill))
        if concept:
            concepts.add(concept)
            labels.setdefault(concept, skill)

    for alias, concept in alias_to_concept.items():
        if _contains_phrase(lowered, alias):
            concepts.add(concept)
            labels.setdefault(concept, alias)

    return {
        "concepts": concepts,
        "labels": labels,
        "display": [_concept_display(concept) for concept in sorted(concepts)],
    }


@lru_cache(maxsize=256)
def _extract_graph_skills_cached(
    text: str,
    seed_terms: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...], tuple[str, ...]]:
    result = extract_graph_skills(text, seed_terms)
    return (
        tuple(sorted(result["concepts"])),
        tuple(sorted((str(k), str(v)) for k, v in result["labels"].items())),
        tuple(result["display"]),
    )


def extract_graph_skills_fast(
    text: str,
    seed_terms: Iterable[str] | None = None,
) -> Dict[str, Any]:
    normalized_seed = tuple(sorted({_clean(term) for term in (seed_terms or []) if _clean(term)}))
    concepts, labels, display = _extract_graph_skills_cached(text or "", normalized_seed)
    return {
        "concepts": set(concepts),
        "labels": dict(labels),
        "display": list(display),
    }


def _ancestors(concept: str, graph_data: Mapping[str, SkillNode] | None = None) -> Set[str]:
    if graph_data is None:
        return set(_ancestors_cached(concept))
    graph = graph_data or SKILL_GRAPH
    seen: Set[str] = set()
    stack = list(graph.get(concept, SkillNode(concept)).parents)
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(graph.get(current, SkillNode(current)).parents)
    return seen


@lru_cache(maxsize=1024)
def _ancestors_cached(concept: str) -> tuple[str, ...]:
    return tuple(sorted(_ancestors(concept, SKILL_GRAPH)))


def _family(concept: str, graph_data: Mapping[str, SkillNode] | None = None) -> Set[str]:
    if graph_data is None:
        return set(_family_cached(concept))
    graph = graph_data or SKILL_GRAPH
    children = _CHILDREN
    node = graph.get(concept, SkillNode(concept))
    return {concept, *_ancestors(concept, graph), *node.related, *children.get(concept, set())}


@lru_cache(maxsize=1024)
def _family_cached(concept: str) -> tuple[str, ...]:
    return tuple(sorted(_family(concept, SKILL_GRAPH)))


def _relationship_score(
    resume_concept: str,
    jd_concept: str,
    graph_data: Mapping[str, SkillNode] | None = None,
) -> Tuple[float, str]:
    if resume_concept == jd_concept:
        return 1.0, "direct"

    resume_ancestors = _ancestors(resume_concept, graph_data)
    jd_ancestors = _ancestors(jd_concept, graph_data)
    if jd_concept in resume_ancestors or resume_concept in jd_ancestors:
        return 0.9, "parent-child"

    if resume_ancestors & jd_ancestors:
        return 0.82, "same-family"

    if resume_concept in _family(jd_concept, graph_data) or jd_concept in _family(resume_concept, graph_data):
        return 0.72, "related"

    return 0.0, ""


def _best_matches(
    resume_concepts: Set[str],
    resume_labels: Dict[str, str],
    jd_concepts: Set[str],
    graph_data: Mapping[str, SkillNode] | None = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    matches: List[Dict[str, Any]] = []
    missing: List[str] = []

    for jd_concept in sorted(jd_concepts):
        best_score = 0.0
        best_resume_concept = None
        best_relation = ""
        for resume_concept in resume_concepts:
            score, relation = _relationship_score(resume_concept, jd_concept, graph_data)
            if score > best_score:
                best_score = score
                best_resume_concept = resume_concept
                best_relation = relation

        if best_resume_concept and best_score >= 0.7:
            resume_label = resume_labels.get(best_resume_concept, _concept_display(best_resume_concept))
            matches.append(
                {
                    "jdConcept": jd_concept,
                    "resumeConcept": best_resume_concept,
                    "score": best_score,
                    "relation": best_relation,
                    "display": f"{resume_label} -> {_concept_display(jd_concept)}",
                    "note": f"{resume_label.title()} was treated as relevant to {_concept_display(jd_concept).lower()} requirements.",
                }
            )
        else:
            missing.append(_concept_display(jd_concept))

    return matches, missing


def analyze_skill_graph_match(
    *,
    resume_text: str,
    jd_text: str,
    jd_required: Set[str],
    jd_preferred: Set[str],
    graph_override: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    graph_data = _build_skill_graph(graph_override) if graph_override else SKILL_GRAPH
    if graph_override:
        resume_graph = extract_graph_skills(resume_text, graph_data=graph_data)
        jd_required_graph = extract_graph_skills(jd_text, jd_required, graph_data=graph_data).get("concepts", set())
        jd_preferred_graph = extract_graph_skills(jd_text, jd_preferred, graph_data=graph_data).get("concepts", set())
    else:
        resume_graph = extract_graph_skills_fast(resume_text)
        jd_required_graph = extract_graph_skills_fast(jd_text, jd_required).get("concepts", set())
        jd_preferred_graph = extract_graph_skills_fast(jd_text, jd_preferred).get("concepts", set())

    if not jd_required_graph and not jd_preferred_graph:
        jd_any = extract_graph_skills(jd_text, graph_data=graph_data) if graph_override else extract_graph_skills_fast(jd_text)
        jd_required_graph = jd_any.get("concepts", set())

    preferred_only = jd_preferred_graph - jd_required_graph
    required_matches, required_missing = _best_matches(
        resume_graph["concepts"],
        resume_graph["labels"],
        jd_required_graph,
        graph_data,
    )
    preferred_matches, preferred_missing = _best_matches(
        resume_graph["concepts"],
        resume_graph["labels"],
        preferred_only,
        graph_data,
    )

    req_score = (
        sum(item["score"] for item in required_matches) / len(jd_required_graph)
        if jd_required_graph
        else 0.0
    )
    pref_score = (
        sum(item["score"] for item in preferred_matches) / len(preferred_only)
        if preferred_only
        else 0.0
    )

    overall = ((req_score * 0.75) + (pref_score * 0.25)) * 100.0 if (jd_required_graph or preferred_only) else 0.0
    notes = [item["note"] for item in required_matches[:3] + preferred_matches[:2]]

    return {
        "normalizedSkills": resume_graph["display"],
        "graphMatchedSkills": [item["display"] for item in required_matches + preferred_matches],
        "graphMissingSkills": required_missing + preferred_missing,
        "graphSkillScore": round(max(0.0, min(100.0, overall)), 1),
        "graphSkillNotes": notes,
    }


def export_skill_graph(graph_data: Mapping[str, SkillNode] | None = None) -> Dict[str, Any]:
    graph = graph_data or SKILL_GRAPH
    return {
        concept: {
            "label": node.label,
            "aliases": list(node.aliases),
            "parents": list(node.parents),
            "related": list(node.related),
        }
        for concept, node in graph.items()
    }
