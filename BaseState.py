from typing import Optional
from pydantic import BaseModel, Field
from uuid import uuid4, UUID

class State(BaseModel):

    id: UUID = Field(default_factory=uuid4)

    main_prompt : str
    complete_context_of_whats_done : str = ""
    to_do_notes : str = ""
    current_decision : str = ""

    sections_to_change : list[int] = Field(default_factory=list)
    suggested_changes : list[str] = Field(default_factory=list)

    estimated_duration_in_hours : float
    words_per_minute : int

    sections_completed : int = 0
    no_of_sections_total : Optional[int] = None

    max_turns_per_section : int = 3
    turns_per_current_section : int = 0