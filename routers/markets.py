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
def get_market_analytics(market_id: str, current_user: dict = Depends(get_current_user), cursor=Depends(get_db_cursor)):
    """Aggregates KPI data, test statuses, and timeline metrics for a specific market."""

    # 0. Get the Market Code
    cursor.execute("SELECT code FROM markets WHERE id = %s", (market_id,))
    market_row = cursor.fetchone()
    if not market_row:
        raise HTTPException(status_code=404, detail="Market not found")

    market_code = market_row[0]

    # 1. Enhanced KPIs (Total, KPI=True, PentestQueue=True)
    cursor.execute("""
        SELECT 
            COUNT(DISTINCT a.id) as total_assets,
            COUNT(DISTINCT CASE WHEN a.kpi ILIKE 'true' OR a.kpi = '1' OR a.kpi ILIKE 'yes' THEN a.id END) as kpi_assets,
            COUNT(DISTINCT CASE WHEN ra.pentest_queue = TRUE THEN a.id END) as pq_assets
        FROM assets a
        LEFT JOIN raw_assets ra ON a.inventory_id = ra.inventory_id
        WHERE a.market = %s
    """, (market_code,))
    kpis = cursor.fetchone()

    # 2. Asset Test Status Breakdown (STRICTLY for Pentest Queue Assets)
    cursor.execute("""
        SELECT 
            CASE 
                WHEN t.id IS NULL THEN 'Not Planned'
                WHEN t.status = 'Completed' THEN 'Completed'
                WHEN t.status = 'Not Planned' THEN 'Not Planned'
                ELSE 'Planned'
            END as mapped_status,
            COUNT(DISTINCT a.id)
        FROM assets a
        LEFT JOIN raw_assets ra ON a.inventory_id = ra.inventory_id
        LEFT JOIN test_assets ta ON a.id = ta.asset_id
        LEFT JOIN tests t ON ta.test_id = t.id
        WHERE a.market = %s AND ra.pentest_queue = TRUE
        GROUP BY mapped_status
    """, (market_code,))

    # Force initialize to guarantee the UI always gets the 3 colors
    status_counts = {"Completed": 0, "Planned": 0, "Not Planned": 0}
    for r in cursor.fetchall():
        if r[0] in status_counts:
            status_counts[r[0]] += r[1]
        else:
            status_counts["Planned"] += r[1]  # Catch-all for Scheduled, Pending, etc.

    status_breakdown = [{"status": k, "count": v} for k, v in status_counts.items()]

    # 3. Service Breakdown (STRICTLY for Pentest Queue Assets)
    cursor.execute("""
        SELECT COALESCE(NULLIF(TRIM(a.gost_service), ''), 'Unassigned') as svc, COUNT(DISTINCT a.id)
        FROM assets a
        LEFT JOIN raw_assets ra ON a.inventory_id = ra.inventory_id
        WHERE a.market = %s AND ra.pentest_queue = TRUE
        GROUP BY svc
    """, (market_code,))
    service_breakdown = [{"service": r[0], "count": r[1]} for r in cursor.fetchall()]

    # 4. Stacked Timeline (Tests per Week stacked by Service)
    cursor.execute("""
        SELECT t.start_year, t.start_week, COALESCE(s.name, 'Other'), COUNT(DISTINCT t.id)
        FROM tests t
        JOIN test_assets ta ON t.id = ta.test_id
        JOIN assets a ON ta.asset_id = a.id
        LEFT JOIN services s ON t.service_id = s.id
        WHERE a.market = %s AND t.start_year IS NOT NULL
        GROUP BY t.start_year, t.start_week, s.name
        ORDER BY t.start_year ASC, t.start_week ASC
        LIMIT 100
    """, (market_code,))

    timeline_dict = {}
    services_set = set()
    for r in cursor.fetchall():
        time_key = f"{r[0]}-W{r[1]}"
        svc_name = r[2]
        cnt = r[3]

        if time_key not in timeline_dict:
            timeline_dict[time_key] = {"time": time_key}
        timeline_dict[time_key][svc_name] = cnt
        services_set.add(svc_name)

    timeline = list(timeline_dict.values())
    timeline.sort(key=lambda x: (int(x["time"].split("-W")[0]), int(x["time"].split("-W")[1])))

    return {
        "total_assets": kpis[0] or 0,
        "kpi_assets": kpis[1] or 0,
        "pq_assets": kpis[2] or 0,
        "status_breakdown": status_breakdown,
        "service_breakdown": service_breakdown,
        "timeline": timeline[-16:],  # Get the most recent 16 weeks
        "timeline_services": list(services_set)
    }