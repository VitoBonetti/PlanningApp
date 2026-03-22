from fastapi import APIRouter, HTTPException, Depends
import sqlite3
import uuid
import bcrypt
from database import DB_FILE
from routers.auth import get_current_user, verify_password
from models import UserCreateSecure, UserUpdate, PasswordChange, AdminPasswordReset, FirstAdminSetup

router = APIRouter(tags=["Users"])


@router.get("/system/status")
def check_system_status():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    count = cursor.fetchone()[0]
    conn.close()
    return {"is_setup": count > 0}


@router.post("/system/setup")
def setup_first_admin(admin: FirstAdminSetup):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    if cursor.fetchone()[0] > 0:
        conn.close()
        raise HTTPException(status_code=400, detail="System is already setup.")

    salt = bcrypt.gensalt()
    hashed_pw = bcrypt.hashpw(admin.password.encode('utf-8'), salt).decode('utf-8')
    new_id = str(uuid.uuid4())

    cursor.execute(
        'INSERT INTO users (id, username, hashed_password, name, role, location, base_capacity, start_week) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (new_id, admin.username, hashed_pw, admin.name, 'admin', admin.location, 1.0, 1))
    conn.commit()
    conn.close()
    return {"message": "Admin account created successfully!"}


@router.post("/users/")
def create_user(u: UserCreateSecure, current_user: dict = Depends(get_current_user)):
    if current_user['role'] != 'admin': raise HTTPException(status_code=403, detail="Only Admins can create new users.")
    salt = bcrypt.gensalt()
    hashed_pw = bcrypt.hashpw(u.password.encode('utf-8'), salt).decode('utf-8')
    new_id = str(uuid.uuid4())
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        # NEW: Added start_week
        cursor.execute(
            'INSERT INTO users (id, username, hashed_password, name, role, location, base_capacity, start_week) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (new_id, u.username, hashed_pw, u.name, u.role, u.location, u.base_capacity, u.start_week))
        conn.commit()
        conn.close()
        return {"message": f"User {u.name} created."}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already exists.")


# Delete User Endpoint
@router.delete("/users/{user_id}")
def delete_user(user_id: str, current_user: dict = Depends(get_current_user)):
    if current_user['role'] != 'admin': raise HTTPException(status_code=403, detail="Admins only.")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM assignments WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM events WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return {"message": "User deleted."}


@router.put("/users/{user_id}")
def update_user(user_id: str, u: UserUpdate, current_user: dict = Depends(get_current_user)):
    if current_user['role'] != 'admin': raise HTTPException(status_code=403, detail="Admins only.")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE users SET name=?, role=?, location=?, base_capacity=?, start_week=? WHERE id=?',
        (u.name, u.role, u.location, u.base_capacity, u.start_week, user_id))
    conn.commit()
    conn.close()
    return {"message": "User updated."}


@router.put("/users/{user_id}/reset-password")
def admin_reset_password(user_id: str, p: AdminPasswordReset, current_user: dict = Depends(get_current_user)):
    if current_user['role'] != 'admin': raise HTTPException(status_code=403, detail="Admins only.")
    salt = bcrypt.gensalt()
    hashed_pw = bcrypt.hashpw(p.new_password.encode('utf-8'), salt).decode('utf-8')
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET hashed_password=? WHERE id=?', (hashed_pw, user_id))
    conn.commit()
    conn.close()
    return {"message": "User password reset successfully."}


@router.put("/users/me/password")
def change_own_password(p: PasswordChange, current_user: dict = Depends(get_current_user)):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT hashed_password FROM users WHERE id = ?", (current_user['id'],))
    db_hash = cursor.fetchone()[0]

    if not verify_password(p.old_password, db_hash):
        conn.close()
        raise HTTPException(status_code=400, detail="Incorrect old password.")

    salt = bcrypt.gensalt()
    new_hashed_pw = bcrypt.hashpw(p.new_password.encode('utf-8'), salt).decode('utf-8')
    cursor.execute('UPDATE users SET hashed_password=? WHERE id=?', (new_hashed_pw, current_user['id']))
    conn.commit()
    conn.close()
    return {"message": "Password changed successfully."}

