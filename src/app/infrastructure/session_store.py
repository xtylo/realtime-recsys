"""Session storage: the last N events of each shopping session.

In-memory on purpose for the foundation. Each process (or Lambda instance) has its own copy,
so production needs a shared store such as DynamoDB: see docs/adr/0001-session-state.md.
A replacement only has to implement the same two methods: `add` and `get`.
"""

from collections import defaultdict, deque


class InMemorySessionStore:
    """Keeps the last N interactions per session. WARNING: lives in the process memory."""

    def __init__(self, max_events: int = 20):
        self._sessions: dict[str, deque] = defaultdict(lambda: deque(maxlen=max_events))

    def add(self, session_id: str, product_id: int, event_type: str) -> None:
        self._sessions[session_id].append((product_id, event_type))

    def get(self, session_id: str) -> list[tuple[int, str]]:
        """Events of the session, oldest first. Empty list for an unknown session."""
        return list(self._sessions.get(session_id, []))
