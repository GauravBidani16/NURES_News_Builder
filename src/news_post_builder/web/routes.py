"""FastAPI route handlers for News Post Builder clean web interface."""

import contextlib
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from news_post_builder.core.models import ArticleInput, SessionData, SessionState
from news_post_builder.core.service import NewsPostService
from news_post_builder.web.dependencies import get_service

templates_dir = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

router = APIRouter()

SESSION_COOKIE_NAME = "npb_session_id"


def get_or_create_web_session(
    request: Request,
    service: NewsPostService,
    force_new: bool = False,
) -> tuple[SessionData, bool]:
    """Retrieve session from cookie, or create fresh one if missing or done.

    Returns (session, is_new_cookie_needed).
    """
    if not force_new:
        cookie_id = request.cookies.get(SESSION_COOKIE_NAME)
        if cookie_id:
            try:
                session = service.get_session(cookie_id)
                if session.state not in {SessionState.CANCELLED, SessionState.DONE}:
                    return session, False
            except Exception:
                pass

    session = service.create_session()
    return session, True


def attach_session_cookie(response: Response, session_id: str) -> None:
    """Set the HTTP-only session cookie on the response."""
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        path="/",
    )


# ---------------------------------------------------------------------------
# Clean, Semantic Routes (Zero UUIDs in the URL)
# ---------------------------------------------------------------------------


@router.get("/", response_class=Response)
async def clean_home(
    request: Request,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> Response:
    """Clean home: renders input form or resumes active in-progress state."""
    session, is_new = get_or_create_web_session(request, service)
    if session.state == SessionState.OPTIONS_READY:
        resp: Response = RedirectResponse(url="/options", status_code=303)
    elif session.state == SessionState.PREVIEW:
        resp = RedirectResponse(url="/preview", status_code=303)
    elif session.state == SessionState.FETCH_FAILED:
        resp = templates.TemplateResponse(
            request=request,
            name="fetch_failed.html",
            context={"session": session, "settings": service.settings},
        )
    else:
        resp = templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"session": session, "settings": service.settings},
        )

    if is_new:
        attach_session_cookie(resp, session.session_id)
    return resp


@router.get("/new")
async def clean_new_post(
    service: Annotated[NewsPostService, Depends(get_service)],
) -> RedirectResponse:
    """Start a completely fresh post, resetting the session cookie."""
    session = service.create_session()
    resp = RedirectResponse(url="/", status_code=303)
    attach_session_cookie(resp, session.session_id)
    return resp


@router.post("/submit")
async def clean_submit(
    request: Request,
    service: Annotated[NewsPostService, Depends(get_service)],
    url: Annotated[str | None, Form()] = None,
    text: Annotated[str | None, Form()] = None,
) -> Response:
    """Submit an article URL or text using active cookie session."""
    session, is_new = get_or_create_web_session(request, service)
    input_data = ArticleInput(
        url=url.strip() if url else None,
        text=text.strip() if text else None,
    )
    session = await service.submit(session.session_id, input_data)

    if session.state == SessionState.FETCH_FAILED:
        resp: Response = templates.TemplateResponse(
            request=request,
            name="fetch_failed.html",
            context={"session": session, "settings": service.settings},
        )
    else:
        resp = RedirectResponse(url="/options", status_code=303)

    if is_new:
        attach_session_cookie(resp, session.session_id)
    return resp


