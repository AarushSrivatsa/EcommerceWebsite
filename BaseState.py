from typing import Optional
from pydantic import BaseModel, Field
from uuid import uuid4, UUID

class BaseState(BaseModel):
    # Basic information
    id: UUID = Field(default_factory=uuid4)
    user_prompt : str

    # generation details
    progress_context : Optional[str] = None
    user_prompted_sectional_changes : Optional[list[dict]] = None
    sections_completed : Optional[int] = None

    # generator manager
    router_prompt : Optional[str] = None
    generator_response : Optional[str] = None
    similarity_score : Optional[float] = None
    similarity_threshold : Optional[float] = None
    generated_response_title : Optional[str] = None
    generated_response_word_count : Optional[int] = None

    # duration information
    estimated_duration_in_hours : float
    words_per_minute : int
    total_sections : Optional[int] = None
    



