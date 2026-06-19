import hashlib
import json
import logging
import os
import uuid
from typing import Any, Dict

from google import genai
from google.genai import types
from redis.asyncio import Redis

from backend.services.knowledge_engine.graph.extractors.base_extractor import (
    BaseExtractor,
    ExtractionResult,
    ExtractedRelation,
    IndustrialEntity,
)

logger = logging.getLogger(__name__)


class LLMExtractor(BaseExtractor):
    """
    Uses Gemini to extract complex semantic relationships from unstructured text.
    Caches results in Redis using a text hash to prevent redundant API calls.
    """

    def __init__(self, redis_client: Redis, model: str | None = None):
        self.redis_client = redis_client
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None

        self.system_prompt = (
            "You are an expert industrial maintenance engineer. Extract structured knowledge "
            "from the provided maintenance report. Identify components, failure modes, root "
            "causes, resolution actions, and spare parts used. Output strictly as a JSON object "
            "with the following schema:\n"
            "{\n"
            '  "relations": [\n'
            '    {"source": "EntityA", "relation_type": "CAUSED_BY|RESOLVED_BY|REQUIRES_PART|INDICATES", '
            '"target": "EntityB", "confidence": 0.0-1.0, "sentence_span": "Original text"}\n'
            "  ]\n"
            "}"
        )

    async def extract(self, text: str, doc_metadata: Dict[str, Any]) -> ExtractionResult:
        if not self.client:
            logger.warning("GEMINI_API_KEY not set. LLMExtractor returning empty results.")
            return ExtractionResult()

        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        cache_key = f"ikb:extraction:{text_hash}"

        cached_result = await self.redis_client.get(cache_key)
        if cached_result:
            logger.debug("LLM extraction cache hit for hash %s", text_hash)
            return self._parse_json_to_result(cached_result)

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part(text=f"{self.system_prompt}\n\nDocument:\n{text}")],
                    )
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )

            raw_json = response.text
            if not raw_json:
                return ExtractionResult()

            await self.redis_client.setex(cache_key, 86400, raw_json)
            return self._parse_json_to_result(raw_json)

        except Exception as exc:
            logger.error("Gemini extraction failed: %s", exc)
            return ExtractionResult()

    def _parse_json_to_result(self, raw_json: str | bytes) -> ExtractionResult:
        try:
            data = json.loads(raw_json)
            relations_data = data.get("relations", [])

            relations = []
            entities = []

            for rel in relations_data:
                confidence = float(rel.get("confidence", 1.0))

                source_name = str(rel.get("source"))
                target_name = str(rel.get("target"))

                entities.append(
                    IndustrialEntity(
                        id=str(uuid.uuid4()),
                        label="UNKNOWN",
                        text=source_name,
                        confidence=confidence,
                        start_char=0,
                        end_char=0,
                    )
                )
                entities.append(
                    IndustrialEntity(
                        id=str(uuid.uuid4()),
                        label="UNKNOWN",
                        text=target_name,
                        confidence=confidence,
                        start_char=0,
                        end_char=0,
                    )
                )

                relations.append(
                    ExtractedRelation(
                        source=source_name,
                        relation_type=str(rel.get("relation_type")),
                        target=target_name,
                        confidence=confidence,
                        sentence_span=str(rel.get("sentence_span", "")),
                    )
                )

            return ExtractionResult(entities=entities, relations=relations, confidence=1.0)

        except json.JSONDecodeError as exc:
            logger.error("Failed to parse Gemini JSON: %s", exc)
            return ExtractionResult()
