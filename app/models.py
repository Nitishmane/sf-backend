import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AddressType(str, enum.Enum):
    """What an address is used for. Inherits `str` so it serialises as its value."""

    HOME = "Home"
    WORK = "Work"
    OTHER = "Other"


class Address(Base):
    __tablename__ = "addresses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contact_id: Mapped[int] = mapped_column(
        # ON DELETE CASCADE is enforced by SQLite itself (the engine sets
        # PRAGMA foreign_keys=ON), which is what lets the relationship below
        # use passive_deletes and skip loading rows just to delete them.
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    type: Mapped[AddressType] = mapped_column(
        # native_enum=False stores a VARCHAR rather than a database-level ENUM
        # type, which keeps the schema portable off SQLite without a migration.
        # The other three arguments are each load-bearing, and none of them are
        # the default:
        #   create_constraint  — SQLAlchemy 2 emits no CHECK unless asked, so
        #                        without this the column accepts any string.
        #   values_callable    — by default it persists the *names* (HOME), not
        #                        the values (Home) the API speaks. Storing the
        #                        names would make raw SQL disagree with JSON.
        #   name               — names the CHECK constraint, so a future
        #                        migration can alter it by name.
        SAEnum(
            AddressType,
            native_enum=False,
            length=10,
            create_constraint=True,
            values_callable=lambda enum_type: [member.value for member in enum_type],
            name="address_type",
        ),
        nullable=False,
        default=AddressType.HOME,
    )

    street: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str | None] = mapped_column(String(120))

    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    contact: Mapped["Contact"] = relationship(back_populates="addresses")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Address id={self.id} contact_id={self.contact_id} type={self.type.value!r}>"


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    first_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(40))

    company: Mapped[str | None] = mapped_column(String(200))
    job_title: Mapped[str | None] = mapped_column(String(200))

    notes: Mapped[str | None] = mapped_column(Text)

    # Base64 data URL. Text, not String(n): a 256px JPEG runs to roughly 35 KB.
    photo: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
        nullable=False,
    )

    addresses: Mapped[list[Address]] = relationship(
        back_populates="contact",
        # delete-orphan is what makes a PUT with a shorter list actually remove
        # the dropped rows instead of orphaning them with a dangling contact_id.
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Address.id",
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Contact id={self.id} email={self.email!r}>"
