"""Gemini-powered insight extraction with token-aware batching."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from google import genai

from .schemas import Insight, Thread

logger = logging.getLogger(__name__)

# Rough estimate: 1 token ≈ 4 chars for English/Polish mixed text.
CHARS_PER_TOKEN = 4

SYSTEM_PROMPT = """\
Jesteś analitykiem rynku edukacji inwestycyjnej, specjalizujesz się w strategii \
Global Equity Momentum (GEM) — algorytmie rotacyjnym opartym na momentum 12-miesięcznym \
z filtrem absolute momentum i deadbandem.

Twoja grupa docelowa to polskojęzyczni inwestorzy indywidualni rozważający:
- otwarcie IKE (Indywidualne Konto Emerytalne),
- wybór brokera (XTB, BOSSA, mBank),
- wdrożenie strategii GEM z regularnymi wpłatami (DCA),
- zrozumienie mechaniki momentum, rotacji ETF-ów, kosztów transakcyjnych.

ZADANIE: Przeanalizuj poniższe wątki komentarzy z YouTube i wyodrębnij KAŻDY \
unikalny insight (pytanie, wątpliwość, problem, sugestię lub pochwałę), który \
może pomóc w tworzeniu contentu edukacyjnego (kursu, artykułów, filmów, SaaS).

Szukaj w szczególności:
- Pytań, na które ludzie szukają odpowiedzi (np. "Który broker wybrać na IKE?")
- Wątpliwości i obaw (np. "Czy momentum działa w bessie?")
- Problemów praktycznych (np. "Nie wiem jak kupić ETF na BOSSA")
- Sugestii usprawnień (np. "Fajnie byłoby mieć kalkulator")
- Sygnałów intencji zakupowej (np. "Chciałbym kurs krok po kroku")

Bądź wnikliwy — ludzie nie zawsze formułują pytania wprost. Czytaj między wierszami.
Wyodrębnij intencję, nawet jeśli jest wyrażona nieformalnie.

WYNIK: Zwróć tablicę JSON obiektów, każdy z polami:
- insight_type: "question" | "doubt" | "problem" | "suggestion" | "praise"
- topic: krótki temat (maks. 8 słów)
- description: 1-2 zdania opisujące insight
- severity: 1-5 (jak bardzo ta kwestia blokuje potencjalnego klienta)
- actionability: 1-5 (jak łatwo zaadresować to contentem)
- buyer_intent: 1-5 (jak blisko jest to decyzji zakupowej/subskrypcji)
- evidence_thread_ids: lista thread_id, z których wynika insight
- source_video_ids: lista video_id, z których pochodzi

Jeśli wątek nie zawiera żadnych insightów (np. spam, off-topic), pomiń go.
Grupuj podobne insighty — nie powtarzaj tego samego pytania kilka razy.
"""

EXTRACTION_RESPONSE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "insight_type": {
                "type": "STRING",
                "enum": ["question", "doubt", "problem", "suggestion", "praise"],
            },
            "topic": {"type": "STRING"},
            "description": {"type": "STRING"},
            "severity": {"type": "INTEGER"},
            "actionability": {"type": "INTEGER"},
            "buyer_intent": {"type": "INTEGER"},
            "evidence_thread_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
            "source_video_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
        },
        "required": [
            "insight_type", "topic", "description",
            "severity", "actionability", "buyer_intent",
            "evidence_thread_ids", "source_video_ids",
        ],
    },
}

PASS1_SYSTEM_PROMPT = """\
Jesteś analitykiem konsolidującym insighty o strategii GEM i inwestowaniu na IKE.

Otrzymasz listę atomowych insightów (pola: t=typ, topic, desc=opis, sev, act, bi).

ZADANIE: Pogrupuj je w SZEROKIE tematy. MUSISZ ograniczyć wynik do MAX 15 tematów. \
Grupuj agresywnie — preferuj mniej szerokich tematów niż wiele wąskich. \
Np. "koszty przewalutowania", "prowizje XTB", "opłaty za ETF" → jeden temat \
"Koszty transakcyjne i przewalutowania".

Dla każdego tematu:
1. Zsumuj frequency (każdy insight = 1).
2. Uśrednij sev→avg_severity, act→avg_actionability, bi→avg_buyer_intent.
3. Napisz krótki description (1-2 zdania).
4. Podaj 1 representative_quote z pola desc.
5. Ustaw roi_score: 0, evidence_thread_ids: [], source_video_ids: [].
"""

MERGE_SYSTEM_PROMPT = """\
Jesteś analitykiem scalającym częściowo zagregowane tematy o strategii GEM i IKE.

