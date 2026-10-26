"""Photo and signature preparation."""

from __future__ import annotations

from backend.core.biometrics import BiometricCompressor


def test_generated_demo_assets_are_in_spec():
    BiometricCompressor.generate_sample_assets()

    from backend.core import settings

    photo = (settings.UPLOADS_DIR / "candidate_photo.jpg").read_bytes()
    signature = (settings.UPLOADS_DIR / "candidate_signature.jpg").read_bytes()

    photo_result = BiometricCompressor.compress_photograph(photo)
    assert photo_result["success"] is True
    assert photo_result["dimensions"] == "350x350 px"
    assert 20.0 <= photo_result["compressed_size_kb"] <= 50.0
    assert photo_result["in_spec"] is True
    assert photo_result["data_uri"].startswith("data:image/jpeg;base64,")

    signature_result = BiometricCompressor.compress_signature(signature)
    assert signature_result["success"] is True
    assert signature_result["dimensions"] == "140x60 px"
    assert 10.0 <= signature_result["compressed_size_kb"] <= 20.0
    assert signature_result["in_spec"] is True


def test_custom_target_dimensions_are_respected():
    from PIL import Image
    import io

    buffer = io.BytesIO()
    Image.new("RGB", (640, 480), (240, 240, 240)).save(buffer, format="JPEG")
    source = buffer.getvalue()

    result = BiometricCompressor.compress_signature(
        source,
        target_width=160,
        target_height=70,
        min_kb=5.0,
        max_kb=30.0,
    )

    assert result["dimensions"] == "160x70 px"
    assert result["in_spec"] is True
