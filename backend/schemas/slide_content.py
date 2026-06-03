"""This is the final content for each slide — actual title, bullets,
diagram description, speaker notes, and the layout template ready to be
placed into the PPT."""
from pydantic import BaseModel
from typing import Optional
from schemas.slide_plan import TemplateType


class TableBlock(BaseModel):
    """
    Structured rendition of a table found in the source PDF.

    Used by `table_slide` (table-only) and `theory_table_slide` (theory bullets
    above a table). The renderer turns this into a real PowerPoint table — not
    bullet text — so columns line up and the data stays scannable.

    Field rules for the writer:
      • headers    : column titles, exactly as in the source. First entry may
                     be a row-label column header (e.g. "Year", "n"); leave it
                     empty string "" if the source's top-left cell is blank.
      • rows       : list of rows; every row MUST have len(row) == len(headers).
                     Cells should be the raw value (e.g. "0.869", "$5,000",
                     "Yes") with no markdown or bullet markers. Use "" for
                     genuinely empty cells.
      • caption    : optional short caption shown above the table (e.g.
                     "Discount factors for n = 1..4"). Keep ≤ 80 chars.
      • column_alignments (optional) : per-column alignment hints — one of
                     "left" / "center" / "right". If omitted the renderer
                     left-aligns text and right-aligns numbers heuristically.
    """
    headers:            list[str]
    rows:               list[list[str]]
    caption:            Optional[str] = None
    column_alignments:  Optional[list[str]] = None


class SlideContent(BaseModel):
    slide_number:        int
    title:               str
    bullets:             list[str]
    diagram_description: Optional[str] = None
    speaker_notes:       str
    layout:              TemplateType

    # ── passage_slide (cloze / reading-comprehension) only ───────────────────
    # `directions` is the banner line ("Directions (Q. 22-24): Cloze Test –
    # Passage 1"); `passage_text` is the VERBATIM paragraph with every blank
    # (__X__, .....(1).....) preserved exactly as in the source PDF — never
    # filled, paraphrased, or summarised.
    directions:          Optional[str] = None
    passage_text:        Optional[str] = None

    # ── table_slide / theory_table_slide only ────────────────────────────────
    # Structured table extracted from the source page. Required when layout is
    # `table_slide` or `theory_table_slide`; ignored otherwise.
    table_data:          Optional[TableBlock] = None