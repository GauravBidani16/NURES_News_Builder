"""FastAPI route handlers for News Post Builder web interface."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from news_post_builder.core.models import ArticleInput, SessionState
from news_post_builder.core.service import NewsPostService
from news_post_builder.web.dependencies import get_service

templates_dir = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

router = APIRouter()


@router.get("/")
async def index(
    service: Annotated[NewsPostService, Depends(get_service)],
) -> RedirectResponse:
    """Entrypoint: creates a fresh session and redirects to its workflow."""
    session = service.create_session()
    return RedirectResponse(url=f"/session/{session.session_id}", status_code=303)


@router.get("/session/new")
async def start_new_session(
    service: Annotated[NewsPostService, Depends(get_service)],
) -> RedirectResponse:
    """Convenience route to start a clean new session."""
    session = service.create_session()
    return RedirectResponse(url=f"/session/{session.session_id}", status_code=303)


@router.get("/session/{session_id}")
async def session_input_view(
    session_id: str,
    request: Request,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> Response:
    session = service.get_session(session_id)
    if session.state == SessionState.CANCELLED:
        return RedirectResponse(url="/", status_code=303)
    if session.state == SessionState.OPTIONS_READY:
        return RedirectResponse(url=f"/session/{session_id}/options", status_code=303)
    if session.state == SessionState.PREVIEW:
        return RedirectResponse(url=f"/session/{session_id}/preview", status_code=303)
    if session.state == SessionState.FETCH_FAILED:
        return templates.TemplateResponse(
            request=request,
            name="fetch_failed.html",
            context={"session": session},
        )
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"session": session, "settings": service.settings},
    )


@router.post("/session/{session_id}/cancel")
async def cancel_session_post(
    session_id: str,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> JSONResponse:
    """Cancel in-flight operations (LLM/fetch) and mark session cancelled."""
    service.cancel(session_id)
    return JSONResponse({"status": "cancelled", "redirect": "/"})


@router.get("/session/{session_id}/cancel")
async def cancel_session_get(
    session_id: str,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> RedirectResponse:
    """Cancel in-flight operations and redirect to homepage for a clean new post."""
    service.cancel(session_id)
    return RedirectResponse(url="/", status_code=303)


@router.post("/session/{session_id}/submit")
async def submit_article(
    session_id: str,
    request: Request,
    service: Annotated[NewsPostService, Depends(get_service)],
    url: Annotated[str | None, Form()] = None,
    text: Annotated[str | None, Form()] = None,
) -> Response:
    input_data = ArticleInput(
        url=url.strip() if url else None,
        text=text.strip() if text else None,
    )
    session = await service.submit(session_id, input_data)

    if session.state == SessionState.FETCH_FAILED:
        return templates.TemplateResponse(
            request=request,
            name="fetch_failed.html",
            context={"session": session},
        )

    return RedirectResponse(url=f"/session/{session_id}/options", status_code=303)


@router.get("/session/{session_id}/options", response_class=HTMLResponse)
async def options_view(
    session_id: str,
    request: Request,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> HTMLResponse:
    session = service.get_session(session_id)
    if session.state == SessionState.FETCH_FAILED:
        return templates.TemplateResponse(
            request=request,
            name="fetch_failed.html",
            context={"session": session},
        )
    return templates.TemplateResponse(
        request=request,
        name="options.html",
        context={"session": session, "settings": service.settings},
    )


@router.post("/session/{session_id}/more")
async def request_more_options(
    session_id: str,
    service: Annotated[NewsPostService, Depends(get_service)],
    target: Annotated[str, Query()] = "both",
) -> RedirectResponse:
    await service.request_more(session_id, target=target)
    return RedirectResponse(url=f"/session/{session_id}/options", status_code=303)


@router.post("/session/{session_id}/select")
async def select_options(
    session_id: str,
    service: Annotated[NewsPostService, Depends(get_service)],
    headline_text: Annotated[str, Form()],
    description_text: Annotated[str, Form()],
    headline_id: Annotated[str | None, Form()] = None,
    description_id: Annotated[str | None, Form()] = None,
    media_id: Annotated[int | None, Form()] = None,
) -> RedirectResponse:
    service.select(
        session_id=session_id,
        headline=headline_text,
        description=description_text,
        headline_id=headline_id,
        description_id=description_id,
        media_id=media_id,
    )
    return RedirectResponse(url=f"/session/{session_id}/preview", status_code=303)


@router.get("/session/{session_id}/preview", response_class=HTMLResponse)
async def preview_view(
    session_id: str,
    request: Request,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> HTMLResponse:
    session = service.get_session(session_id)
    preview = service.get_preview(session_id)
    return templates.TemplateResponse(
        request=request,
        name="preview.html",
        context={"session": session, "preview": preview, "settings": service.settings},
    )


@router.post("/session/{session_id}/back")
async def back_to_options(
    session_id: str,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> RedirectResponse:
    service.back_to_options(session_id)
    return RedirectResponse(url=f"/session/{session_id}/options", status_code=303)


@router.post("/session/{session_id}/confirm", response_class=HTMLResponse)
async def confirm_post(
    session_id: str,
    request: Request,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> HTMLResponse:
    session, result = await service.confirm(session_id)
    return templates.TemplateResponse(
        request=request,
        name="confirm.html",
        context={"session": session, "result": result},
    )


@router.get("/session/{session_id}/confirm", response_class=HTMLResponse)
async def confirm_view(
    session_id: str,
    request: Request,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> HTMLResponse:
    session = service.get_session(session_id)
    result = session.publish_result
    return templates.TemplateResponse(
        request=request,
        name="confirm.html",
        context={"session": session, "result": result},
    )