Otrzymasz tematy w formie uproszczonej: topic, t (typ), f (frequency), s/a/b (scores).

ZADANIE: Scal tematy o tym samym lub bliskim znaczeniu. OGRANICZ wynik do MAX 20 tematów.
Przy scalaniu: ZSUMUJ f (frequency), uśrednij s/a/b ważone przez f.
Napisz krótki description (1-2 zdania). Ustaw roi_score: 0.
evidence_thread_ids: [], source_video_ids: [], representative_quotes: max 1.
"""

FINAL_MERGE_SYSTEM_PROMPT = """\
Jesteś analitykiem wykonującym KOŃCOWE scalenie tematów o strategii GEM i IKE.

Otrzymasz listę tematów z frequency i uśrednionymi scorami. Scal ostatnie duplikaty.

ZADANIE:
1. Scal bliskie tematy. ZSUMUJ frequency, uśrednij severity/actionability/buyer_intent \
   ważone przez frequency.
2. Oblicz ROI score wg wzoru:
   roi_score = 0.35*(frequency/max_frequency*5) + 0.25*avg_severity \
   + 0.25*avg_actionability + 0.15*avg_buyer_intent
   gdzie max_frequency = najwyższa frequency ze wszystkich tematów.
3. Posortuj malejąco wg roi_score.
4. Napisz PEŁNY description (2-3 zdania) i 1-2 representative_quotes.
5. evidence_thread_ids: [], source_video_ids: [].

