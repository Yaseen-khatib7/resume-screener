from dataclasses import dataclass
from typing import List, Dict, Any, Tuple
import numpy as np

from src.skills import extract_skills, split_jd_required_preferred, coverage
from src.embeddings import cosine_similarity, Embedder

@dataclass
class AutoLabelConfig:
    # thresholds in 0..1 space
    strong_sim: float = 0.70
    good_sim: float = 0.62
    weak_sim: float = 0.52

    strong_req_cov: float = 0.65
    good_req_cov: float = 0.45
    weak_req_cov: float = 0.25

    # mixing weights for pseudo-score
    w_sim: float = 0.65
    w_req: float = 0.30
    w_pref: float = 0.05

CFG = AutoLabelConfig()

def auto_label_resumes(
    jd_text: str,
    resumes: List[Dict[str, Any]],
    embedder: Embedder,
    cfg: AutoLabelConfig = CFG
) -> Tuple[List[int], Dict[str, float]]:
    """
    Returns:
      labels: list of int labels 0..3 (same order as resumes)
      debug: dict with some helpful stats
    """
    jd_req, jd_pref = split_jd_required_preferred(jd_text)

    jd_emb = embedder.embed([jd_text])[0]
    res_embs = embedder.embed([r["text"] for r in resumes])

    labels = []
    pseudo_scores = []

    for i, r in enumerate(resumes):
        sem = cosine_similarity(jd_emb, res_embs[i])
        res_skills, _ = extract_skills(r["text"])
        req_cov, pref_cov = coverage(res_skills, jd_req, jd_pref)

        ps = (cfg.w_sim * sem) + (cfg.w_req * req_cov) + (cfg.w_pref * pref_cov)
        pseudo_scores.append(ps)

        # Convert to 0..3 using rules (more stable than raw quantiles)
        if sem >= cfg.strong_sim and req_cov >= cfg.strong_req_cov:
            y = 3
        elif sem >= cfg.good_sim and req_cov >= cfg.good_req_cov:
            y = 2
        elif sem >= cfg.weak_sim and req_cov >= cfg.weak_req_cov:
            y = 1
        else:
            y = 0
        labels.append(y)

    debug = {
        "mean_pseudo_score": float(np.mean(pseudo_scores)) if pseudo_scores else 0.0,
        "pos_ge2": float(sum(1 for y in labels if y >= 2)),
        "total": float(len(labels)),
    }
    return labels, debug