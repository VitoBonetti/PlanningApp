from fastapi import APIRouter, Depends, BackgroundTasks
from routers.auth import get_current_user

router = APIRouter(tags=["Markets"])


@router.get("/markets/")
def get_available_market(current_user: dict = Depends(get_current_user)):
    role = current_user.get('role')

    return {"role": role}