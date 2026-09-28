"""Phase 3: secure image upload, re-encoding, limits, ordering, storage backends."""

from __future__ import annotations

import io
import os

import pytest
from PIL import Image

from app.config import get_settings
from app.models import Vehicle
from app.services import images as image_service
from app.services.images import ImageError, process_image
from app.services.site import set_values
from app.services.storage import S3Storage, get_storage
from tests.helpers import (
    create_user,
    get_csrf,
    gps_exif,
    image_bytes,
    login_as,
    make_vehicle,
)

settings = get_settings()


def _upload(client, vehicle_id, files, plates="1", json=True):
    token = get_csrf(client, f"/admin/vozila/{vehicle_id}/slike")
    headers = {"Accept": "application/json"} if json else {}
    return client.post(
        f"/admin/vozila/{vehicle_id}/slike",
        data={"csrf_token": token, "plates_confirmed": plates},
        files=[("files", f) for f in files],
        headers=headers,
        follow_redirects=False,
    )


@pytest.fixture
def owner_vehicle(client, db):
    user_id, _ = create_user("vlasnik@test.hr")
    vehicle = make_vehicle(db, user_id)
    login_as(client, user_id)
    return vehicle


def test_non_image_with_jpg_extension_rejected(client, db, owner_vehicle):
    response = _upload(
        client, owner_vehicle.id, [("auto.jpg", b"<html>nije slika</html>", "image/jpeg")]
    )
    assert response.status_code == 400
    assert "nije ispravna slika" in response.json()["errors"][0]
    db.expire_all()
    assert db.get(Vehicle, owner_vehicle.id).images == []


def test_svg_and_gif_rejected():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    with pytest.raises(ImageError):
        process_image(svg)
    gif = io.BytesIO()
    Image.new("RGB", (10, 10)).save(gif, "GIF")
    with pytest.raises(ImageError, match="Dopušteni formati"):
        process_image(gif.getvalue())
    with pytest.raises(ImageError):
        process_image(b"%PDF-1.4 lazni pdf")


