from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uuid
from database import get_db_cursor
from routers.auth import get_current_user, require_admin
from models import MarketAssignment, MarketContactSchema

router = APIRouter(tags=["Market Contacts"])


@router.get("/market-contacts/")
def get_market_contacts(current_user: dict = Depends(get_current_user), cursor = Depends(get_db_cursor)):
    if current_user.get('role') == 'pentester':
        raise HTTPException(status_code=403, detail="Access denied.")
        
    cursor.execute("SELECT id, name, email, platform_role, is_active FROM market_contacts ORDER BY name")
    contacts_rows = cursor.fetchall()
    
    contacts = {}
    for r in contacts_rows:
        contacts[r[0]] = {
            "id": r[0], "name": r[1], "email": r[2], 
            "platform_role": r[3], "is_active": r[4], 
            "assignments": []
        }
        
    # Join with the markets table!
    cursor.execute("""
        SELECT a.contact_id, a.market_id, m.name, m.code, a.market_role 
        FROM market_contact_assignments a
        JOIN markets m ON a.market_id = m.id
    """)
    for row in cursor.fetchall():
        contact_id, market_id, market_name, market_code, market_role = row
        if contact_id in contacts:
            contacts[contact_id]["assignments"].append({
                "market_id": market_id,
                "market_name": market_name,
                "market_code": market_code,
                "market_role": market_role
            })
            
    return {"contacts": list(contacts.values())}


@router.post("/market-contacts/")
def create_market_contact(c: MarketContactSchema, current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):
    contact_id = str(uuid.uuid4())
    try:
        cursor.execute(
            "INSERT INTO market_contacts (id, name, email, platform_role, is_active) VALUES (%s, %s, %s, %s, %s)", 
            (contact_id, c.name, c.email, c.platform_role, c.is_active)
        )
        for assign in c.assignments:
            cursor.execute(
                "INSERT INTO market_contact_assignments (id, contact_id, market_id, market_role) VALUES (%s, %s, %s, %s)",
                (str(uuid.uuid4()), contact_id, assign.market_id, assign.market_role)
            )
        cursor.connection.commit()
        return {"id": contact_id, "message": "Contact created."}
    except Exception as e:
        cursor.connection.rollback()
        raise HTTPException(status_code=400, detail=f"Database error. {str(e)}")


@router.put("/market-contacts/{contact_id}")
def update_market_contact(contact_id: str, c: MarketContactSchema, current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):
    try:
        cursor.execute(
            "UPDATE market_contacts SET name=%s, email=%s, platform_role=%s, is_active=%s WHERE id=%s", 
            (c.name, c.email, c.platform_role, c.is_active, contact_id)
        )
        cursor.execute("DELETE FROM market_contact_assignments WHERE contact_id = %s", (contact_id,))
        for assign in c.assignments:
            cursor.execute(
                "INSERT INTO market_contact_assignments (id, contact_id, market_id, market_role) VALUES (%s, %s, %s, %s)",
                (str(uuid.uuid4()), contact_id, assign.market_id, assign.market_role)
            )
        cursor.connection.commit()
        return {"message": "Contact updated."}
    except Exception as e:
        cursor.connection.rollback()
        raise HTTPException(status_code=400, detail="Error updating contact.")


@router.delete("/market-contacts/{contact_id}")
def delete_market_contact(contact_id: str, current_user: dict = Depends(require_admin), cursor = Depends(get_db_cursor)):
    cursor.execute("DELETE FROM market_contacts WHERE id = %s", (contact_id,))
    cursor.connection.commit()
    return {"message": "Contact deleted."}