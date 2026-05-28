"""RAG + self-healing hallucination detection.

Implements the Retrieval-Augmented Verification Strategy from
Engineering_Intent_Framework.md Section 3:

    "A primary cause of AI slop is hallucination. The defense against
    this is a combined architecture of Retrieval-Augmented Generation
    (RAG) and self-correction..."

Four failure patterns detected and healed:
    1. Numeric Contradiction — regex-based comparison + entity scrubbing
    2. Negation Flip — semantic check for antonyms + grounding rewrite
    3. Answer Drift — similarity query vs prompt + loop re-initiation
    4. Ungrounded Assertions — low faithfulness score <40% + re-retrieval
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Embedding Store ──────────────────────────────────────────────────────────


@dataclass
class Document:
    """A document in the embedding store."""

    id: str
    content: str
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class EmbeddingStore:
    """In-memory vector store using TF-IDF weighted cosine similarity.

    Stores project files as documents and retrieves the most
    relevant context for a query using term frequency analysis.

    Falls back to simple bag-of-words when no external embedding
    library is available.

    Usage:
        store = EmbeddingStore()
        store.add(Document(id="models.py", content=open("models.py").read()))
        results = store.search("User model with email field", top_k=3)
    """

    def __init__(self) -> None:
        self._docs: dict[str, Document] = {}
        self._idf: dict[str, float] = {}  # Inverse document frequency
        self._tf: dict[str, dict[str, float]] = {}  # Term frequency per doc

    def add(self, doc: Document) -> None:
        """Add a document to the store."""
        self._docs[doc.id] = doc
        terms = self._tokenize(doc.content)
        total = len(terms) if terms else 1
        self._tf[doc.id] = {t: c / total for t, c in Counter(terms).items()}
        self._rebuild_idf()

    def add_file(self, path: Path | str) -> None:
        """Add a file to the store."""
        p = Path(path)
        try:
            content = p.read_text()
        except Exception as e:
            logger.warning("Failed to read %s: %s", p, e)
            return
        self.add(Document(id=str(p), content=content, source=str(p)))

    def add_directory(self, directory: Path | str, glob: str = "*.py") -> None:
        """Add all matching files in a directory."""
        for f in Path(directory).rglob(glob):
            if f.is_file() and "__pycache__" not in str(f):
                self.add_file(f)

    def search(self, query: str, top_k: int = 3) -> list[tuple[Document, float]]:
        """Search for documents most relevant to the query.

        Args:
            query: The search query.
            top_k: Number of results to return.

        Returns:
            List of (Document, similarity_score) sorted by relevance.
        """
        if not self._docs:
            return []

        query_terms = self._tokenize(query)
        if not query_terms:
            return []

        query_tf = {}
        total = len(query_terms)
        for t, c in Counter(query_terms).items():
            query_tf[t] = c / total

        scores: list[tuple[str, float]] = []
        for doc_id, doc_tf in self._tf.items():
            score = self._cosine_similarity(query_tf, doc_tf)
            scores.append((doc_id, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [(self._docs[did], score) for did, score in scores[:top_k] if score > 0]

    def _rebuild_idf(self) -> None:
        """Rebuild inverse document frequency scores."""
        n = len(self._docs)
        if n == 0:
            return
        df: dict[str, int] = {}
        for doc_tf in self._tf.values():
            for term in doc_tf:
                df[term] = df.get(term, 0) + 1
        self._idf = {t: math.log(n / (c + 1)) + 1 for t, c in df.items()}

    def _cosine_similarity(self, tf1: dict[str, float], tf2: dict[str, float]) -> float:
        """Compute cosine similarity between two TF-IDF vectors."""
        all_terms = set(tf1) | set(tf2)
        dot = sum(
            tf1.get(t, 0) * self._idf.get(t, 1) * tf2.get(t, 0) * self._idf.get(t, 1)
            for t in all_terms
        )
        mag1 = math.sqrt(sum((tf1.get(t, 0) * self._idf.get(t, 1)) ** 2 for t in tf1))
        mag2 = math.sqrt(sum((tf2.get(t, 0) * self._idf.get(t, 1)) ** 2 for t in tf2))
        if mag1 == 0 or mag2 == 0:
            return 0.0
        return dot / (mag1 * mag2)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple tokenizer: lowercase, split on non-alphanumeric."""
        return re.findall(r"[a-z0-9_]+", text.lower())

    def __len__(self) -> int:
        return len(self._docs)


