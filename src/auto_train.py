import os
import random
from typing import List, Dict, Any, Tuple

from src.embeddings import Embedder, cosine_similarity
from src.eval import ndcg_at_k
from src.train_embed import build_training_pairs_from_labels, finetune_sentence_transformer


def train_val_split(n: int, val_ratio: float = 0.2, seed: int = 42):
    idx = list(range(n))
    random.Random(seed).shuffle(idx)
    val_n = max(1, int(n * val_ratio))
    val_idx = set(idx[:val_n])
    train_idx = [i for i in range(n) if i not in val_idx]
    val_idx = [i for i in range(n) if i in val_idx]
    return train_idx, val_idx


def rank_by_semantic(jd_text: str, resumes: List[Dict[str, Any]], embedder: Embedder) -> List[str]:
    jd_emb = embedder.embed([jd_text])[0]
    res_embs = embedder.embed([r["text"] for r in resumes])
    scores = [(resumes[i]["name"], cosine_similarity(jd_emb, res_embs[i])) for i in range(len(resumes))]
    scores.sort(key=lambda x: x[1], reverse=True)
    return [name for name, _ in scores]


def evaluate_ndcg_for_subset(
    jd_text: str,
    resumes: List[Dict[str, Any]],
    labels_map: dict,
    subset_names: List[str],
    embedder: Embedder,
    k: int = 10
) -> float:
    subset_set = set(subset_names)
    subset = [r for r in resumes if r["name"] in subset_set]
    order = rank_by_semantic(jd_text, subset, embedder)
    rels = [labels_map.get(n, 0) for n in order]
    return ndcg_at_k(rels, min(k, len(rels)))


def auto_train_if_helpful(
    jd_text: str,
    resumes: List[Dict[str, Any]],
    labels: List[int],
    baseline_model_name: str,
    finetuned_dir: str,
    epochs: int = 1,
    batch_size: int = 16,
    k: int = 10,
    min_positives: int = 5,
    seed: int = 42
) -> Tuple[str, float, float]:
    names = [r["name"] for r in resumes]
    labels_map = {names[i]: int(labels[i]) for i in range(len(names))}

    train_idx, val_idx = train_val_split(len(resumes), val_ratio=0.2, seed=seed)
    val_names = [names[i] for i in val_idx]

    # Baseline eval
    base = Embedder(baseline_model_name)
    ndcg_base = evaluate_ndcg_for_subset(jd_text, resumes, labels_map, val_names, base, k=k)

    # Train only if enough positives in train split
    train_labels = [int(labels[i]) for i in train_idx]
    pos = sum(1 for y in train_labels if y >= 2)
    if pos < min_positives:
        return "baseline", ndcg_base, 0.0

    train_examples = build_training_pairs_from_labels(
        jd_text=jd_text,
        resume_texts=[resumes[i]["text"] for i in train_idx],
        labels=train_labels,
        pos_threshold=2
    )
    if len(train_examples) < 3:
        return "baseline", ndcg_base, 0.0

    os.makedirs(finetuned_dir, exist_ok=True)
    finetune_sentence_transformer(
        base_model_name=baseline_model_name,
        train_examples=train_examples,
        output_dir=finetuned_dir,
        epochs=epochs,
        batch_size=batch_size,
        warmup_steps=50
    )

    ft = Embedder(finetuned_dir)
    ndcg_ft = evaluate_ndcg_for_subset(jd_text, resumes, labels_map, val_names, ft, k=k)

    chosen = "fine-tuned" if ndcg_ft >= ndcg_base else "baseline"
    return chosen, ndcg_base, ndcg_ft