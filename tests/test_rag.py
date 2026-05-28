"""Test suite for RAG + self-healing hallucination detection."""

from __future__ import annotations

from no_slop_harness.rag import (
    Document,
    EmbeddingStore,
    HallucinationDetector,
    HealingResult,
    SelfHealingRAG,
)


class TestEmbeddingStore:
    """Document storage and retrieval."""

    def test_add_and_search(self) -> None:
        store = EmbeddingStore()
        store.add(Document(id="doc1", content="User model with email and password fields"))
        store.add(Document(id="doc2", content="Login endpoint using JWT tokens"))
        store.add(Document(id="doc3", content="Database migration for PostgreSQL"))

        results = store.search("user authentication", top_k=2)
        assert len(results) <= 2
        # Most relevant should be about login/User
        doc_ids = [r[0].id for r in results]
        assert "doc1" in doc_ids or "doc2" in doc_ids

    def test_empty_store(self) -> None:
        store = EmbeddingStore()
        results = store.search("anything")
        assert results == []

    def test_tokenize(self) -> None:
        tokens = EmbeddingStore._tokenize("Hello World! user_model_123")
        assert "hello" in tokens
        assert "world" in tokens
        assert "user_model_123" in tokens

    def test_add_directory(self, tmp_path) -> None:
        (tmp_path / "a.py").write_text("def hello(): pass\n")
        (tmp_path / "b.py").write_text("class User:\n    email: str\n")

        store = EmbeddingStore()
        store.add_directory(tmp_path)
        assert len(store) >= 2


class TestHallucinationDetector:
    """Detection of the four failure patterns."""

    def test_numeric_contradiction(self) -> None:
        detector = HallucinationDetector()
        output = "The User model has 5 fields"
        context = "class User:\n    email: str\n    name: str\n"
        contradictions = detector.detect_numeric_contradiction(output, context)
        # "has 5 fields" vs 2 actual fields
        assert len(contradictions) > 0
        assert contradictions[0]["claimed_count"] == 5

    def test_no_contradiction_when_matching(self) -> None:
        detector = HallucinationDetector()
        output = "The User model has 2 fields"
        context = "class User:\n    email: str\n    name: str\n"
        contradictions = detector.detect_numeric_contradiction(output, context)
        assert len(contradictions) == 0

    def test_negation_flip_detected(self) -> None:
        detector = HallucinationDetector()
        prompt = "Do not use databases"
        output = "I will use databases to store the data"
        assert detector.detect_negation_flip(output, prompt) is True

    def test_negation_flip_not_detected(self) -> None:
        detector = HallucinationDetector()
        prompt = "Do not use async in the implementation"
        output = "def handle_request(): ..."
        assert detector.detect_negation_flip(output, prompt) is False

    def test_answer_drift(self) -> None:
        detector = HallucinationDetector()
        prompt = "Write a User model with email and password"
        on_topic = "class User:\n    email: str\n    password: str\n"
        off_topic = "The weather today is sunny with a chance of rain"

        assert detector.detect_answer_drift(on_topic, prompt) > 0.3
        assert detector.detect_answer_drift(off_topic, prompt) < 0.3

    def test_faithfulness_score(self) -> None:
        detector = HallucinationDetector()
        store = EmbeddingStore()
        store.add(Document(id="ctx", content="User has email and password fields"))

        docs = store.search("User model")
        grounded = "The User model with email and password fields"
        ungrounded = "The Zorg model has blorp and flarp fields"

        assert detector.faithfulness_score(grounded, docs) > detector.faithfulness_score(
            ungrounded, docs
        )  # noqa: E501

    def test_is_ungrounded_threshold(self) -> None:
        detector = HallucinationDetector()
        store = EmbeddingStore()
        store.add(Document(id="ctx", content="def hello(): pass"))

        docs = store.search("hello")
        # Output with completely unrelated terms
        assert detector.is_ungrounded("completely different unrelated terms", docs) is True


class TestSelfHealingRAG:
    """Self-healing detection + correction prompts."""

    def test_heal_no_issues(self) -> None:
        store = EmbeddingStore()
        store.add(Document(id="ctx", content="class User:\n    email: str\n    name: str\n"))
        rag = SelfHealingRAG(store)

        output = "class User:\n    email: str\n    name: str\n"
        prompt = "Write a User class"
        result = rag.heal(output, prompt)

        assert not result.was_healed
        assert result.issues_found == []

    def test_heal_detects_contradiction(self) -> None:
        store = EmbeddingStore()
        store.add(Document(id="ctx", content="class User:\n    email: str\n    name: str\n"))
        rag = SelfHealingRAG(store)

        output = "The User model has 5 fields including email and name"
        prompt = "Describe the User model"
        result = rag.heal(output, prompt)

        assert result.was_healed
        assert any("Numeric contradiction" in i for i in result.issues_found)
        # The healed_output is a correction prompt for re-generation
        assert "correction" in result.healed_output.lower()

    def test_scrub_entities(self) -> None:
        store = EmbeddingStore()
        store.add(Document(id="ctx", content="class User:\n    email: str\n"))
        rag = SelfHealingRAG(store)

        output = "The User model has 5 fields"
        contradictions = [{"claim": "has 5 fields", "claimed_count": 5, "actual_count": 1}]
        scrubbed = rag.scrub_entities(output, contradictions)
        assert "CORRECTED" in scrubbed
        assert "1" in scrubbed
        assert "was 5" in scrubbed

    def test_healing_result_dataclass(self) -> None:
        result = HealingResult(
            original_output="original",
            healed_output="healed",
            issues_found=["issue1"],
            was_healed=True,
            faithfulness_before=30.0,
            faithfulness_after=85.0,
        )
        assert result.was_healed
        assert result.faithfulness_after > result.faithfulness_before
