from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.models.user import User
from app.services.wiki.service import WikiService

router = APIRouter(prefix="/wiki", tags=["wiki"])


class CompileRequest(BaseModel):
    source: str


def get_wiki_service() -> WikiService:
    return WikiService()


@router.get("/status")
def wiki_status(service: WikiService = Depends(get_wiki_service)):
    return service.get_status()


@router.get("/schema")
def wiki_schema(service: WikiService = Depends(get_wiki_service)):
    return {"schema": service.get_schema()}


@router.post("/compile")
def wiki_compile(
    payload: CompileRequest,
    service: WikiService = Depends(get_wiki_service),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    from app.services.llm.registry import default_registry

    try:
        llm_client = default_registry.get_model(settings.llm_default_model)
        return service.compile_file(payload.source, llm_client, db=db)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