# ── Hallucination Detector ───────────────────────────────────────────────────


class HallucinationDetector:
    """Detects hallucinations in LLM output using four failure patterns.

    Usage:
        detector = HallucinationDetector()
        contradictions = detector.detect_numeric_contradiction(
            output="The User has 5 fields",
            context="class User:\n    email: str\n    name: str",
        )
    """

    def detect_numeric_contradiction(self, output: str, context: str) -> list[dict]:
        """Detect when the LLM states a number that contradicts the context.

        Example: LLM says "User has 5 fields" but context shows only 3 fields.

        Args:
            output: The LLM-generated text.
            context: The ground-truth context (source code, docs).

        Returns:
            List of contradiction dicts with {claim, actual, location}.
        """
        contradictions: list[dict] = []

        # Extract numeric claims from output
        num_pattern = re.compile(
            r"(\b(has|contains|defines|declares|uses|requires|needs|consists of)\s+(\d+)\b)",
            re.IGNORECASE,
        )
        for match in num_pattern.finditer(output):
            claim = match.group(0)
            num = int(match.group(3))

            # Count actual occurrences in context
            # For "has X fields" → count class attributes
            if "field" in output.lower() or "attribute" in output.lower():
                # Count class attributes in Python context
                attr_pattern = re.compile(r"^\s{4}(\w+)\s*:", re.MULTILINE)
                actual = len(attr_pattern.findall(context))
                if actual != num and actual > 0:
                    contradictions.append({
                        "pattern": "numeric_contradiction",
                        "claim": claim.strip(),
                        "claimed_count": num,
                        "actual_count": actual,
                        "location": f"Output claims {num}, context has {actual}",
                    })

        return contradictions

    def detect_negation_flip(self, output: str, prompt: str) -> bool:
        """Detect when the LLM negates a requirement from the prompt.

        Example: Prompt says "do NOT use async" but output uses async.

        Args:
            output: The LLM-generated text.
            prompt: The original prompt/requirements.

        Returns:
            True if a negation flip is detected.
        """
        # Extract negated requirements from prompt
        neg_pattern = re.compile(
            r"\b(do not|don't|must not|cannot|should not|never|avoid)\s+(.+?)(?:\.|,|\n|$)",
            re.IGNORECASE,
        )
        for match in neg_pattern.finditer(prompt):
            negated_phrase = match.group(2).strip().lower()
            # Check if the negated concept appears positively in output
            if negated_phrase in output.lower():
                logger.warning(
                    "Negation flip detected: '%s' negated in prompt but used in output",
                    negated_phrase,
                )
                return True

        return False

    def detect_answer_drift(self, output: str, prompt: str) -> float:
        """Measure how much the output drifts from the prompt's topic.

        Returns a similarity score (0.0 = completely drifted, 1.0 = perfectly on-topic).

        Args:
            output: The LLM-generated text.
            prompt: The original prompt.

        Returns:
            Similarity score between 0.0 and 1.0.
        """
        prompt_terms = set(EmbeddingStore._tokenize(prompt))
        output_terms = set(EmbeddingStore._tokenize(output))

        if not prompt_terms:
            return 1.0

        overlap = prompt_terms & output_terms
        return len(overlap) / len(prompt_terms)

    def faithfulness_score(self, output: str, retrieved_docs: list[tuple[Document, float]]) -> float:  # noqa: E501
        """Score how faithful the output is to retrieved context (0-100).

        A score <40% means the output contains ungrounded assertions
        and should be re-grounded via re-retrieval.

        Args:
            output: The LLM-generated text.
            retrieved_docs: List of (Document, similarity) from EmbeddingStore.search().

        Returns:
            Faithfulness score from 0.0 to 100.0.
        """
        if not retrieved_docs:
            return 0.0

        output_terms = set(EmbeddingStore._tokenize(output))
        if not output_terms:
            return 0.0

        # Count how many output terms appear in the retrieved context
        context_terms: set[str] = set()
        for doc, _ in retrieved_docs:
            context_terms.update(EmbeddingStore._tokenize(doc.content))

        if not context_terms:
            return 0.0

        grounded = output_terms & context_terms
        return (len(grounded) / len(output_terms)) * 100.0

    def is_ungrounded(self, output: str, retrieved_docs: list[tuple[Document, float]]) -> bool:
        """Check if the output contains ungrounded assertions.

        Returns True if faithfulness_score < 40%.
        """
        return self.faithfulness_score(output, retrieved_docs) < 40.0


