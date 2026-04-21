from fastapi import APIRouter, HTTPException, Depends
from backend.database import get_db_cursor
from backend.routers.auth import require_admin
from backend.models import ServiceUpdate

router = APIRouter(tags=["Services"])


@router.get("/services/")
def get_services(cursor=Depends(get_db_cursor), current_user: dict = Depends(require_admin)):
    """Fetches all services and their capacity limits."""
    cursor.execute("SELECT id, name, max_concurrent_per_week FROM services ORDER BY name")
    return [{"id": r[0], "name": r[1], "max_concurrent_per_week": r[2]} for r in cursor.fetchall()]


@router.put("/services/{service_id}")
def update_service(service_id: str, data: ServiceUpdate, cursor=Depends(get_db_cursor),
                   current_user: dict = Depends(require_admin)):
    """Updates the name and capacity limit of a specific service."""
    cursor.execute(
        "UPDATE services SET name = %s, max_concurrent_per_week = %s WHERE id = %s RETURNING id",
        (data.name, data.max_concurrent_per_week, service_id)
    )
    if cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail="Service not found")

    cursor.connection.commit()
    return {"message": "Service updated successfully"}
