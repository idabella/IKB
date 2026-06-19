import logging
import uuid
from typing import Any, Dict

from pydantic import BaseModel, ConfigDict

from backend.shared.infrastructure.messaging.kafka_producer import KafkaMessageProducer
from backend.services.knowledge_engine.graph.graph_db.neo4j_client import Neo4jClient
from backend.services.knowledge_engine.graph.extractors.relation_extractor import RelationExtractor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Relationship-type whitelist
#
# WHY a frozenset: O(1) lookup + immutable at runtime — no accidental mutation
# by any import consumer.
#
# HOW TO EXTEND WITHOUT A CODE DEPLOY (pick one strategy and document it in
# your runbook):
#
#   Option A — Database config table:
#       SELECT rel_type FROM graph_config.valid_relationship_types WHERE active = TRUE;
#       Load at application startup and store in a module-level set. Refresh on
#       SIGHUP or via a background task (e.g. every 5 min). Access is already
#       controlled by your Neo4j/Postgres IAM rules.
#
#   Option B — Environment variable (JSON array, good for k8s ConfigMaps):
#       EXTRA_REL_TYPES='["TRIGGERS","DEPENDS_ON"]'
#       Parse in setup and union with the base frozenset below. Operations
#       update the ConfigMap; pods pick it up on next rollout (no image rebuild).
#
#   Option C — Remote config (e.g. AWS AppConfig, LaunchDarkly):
#       Gives you instant push-based updates with audit trail and rollback.
#
# Keep this base set as the hardened minimum that is always present; the
# extension mechanism adds to it, never replaces it.
# ---------------------------------------------------------------------------
VALID_RELATIONSHIP_TYPES: frozenset[str] = frozenset(
    {
        "HAS_COMPONENT",
        "HAS_SENSOR",
        "CAN_FAIL_WITH",
        "INDICATES",
        "RESOLVED_BY",
        "PROPAGATES_TO",
        "CONNECTED_TO",
        "MONITORS",
        "CAUSED_BY",
    }
)


class ExtractEntitiesCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    doc_id: str
    text: str
    doc_type: str
    tenant_id: str


class ExtractEntitiesHandler:
    """
    CQRS Handler orchestrating the full extraction pipeline.
    Runs extractors, upserts to Neo4j, and broadcasts the event.
    """

    def __init__(
        self,
        relation_extractor: RelationExtractor,
        neo4j_client: Neo4jClient,
        kafka_producer: KafkaMessageProducer,
    ):
        self.relation_extractor = relation_extractor
        self.neo4j_client = neo4j_client
        self.kafka_producer = kafka_producer

    @staticmethod
    def _sanitize_relationship_type(raw: str) -> str | None:
        """Normalise and whitelist-check a raw LLM-supplied relationship type.

        Returns the sanitized string if it is a known type, or ``None`` if it
        must be rejected.  The caller is responsible for skipping the
        relationship when ``None`` is returned.

        Keeping this as a static method makes it trivially unit-testable in
        isolation — no graph connection or Kafka broker required.
        """
        # Normalise: uppercase, collapse spaces and hyphens to underscores.
        # Apply the same transformation that was previously used inline so
        # existing Neo4j data is not affected.
        sanitized: str = (
            raw.strip()
               .upper()
               .replace(" ", "_")
               .replace("-", "_")
        )

        if sanitized not in VALID_RELATIONSHIP_TYPES:
            logger.warning(
                "LLM returned unknown relationship type '%s' (normalised: '%s') "
                "— skipping relationship creation. "
                "If this type is intentional, add it to VALID_RELATIONSHIP_TYPES "
                "or the runtime extension mechanism.",
                raw,
                sanitized,
            )
            return None

        logger.debug(
            "Relationship type '%s' passed whitelist check → '%s'",
            raw,
            sanitized,
        )
        return sanitized

    async def handle(self, cmd: ExtractEntitiesCommand) -> None:
        logger.info(
            "Extracting entities for doc_id=%s, doc_type=%s",
            cmd.doc_id,
            cmd.doc_type,
        )

        doc_metadata = {
            "doc_id": cmd.doc_id,
            "tenant_id": cmd.tenant_id,
            "doc_type": cmd.doc_type,
        }

        # 1. & 2. & 3. Run extractors and merge
        result = await self.relation_extractor.extract(cmd.text, doc_metadata)

        if not result.entities and not result.relations:
            logger.warning(
                "No entities or relations found for doc_id=%s", cmd.doc_id
            )
            return

        # 4. Upsert Entities to Neo4j
        for ent in result.entities:
            ent_text = ent.text.replace("'", "").replace('"', "")

            label = (
                "Machine"         if ent.label == "MACHINE_ID"   else
                "SparePartSKU"    if ent.label == "PART_NUMBER"   else
                "FailureMode"     if ent.label == "ERROR_CODE"    else
                "ExtractedEntity"
            )

            query = """
                MERGE (e:{label} {{name: $name}})
                SET e.label = $entity_label, e.last_seen_in_doc = $doc_id
            """.format(label=label)   # label comes from the closed if/else above — not LLM input

            try:
                await self.neo4j_client.execute_write(
                    query,
                    {
                        "name": ent_text,
                        "entity_label": ent.label,
                        "doc_id": cmd.doc_id,
                    },
                )
            except Exception as e:
                logger.error("Failed to upsert entity %s: %s", ent.text, e)

        # 5. Create Relationships
        for rel in result.relations:
            # ------------------------------------------------------------------
            # SECURITY: rel.relation_type originates from LLM output and MUST
            # NOT be interpolated into Cypher without whitelist validation.
            # Neo4j does not support parameterised relationship type names, so
            # string interpolation is unavoidable — the whitelist is the only
            # guard between an untrusted string and the graph database engine.
            # ------------------------------------------------------------------
            sanitized_rel_type = self._sanitize_relationship_type(
                rel.relation_type or ""
            )
            if sanitized_rel_type is None:
                # _sanitize_relationship_type already logged a warning; move on
                # so the remaining relations and the Kafka event are not lost.
                continue

            source = rel.source.replace("'", "").replace('"', "")
            target = rel.target.replace("'", "").replace('"', "")

            # Only `sanitized_rel_type` — which has passed the whitelist — is
            # interpolated here. `source`, `target`, and scalar values are
            # always passed as Cypher parameters ($…), never interpolated.
            query = f"""
                MATCH (s) WHERE s.name = $source
                MATCH (t) WHERE t.name = $target
                MERGE (s)-[r:{sanitized_rel_type}]->(t)
                SET r.confidence = $confidence, r.sentence = $sentence
            """

            try:
                await self.neo4j_client.execute_write(
                    query,
                    {
                        "source": source,
                        "target": target,
                        "confidence": rel.confidence,
                        "sentence": rel.sentence_span,
                    },
                )
            except Exception as e:
                logger.error(
                    "Failed to upsert relation %s-[%s]->%s: %s",
                    source,
                    sanitized_rel_type,
                    target,
                    e,
                )

        # 6. Emit EntityExtracted Event
        payload = {
            "event_type": "EntityExtracted",
            "doc_id": cmd.doc_id,
            "tenant_id": cmd.tenant_id,
            "entity_count": len(result.entities),
            "relation_count": len(result.relations),
        }

        await self.kafka_producer.send(
            topic="ikb.graph.updates",
            value=payload,
            key=cmd.doc_id,
        )

        logger.info(
            "Extraction complete. Upserted %d entities and %d relations for doc %s",
            len(result.entities),
            len(result.relations),
            cmd.doc_id,
        )