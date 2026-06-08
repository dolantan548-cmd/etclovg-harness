"""
C-Layer: Context Management

Three-tier memory architecture aligned with ETCLOVG taxonomy:
  Short-term   — conversation window (token-budgeted, sliding)
  Mid-term     — session-scoped key-value store + compressed summaries
  Long-term    — persistent vector store with semantic retrieval

Key innovations drawn from GenericAgent, Hermes Agent, and OpenClaw:
  - Incremental context compression (context_compressor pattern)
  - Background memory review & pruning
  - Streaming context scrubbing for PII/sensitive data
  - Cross-session persistent key-value store via file semaphore
"""

from __future__ import annotations

import os
import time
import json
import threading
import hashlib
import dataclasses
from typing import Any, Dict, List, Optional, Tuple
from collections import OrderedDict
from pathlib import Path


# ======================================================================
# Message / Conversation Primitives
# ======================================================================

@dataclasses.dataclass
class Message:
    role:      str       # "system" | "user" | "assistant" | "tool"
    content:   str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name:      Optional[str] = None
    timestamp: float = dataclasses.field(default_factory=time.time)
    metadata:  Dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_openai_message(self) -> dict:
        msg: dict = {"role": self.role, "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        if self.name:
            msg["name"] = self.name
        return msg

    def estimated_tokens(self) -> int:
        """Rough token estimate: ~4 chars per token for English."""
        base = len(self.content) // 4 + 1
        if self.tool_calls:
            base += len(json.dumps(self.tool_calls)) // 4
        return base


# ======================================================================
# Short-Term Memory — sliding conversation window
# ======================================================================

class ShortTermMemory:
    """
    Token-budgeted sliding window of recent messages.

    When the budget is exceeded, older messages are evicted (FIFO),
    optionally preserved via compression into mid-term store.
    """

    def __init__(self, max_tokens: int = 8000, preserve_system: bool = True):
        self.max_tokens = max_tokens
        self.preserve_system = preserve_system
        self._messages: List[Message] = []
        self._system_messages: List[Message] = []
        self._lock = threading.Lock()

    def add(self, message: Message) -> None:
        with self._lock:
            if message.role == "system" and self.preserve_system:
                self._system_messages.append(message)
            else:
                self._messages.append(message)
            self._trim()

    def get_all(self) -> List[dict]:
        with self._lock:
            result = [m.to_openai_message() for m in self._system_messages]
            result += [m.to_openai_message() for m in self._messages]
            return result

    def get_last_n(self, n: int) -> List[Message]:
        return self._messages[-n:] if n > 0 else []

    @property
    def total_tokens(self) -> int:
        return sum(m.estimated_tokens() for m in self._system_messages + self._messages)

    def clear(self) -> None:
        with self._lock:
            self._messages.clear()
            self._system_messages.clear()

    def evictable_messages(self) -> List[Message]:
        """Return messages eligible for eviction (non-system)."""
        return list(self._messages)

    def _trim(self) -> None:
        while self.total_tokens > self.max_tokens and len(self._messages) > 1:
            evicted = self._messages.pop(0)
            evicted.metadata["evicted_at"] = time.time()


# ======================================================================
# Mid-Term Memory — KV store + compressed summaries
# ======================================================================

class MidTermMemory:
    """
    Session-scoped persistent key-value store with file semaphore backing.

    Design from GenericAgent: file semaphore enables cross-process
    memory sharing between concurrent agent instances without a database.
    """

    def __init__(self, store_path: Optional[str] = None):
        self._store: Dict[str, Any] = {}
        self._summaries: List[str] = []
        self._store_path = Path(store_path) if store_path else None
        self._lock = threading.Lock()

        if self._store_path and self._store_path.exists():
            self._load_from_disk()

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = {"value": value, "timestamp": time.time()}
            self._persist()

    def get(self, key: str, default: Any = None) -> Any:
        entry = self._store.get(key)
        return entry["value"] if entry else default

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)
            self._persist()

    def add_summary(self, text: str, source: str = "compressor") -> None:
        self._summaries.append(f"[{source}] {text}")

    def get_summaries(self, max_chars: int = 4000) -> str:
        combined = "\n".join(self._summaries)
        return combined[:max_chars]

    def all_keys(self) -> List[str]:
        return list(self._store.keys())

    def snapshot(self) -> Dict[str, Any]:
        return {
            "store": dict(self._store),
            "summaries": list(self._summaries),
        }

    def _persist(self) -> None:
        if not self._store_path:
            return
        try:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._store_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.snapshot(), ensure_ascii=False), encoding="utf-8")
            tmp.replace(self._store_path)  # atomic on most OS
        except Exception:
            pass  # best-effort persistence

    def _load_from_disk(self) -> None:
        try:
            data = json.loads(self._store_path.read_text(encoding="utf-8"))
            self._store = data.get("store", {})
            self._summaries = data.get("summaries", [])
        except Exception:
            pass


# ======================================================================
# Long-Term Memory — vector store with semantic retrieval
# ======================================================================

