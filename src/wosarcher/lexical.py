"""BM25 keyword ranking over plain strings: tokenizer, scores, and ranking.

Pure and local: no I/O, no model, no state between calls.
"""

import math
import re
from collections import Counter
from collections.abc import Sequence

_STOPWORD_TEXT = """
a about above after again against all am an and any are as at be because
been before being below between both but by can could did do does doing
down during each few for from further had has have having he her here hers
herself him himself his how if in into is it its itself just me more most
my myself no nor not now of off on once only or other our ours ourselves
out over own same she should so some such than that the their theirs them
themselves then there these they this those through to too under until up
very was we were what when where which while who whom why will with would
you your yours yourself yourselves
"""
STOPWORDS = frozenset(_STOPWORD_TEXT.split())

_WORD = re.compile(r"\w+")


def _stem(token: str) -> str:
    if len(token) <= 4 or token.endswith("ss"):
        return token
    if token.endswith("ies"):
        return token[:-3] + "y"
    if token.endswith(("sses", "xes", "zes", "ches", "shes")):
        return token[:-2]
    if token.endswith("s"):
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    """Lowercased word tokens, without stopwords or one-character tokens, stemmed."""
    return [_stem(token) for token in _WORD.findall(text.lower()) if len(token) > 1 and token not in STOPWORDS]


def bm25_scores(query: str, texts: Sequence[str], *, k1: float = 1.5, b: float = 0.75) -> list[float]:
    """One BM25 score per text, in input order; IDF is computed over `texts`."""
    terms = set(tokenize(query))
    docs = [Counter(tokenize(text)) for text in texts]
    n_docs = len(docs)
    lengths = [sum(doc.values()) for doc in docs]
    avg_len = (sum(lengths) / n_docs if n_docs else 0) or 1
    idf = {
        term: math.log((n_docs - n + 0.5) / (n + 0.5) + 1)
        for term in terms
        for n in [sum(1 for doc in docs if term in doc)]
    }
    scores: list[float] = []
    for doc, length in zip(docs, lengths, strict=True):
        norm = k1 * (1 - b + b * length / avg_len)
        score = 0.0
        for term in terms:
            tf = doc[term]
            if tf:
                score += idf[term] * tf * (k1 + 1) / (tf + norm)
        scores.append(score)
    return scores


def rank(
    query: str,
    texts: Sequence[str],
    *,
    relative_threshold: float = 0.5,
    max_results: int = 25,
) -> list[int]:
    """Positions of the texts to keep, best first; opening texts if nothing matches."""
    if not 0 <= relative_threshold <= 1:
        raise ValueError(f"relative_threshold must be in [0, 1], got {relative_threshold}")
    if max_results < 1:
        raise ValueError(f"max_results must be at least 1, got {max_results}")
    if not texts:
        return []
    return _select(bm25_scores(query, texts), relative_threshold, max_results)


def _select(scores: Sequence[float], relative_threshold: float, max_results: int) -> list[int]:
    best = max(scores)
    if best == 0:
        return list(range(min(max_results, len(scores))))
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
    kept = [i for i in order if scores[i] > 0 and scores[i] >= relative_threshold * best]
    return kept[:max_results]
