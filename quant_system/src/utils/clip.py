def clip_score(score: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp a score to [lo, hi]. Applied at the return of every score function."""
    if score is None:
        return lo
    return max(lo, min(hi, float(score)))
