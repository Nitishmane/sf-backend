import base64

from sqlalchemy import func, select, text

from app.database import SessionLocal
from app.models import Address
from app.schemas import MAX_ADDRESSES, MAX_PHOTO_BYTES

BASE = "/api/v1/contacts"

# Just the 8-byte PNG signature. The validator checks the envelope, not the
# pixels, so a full image would only make these tests slower to read.
PHOTO = "data:image/png;base64,iVBORw0KGgo="

HOME_ADDRESS = {
    "type": "Home",
    "street": "10 Downing St",
    "city": "London",
    "postal_code": "SW1A 1AA",
    "country": "UK",
}
WORK_ADDRESS = {
    "type": "Work",
    "street": "1 Market St",
    "city": "San Francisco",
    "state": "CA",
    "postal_code": "94105",
    "country": "USA",
    "is_primary": True,
}


def count_address_rows() -> int:
    """
    Count `addresses` rows straight from the database.

    Orphan cleanup and delete-cascade are precisely the things a response body
    cannot prove: a contact can report zero addresses while the rows sit there
    with a dangling `contact_id`. Only the table tells the truth.
    """
    with SessionLocal() as db:
        return db.execute(select(func.count()).select_from(Address)).scalar_one()


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "sqlite"


def test_create_contact(client, payload):
    response = client.post(BASE, json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["email"] == "ada@example.com"
    assert body["full_name"] == "Ada Lovelace"
    assert body["created_at"] and body["updated_at"]


def test_create_requires_valid_email(client, payload):
    response = client.post(BASE, json={**payload, "email": "not-an-email"})
    assert response.status_code == 422


def test_create_requires_names(client, payload):
    response = client.post(BASE, json={**payload, "first_name": ""})
    assert response.status_code == 422


def test_duplicate_email_conflicts(client, payload):
    assert client.post(BASE, json=payload).status_code == 201
    response = client.post(BASE, json={**payload, "email": "ADA@example.com"})
    assert response.status_code == 409


def test_get_contact(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    response = client.get(f"{BASE}/{contact_id}")
    assert response.status_code == 200
    assert response.json()["id"] == contact_id


def test_get_missing_contact_returns_404(client):
    assert client.get(f"{BASE}/9999").status_code == 404


def test_list_pagination_and_total(client, payload):
    for index in range(5):
        client.post(BASE, json={**payload, "email": f"user{index}@example.com"})

    response = client.get(BASE, params={"limit": 2, "offset": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["limit"] == 2 and body["offset"] == 2


def test_list_search(client, payload):
    client.post(BASE, json=payload)
    client.post(
        BASE,
        json={**payload, "first_name": "Grace", "last_name": "Hopper", "email": "grace@example.com", "company": "US Navy"},
    )

    hits = client.get(BASE, params={"search": "hopper"}).json()
    assert hits["total"] == 1
    assert hits["items"][0]["last_name"] == "Hopper"

    by_company = client.get(BASE, params={"search": "navy"}).json()
    assert by_company["total"] == 1

    misses = client.get(BASE, params={"search": "nobody"}).json()
    assert misses["total"] == 0


def test_list_sorting(client, payload):
    client.post(BASE, json={**payload, "last_name": "Zhang", "email": "z@example.com"})
    client.post(BASE, json={**payload, "last_name": "Adams", "email": "a@example.com"})

    names = [
        item["last_name"]
        for item in client.get(BASE, params={"sort_by": "last_name", "order": "asc"}).json()["items"]
    ]
    assert names == ["Adams", "Zhang"]


def test_list_rejects_bad_sort_field(client):
    assert client.get(BASE, params={"sort_by": "; DROP TABLE contacts"}).status_code == 422


def test_patch_updates_only_sent_fields(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    response = client.patch(f"{BASE}/{contact_id}", json={"phone": "+1-000-000-0000"})
    assert response.status_code == 200
    body = response.json()
    assert body["phone"] == "+1-000-000-0000"
    assert body["first_name"] == "Ada"
    assert body["company"] == "Analytical Engines"


def test_patch_duplicate_email_conflicts(client, payload):
    first = client.post(BASE, json=payload).json()["id"]
    client.post(BASE, json={**payload, "email": "grace@example.com"})
    response = client.patch(f"{BASE}/{first}", json={"email": "grace@example.com"})
    assert response.status_code == 409


def test_patch_same_email_is_allowed(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    response = client.patch(f"{BASE}/{contact_id}", json={"email": payload["email"]})
    assert response.status_code == 200


def test_put_replaces_contact(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    response = client.put(
        f"{BASE}/{contact_id}",
        json={"first_name": "Grace", "last_name": "Hopper", "email": "grace@example.com"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Grace Hopper"
    assert body["company"] is None  # omitted fields are cleared by PUT


def test_put_missing_contact_returns_404(client):
    response = client.put(
        f"{BASE}/9999",
        json={"first_name": "A", "last_name": "B", "email": "ab@example.com"},
    )
    assert response.status_code == 404


def test_photo_round_trips(client, payload):
    response = client.post(BASE, json={**payload, "photo": PHOTO})
    assert response.status_code == 201
    contact_id = response.json()["id"]
    assert response.json()["photo"] == PHOTO
    assert client.get(f"{BASE}/{contact_id}").json()["photo"] == PHOTO


def test_photo_defaults_to_none(client, payload):
    assert client.post(BASE, json=payload).json()["photo"] is None


def test_photo_rejects_non_image_data_url(client, payload):
    response = client.post(BASE, json={**payload, "photo": "data:text/html;base64,PHNjcmlwdD4="})
    assert response.status_code == 422


def test_photo_rejects_remote_url(client, payload):
    # A URL would make the frontend fetch third-party content; only inline data is allowed.
    response = client.post(BASE, json={**payload, "photo": "https://example.com/ada.png"})
    assert response.status_code == 422


def test_photo_rejects_malformed_base64(client, payload):
    response = client.post(BASE, json={**payload, "photo": "data:image/png;base64,not!valid!"})
    assert response.status_code == 422


def test_photo_rejects_oversized_image(client, payload):
    oversized = base64.b64encode(b"\x00" * (MAX_PHOTO_BYTES + 1)).decode()
    response = client.post(BASE, json={**payload, "photo": f"data:image/png;base64,{oversized}"})
    assert response.status_code == 422
    assert "limit" in response.text


def test_blank_photo_is_stored_as_null(client, payload):
    response = client.post(BASE, json={**payload, "photo": ""})
    assert response.status_code == 201
    assert response.json()["photo"] is None


def test_put_without_photo_clears_it(client, payload):
    contact_id = client.post(BASE, json={**payload, "photo": PHOTO}).json()["id"]
    response = client.put(
        f"{BASE}/{contact_id}",
        json={"first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com"},
    )
    assert response.status_code == 200
    assert response.json()["photo"] is None  # PUT is a full replace


def test_patch_without_photo_keeps_it(client, payload):
    contact_id = client.post(BASE, json={**payload, "photo": PHOTO}).json()["id"]
    response = client.patch(f"{BASE}/{contact_id}", json={"job_title": "Countess"})
    assert response.status_code == 200
    assert response.json()["photo"] == PHOTO


def test_patch_can_clear_photo(client, payload):
    contact_id = client.post(BASE, json={**payload, "photo": PHOTO}).json()["id"]
    response = client.patch(f"{BASE}/{contact_id}", json={"photo": None})
    assert response.status_code == 200
    assert response.json()["photo"] is None


def test_create_with_multiple_addresses(client, payload):
    response = client.post(
        BASE,
        json={**payload, "addresses": [HOME_ADDRESS, WORK_ADDRESS]},
    )
    assert response.status_code == 201

    addresses = response.json()["addresses"]
    assert [a["type"] for a in addresses] == ["Home", "Work"]
    assert addresses[0]["city"] == "London"
    assert addresses[1]["is_primary"] is True
    # Each child row comes back with its own id, which is the point of AddressRead.
    assert len({a["id"] for a in addresses}) == 2


def test_addresses_default_to_empty_list(client, payload):
    response = client.post(BASE, json={k: v for k, v in payload.items() if k != "addresses"})
    assert response.status_code == 201
    assert response.json()["addresses"] == []


def test_address_rejects_unknown_type(client, payload):
    response = client.post(
        BASE,
        json={**payload, "addresses": [{**HOME_ADDRESS, "type": "Vacation"}]},
    )
    assert response.status_code == 422


def test_address_type_defaults_to_home(client, payload):
    response = client.post(BASE, json={**payload, "addresses": [{"city": "Paris"}]})
    assert response.status_code == 201
    assert response.json()["addresses"][0]["type"] == "Home"


def test_rejects_more_than_max_addresses(client, payload):
    too_many = [{**HOME_ADDRESS, "city": f"City {i}"} for i in range(MAX_ADDRESSES + 1)]
    response = client.post(BASE, json={**payload, "addresses": too_many})
    assert response.status_code == 422


def test_addresses_survive_a_read_after_write(client, payload):
    contact_id = client.post(BASE, json={**payload, "addresses": [HOME_ADDRESS]}).json()["id"]
    body = client.get(f"{BASE}/{contact_id}").json()
    assert len(body["addresses"]) == 1
    assert body["addresses"][0]["postal_code"] == "SW1A 1AA"


def test_addresses_appear_in_the_list_endpoint(client, payload):
    client.post(BASE, json={**payload, "addresses": [HOME_ADDRESS, WORK_ADDRESS]})
    items = client.get(BASE).json()["items"]
    assert len(items[0]["addresses"]) == 2


def test_put_with_shorter_list_deletes_the_orphans(client, payload):
    contact_id = client.post(BASE, json={**payload, "addresses": [HOME_ADDRESS, WORK_ADDRESS]}).json()["id"]

    response = client.put(
        f"{BASE}/{contact_id}",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "addresses": [WORK_ADDRESS],
        },
    )
    assert response.status_code == 200
    assert [a["type"] for a in response.json()["addresses"]] == ["Work"]
    # The dropped row is gone for good, not merely detached.
    assert count_address_rows() == 1


def test_put_without_addresses_clears_them(client, payload):
    contact_id = client.post(BASE, json={**payload, "addresses": [HOME_ADDRESS]}).json()["id"]
    response = client.put(
        f"{BASE}/{contact_id}",
        json={"first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com"},
    )
    assert response.status_code == 200
    assert response.json()["addresses"] == []
    assert count_address_rows() == 0


def test_patch_without_addresses_keeps_them(client, payload):
    contact_id = client.post(BASE, json={**payload, "addresses": [HOME_ADDRESS]}).json()["id"]
    response = client.patch(f"{BASE}/{contact_id}", json={"job_title": "Countess"})
    assert response.status_code == 200
    assert len(response.json()["addresses"]) == 1


def test_patch_can_replace_the_address_list(client, payload):
    contact_id = client.post(BASE, json={**payload, "addresses": [HOME_ADDRESS]}).json()["id"]
    response = client.patch(f"{BASE}/{contact_id}", json={"addresses": [WORK_ADDRESS, HOME_ADDRESS]})
    assert response.status_code == 200
    assert [a["type"] for a in response.json()["addresses"]] == ["Work", "Home"]
    assert count_address_rows() == 2


def test_patch_with_empty_list_deletes_all_addresses(client, payload):
    contact_id = client.post(BASE, json={**payload, "addresses": [HOME_ADDRESS]}).json()["id"]
    response = client.patch(f"{BASE}/{contact_id}", json={"addresses": []})
    assert response.status_code == 200
    assert response.json()["addresses"] == []
    assert count_address_rows() == 0


def test_patch_rejects_an_explicit_null_address_list(client, payload):
    """
    `null` is not a third spelling of "leave them alone".

    Omission already means that. Accepting `null` too would let a well-formed
    request report 200 while quietly doing nothing, so it fails validation.
    """
    contact_id = client.post(BASE, json={**payload, "addresses": [HOME_ADDRESS]}).json()["id"]

    assert client.patch(f"{BASE}/{contact_id}", json={"addresses": None}).status_code == 422
    assert client.get(f"{BASE}/{contact_id}").json()["addresses"][0]["city"] == HOME_ADDRESS["city"]


def test_address_type_is_stored_as_the_value_the_api_speaks(client, payload):
    """
    SQLAlchemy persists enum *names* by default, which would put `WORK` in the
    column while the API says `Work`. Reading the raw column is the only way to
    catch that — the ORM converts it back on the way out either way.
    """
    client.post(BASE, json={**payload, "addresses": [WORK_ADDRESS]})

    with SessionLocal() as db:
        assert db.execute(text("SELECT type FROM addresses")).scalar_one() == "Work"


def test_the_database_itself_rejects_an_unknown_address_type(client):
    """The CHECK constraint is not the default for a non-native enum, so prove it exists."""
    with SessionLocal() as db:
        ddl = db.execute(
            text("SELECT sql FROM sqlite_master WHERE name = 'addresses'")
        ).scalar_one()

    assert "CHECK" in ddl.upper()
    assert "'Home'" in ddl and "'Work'" in ddl and "'Other'" in ddl


def test_delete_contact(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    assert client.delete(f"{BASE}/{contact_id}").status_code == 204
    assert client.get(f"{BASE}/{contact_id}").status_code == 404
    assert client.delete(f"{BASE}/{contact_id}").status_code == 404


def test_deleting_a_contact_cascades_its_addresses(client, payload):
    contact_id = client.post(BASE, json={**payload, "addresses": [HOME_ADDRESS, WORK_ADDRESS]}).json()["id"]
    assert count_address_rows() == 2

    assert client.delete(f"{BASE}/{contact_id}").status_code == 204
    # passive_deletes hands this to SQLite's ON DELETE CASCADE, so the check is
    # that the rows are really gone rather than left with a dangling contact_id.
    assert count_address_rows() == 0


def test_root_lists_entrypoints(client):
    body = client.get("/").json()
    assert body["contacts"] == BASE
