from fastapi import APIRouter, Depends, HTTPException, status
from models import MarketBase, MarketCreate, MarketUpdate
from typing import Optional
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


@router.get("/markets/{market_id}/analytics")
def get_market_analytics(market_id: str, current_user: dict = Depends(require_admin), cursor=Depends(get_db_cursor)):
    """Aggregates KPI data, test statuses, and timeline metrics for a specific market."""

    # 1. Total Assets
    cursor.execute("SELECT COUNT(*) FROM assets WHERE market_id = %s", (market_id,))
    total_assets = cursor.fetchone()[0]

    # 2. Asset Test Status Breakdown (Queue vs Completed)
    cursor.execute("""
        SELECT t.status, COUNT(DISTINCT a.id)
        FROM assets a
        JOIN test_assets ta ON a.id = ta.asset_id
        JOIN tests t ON ta.test_id = t.id
        WHERE a.market_id = %s
        GROUP BY t.status
    """, (market_id,))
    status_breakdown = [{"status": r[0], "count": r[1]} for r in cursor.fetchall()]

    # 3. Timeline / Burn-down (Tests per Week/Year)
    cursor.execute("""
        SELECT t.start_year, t.start_week, COUNT(*) as test_count
        FROM tests t
        JOIN test_assets ta ON t.id = ta.test_id
        JOIN assets a ON ta.asset_id = a.id
        WHERE a.market_id = %s AND t.start_year IS NOT NULL
        GROUP BY t.start_year, t.start_week
        ORDER BY t.start_year ASC, t.start_week ASC
        LIMIT 12
    """, (market_id,))

    # Format for Recharts (e.g., "2024-W14")
    timeline = [{"time": f"{r[0]}-W{r[1]}", "tests": r[2]} for r in cursor.fetchall()]

    return {
        "total_assets": total_assets,
        "status_breakdown": status_breakdown,
        "timeline": timeline
    }