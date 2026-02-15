from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_current_user
from app.api.schemas import AuditEventResponse
from app.db import crud
from app.db.models import User

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditEventResponse])
def list_audit(
    action: str | None = None,
    entity_type: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    user: User = Depends(require_current_user),
):
    del user
    return crud.list_audit_logs(db, action=action, entity_type=entity_type, limit=limit)
