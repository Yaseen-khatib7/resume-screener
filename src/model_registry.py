import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


REGISTRY_PATH = os.path.join("models", "registry.json")
BASELINE_ID = "baseline"
LEGACY_FINETUNED_ID = "legacy-finetuned"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_model_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", (value or "").strip().lower()).strip("-")
    return cleaned[:80] or f"model-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"


def _baseline_entry(baseline_name: str) -> Dict[str, Any]:
    return {
        "id": BASELINE_ID,
        "label": "SBERT baseline",
        "type": "baseline",
        "path": None,
        "created_at": None,
        "status": "ready",
        "baseline_model_name": baseline_name,
        "metrics": {},
    }


def _is_valid_model_root(path: Optional[str]) -> bool:
    if not path or not os.path.isdir(path):
        return False
    return (
        os.path.exists(os.path.join(path, "modules.json"))
        or os.path.exists(os.path.join(path, "config_sentence_transformers.json"))
        or os.path.exists(os.path.join(path, "sentence_bert_config.json"))
    )


def _discover_local_models(finetuned_root: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not finetuned_root or not os.path.isdir(finetuned_root):
        return out

    legacy_config = os.path.join(finetuned_root, "config.json")
    if os.path.exists(legacy_config):
        out.append({
            "id": LEGACY_FINETUNED_ID,
            "label": "Legacy fine-tuned",
            "type": "finetuned",
            "path": finetuned_root,
            "created_at": None,
            "status": "ready",
            "metrics": {},
        })

    for name in sorted(os.listdir(finetuned_root)):
        path = os.path.join(finetuned_root, name)
        if not os.path.isdir(path):
            continue
        if not _is_valid_model_root(path):
            continue
        out.append({
            "id": name,
            "label": name,
            "type": "finetuned",
            "path": path,
            "created_at": None,
            "status": "ready",
            "metrics": {},
        })
    return out


def load_registry(baseline_name: str, finetuned_root: str) -> Dict[str, Any]:
    registry: Dict[str, Any]
    if os.path.exists(REGISTRY_PATH):
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            registry = json.load(f)
    else:
        registry = {"default_model": BASELINE_ID, "models": []}

    models = {m["id"]: m for m in registry.get("models", []) if m.get("id")}
    models = {
        model_id: item
        for model_id, item in models.items()
        if model_id == BASELINE_ID or item.get("type") == "baseline" or _is_valid_model_root(item.get("path"))
    }
    models[BASELINE_ID] = {**_baseline_entry(baseline_name), **models.get(BASELINE_ID, {})}

    for discovered in _discover_local_models(finetuned_root):
        existing = models.get(discovered["id"], {})
        models[discovered["id"]] = {**discovered, **existing}

    default_model = registry.get("default_model") or BASELINE_ID
    if default_model not in models:
        default_model = BASELINE_ID

    return {
        "default_model": default_model,
        "models": sorted(models.values(), key=lambda item: (item["id"] != BASELINE_ID, item["id"])),
    }


def save_registry(registry: Dict[str, Any]) -> Dict[str, Any]:
    os.makedirs(os.path.dirname(REGISTRY_PATH), exist_ok=True)
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2)
    return registry


def ensure_registry(baseline_name: str, finetuned_root: str) -> Dict[str, Any]:
    return save_registry(load_registry(baseline_name, finetuned_root))


def list_models(baseline_name: str, finetuned_root: str) -> Dict[str, Any]:
    registry = ensure_registry(baseline_name, finetuned_root)
    default_model = registry["default_model"]
    return {
        "default_model": default_model,
        "models": [
            {
                "id": item["id"],
                "label": item.get("label") or item["id"],
                "type": item.get("type", "finetuned"),
                "status": item.get("status", "ready"),
                "created_at": item.get("created_at"),
                "metrics": item.get("metrics", {}),
                "is_default": item["id"] == default_model,
            }
            for item in registry["models"]
        ],
    }


def register_trained_model(
    *,
    baseline_name: str,
    finetuned_root: str,
    model_id: str,
    model_path: str,
    metrics: Optional[Dict[str, Any]] = None,
    set_as_default: bool = False,
) -> Dict[str, Any]:
    registry = load_registry(baseline_name, finetuned_root)
    models = {m["id"]: m for m in registry["models"]}
    models[model_id] = {
        "id": model_id,
        "label": model_id,
        "type": "finetuned",
        "path": model_path,
        "created_at": _utc_now_iso(),
        "status": "ready",
        "metrics": metrics or {},
    }
    registry["models"] = sorted(models.values(), key=lambda item: (item["id"] != BASELINE_ID, item["id"]))
    if set_as_default:
        registry["default_model"] = model_id
    return save_registry(registry)


def resolve_model(
    *,
    model_choice: str,
    baseline_name: str,
    finetuned_root: str,
) -> Tuple[str, str]:
    registry = ensure_registry(baseline_name, finetuned_root)
    requested = model_choice or registry["default_model"]
    if requested in ("best", "default"):
        requested = registry["default_model"]

    models = {m["id"]: m for m in registry["models"]}
    chosen = models.get(requested) or models[BASELINE_ID]

    if chosen.get("type") == "baseline":
        return baseline_name, BASELINE_ID

    path = chosen.get("path")
    if path and os.path.exists(os.path.join(path, "config.json")):
        return path, chosen["id"]

    return baseline_name, BASELINE_ID


def build_versioned_model_id(prefix: str = "finetuned") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return _safe_model_id(f"{prefix}-{stamp}")
