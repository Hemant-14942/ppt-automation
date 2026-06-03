"""
Direct pipeline runner — no server needed.
Run: venv/bin/python3 run_pipeline.py
"""

import asyncio
import sys
import os

# add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from pipeline.orchestrator import run_pipeline_async
from schemas.request import PDFContext, AnnotationItem

# ── Context for Source File 1.pdf ────────────────────────────────────────────
# SSC CGL/CPO One Word Substitution question bank
# Blue circles = questions to include in the PPT

context = PDFContext(
    subject      = "English",
    batch        = "SSC CGL CPO",
    purpose      = "DPP",
    class_level  = "Competitive exam",
    language     = "English",
    extra_context= (
        "This is a One Word Substitution question bank for SSC CGL and CPO exams. "
        "Each question has 4 options (a, b, c, d) with one correct answer. "
        "Blue circles mark questions that MUST be included in the presentation. "
        "Include the question text, all 4 options, and the correct answer for each question. "
        "Group similar types of one word substitution together (e.g., words for people, "
        "words for actions, words for places). "
        "Each slide should have maximum 3-4 questions so they are readable."
    ),
    annotations  = [
        AnnotationItem(
            id       = "circle",
            type     = "circle",
            label    = "Blue circle",
            selected = True,
            reason   = "This question MUST be included in the PPT — do not skip it"
        ),
        AnnotationItem(
            id       = "strikethrough",
            type     = "other",
            label    = "Strikethrough on exam name/date",
            selected = True,
            customName = "Strikethrough",
            reason   = "Just marks the exam source — ignore for content, keep for reference"
        ),
    ]
)

pdf_path = os.path.join(os.path.dirname(__file__), "Source File 1.pdf")


async def main():
    print(f"PDF: {pdf_path}")
    print(f"Subject: {context.subject} | Batch: {context.batch} | Purpose: {context.purpose}")
    print()

    result = await run_pipeline_async(pdf_path, context)

    print()
    if result["status"] == "success":
        out = os.path.join(os.path.dirname(__file__), "backend", "outputs", result["filename"])
        print(f"SUCCESS: {result['filename']}")
        print(f"Pages read  : {result['total_pages']}")
        print(f"Slides made : {result['total_slides']}")
        print(f"Output path : {out}")
    else:
        print(f"ERROR: {result['message']}")


if __name__ == "__main__":
    asyncio.run(main())
