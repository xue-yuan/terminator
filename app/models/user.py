from sqlalchemy import Boolean, ForeignKey, String, true, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    google_sub: Mapped[str | None] = mapped_column(String, unique=True, index=True)
    active_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("plans.id", ondelete="SET NULL", use_alter=True, name="users_active_plan_id_fkey")
    )
