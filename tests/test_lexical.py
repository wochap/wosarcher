import pytest

from wosarcher.lexical import _select, _stem, bm25_scores, rank, tokenize


def test_stem_plurals():
    assert [_stem(t) for t in ["batteries", "costs", "boxes", "churches"]] == [
        "battery",
        "cost",
        "box",
        "church",
    ]


def test_stem_non_plurals():
    words = ["class", "glass", "bus", "news"]
    assert [_stem(t) for t in words] == words


def test_tokenize_words_and_case():
    assert tokenize("The Battery-Life of EVs in 2024") == ["battery", "life", "evs", "2024"]


def test_tokenize_non_latin():
    assert tokenize("café naïve 東京") == ["café", "naïve", "東京"]


def test_tokenize_only_stopwords():
    assert tokenize("what is the") == []


def test_scores_matching_text_higher():
    scores = bm25_scores(
        "battery recycling",
        ["Battery recycling plants recover lithium.", "The weather was mild."],
    )
    assert scores[0] > 0
    assert scores[1] == 0


def test_scores_rarer_term_weighs_more():
    scores = bm25_scores("solar cost", ["solar panel", "cost panel", "cost model"])
    assert scores[0] > scores[1]


def test_scores_repeated_query_terms():
    texts = ["cost panel", "solar cost cost", "model"]
    assert bm25_scores("cost cost cost", texts) == bm25_scores("cost", texts)


def test_scores_deterministic():
    texts = ["solar panel cost", "wind turbine", "solar farm"]
    assert bm25_scores("solar cost", texts) == bm25_scores("solar cost", texts)


def test_scores_empty_texts():
    assert bm25_scores("solar", []) == []


def test_select_drops_weak_matches():
    assert _select([4.0, 2.5, 1.0], 0.5, 25) == [0, 1]


def test_rank_ties_keep_input_order():
    texts = ["wind farm", "solar panel", "wind turbine", "solar panel"]
    assert rank("solar", texts) == [1, 3]


def test_rank_result_cap():
    assert rank("solar", ["solar panel"] * 40, max_results=25) == list(range(25))


def test_rank_invalid_threshold():
    with pytest.raises(ValueError, match="relative_threshold"):
        rank("solar", ["solar"], relative_threshold=1.5)


def test_rank_nothing_matches():
    texts = [f"text number {i} about gardening" for i in range(30)]
    assert rank("quantum entanglement", texts, max_results=5) == [0, 1, 2, 3, 4]


def test_rank_stopword_only_query():
    assert rank("what is it", ["solar", "wind", "coal"]) == [0, 1, 2]


def test_rank_no_texts():
    assert rank("solar", []) == []
