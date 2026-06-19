import json
import logging
from typing import Any, Dict, List
from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class EpisodicMemory:
    """
    Redis-backed conversational memory for agents.
    Implements a sliding window (max 50 turns) and 8-hour shift-based TTL.
    Uses LLM-powered summarization to compress older turns while preserving
    key diagnostic findings, actions taken, anomalies, and machine IDs.
    """

    def __init__(self, redis_client: Redis, llm_client: Any, max_turns: int = 50, ttl_seconds: int = 28800) -> None:
        self.redis_client = redis_client
        self.llm_client = llm_client
        self.max_turns = max_turns
        self.ttl_seconds = ttl_seconds

    def _key(self, session_id: str) -> str:
        return f"agent:memory:episodic:{session_id}"

    async def append(self, session_id: str, role: str, content: str, metadata: Dict[str, Any] = None) -> None:
        """Append a message to the episodic memory."""
        key = self._key(session_id)
        msg = {
            "role": role,
            "content": content,
            "metadata": metadata or {}
        }

        # Pipeline all three commands into one round-trip (~1ms saved vs 3 sequential RTTs)
        async with self.redis_client.pipeline(transaction=False) as pipe:
            pipe.rpush(key, json.dumps(msg))
            pipe.ltrim(key, -self.max_turns, -1)
            pipe.expire(key, self.ttl_seconds)
            await pipe.execute()

    async def get_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieve the full history for a session."""
        key = self._key(session_id)
        raw_msgs = await self.redis_client.lrange(key, 0, -1)
        
        history = []
        for rm in raw_msgs:
            try:
                history.append(json.loads(rm))
            except json.JSONDecodeError:
                continue
                
        return history

    async def summarize_if_needed(self, session_id: str, current_token_count: int, threshold: int = 4096) -> None:
        """
        Auto-summarize when token budget is exceeded.
        Compresses old turns via LLM, keeps the last 10 verbatim.
        On LLM failure, retains original messages (graceful degradation).
        """
        if current_token_count < threshold:
            return
            
        history = await self.get_history(session_id)
        
        if len(history) <= 10:
            return
            
        old_msgs = history[:-10]
        recent_msgs = history[-10:]
        
        # Build the conversation transcript for summarization
        transcript_lines = [f"{msg['role']}: {msg['content']}" for msg in old_msgs]
        transcript = "\n".join(transcript_lines)
        
        prompt = (
            "You are a senior industrial diagnostics assistant. Summarize the following "
            "diagnostic conversation history into a concise context summary. Preserve:\n"
            "- Key diagnostic findings and conclusions\n"
            "- Actions taken or recommended\n"
            "- Anomalies and faults detected\n"
            "- All machine IDs, sensor IDs, and equipment references mentioned\n"
            "- Any unresolved issues or pending investigations\n\n"
            "Be concise but do not omit critical technical details.\n\n"
            f"Conversation ({len(old_msgs)} messages):\n{transcript}"
        )
        
        try:
            summary = await self.llm_client.complete(prompt)
            logger.info(
                "Summarized %d messages for session %s (token count was %d).",
                len(old_msgs), session_id, current_token_count
            )
        except Exception as e:
            logger.warning(
                "LLM summarization failed for session %s, retaining original messages: %s",
                session_id, str(e)
            )
            return
        
        summarized_msg: Dict[str, Any] = {
            "role": "system",
            "content": f"[DIAGNOSTIC SESSION CONTEXT SUMMARY]\n{summary}",
            "metadata": {"type": "summary", "summarized_count": len(old_msgs)}
        }
        
        key = self._key(session_id)
        await self.redis_client.delete(key)
        
        new_list = [summarized_msg] + recent_msgs
        for msg in new_list:
            await self.redis_client.rpush(key, json.dumps(msg))
            
        await self.redis_client.expire(key, self.ttl_seconds)
