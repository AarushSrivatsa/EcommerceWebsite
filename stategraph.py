from typing import Optional
from pydantic import BaseModel

class State(BaseModel):

    main_prompt : str
    complete_context_of_whats_done : str = ""
    to_do_notes : str = ""
    current_decision : str = ""

    section_user_wants_changed : Optional[int] = None
    user_suggested_changes : Optional[str] = None

    estimated_duration_in_hours : float
    words_per_minute : int

    sections_completed : int = 0
    no_of_sections_total : Optional[int] = None

    max_turns_per_section : int = 3
    turns_per_current_section : int = 0