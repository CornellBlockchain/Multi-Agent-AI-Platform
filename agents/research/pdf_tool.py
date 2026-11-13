import asyncio
from io import BytesIO
import httpx
from pypdf import PdfReader
from pypdf.errors import PyPdfError
from uuid import uuid4

if __package__:
    from .events import create_tool_event
else:
    from events import create_tool_event

async def extract_pdf(url: str) -> dict:
    """Download a PDF and extract text with page references."""
    url = url.strip()

    if not url:
        raise ValueError("The PDF URL cannot be empty.")

    if not url.startswith(("https://", "http://")):
        raise ValueError("Enter an HTTP or HTTPS URL.")

    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
    ) as client:
        response = await client.get(url)
        response.raise_for_status()

    pdf_bytes = response.content



    reader = PdfReader(BytesIO(pdf_bytes))

    passages = []

    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = text.strip()

        if text:
            passages.append(f"Page {page_number}\n{text}")

    if not passages:
        raise ValueError(
            "No readable text was found. This PDF may need OCR."
        )

    return {
        "message": f"Extracted text from {len(passages)} pages.",
        "summary": (
            f"Read {len(reader.pages)} PDF pages; "
            f"found text on {len(passages)} pages."
        ),
        "sources": [
            {
                "title": "PDF document",
                "url": url,
            }
        ],
        "artifacts": [
            {
                "name": "PDF extracted text",
                "content": "\n\n".join(passages),
            }
        ],
    }

async def extract_pdf_with_events(
    url: str,
    run_id: str,
    task_id: str,
    events: list,
) -> dict:
    tool_call_id = str(uuid4())

    def emit(event_type: str, message: str):
        event = create_tool_event(
            run_id=run_id,
            task_id=task_id,
            tool_call_id=tool_call_id,
            event_type=event_type,
            message=message,
            tool="pdf_extraction",
        )
        events.append(event)
        print(f"[{event_type}] {message}", flush=True)

    emit("tool.started", "Downloading and reading PDF")

    try:
        result = await extract_pdf(url)
    except asyncio.CancelledError:
        emit("tool.failed", "PDF extraction was cancelled")
        raise
    except Exception:
        emit("tool.failed", "PDF extraction failed")
        raise
    else:
        emit("tool.completed", result["message"])
        return result

if __name__ == "__main__":
    url = input("Enter a PDF URL: ")
    events = []

    try:
        result = asyncio.run(
            extract_pdf_with_events(
                url=url,
                run_id="local-run",
                task_id="local-task",
                events=events,
            )
        )
    except httpx.TimeoutException:
        print("The download timed out. Please try again.")
    except httpx.HTTPError as error:
        print(f"Could not download the PDF: {error}")
    except ValueError as error:
        print(f"Could not extract text: {error}")
    except PyPdfError:
        print(
            "Could not read the PDF. It may be invalid, "
            "damaged, or require a password."
        )
    else:
        print()
        print(result["message"])
        print(result["summary"])

        for source in result["sources"]:
            print("Source:", source["url"])

        for artifact in result["artifacts"]:
            print()
            print(artifact["content"])