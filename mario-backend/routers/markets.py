from fastapi import APIRouter, Depends, HTTPException, status
from models import MarketBase, MarketCreate, MarketUpdate
import uuid
from database import get_db_cursor
from routers.auth import get_current_user, require_admin

router = APIRouter(tags=["Markets"])


@router.get("/markets/")
def get_markets(current_user: dict = Depends(get_current_user), cursor = Depends(get_db_cursor)):
    # Block pentesters entirely
    if current_user.get('role') == 'pentester':
        raise HTTPException(status_code=403, detail="Pentesters cannot access market data.")
        
    cursor.execute("SELECT id, code, name, language, region, is_active, description, created_at FROM markets ORDER BY region, name")
    rows = cursor.fetchall()
    
    markets = []
    for r in rows:
        markets.append({
            "id": r[0], "code": r[1], "name": r[2], "language": r[3],
            "region": r[4], "is_active": r[5], "description": r[6], "created_at": r[7]
        })
    return {"markets": markets}


@router.post("/markets/")
def create_market(m: MarketCreate, current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):
    market_id = str(uuid.uuid4())
    try:
        cursor.execute("""
            INSERT INTO markets (id, code, name, language, region, is_active, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (market_id, m.code, m.name, m.language, m.region, m.is_active, m.description))
        cursor.connection.commit()
        return {"id": market_id, "message": "Market created successfully."}
    except Exception as e:
        cursor.connection.rollback()
        raise HTTPException(status_code=400, detail=f"Database error (Code might already exist): {str(e)}")

@router.put("/markets/{market_id}")
def update_market(market_id: str, m: MarketUpdate, current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):
    cursor.execute("""
        UPDATE markets 
        SET code=%s, name=%s, language=%s, region=%s, is_active=%s, description=%s
        WHERE id=%s
    """, (m.code, m.name, m.language, m.region, m.is_active, m.description, market_id))
    cursor.connection.commit()
    return {"message": "Market updated successfully."}

@router.delete("/markets/{market_id}")
def delete_market(market_id: str, current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):
    cursor.execute("DELETE FROM markets WHERE id = %s", (market_id,))
    cursor.connection.commit()
    return {"message": "Market deleted."}