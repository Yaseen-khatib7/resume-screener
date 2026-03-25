import os
import numpy as np

APP_DATA_ROOT = os.getenv("APP_DATA_ROOT", "").strip()
MODEL_ROOT = os.getenv("MODEL_ROOT", "").strip() or (
    os.path.join(APP_DATA_ROOT, "models") if APP_DATA_ROOT else "models"
)
PROJECT_CACHE_ROOT = os.getenv("HF_CACHE_ROOT", "").strip() or os.path.join(MODEL_ROOT, "hf-cache")
os.makedirs(PROJECT_CACHE_ROOT, exist_ok=True)
os.environ.setdefault("HF_HOME", PROJECT_CACHE_ROOT)
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", os.path.join(PROJECT_CACHE_ROOT, "hub"))
os.environ.setdefault("TRANSFORMERS_CACHE", os.path.join(PROJECT_CACHE_ROOT, "transformers"))
os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", os.path.join(PROJECT_CACHE_ROOT, "sentence-transformers"))

from sentence_transformers import SentenceTransformer


_EMBEDDER_CACHE = {}


class Embedder:
    def __init__(self, model_name_or_path: str):
        self.model = SentenceTransformer(model_name_or_path)

    def embed(self, texts):
        emb = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False
        )
        return emb.astype(np.float32)

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def get_cached_embedder(model_name_or_path: str) -> "Embedder":
    cached = _EMBEDDER_CACHE.get(model_name_or_path)
    if cached is None:
        cached = Embedder(model_name_or_path)
        _EMBEDDER_CACHE[model_name_or_path] = cached
    return cached


def load_embedder(baseline_name: str, finetuned_dir: str):
    # if a finetuned model exists, SentenceTransformer stores config.json in root
    if finetuned_dir and os.path.isdir(finetuned_dir) and os.path.exists(os.path.join(finetuned_dir, "config.json")):
        return get_cached_embedder(finetuned_dir), "fine-tuned"
    return get_cached_embedder(baseline_name), "baseline"
