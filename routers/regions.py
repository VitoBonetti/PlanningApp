from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import uuid
from database import get_db_cursor
from routers.auth import get_current_user, require_admin
from models import RegionSchema

router = APIRouter(tags=["Regions"])


@router.get("/regions/")
def get_regions(current_user: dict = Depends(get_current_user), cursor = Depends(get_db_cursor)):
    # Block pentesters from viewing settings data
    if current_user.get('role') == 'pentester':
        raise HTTPException(status_code=403, detail="Pentesters cannot access region data.")
        
    cursor.execute("SELECT id, regions, is_active FROM regions ORDER BY regions")
    regions_data = [{"id": r[0], "regions": r[1], "is_active": r[2]} for r in cursor.fetchall()]
    return {"regions": regions_data}


@router.post("/regions/")
def create_region(r: RegionSchema, current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):
    region_id = str(uuid.uuid4())
    try:
        cursor.execute(
            "INSERT INTO regions (id, regions, is_active) VALUES (%s, %s, %s)", 
            (region_id, r.regions, r.is_active)
        )
        cursor.connection.commit()
        return {"id": region_id, "message": "Region created."}
    except Exception as e:
        cursor.connection.rollback()
        raise HTTPException(status_code=400, detail="Region name already exists.")


@router.put("/regions/{region_id}")
def update_region(region_id: str, r: RegionSchema, current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):
    try:
        cursor.execute(
            "UPDATE regions SET regions=%s, is_active=%s WHERE id=%s", 
            (r.regions, r.is_active, region_id)
        )
        cursor.connection.commit()
        return {"message": "Region updated."}
    except Exception as e:
        cursor.connection.rollback()
        raise HTTPException(status_code=400, detail="Region name already exists.")


@router.delete("/regions/{region_id}")
def delete_region(region_id: str, current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):
    cursor.execute("DELETE FROM regions WHERE id = %s", (region_id,))
    cursor.connection.commit()
    return {"message": "Region deleted."}