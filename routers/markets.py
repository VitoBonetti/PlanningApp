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

    cursor.execute("SELECT id, code, name, language, region, is_active, description, created_at FROM markets ORDER BY code")
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
    """Aggregates KPI data, test statuses, timeline metrics, and Whitebox details for a specific market."""

    cursor.execute("SELECT code FROM markets WHERE id = %s", (market_id,))
    market_row = cursor.fetchone()
    if not market_row:
        raise HTTPException(status_code=404, detail="Market not found")
    market_code = market_row[0]

    # Enhanced KPIs
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

    #  Asset Test Status Breakdown (+ Asset Names)
    cursor.execute("""
        SELECT 
            CASE 
                WHEN t.id IS NULL THEN 'Not Planned'
                WHEN t.status = 'Completed' THEN 'Completed'
                WHEN t.status = 'Not Planned' THEN 'Not Planned'
                ELSE 'Planned'
            END as mapped_status,
            COUNT(DISTINCT a.id),
            STRING_AGG(DISTINCT a.name, ', ') as assets
        FROM assets a
        LEFT JOIN raw_assets ra ON a.inventory_id = ra.inventory_id
        LEFT JOIN test_assets ta ON a.id = ta.asset_id
        LEFT JOIN tests t ON ta.test_id = t.id
        WHERE a.market = %s AND ra.pentest_queue = TRUE
        GROUP BY mapped_status
    """, (market_code,))

    status_counts = {"Completed": {"count": 0, "assets": ""}, "Planned": {"count": 0, "assets": ""},
                     "Not Planned": {"count": 0, "assets": ""}}
    for r in cursor.fetchall():
        stat, cnt, assets = r[0], r[1], r[2]
        if stat in status_counts:
            status_counts[stat]["count"] += cnt
            status_counts[stat]["assets"] = assets
        else:
            status_counts["Planned"]["count"] += cnt
            status_counts["Planned"]["assets"] += f", {assets}" if status_counts["Planned"]["assets"] else assets

    status_breakdown = [{"status": k, "count": v["count"], "assets": v["assets"]} for k, v in status_counts.items()]

    #  Service Breakdown (+ Asset Names)
    cursor.execute("""
        SELECT COALESCE(NULLIF(TRIM(a.gost_service), ''), 'Unassigned') as svc, COUNT(DISTINCT a.id), STRING_AGG(DISTINCT a.name, ', ')
        FROM assets a
        LEFT JOIN raw_assets ra ON a.inventory_id = ra.inventory_id
        WHERE a.market = %s AND ra.pentest_queue = TRUE
        GROUP BY svc
    """, (market_code,))
    service_breakdown = [{"service": r[0], "count": r[1], "assets": r[2]} for r in cursor.fetchall()]

    #  Quarterly Timeline (+ Asset Names)
    cursor.execute("""
        SELECT 
            t.start_year, 
            CASE 
                WHEN t.start_week BETWEEN 1 AND 13 THEN 'Q1'
                WHEN t.start_week BETWEEN 14 AND 26 THEN 'Q2'
                WHEN t.start_week BETWEEN 27 AND 39 THEN 'Q3'
                ELSE 'Q4'
            END as quarter,
            COALESCE(s.name, 'Other'), 
            COUNT(DISTINCT t.id),
            STRING_AGG(DISTINCT a.name, ', ')
        FROM tests t
        JOIN test_assets ta ON t.id = ta.test_id
        JOIN assets a ON ta.asset_id = a.id
        LEFT JOIN services s ON t.service_id = s.id
        WHERE a.market = %s AND t.start_year IS NOT NULL
        GROUP BY t.start_year, quarter, COALESCE(s.name, 'Other')
        ORDER BY t.start_year ASC, quarter ASC
    """, (market_code,))

    timeline_dict = {}
    services_set = set()
    for r in cursor.fetchall():
        time_key = f"{r[0]}-{r[1]}"
        svc_name, cnt, assets = r[2], r[3], r[4]

        if time_key not in timeline_dict:
            timeline_dict[time_key] = {"time": time_key}
        timeline_dict[time_key][svc_name] = cnt
        timeline_dict[time_key][f"{svc_name}_assets"] = assets
        services_set.add(svc_name)

    timeline = list(timeline_dict.values())

    #  Whitebox Category Breakdown (+ Asset Names)
    cursor.execute("""
        SELECT 
            COALESCE(NULLIF(TRIM(a.whitebox_category), ''), 'Uncategorized') as category,
            CASE 
                WHEN t.id IS NULL THEN 'Not Planned'
                WHEN t.status = 'Completed' THEN 'Completed'
                WHEN t.status = 'Not Planned' THEN 'Not Planned'
                ELSE 'Planned'
            END as mapped_status,
            COUNT(DISTINCT a.id),
            STRING_AGG(DISTINCT a.name, ', ')
        FROM assets a
        LEFT JOIN test_assets ta ON a.id = ta.asset_id
        LEFT JOIN tests t ON ta.test_id = t.id
        WHERE a.market = %s AND a.whitebox_category IS NOT NULL AND TRIM(a.whitebox_category) != ''
        GROUP BY category, mapped_status
    """, (market_code,))

    wb_dict = {}
    for r in cursor.fetchall():
        cat, status, cnt, assets = r[0], r[1], r[2], r[3]
        if cat not in wb_dict:
            wb_dict[cat] = {"category": cat, "Completed": 0, "Planned": 0, "Not Planned": 0}
        wb_dict[cat][status] = cnt
        wb_dict[cat][f"{status}_assets"] = assets

    whitebox_breakdown = list(wb_dict.values())

    return {
        "total_assets": kpis[0] or 0,
        "kpi_assets": kpis[1] or 0,
        "pq_assets": kpis[2] or 0,
        "status_breakdown": status_breakdown,
        "service_breakdown": service_breakdown,
        "timeline": timeline,
        "timeline_services": list(services_set),
        "whitebox_breakdown": whitebox_breakdown
    }