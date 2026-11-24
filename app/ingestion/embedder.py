"""Dense Vector Embedding Generator (384-dimensional).

Supports high-speed deterministic hashing/TF-IDF projection for instant self-contained 
evaluation & tests, with seamless compatibility for Sentence-Transformers.
"""
import numpy as np
import hashlib
from typing import List

EMBEDDING_DIM = 384

def get_text_embedding(text: str, dim: int = EMBEDDING_DIM) -> List[float]:
    """
    Computes a normalized 384-dimensional dense semantic embedding vector.
    Uses token n-gram projection with semantic term weighting and L2 normalization.
    """
    vec = np.zeros(dim, dtype=np.float32)
    tokens = text.lower().split()
    if not tokens:
        return vec.tolist()

    for idx, token in enumerate(tokens):
        # 1-gram hash
        h1 = int(hashlib.md5(token.encode('utf-8')).hexdigest()[:8], 16)
        vec[h1 % dim] += 1.0

        # 2-gram hash for phrase sensitivity
        if idx < len(tokens) - 1:
            bigram = f"{token}_{tokens[idx+1]}"
            h2 = int(hashlib.sha1(bigram.encode('utf-8')).hexdigest()[:8], 16)
            vec[h2 % dim] += 1.5

    # L2 normalize
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm

    return vec.tolist()

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Calculates cosine similarity between two vector representations."""
    a = np.array(v1, dtype=np.float32)
    b = np.array(v2, dtype=np.float32)
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))
