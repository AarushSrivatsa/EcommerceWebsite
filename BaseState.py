from typing import Optional
from pydantic import BaseModel, Field
from uuid import uuid4, UUID

class BaseState(BaseModel):
    # Basic information
    id: UUID = Field(default_factory=uuid4)
    user_prompt : str

    # generation details
    progress_context : Optional[str] = None
    user_prompted_sectional_changes : Optional[dict[int, str]] = None   # {1: "make it funnier", 4: "shorter"}
    sections_completed : Optional[int] = None
    video_type : Optional[str] = None            # "facts" or "story", decided by the router

    # generator manager
    router_prompt : Optional[str] = None
    generator_response : Optional[str] = None
    similarity_score : Optional[float] = None
    similarity_threshold : Optional[float] = None    # None = default for the video type
    generated_response_title : Optional[str] = None
    generated_response_word_count : Optional[int] = None

    # duration information
    estimated_duration_in_hours : float
    words_per_minute : int
    total_sections : Optional[int] = None

    # router control
    next_step : Optional[str] = None             # router: write/push/review   review: rewrite/render/review
    current_section : Optional[int] = None
    rewrite_attempts : int = 0
    section_word_limit_error_percentage : float = 10.0

    # output
    voice_model : str = "af_heart"
    audio_path : Optional[str] = None
    video_path : Optional[str] = None

    # progress
    current_node : Optional[str] = None