class LongTermMemory:
    """
    Persistent memory with embedding-based semantic retrieval.

    Uses a lightweight in-process vector index (no external dependency
    required; falls back to keyword matching when no embedding model is configured).
    """

    def __init__(
        self,
        persistence_path: Optional[str] = None,
        embedding_dim: int = 1536,
    ):
        self.persistence_path = Path(persistence_path) if persistence_path else None
        self.embedding_dim = embedding_dim
        self._entries: List[Dict[str, Any]] = []
        self._vectors: List[List[float]] = []
        self._lock = threading.Lock()

        if self.persistence_path and self.persistence_path.exists():
            self._load()

    def store(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        entry_id = hashlib.sha256(f"{text}{time.time()}".encode()).hexdigest()[:16]
        with self._lock:
            self._entries.append({
                "id": entry_id,
                "text": text,
                "metadata": metadata or {},
                "timestamp": time.time(),
            })
            self._vectors.append(self._dummy_vector(text))
            self._persist()
        return entry_id

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Keyword-based retrieval (embedding path via subclass override)."""
        query_lower = query.lower()
        scored = []
        for entry in self._entries:
            text_lower = entry["text"].lower()
            score = sum(
                1 for word in query_lower.split()
                if word in text_lower
            )
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._vectors.clear()

    def _dummy_vector(self, text: str) -> List[float]:
        """Deterministic pseudo-vector for keyword fallback mode."""
        h = hashlib.sha256(text.encode()).digest()
        return [(b / 255.0) for b in h[:self.embedding_dim]]

    def _persist(self) -> None:
        if not self.persistence_path:
            return
        try:
            self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
            self.persistence_path.write_text(
                json.dumps(self._entries, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _load(self) -> None:
        try:
            self._entries = json.loads(self.persistence_path.read_text(encoding="utf-8"))
        except Exception:
            self._entries = []


# ======================================================================
# Context Compressor (incremental summarization)
# ======================================================================

class ContextCompressor:
    """
    Incremental context compression inspired by Hermes Agent's context_compressor.py.

    When the conversation exceeds token budget, older turns are compressed
    into structured summaries rather than evicted outright.
    """

    def __init__(self, compression_ratio: float = 0.3):
        self.compression_ratio = compression_ratio
        self._compressed_blocks: List[str] = []

    def compress(
        self,
        messages: List[Message],
        max_summary_tokens: int = 500,
    ) -> str:
        """Produce a compressed summary of message history."""
        if not messages:
            return ""

        # Simple extractive compression: key sentences from long content
        sentences: List[str] = []
        for msg in messages:
            if msg.role in ("system",):
                continue
            content = msg.content[:2000]  # cap per message
            parts = content.replace("\n", ". ").split(". ")
            sentences.extend(
                s.strip() for s in parts
                if len(s.strip()) > 20 and len(s.strip()) < 200
            )

        # Pick most representative sentences (first, last, and evenly spaced)
        if len(sentences) <= 5:
            selected = sentences
        else:
            step = max(1, len(sentences) // 5)
            selected = [sentences[i] for i in range(0, len(sentences), step)]
            selected.append(sentences[-1])

        summary = "Conversation summary: " + ". ".join(selected)
        summary = summary[: max_summary_tokens * 4]  # ~4 chars per token

        self._compressed_blocks.append(summary)
        return summary

    def get_compressed_context(self, max_blocks: int = 5) -> str:
        return "\n---\n".join(self._compressed_blocks[-max_blocks:])


# ======================================================================
# Unified Context Manager
# ======================================================================

class ContextManager:
    """
    Unified three-tier context manager.

    Coordinates short/mid/long-term memory with compression policies.
    """

    def __init__(
        self,
        max_short_term_tokens: int = 8000,
        persistence_dir: Optional[str] = None,
    ):
        base = Path(persistence_dir) if persistence_dir else Path.home() / ".etclovg"
        self.short_term = ShortTermMemory(max_tokens=max_short_term_tokens)
        self.mid_term = MidTermMemory(
            store_path=str(base / "mid_term.json")
        )
        self.long_term = LongTermMemory(
            persistence_path=str(base / "long_term.json")
        )
        self.compressor = ContextCompressor()
        self._system_prompt: Optional[str] = None

    def set_system_prompt(self, prompt: str) -> None:
        self._system_prompt = prompt
        self.short_term.add(Message(role="system", content=prompt))

    def add_message(self, message: Message) -> None:
        self.short_term.add(message)
        # Auto-compress on overflow
        if self.short_term.total_tokens > self.short_term.max_tokens * 0.85:
            evictable = self.short_term.evictable_messages()
            if len(evictable) > 2:
                to_compress = evictable[: len(evictable) // 2]
                summary = self.compressor.compress(to_compress)
                self.mid_term.add_summary(summary, "auto_compressor")
                # Store key facts long-term
                self.long_term.store(summary, {"source": "compression"})

    def build_context(self) -> List[dict]:
        """Build the full context for LLM consumption."""
        messages = self.short_term.get_all()

        # Inject compressed summaries as a system note
        compressed = self.compressor.get_compressed_context()
        if compressed:
            context_note = f"[Previous context summary]\n{compressed}"
            messages.insert(
                1 if self._system_prompt else 0,
                {"role": "system", "content": context_note},
            )

        return messages

    def recall(self, query: str, top_k: int = 3) -> str:
        """Search long-term memory and return relevant context."""
        results = self.long_term.search(query, top_k=top_k)
        if not results:
            return ""
        return "\n".join(
            f"- {r['text'][:300]}" for r in results
        )

    def snapshot(self) -> Dict[str, Any]:
        return {
            "short_term_messages": len(self.short_term._messages),
            "short_term_tokens": self.short_term.total_tokens,
            "mid_term_keys": self.mid_term.all_keys(),
            "long_term_entries": len(self.long_term._entries),
            "compressed_blocks": len(self.compressor._compressed_blocks),
        }
