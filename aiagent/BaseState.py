from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class BaseState(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    user_prompt: str

    # Generation context
    progress_context: str | None = None
    user_prompted_sectional_changes: dict[int, str] | None = None
    sections_completed: int | None = None
    video_type: str | None = None

    # Writer and similarity checks
    router_prompt: str | None = None
    generator_response: str | None = None
    similarity_score: float | None = None
    similarity_threshold: float | None = None
    grounding_score: float | None = None
    grounding_feedback: str | None = None
    retrieved_sources: list[dict] | None = None
    visual_plan: list[dict] | None = None
    generated_response_title: str | None = None
    generated_response_word_count: int | None = None

    # Duration
    estimated_duration_in_hours: float
    words_per_minute: int
    total_sections: int | None = None

    # Router control
    next_step: str | None = None
    current_section: int | None = None
    rewrite_attempts: int = 0
    section_word_limit_error_percentage: float = 10.0

    # Used later by the video service
    voice_model: str = "Zoey"

    # Progress
    current_node: str | None = None

    # Project-scoped research index lifecycle
    research_complete: bool = False
    research_status: str = "pending"
    research_error: str | None = None