def test_upload_over_size_limit_rejected(client, db, owner_vehicle, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    noise = Image.frombytes("RGB", (800, 800), os.urandom(800 * 800 * 3))  # incompressible
    buffer = io.BytesIO()
    noise.save(buffer, "PNG")
    big = buffer.getvalue()
    assert len(big) > 1024 * 1024
    response = _upload(client, owner_vehicle.id, [("velika.png", big, "image/png")])
    assert response.status_code == 400
    assert "veća od 1 MB" in response.json()["errors"][0]


def test_too_large_dimensions_rejected():
    buffer = io.BytesIO()
    Image.new("L", (12_500, 10)).save(buffer, "PNG")
    with pytest.raises(ImageError, match="prevelika"):
        process_image(buffer.getvalue())


def test_exif_gps_removed_orientation_fixed_three_variants(client, db, owner_vehicle):
    data = image_bytes("JPEG", size=(1800, 1200), exif=gps_exif(orientation=6))
    assert Image.open(io.BytesIO(data)).getexif().get_ifd(0x8825)  # GPS present in source
    response = _upload(client, owner_vehicle.id, [("gps.jpg", data, "image/jpeg")])
    assert response.status_code == 200 and response.json()["ok"]
    db.expire_all()
    image = db.get(Vehicle, owner_vehicle.id).images[0]
    assert image.file_key.startswith(f"vehicles/{owner_vehicle.id}/")
    assert (image.width, image.height) == (1200, 1800)  # rotated by EXIF orientation 6
    storage = get_storage()
    for size in (400, 1000, 1600):
        payload = storage.read(f"{image.file_key}_{size}.webp")
        variant = Image.open(io.BytesIO(payload))
        assert variant.format == "WEBP"
        assert variant.width == min(size, 1200)
        assert variant.height > variant.width  # portrait after orientation fix
        assert not variant.getexif()  # no EXIF at all (GPS, camera...)
        assert b"TestCam" not in payload


def test_png_with_transparency_is_flattened():
    buffer = io.BytesIO()
    Image.new("RGBA", (500, 400), (0, 0, 0, 0)).save(buffer, "PNG")
    processed = process_image(buffer.getvalue(), sizes=(400,))
    variant = Image.open(io.BytesIO(processed.variants[400]))
    assert variant.mode == "RGB"


def test_plates_confirmation_required(client, db, owner_vehicle):
    response = _upload(
        client, owner_vehicle.id, [("a.jpg", image_bytes(), "image/jpeg")], plates=""
    )
    assert response.status_code == 400
    assert "registarske tablice" in response.json()["errors"][0]
    set_values(db, {"plates_reminder_enabled": "false"})
    db.commit()
    response = _upload(
        client, owner_vehicle.id, [("a.jpg", image_bytes(), "image/jpeg")], plates=""
    )
    assert response.status_code == 200


def test_image_count_limit(client, db, owner_vehicle, monkeypatch):
    monkeypatch.setattr(settings, "MAX_IMAGES_PER_VEHICLE", 2)
    files = [(f"{i}.jpg", image_bytes(size=(400, 300)), "image/jpeg") for i in range(3)]
    response = _upload(client, owner_vehicle.id, files)
    assert response.status_code == 400
    assert "Najviše 2 slika" in response.json()["errors"][0]
    assert _upload(client, owner_vehicle.id, files[:2]).status_code == 200
    assert _upload(client, owner_vehicle.id, files[:1]).status_code == 400


def test_reorder_set_main_and_delete(client, db, owner_vehicle):
    files = [
        (f"{i}.jpg", image_bytes(size=(400, 300), color=(i * 60, 0, 0)), "image/jpeg")
        for i in range(3)
    ]
    _upload(client, owner_vehicle.id, files)
    db.expire_all()
    ids = [image.id for image in db.get(Vehicle, owner_vehicle.id).images]
    token = get_csrf(client, f"/admin/vozila/{owner_vehicle.id}/slike")
    new_order = [ids[2], ids[0], ids[1]]
    response = client.post(
        f"/admin/vozila/{owner_vehicle.id}/slike/redoslijed",
        json={"order": new_order},
        headers={"X-CSRF-Token": token},
    )
    assert response.json() == {"ok": True}
    db.expire_all()
    assert [i.id for i in db.get(Vehicle, owner_vehicle.id).images] == new_order
    # Wrong ids are rejected; missing CSRF header -> 403.
    bad = client.post(
        f"/admin/vozila/{owner_vehicle.id}/slike/redoslijed",
        json={"order": [ids[0], 999]},
        headers={"X-CSRF-Token": token},
    )
    assert bad.status_code == 400
    no_csrf = client.post(
        f"/admin/vozila/{owner_vehicle.id}/slike/redoslijed", json={"order": new_order}
    )
    assert no_csrf.status_code == 403
    # Set main.
    client.post(
        f"/admin/vozila/{owner_vehicle.id}/slike/{ids[1]}/glavna", data={"csrf_token": token}
    )
    db.expire_all()
    assert db.get(Vehicle, owner_vehicle.id).images[0].id == ids[1]
    # Delete removes the files.
    image = db.get(Vehicle, owner_vehicle.id).images[0]
    key = image.file_key
    client.post(
        f"/admin/vozila/{owner_vehicle.id}/slike/{image.id}/obrisi", data={"csrf_token": token}
    )
    db.expire_all()
    assert len(db.get(Vehicle, owner_vehicle.id).images) == 2
    assert not get_storage().exists(f"{key}_400.webp")


def test_upload_without_js_redirects_with_flash(client, db, owner_vehicle):
    response = _upload(
        client, owner_vehicle.id, [("a.jpg", image_bytes(), "image/jpeg")], json=False
    )
    assert response.status_code == 303
    page = client.get(f"/admin/vozila/{owner_vehicle.id}/slike")
    assert "Učitano slika: 1" in page.text


def test_alt_texts_saved(client, db, owner_vehicle):
    _upload(client, owner_vehicle.id, [("a.jpg", image_bytes(), "image/jpeg")])
    db.expire_all()
    image = db.get(Vehicle, owner_vehicle.id).images[0]
    token = get_csrf(client, f"/admin/vozila/{owner_vehicle.id}/slike")
    client.post(
        f"/admin/vozila/{owner_vehicle.id}/slike/alt",
        data={"csrf_token": token, f"alt_{image.id}": "Prednja strana"},
    )
    db.expire_all()
    assert db.get(Vehicle, owner_vehicle.id).images[0].alt == "Prednja strana"


def test_logo_keeps_alpha_and_two_sizes():
    buffer = io.BytesIO()
    Image.new("RGBA", (800, 300), (10, 20, 30, 0)).save(buffer, "PNG")
    key = image_service.save_logo(buffer.getvalue())
    storage = get_storage()
    for size in (200, 400):
        variant = Image.open(io.BytesIO(storage.read(f"{key}_{size}.webp")))
        assert variant.mode == "RGBA" and variant.width == size


def test_s3_storage_backend_with_moto():
    boto3 = pytest.importorskip("boto3")
    moto = pytest.importorskip("moto")
    with moto.mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="autokuca-test")
        storage = S3Storage(
            endpoint="",
            bucket="autokuca-test",
            access_key="test",
            secret_key="test",
            region="us-east-1",
            media_url="https://media.primjer.hr",
        )
        storage.save("vehicles/1/abc_400.webp", b"RIFF0000WEBP", "image/webp")
        assert storage.exists("vehicles/1/abc_400.webp")
        assert storage.read("vehicles/1/abc_400.webp") == b"RIFF0000WEBP"
        head = client.head_object(Bucket="autokuca-test", Key="vehicles/1/abc_400.webp")
        assert head["ContentType"] == "image/webp"
        assert storage.url("vehicles/1/abc_400.webp") == (
            "https://media.primjer.hr/vehicles/1/abc_400.webp"
        )
        storage.delete("vehicles/1/abc_400.webp")
        assert not storage.exists("vehicles/1/abc_400.webp")
        with pytest.raises(ValueError):
            storage.save("../etc/passwd.webp", b"x")
