"""Phase 3: GET /help - the Help & info content shown on the website's Help page."""
from fastapi import APIRouter

from app.help_info import load_help
from app.models import HelpInfo

router = APIRouter(prefix="/help", tags=["help"])


@router.get("", response_model=HelpInfo)
def read_help():
    return load_help()