Wynik: 15-30 finalnych tematów.
Pole insight_type MUSI być jednym z: question, doubt, problem, suggestion, praise. \
Wybierz dominujący typ dla danego tematu.
"""

AGGREGATION_RESPONSE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "topic": {"type": "STRING"},
            "insight_type": {
                "type": "STRING",
                "enum": ["question", "doubt", "problem", "suggestion", "praise"],
            },
            "description": {"type": "STRING"},
            "frequency": {"type": "INTEGER"},
            "avg_severity": {"type": "NUMBER"},
            "avg_actionability": {"type": "NUMBER"},
            "avg_buyer_intent": {"type": "NUMBER"},
            "roi_score": {"type": "NUMBER"},
            "evidence_thread_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
            "source_video_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
            "representative_quotes": {"type": "ARRAY", "items": {"type": "STRING"}},
        },
        "required": [
            "topic", "insight_type", "description", "frequency",
            "avg_severity", "avg_actionability", "avg_buyer_intent",
            "roi_score", "evidence_thread_ids", "source_video_ids",
            "representative_quotes",
        ],
    },
}


class GeminiAnalyzer:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-lite",
                 temperature: float = 0.2, batch_token_budget: int = 10_000,
                 max_output_tokens: int = 4096):
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._temperature = temperature
        self._batch_token_budget = batch_token_budget
        self._max_output_tokens = max_output_tokens

    # ── public API ──────────────────────────────────────────────────

    def extract_insights(self, threads: list[Thread],
                         video_titles: dict[str, str] | None = None,
                         max_batches: int | None = None) -> list[Insight]:
        """Extract atomic insights from threads using token-aware batching."""
        if not threads:
            return []

        batches = self._build_batches(threads, video_titles)
        total = len(batches)
        if max_batches and max_batches < total:
            logger.info("Built %d batches, limiting to %d (--max-batches)", total, max_batches)
            batches = batches[:max_batches]
        else:
            logger.info("Built %d batches from %d threads", total, len(threads))

        all_insights: list[Insight] = []
        for i, batch_text in enumerate(batches, 1):
            logger.info("  Batch %d/%d (%d chars, ~%d tokens)",
                         i, len(batches),
                         len(batch_text), len(batch_text) // CHARS_PER_TOKEN)
            raw = self._call_gemini(batch_text, SYSTEM_PROMPT,
                                    EXTRACTION_RESPONSE_SCHEMA)
            insights = self._parse_extraction(raw)
            all_insights.extend(insights)
            logger.info("    → %d insights extracted", len(insights))

        return all_insights

    @staticmethod
    def _slim_insight_for_aggregation(i: Insight) -> dict:
        """Minimal payload per insight — only fields Gemini needs for semantic grouping."""
        return {
            "t": i.insight_type,
            "topic": i.topic,
            "desc": i.description,
            "sev": i.severity,
            "act": i.actionability,
            "bi": i.buyer_intent,
        }

    def aggregate_insights(self, insights: list[Insight]) -> list[dict]:
        """Three-phase Gemini aggregation.

        Phase 1: batch raw insights (~80) → max 15 topics each (aggressive grouping).
        Phase 2: ultra-slim merge of all intermediate topics → max 20 per batch.
        Phase 3: final merge → 15-30 ranked topics with full descriptions.
        """
        if not insights:
            return []

        PASS1_BATCH = 80
        MERGE_BATCH = 120
        MAX_FINAL_CHARS = 40_000

        slim = [self._slim_insight_for_aggregation(i) for i in insights]
        payload = json.dumps(slim, ensure_ascii=False)

        if len(payload) <= MAX_FINAL_CHARS:
            logger.info("Aggregating %d insights in single pass (%d chars)",
                        len(insights), len(payload))
            raw = self._call_gemini(payload, FINAL_MERGE_SYSTEM_PROMPT,
                                    AGGREGATION_RESPONSE_SCHEMA)
            return self._parse_aggregation(raw)

        # ── Phase 1: aggressive grouping per batch ───────────────────
        batches = [slim[i:i + PASS1_BATCH] for i in range(0, len(slim), PASS1_BATCH)]
        logger.info("Phase 1: %d insights → %d batches (max 15 topics each)",
                     len(insights), len(batches))

        intermediate: list[dict] = []
        for idx, batch in enumerate(batches, 1):
            batch_json = json.dumps(batch, ensure_ascii=False)
            logger.info("  P1 batch %d/%d (%d insights, %d chars)",
                        idx, len(batches), len(batch), len(batch_json))
            raw = self._call_gemini(batch_json, PASS1_SYSTEM_PROMPT,
                                    AGGREGATION_RESPONSE_SCHEMA)
            partial = self._parse_aggregation(raw)
            intermediate.extend(partial)
            logger.info("    → %d topics", len(partial))

        logger.info("Phase 1 complete: %d intermediate topics", len(intermediate))

        # ── Phase 2: ultra-slim merge ────────────────────────────────
        ultra_slim = self._to_ultra_slim(intermediate)
        us_payload = json.dumps(ultra_slim, ensure_ascii=False)

        if len(us_payload) <= MAX_FINAL_CHARS:
            merged = intermediate
        else:
            us_batches = [ultra_slim[i:i + MERGE_BATCH]
                          for i in range(0, len(ultra_slim), MERGE_BATCH)]
            logger.info("Phase 2: %d topics → %d merge batches (max 20 topics each)",
                        len(ultra_slim), len(us_batches))

            merged = []
            for idx, ub in enumerate(us_batches, 1):
                ub_json = json.dumps(ub, ensure_ascii=False)
                logger.info("  P2 batch %d/%d (%d topics, %d chars)",
                            idx, len(us_batches), len(ub), len(ub_json))
                raw = self._call_gemini(ub_json, MERGE_SYSTEM_PROMPT,
                                        AGGREGATION_RESPONSE_SCHEMA)
                merged.extend(self._parse_aggregation(raw))
                logger.info("    → %d topics after merge", len(merged))

        logger.info("Phase 2 complete: %d topics for final merge", len(merged))

        # ── Phase 3: final merge ─────────────────────────────────────
        final_input = self._to_ultra_slim(merged)
        final_payload = json.dumps(final_input, ensure_ascii=False)
        logger.info("Phase 3 (final): %d topics (%d chars)", len(final_input), len(final_payload))
        raw = self._call_gemini(final_payload, FINAL_MERGE_SYSTEM_PROMPT,
                                AGGREGATION_RESPONSE_SCHEMA)
        return self._parse_aggregation(raw)

    @staticmethod
    def _to_ultra_slim(items: list[dict]) -> list[dict]:
        """Strip to bare minimum for merge passes: topic + type + scores."""
        return [
            {
                "topic": it.get("topic", ""),
                "t": it.get("insight_type", "question"),
                "f": it.get("frequency", 1),
                "s": round(it.get("avg_severity", 3), 1),
                "a": round(it.get("avg_actionability", 3), 1),
                "b": round(it.get("avg_buyer_intent", 3), 1),
            }
            for it in items
        ]

    # ── batching ────────────────────────────────────────────────────

    def _build_batches(self, threads: list[Thread],
                       video_titles: dict[str, str] | None = None) -> list[str]:
        """Pack threads into batches that fit within the token budget."""
        budget_chars = self._batch_token_budget * CHARS_PER_TOKEN
        batches: list[str] = []
        current_parts: list[str] = []
        current_len = 0

        for t in threads:
            title = (video_titles or {}).get(t.video_id, t.video_id)
            part = self._format_thread(t, title)
            part_len = len(part)

            if current_len + part_len > budget_chars and current_parts:
                batches.append("\n\n---\n\n".join(current_parts))
                current_parts = []
                current_len = 0

            current_parts.append(part)
            current_len += part_len

        if current_parts:
            batches.append("\n\n---\n\n".join(current_parts))

        return batches

    @staticmethod
    def _format_thread(thread: Thread, video_title: str) -> str:
        header = f"[Video: {video_title}] [Thread: {thread.thread_id}]"
        body = thread.total_text
        return f"{header}\n{body}"

    # ── Gemini calls ────────────────────────────────────────────────

    def _call_gemini(self, user_content: str, system_prompt: str,
                     response_schema: dict) -> str:
        max_attempts = 7
        for attempt in range(max_attempts):
            try:
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=user_content,
                    config={
                        "system_instruction": system_prompt,
                        "temperature": self._temperature,
                        "max_output_tokens": self._max_output_tokens,
                        "response_mime_type": "application/json",
                        "response_schema": response_schema,
                    },
                )
                return response.text
            except Exception as e:
                if attempt < max_attempts - 1:
                    wait = min(2 ** (attempt + 1), 60)
                    logger.warning("Gemini error (attempt %d/%d): %s — retrying in %ds",
                                   attempt + 1, max_attempts, e, wait)
                    time.sleep(wait)
                else:
                    logger.error("Gemini failed after %d attempts: %s", max_attempts, e)
                    raise

    # ── parsing ─────────────────────────────────────────────────────

    @staticmethod
    def _try_fix_truncated_json(raw: str) -> list | None:
        """Recover valid items from a truncated JSON array."""
        raw = raw.strip()
        if not raw.startswith("["):
            return None
        for i in range(len(raw) - 1, 0, -1):
            if raw[i] == "}":
                attempt = raw[: i + 1] + "]"
                try:
                    result = json.loads(attempt)
                    if isinstance(result, list) and result:
                        return result
                except json.JSONDecodeError:
                    continue
        return None

    def _parse_extraction(self, raw_json: str) -> list[Insight]:
        MAX_INSIGHTS_PER_BATCH = 60
        data = None
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            data = self._try_fix_truncated_json(raw_json)
            if data:
                if len(data) > MAX_INSIGHTS_PER_BATCH:
                    logger.warning("Truncated recovery produced %d items (cap %d) — discarding",
                                   len(data), MAX_INSIGHTS_PER_BATCH)
                    data = None
                else:
                    logger.warning("Recovered %d items from truncated extraction JSON", len(data))
            if data is None:
                logger.error("Failed to parse extraction JSON: %s", raw_json[:300])
                return []

        insights: list[Insight] = []
        for item in data:
            try:
                insights.append(Insight(
                    insight_type=item["insight_type"],
                    topic=item["topic"],
                    description=item["description"],
                    severity=max(1, min(5, int(item.get("severity", 3)))),
                    actionability=max(1, min(5, int(item.get("actionability", 3)))),
                    buyer_intent=max(1, min(5, int(item.get("buyer_intent", 3)))),
                    evidence_thread_ids=item.get("evidence_thread_ids", []),
                    source_video_ids=item.get("source_video_ids", []),
                ))
            except (KeyError, ValueError) as e:
                logger.warning("Skipping malformed insight: %s", e)
        return insights

    def _parse_aggregation(self, raw_json: str) -> list[dict]:
        try:
            return json.loads(raw_json)
        except json.JSONDecodeError:
            result = self._try_fix_truncated_json(raw_json)
            if result:
                logger.warning("Recovered %d items from truncated aggregation JSON", len(result))
                return result
            logger.error("Failed to parse aggregation JSON: %s", raw_json[:300])
            return []
