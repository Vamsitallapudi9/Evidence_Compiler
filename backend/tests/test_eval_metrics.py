from eval.metrics import QuestionScore, aggregate, fact_covered, score_deterministic
from eval.systems import Citation, SystemOutput


def test_fact_coverage_numbers_and_keywords():
    fact = {"numbers": [7400000], "keywords_all": ["europe"]}
    assert fact_covered(fact, "European revenue fell by $7.4 million.")
    assert not fact_covered(fact, "Revenue in Europe fell by $7.1 million.")
    assert fact_covered({"numbers": [71.15]}, "Europe drove about 71% of the decline")
    assert not fact_covered({"keywords_any": ["declin", "fell"]}, "Revenue grew strongly.")


def test_attribution_and_aggregate():
    q = {
        "id": "q",
        "category": "derived",
        "answerable": True,
        "facts": [{"numbers": [7400000], "derived": True, "sources": ["regional_sales.csv"]}],
    }
    out = SystemOutput(
        system="B",
        question_id="q",
        answer="Europe fell $7.4M.",
        citations=[Citation("Europe fell $7.4M.", ["row"], ["regional_sales.csv"])],
    )
    s = score_deterministic(q, out)
    assert (s.facts_covered, s.derived_covered, s.attributed_correctly) == (1, 1, 1)
    s.verdicts = ["supported", "unsupported"]
    agg = aggregate([s, QuestionScore("u", "B", "unanswerable", False, abstained=True)])
    assert agg["unsupported_claim_rate"] == 0.5 and agg["abstention_accuracy"] == 1.0
