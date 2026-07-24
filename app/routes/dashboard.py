from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.core.auth import is_logged_in, create_session_cookie_value, COOKIE_NAME

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _require_login(request: Request):
    if not is_logged_in(request):
        return RedirectResponse(url="/dashboard/login")
    return None


@router.get("/dashboard/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/dashboard/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == settings.DASHBOARD_USERNAME and password == settings.DASHBOARD_PASSWORD:
        response = RedirectResponse(url="/dashboard/overview", status_code=302)
        response.set_cookie(COOKIE_NAME, create_session_cookie_value(), httponly=True, max_age=60 * 60 * 24 * 7)
        return response
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid username or password"})


@router.get("/dashboard/logout")
async def logout():
    response = RedirectResponse(url="/dashboard/login")
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get("/dashboard")
async def dashboard_root(request: Request):
    return RedirectResponse(url="/dashboard/overview")


@router.get("/dashboard/overview", response_class=HTMLResponse)
async def overview_page(request: Request):
    redirect = _require_login(request)
    if redirect:
        return redirect
    return templates.TemplateResponse("overview.html", {"request": request, "active": "overview"})


@router.get("/dashboard/myfiles", response_class=HTMLResponse)
async def myfiles_page(request: Request):
    redirect = _require_login(request)
    if redirect:
        return redirect
    return templates.TemplateResponse("myfiles.html", {"request": request, "active": "myfiles"})


@router.get("/dashboard/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    redirect = _require_login(request)
    if redirect:
        return redirect
    return templates.TemplateResponse("settings.html", {"request": request, "active": "settings"})
