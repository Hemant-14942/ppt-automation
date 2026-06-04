import os
import json
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from schemas.request import PDFContext, AnnotationItem, GenerateResponse
from pipeline.orchestrator import run_pipeline_async
from pipeline.pptx_to_pdf import (
    convert_pptx_to_pdf,
    is_available as libreoffice_available,
    LibreOfficeNotInstalled,
)
from config import UPLOAD_DIR, OUTPUT_DIR, STORAGE_BACKEND
import uuid
from storage.s3_storage import upload_file_to_s3, create_presigned_download_url


router = APIRouter()


@router.post("/generate", response_model=GenerateResponse)
async def generate_ppt(
    pdf_file: UploadFile = File(...),
    context_json: str = Form(...)
):
    """
    Main endpoint — receives PDF + form context, returns PPT info.

    Frontend sends:
    - pdf_file:     the actual PDF file (multipart upload)
    - context_json: form data as JSON string
    """

    # ── validate file type ──────────────────────────
    if not pdf_file.filename.endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are accepted"
        )

    # ── parse form context ──────────────────────────
    try:
        context_data = json.loads(context_json)
        context = PDFContext(**context_data)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid form data: {e}"
        )

    # ── save uploaded PDF temporarily ───────────────
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    job_id = str(uuid.uuid4())

    if STORAGE_BACKEND == "s3":
        pdf_path = os.path.join(UPLOAD_DIR, f"{job_id}.pdf")
    else:
        pdf_path = os.path.join(UPLOAD_DIR, pdf_file.filename)

    with open(pdf_path, "wb") as f:
        content = await pdf_file.read()
        f.write(content)

    print(f"  PDF saved → {pdf_path}")

    # ── run pipeline ────────────────────────────────
    result = await run_pipeline_async(pdf_path, context)

    # ── upload generated PPT to S3 in production ─────
    filename = result.get("filename")

    if STORAGE_BACKEND == "s3" and result.get("status") == "success" and filename:
        pptx_path = os.path.join(OUTPUT_DIR, filename)
        s3_key = f"outputs/{job_id}/{filename}"

        try:
            upload_file_to_s3(
                local_path=pptx_path,
                s3_key=s3_key,
                content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            )
            result["job_id"] = job_id
            result["download_url"] = create_presigned_download_url(s3_key)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"PPT generated but S3 upload failed: {e}",
            )

        # ── cleanup local PPT ──────────────────────────
        try:
            os.remove(pptx_path)
            print(f"  Cleaned up local PPT → {pptx_path}")
        except Exception:
            pass
    # ── cleanup uploaded PDF ────────────────────────
    try:
        os.remove(pdf_path)
        print(f"  Cleaned up → {pdf_path}")
    except Exception:
        pass  # not critical if cleanup fails

    # ── return result ───────────────────────────────
    return GenerateResponse(**result)


@router.get("/download/{filename}")
async def download_ppt(filename: str):
    """
    Download endpoint — frontend calls this to get the .pptx file.
    """

    file_path = os.path.join(OUTPUT_DIR, filename)

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail="File not found"
        )

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )


@router.get("/download-pdf/{filename}")
async def download_pdf(filename: str):
    """
    Download endpoint — converts a generated .pptx to PDF and returns it as an
    attachment. This requires LibreOffice on the backend.
    """
    pptx_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(pptx_path):
        raise HTTPException(status_code=404, detail="PPT file not found")

    try:
        pdf_path = convert_pptx_to_pdf(pptx_path)
    except LibreOfficeNotInstalled as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF export failed: {e}")

    pdf_filename = os.path.splitext(os.path.basename(filename))[0] + ".pdf"
    return FileResponse(
        path=pdf_path,
        filename=pdf_filename,
        media_type="application/pdf",
    )


@router.get("/preview/{filename}")
async def preview_ppt(filename: str):
    """
    Render a generated .pptx as a PDF stream so the frontend can embed it
    in an <iframe> for slide preview. The PDF is cached next to the .pptx
    and only re-generated when the .pptx changes.
    """
    pptx_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(pptx_path):
        raise HTTPException(status_code=404, detail="PPT file not found")

    try:
        pdf_path = convert_pptx_to_pdf(pptx_path)
    except LibreOfficeNotInstalled as e:
        # 501 Not Implemented — frontend can show a friendly message
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview failed: {e}")

    pdf_filename = os.path.basename(pdf_path)
    return FileResponse(
        path=pdf_path,
        filename=pdf_filename,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{pdf_filename}"'},
    )


@router.get("/health")
async def health_check():
    """Simple health check — frontend can ping this to check if server is running."""
    return {
        "status": "ok",
        "storage_backend": STORAGE_BACKEND,
        "preview_available": libreoffice_available(),
    }