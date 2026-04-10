"""Pydantic models for the Phase 3 learning loop.

These models represent the data flowing between agents and the knowledge store.
They are NOT ORM models — they are typed containers for:
  - Knowledge gap descriptions (GapInfo, GapRecord)
  - Agent task and result records (AgentTaskRecord, AgentResultRecord)
  - Agent findings output (FindingItem, AgentFindings)
  - Operation classification (UpdateOp)
"""

from enum import Enum

from pydantic import BaseModel


class GapInfo(BaseModel):
    """A knowledge gap to be investigated.

    Minimal representation used when creating a new gap — before it is
    persisted and assigned an id.
    """

    gap_type: str                       # e.g. "missing_docs", "unresolved_relationship"
    entity_type: str                    # "table", "column", "sp", "relationship"
    entity_id: int | None = None        # FK to the entity (nullable for system-level gaps)
    entity_name: str                    # human-readable name for display
    description: str | None = None     # optional detail about what is unknown
    severity: float = 0.5              # 0.0-1.0, higher = more critical


class GapRecord(BaseModel):
    """A persisted knowledge gap record read from the knowledge_gaps table.

    Extends GapInfo with storage fields populated after INSERT.
    """

    id: int
    gap_type: str
    entity_type: str
    entity_id: int | None = None
    entity_name: str
    description: str | None = None
    severity: float = 0.5
    priority_score: float = 0.0
    status: str = "open"
    attempt_count: int = 0
    cooldown_until: str | None = None
    cooldown_until_ts: int | None = None
    last_attempt_at: str | None = None
    human_confirmed: bool = False
    recorded_at_ts: int = 0


class AgentTaskRecord(BaseModel):
    """A persisted agent task record read from the agent_tasks table."""

    id: int
    gap_id: int
    agent_type: str                     # research|review|collector
    status: str = "pending"            # pending|running|done|failed
    input_json: str | None = None      # JSON blob of agent input parameters


class AgentResultRecord(BaseModel):
    """A persisted agent result record read from the agent_results table."""

    id: int
    task_id: int
    agent_type: str
    success: bool = False
    findings_json: str | None = None   # JSON blob of structured findings
    rationale: str | None = None       # free-text explanation
    approved: bool | None = None       # None=pending, True=approved, False=rejected


class UpdateOp(str, Enum):
    """Classification of how a new finding relates to existing knowledge.

    Used by the Reason/Validate agents to decide what to do with findings.
    """

    ADD = "ADD"             # New fact, no conflict
    REINFORCE = "REINFORCE" # Confirms existing fact, increases confidence
    CONFLICT = "CONFLICT"   # Contradicts existing fact, needs escalation
    NOOP = "NOOP"           # No useful information gained


class FindingItem(BaseModel):
    """A single structured finding from an agent investigation.

    Represents one atomic fact discovered about an entity attribute.
    """

    entity_type: str
    entity_name: str
    attribute: str          # what attribute was discovered (e.g. "description", "type")
    value: str              # the discovered value
    confidence: float = 0.5
    source: str | None = None  # where the finding came from (SP name, DDL file, etc.)


class AgentFindings(BaseModel):
    """Structured output from an agent run.

    Aggregates multiple FindingItems with overall quality metadata.
    Serialized to findings_json in agent_results.
    """

    items: list[FindingItem] = []
    summary: str = ""
    evidence_quality: float = 0.5   # 0.0-1.0 overall quality of the evidence
