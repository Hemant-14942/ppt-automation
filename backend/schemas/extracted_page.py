"""Defines what Gemini Vision returns for each PDF page."""

from pydantic import BaseModel
from typing import Optional
from enum import Enum


class ContentType(str, Enum):
    text_heavy   = "text_heavy"
    diagram      = "diagram"
    mixed        = "mixed"
    mostly_blank = "mostly_blank"


class AnnotationType(str, Enum):
    circle      = "circle"
    underline   = "underline"
    tick        = "tick"
    cross       = "cross"
    highlight   = "highlight"
    handwritten = "handwritten"
    other       = "other"


class Annotation(BaseModel):
    type:        AnnotationType
    target:      str
    instruction: str


class ExtractedPage(BaseModel):
    page_number:        int
    content_type:       ContentType
    main_text:          str
    diagrams_described: Optional[str] = None
    annotations:        list[Annotation] = []
    instructor_notes:   Optional[str] = None
    should_skip:        bool
