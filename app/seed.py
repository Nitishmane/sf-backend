from app.crud import count_contacts, create_contact
from app.database import SessionLocal
from app.models import AddressType
from app.schemas import AddressCreate, ContactCreate

SAMPLE_CONTACTS = [
    ContactCreate(
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        phone="+1-415-555-0101",
        company="Analytical Engines",
        job_title="Mathematician",
        notes="First programmer.",
        # Two addresses so the seeded data actually exercises the one-to-many
        # rather than looking like the old single-address shape.
        addresses=[
            AddressCreate(
                type=AddressType.WORK,
                street="1 Market St, Suite 400",
                city="San Francisco",
                state="CA",
                postal_code="94105",
                country="USA",
                is_primary=True,
            ),
            AddressCreate(
                type=AddressType.HOME,
                street="12 Ockham Rd",
                city="Surrey",
                postal_code="GU23 6PA",
                country="UK",
            ),
        ],
    ),
    ContactCreate(
        first_name="Grace",
        last_name="Hopper",
        email="grace@example.com",
        phone="+1-415-555-0102",
        company="US Navy",
        job_title="Rear Admiral",
        addresses=[
            AddressCreate(
                type=AddressType.WORK,
                street="1 Navy Yard",
                city="Arlington",
                state="VA",
                postal_code="22202",
                country="USA",
                is_primary=True,
            )
        ],
    ),
    ContactCreate(
        first_name="Alan",
        last_name="Turing",
        email="alan@example.com",
        phone="+44-20-5555-0103",
        company="Bletchley Park",
        job_title="Cryptanalyst",
        addresses=[
            AddressCreate(
                type=AddressType.HOME,
                street="Sherwood, Adlington Rd",
                city="London",
                country="UK",
                is_primary=True,
            )
        ],
    ),
]


def seed_if_empty() -> int:
    """Insert sample contacts when the database has none. Returns rows added."""
    with SessionLocal() as db:
        if count_contacts(db) > 0:
            return 0
        for contact in SAMPLE_CONTACTS:
            create_contact(db, contact)
        return len(SAMPLE_CONTACTS)