@router.get("/options", response_class=HTMLResponse)
async def clean_options_view(
    request: Request,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> HTMLResponse:
    """Clean options studio view."""
    session, is_new = get_or_create_web_session(request, service)
    if session.state == SessionState.FETCH_FAILED:
        resp: HTMLResponse = templates.TemplateResponse(
            request=request,
            name="fetch_failed.html",
            context={"session": session, "settings": service.settings},
        )
    else:
        resp = templates.TemplateResponse(
            request=request,
            name="options.html",
            context={"session": session, "settings": service.settings},
        )
    if is_new:
        attach_session_cookie(resp, session.session_id)
    return resp


@router.post("/more")
async def clean_request_more(
    request: Request,
    service: Annotated[NewsPostService, Depends(get_service)],
    target: Annotated[str, Query()] = "both",
) -> RedirectResponse:
    """Generate more options for active session."""
    session, is_new = get_or_create_web_session(request, service)
    await service.request_more(session.session_id, target=target)
    resp = RedirectResponse(url="/options", status_code=303)
    if is_new:
        attach_session_cookie(resp, session.session_id)
    return resp


@router.post("/select")
async def clean_select_options(
    request: Request,
    service: Annotated[NewsPostService, Depends(get_service)],
    headline_text: Annotated[str, Form()],
    description_text: Annotated[str, Form()],
    headline_id: Annotated[str | None, Form()] = None,
    description_id: Annotated[str | None, Form()] = None,
    media_id: Annotated[int | None, Form()] = None,
) -> RedirectResponse:
    """Save selected options and media."""
    session, is_new = get_or_create_web_session(request, service)
    service.select(
        session_id=session.session_id,
        headline=headline_text,
        description=description_text,
        headline_id=headline_id,
        description_id=description_id,
        media_id=media_id,
    )
    resp = RedirectResponse(url="/preview", status_code=303)
    if is_new:
        attach_session_cookie(resp, session.session_id)
    return resp


@router.get("/preview", response_class=HTMLResponse)
async def clean_preview_view(
    request: Request,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> HTMLResponse:
    """Clean preview screen."""
    session, is_new = get_or_create_web_session(request, service)
    preview = service.get_preview(session.session_id)
    resp = templates.TemplateResponse(
        request=request,
        name="preview.html",
        context={"session": session, "preview": preview, "settings": service.settings},
    )
    if is_new:
        attach_session_cookie(resp, session.session_id)
    return resp


@router.post("/back")
async def clean_back_to_options(
    request: Request,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> RedirectResponse:
    """Navigate back from preview to options."""
    session, _ = get_or_create_web_session(request, service)
    service.back_to_options(session.session_id)
    return RedirectResponse(url="/options", status_code=303)


@router.post("/confirm", response_class=HTMLResponse)
async def clean_confirm_post(
    request: Request,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> HTMLResponse:
    """Confirm and publish post."""
    session, is_new = get_or_create_web_session(request, service)
    session, result = await service.confirm(session.session_id)
    resp = templates.TemplateResponse(
        request=request,
        name="confirm.html",
        context={"session": session, "result": result, "settings": service.settings},
    )
    if is_new:
        attach_session_cookie(resp, session.session_id)
    return resp


@router.get("/confirm", response_class=HTMLResponse)
async def clean_confirm_view(
    request: Request,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> HTMLResponse:
    """View result of confirmed post."""
    session, is_new = get_or_create_web_session(request, service)
    result = session.publish_result
    resp = templates.TemplateResponse(
        request=request,
        name="confirm.html",
        context={"session": session, "result": result, "settings": service.settings},
    )
    if is_new:
        attach_session_cookie(resp, session.session_id)
    return resp


@router.post("/cancel")
async def clean_cancel_post(
    request: Request,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> JSONResponse:
    """Cancel in-flight task and create fresh session."""
    cookie_id = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_id:
        with contextlib.suppress(Exception):
            service.cancel(cookie_id)

    new_session = service.create_session()
    resp = JSONResponse({"status": "cancelled", "redirect": "/"})
    attach_session_cookie(resp, new_session.session_id)
    return resp


@router.get("/cancel")
async def clean_cancel_get(
    request: Request,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> RedirectResponse:
    """Cancel and return to clean home."""
    cookie_id = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_id:
        with contextlib.suppress(Exception):
            service.cancel(cookie_id)

    new_session = service.create_session()
    resp = RedirectResponse(url="/", status_code=303)
    attach_session_cookie(resp, new_session.session_id)
    return resp


# ---------------------------------------------------------------------------
# Backwards-Compatible Session-in-URL Routes
# ---------------------------------------------------------------------------


@router.get("/session/new")
async def legacy_start_new_session(
    service: Annotated[NewsPostService, Depends(get_service)],
) -> RedirectResponse:
    session = service.create_session()
    resp = RedirectResponse(url=f"/session/{session.session_id}", status_code=303)
    attach_session_cookie(resp, session.session_id)
    return resp


@router.get("/session/{session_id}")
async def legacy_session_input_view(
    session_id: str,
    request: Request,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> Response:
    session = service.get_session(session_id)
    if session.state == SessionState.CANCELLED:
        return RedirectResponse(url="/", status_code=303)
    if session.state == SessionState.OPTIONS_READY:
        resp: Response = RedirectResponse(url=f"/session/{session_id}/options", status_code=303)
    elif session.state == SessionState.PREVIEW:
        resp = RedirectResponse(url=f"/session/{session_id}/preview", status_code=303)
    elif session.state == SessionState.FETCH_FAILED:
        resp = templates.TemplateResponse(
            request=request,
            name="fetch_failed.html",
            context={"session": session, "settings": service.settings},
        )
    else:
        resp = templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"session": session, "settings": service.settings},
        )
    attach_session_cookie(resp, session_id)
    return resp


@router.post("/session/{session_id}/cancel")
async def legacy_cancel_session_post(
    session_id: str,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> JSONResponse:
    service.cancel(session_id)
    return JSONResponse({"status": "cancelled", "redirect": "/"})


@router.get("/session/{session_id}/cancel")
async def legacy_cancel_session_get(
    session_id: str,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> RedirectResponse:
    service.cancel(session_id)
    return RedirectResponse(url="/", status_code=303)


@router.post("/session/{session_id}/submit")
async def legacy_submit_article(
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
        resp: Response = templates.TemplateResponse(
            request=request,
            name="fetch_failed.html",
            context={"session": session, "settings": service.settings},
        )
    else:
        resp = RedirectResponse(url=f"/session/{session_id}/options", status_code=303)
    attach_session_cookie(resp, session_id)
    return resp


@router.get("/session/{session_id}/options", response_class=HTMLResponse)
async def legacy_options_view(
    session_id: str,
    request: Request,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> HTMLResponse:
    session = service.get_session(session_id)
    if session.state == SessionState.FETCH_FAILED:
        resp: HTMLResponse = templates.TemplateResponse(
            request=request,
            name="fetch_failed.html",
            context={"session": session, "settings": service.settings},
        )
    else:
        resp = templates.TemplateResponse(
            request=request,
            name="options.html",
            context={"session": session, "settings": service.settings},
        )
    attach_session_cookie(resp, session_id)
    return resp


@router.post("/session/{session_id}/more")
async def legacy_request_more_options(
    session_id: str,
    service: Annotated[NewsPostService, Depends(get_service)],
    target: Annotated[str, Query()] = "both",
) -> RedirectResponse:
    await service.request_more(session_id, target=target)
    resp = RedirectResponse(url=f"/session/{session_id}/options", status_code=303)
    attach_session_cookie(resp, session_id)
    return resp


@router.post("/session/{session_id}/select")
async def legacy_select_options(
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
    resp = RedirectResponse(url=f"/session/{session_id}/preview", status_code=303)
    attach_session_cookie(resp, session_id)
    return resp


@router.get("/session/{session_id}/preview", response_class=HTMLResponse)
async def legacy_preview_view(
    session_id: str,
    request: Request,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> HTMLResponse:
    session = service.get_session(session_id)
    preview = service.get_preview(session_id)
    resp = templates.TemplateResponse(
        request=request,
        name="preview.html",
        context={"session": session, "preview": preview, "settings": service.settings},
    )
    attach_session_cookie(resp, session_id)
    return resp


@router.post("/session/{session_id}/back")
async def legacy_back_to_options(
    session_id: str,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> RedirectResponse:
    service.back_to_options(session_id)
    resp = RedirectResponse(url=f"/session/{session_id}/options", status_code=303)
    attach_session_cookie(resp, session_id)
    return resp


@router.post("/session/{session_id}/confirm", response_class=HTMLResponse)
async def legacy_confirm_post(
    session_id: str,
    request: Request,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> HTMLResponse:
    session, result = await service.confirm(session_id)
    resp = templates.TemplateResponse(
        request=request,
        name="confirm.html",
        context={"session": session, "result": result, "settings": service.settings},
    )
    attach_session_cookie(resp, session_id)
    return resp


@router.get("/session/{session_id}/confirm", response_class=HTMLResponse)
async def legacy_confirm_view(
    session_id: str,
    request: Request,
    service: Annotated[NewsPostService, Depends(get_service)],
) -> HTMLResponse:
    session = service.get_session(session_id)
    result = session.publish_result
    resp = templates.TemplateResponse(
        request=request,
        name="confirm.html",
        context={"session": session, "result": result, "settings": service.settings},
    )
    attach_session_cookie(resp, session_id)
    return resp