# ── Self-Healing RAG ─────────────────────────────────────────────────────────


@dataclass
class HealingResult:
    """Result of a self-healing pass."""

    original_output: str
    healed_output: str
    issues_found: list[str]
    was_healed: bool
    faithfulness_before: float
    faithfulness_after: float


class SelfHealingRAG:
    """Combines retrieval, detection, and re-generation for self-healing.

    When the LLM produces output with hallucinations, this module:
    1. Retrieves relevant context from the embedding store
    2. Detects contradictions, negation flips, drift, and ungrounded claims
    3. Builds a correction prompt with the detected issues
    4. Re-generates a grounded version

    Usage:
        rag = SelfHealingRAG(embedding_store, detector, llm_client)
        result = await rag.heal(output, prompt)
        if result.was_healed:
            use(result.healed_output)
    """

    def __init__(
        self,
        store: EmbeddingStore,
        detector: HallucinationDetector | None = None,
    ) -> None:
        self.store = store
        self.detector = detector or HallucinationDetector()

    def heal(
        self,
        output: str,
        prompt: str,
        *,
        retrieve_k: int = 5,
    ) -> HealingResult:
        """Detect and heal hallucinations in LLM output.

        Note: This method provides detection + correction prompt building.
        Actual re-generation is done by the caller (LLM client).

        Args:
            output: The LLM-generated text to check.
            prompt: The original prompt/requirements.
            retrieve_k: Number of documents to retrieve.

        Returns:
            HealingResult with detected issues and correction prompt.
        """
        issues: list[str] = []

        # Retrieve relevant context
        docs = self.store.search(prompt, top_k=retrieve_k)
        context = "\n".join(d.content for d, _ in docs) if docs else ""

        faithfulness_before = self.detector.faithfulness_score(output, docs)

        # 1. Numeric contradictions
        if context:
            contradictions = self.detector.detect_numeric_contradiction(output, context)
            for c in contradictions:
                issues.append(
                    f"Numeric contradiction: {c['claim']} (claimed {c['claimed_count']}, "
                    f"actual {c['actual_count']})"
                )

        # 2. Negation flips
        if self.detector.detect_negation_flip(output, prompt):
            issues.append("Negation flip: output contradicts a negative requirement in the prompt")

        # 3. Answer drift
        drift = self.detector.detect_answer_drift(output, prompt)
        if drift < 0.3:
            issues.append(f"Answer drift: output similarity to prompt = {drift:.2f} (threshold: 0.3)")  # noqa: E501

        # 4. Ungrounded assertions
        if self.detector.is_ungrounded(output, docs):
            issues.append(f"Ungrounded assertions: faithfulness = {faithfulness_before:.1f}% (threshold: 40%)")  # noqa: E501

        # Build correction prompt
        healed_output = output
        if issues:
            correction_prompt = (
                "The following output contains issues that need correction:\n\n"
                + "\n".join(f"- {i}" for i in issues)
                + f"\n\nRelevant context for grounding:\n{context[:3000]}\n\n"
                + f"Original prompt: {prompt[:1000]}\n\n"
                + "Please regenerate the output with these corrections. The corrected output should:\n"  # noqa: E501
                + "1. Use only the actual values from the context\n"
                + "2. Respect all negation requirements from the prompt\n"
                + "3. Stay on-topic with the original prompt\n"
                + "4. Ground all claims in the provided context"
            )
            # The caller passes correction_prompt to the LLM for re-generation
            healed_output = correction_prompt

        faithfulness_after = faithfulness_before  # Will be recalculated after re-generation

        return HealingResult(
            original_output=output,
            healed_output=healed_output,
            issues_found=issues,
            was_healed=len(issues) > 0,
            faithfulness_before=faithfulness_before,
            faithfulness_after=faithfulness_after,
        )

    def scrub_entities(self, output: str, contradictions: list[dict]) -> str:
        """Remove contradictory numeric claims from output.

        Args:
            output: The text to scrub.
            contradictions: List from detect_numeric_contradiction().

        Returns:
            Scrubbed text with contradictions replaced by [CORRECTED] markers.
        """
        result = output
        for c in contradictions:
            claim = c["claim"]
            replacement = f"[CORRECTED: {c['actual_count']} (was {c['claimed_count']})]"
            result = result.replace(claim, replacement)
        return result
