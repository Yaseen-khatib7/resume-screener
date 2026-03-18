import math
from typing import List

def dcg(rels: List[int], k: int) -> float:
    s = 0.0
    for i, rel in enumerate(rels[:k]):
        s += (2**rel - 1) / math.log2(i + 2)
    return s

def ndcg_at_k(rels_by_rank: List[int], k: int) -> float:
    ideal = sorted(rels_by_rank, reverse=True)
    denom = dcg(ideal, k)
    if denom == 0:
        return 0.0
    return dcg(rels_by_rank, k) / denom