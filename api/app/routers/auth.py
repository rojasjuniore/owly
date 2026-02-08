from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from jose import jwt

from app.db import get_db
from app.models.user import User, UserRole
from app.config import settings

router = APIRouter()


class LoginRequest(BaseModel):
    email: EmailStr


class LoginResponse(BaseModel):
    token: str
    user: dict


class UserResponse(BaseModel):
    id: str
    email: str
    name: str | None
    role: str


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Simple email-based login for Phase 0 demo.
    Creates user if doesn't exist.
    """
    # Find or create user
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(
            email=request.email,
            name=request.email.split("@")[0],
            role=UserRole.LO
        )
        db.add(user)
        await db.flush()
    
    # Generate JWT
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "exp": datetime.utcnow() + timedelta(hours=settings.jwt_expiration_hours)
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    
    return LoginResponse(
        token=token,
        user={
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role.value
        }
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    db: AsyncSession = Depends(get_db),
    # TODO: Add proper auth dependency
):
    """Get current user info."""
    # Placeholder - implement proper auth
    raise HTTPException(status_code=401, detail="Not authenticated")
