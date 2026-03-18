import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List


ATS_FILENAME = "ats_state.json"
DEFAULT_STAGE = "New"
SHORTLIST_STAGE = "Screening"
REJECTED_STAGE = "Rejected"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ats_state_path(session_dir: str) -> str:
    return os.path.join(session_dir, ATS_FILENAME)


def load_ats_state(session_dir: str) -> Dict[str, Any]:
    path = ats_state_path(session_dir)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"candidates": []}


def save_ats_state(session_dir: str, state: Dict[str, Any]) -> Dict[str, Any]:
    os.makedirs(session_dir, exist_ok=True)
    with open(ats_state_path(session_dir), "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    return state


def sync_ats_candidates(session_dir: str, ranked: List[Dict[str, Any]], shortlist_names: List[str]) -> Dict[str, Any]:
    state = load_ats_state(session_dir)
    existing = {
        item["candidate"]: item
        for item in state.get("candidates", [])
        if item.get("candidate")
    }

    synced: List[Dict[str, Any]] = []
    for item in ranked:
        candidate = item["candidate"]
        prev = existing.get(candidate, {})
        if item.get("atsDecision") == "Reject":
            default_stage = REJECTED_STAGE
        elif candidate in shortlist_names:
            default_stage = SHORTLIST_STAGE
        else:
            default_stage = DEFAULT_STAGE
        synced.append({
            "candidate": candidate,
            "score": item.get("score"),
            "recommendation": item.get("recommendation"),
            "contactEmail": item.get("contactEmail"),
            "atsScore": item.get("atsScore"),
            "atsStatus": item.get("atsStatus"),
            "atsDecision": item.get("atsDecision"),
            "atsReasons": item.get("atsReasons", []),
            "stage": prev.get("stage") or default_stage,
            "notes": prev.get("notes", ""),
            "updated_at": prev.get("updated_at") or _utc_now_iso(),
        })

    state["candidates"] = synced
    return save_ats_state(session_dir, state)


def update_ats_candidate(
    session_dir: str,
    *,
    candidate: str,
    stage: str | None = None,
    notes: str | None = None,
) -> Dict[str, Any]:
    state = load_ats_state(session_dir)
    candidates = state.get("candidates", [])

    for item in candidates:
        if item.get("candidate") != candidate:
            continue
        if stage is not None:
            item["stage"] = stage
        if notes is not None:
            item["notes"] = notes
        item["updated_at"] = _utc_now_iso()
        save_ats_state(session_dir, state)
        return item

    raise KeyError(f"Candidate not found in ATS state: {candidate}")
