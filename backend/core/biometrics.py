import io
import os
import base64
from typing import Dict, Any, Tuple
from PIL import Image, ImageOps, ImageEnhance

UPLOADS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

class BiometricCompressor:
    """Deterministic binary search biometric compression engine matching strict NIC/RRB/SSC specs."""

    @staticmethod
    def _strip_exif(image: Image.Image) -> Image.Image:
        """Strips EXIF metadata to ensure privacy and byte reduction."""
        data = list(image.getdata())
        image_without_exif = Image.new(image.mode, image.size)
        image_without_exif.putdata(data)
        return image_without_exif

    @classmethod
    def compress_signature(
        cls,
        image_bytes: bytes,
        target_width: int = 140,
        target_height: int = 60,
        min_kb: float = 10.0,
        max_kb: float = 20.0,
        output_filename: str = "compressed_signature.jpg"
    ) -> Dict[str, Any]:
        """
        Compresses signature deterministically to 10KB - 20KB JPEG with 140x60 px dimensions.
        Converts background to clean white and optimizes contrast for ink clarity.
        """
        original_size_kb = len(image_bytes) / 1024.0
        
        # Load image
        img = Image.open(io.BytesIO(image_bytes))
        orig_dims = img.size

        # Convert to RGB (handling RGBA transparency by flattening on pure white background)
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[3])
            img = background
        else:
            img = img.convert("RGB")

        # Enhance ink contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.2)

        # Resize to exact dimensions (using high-quality LANCZOS)
        img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
        img = cls._strip_exif(img)

        # Binary search for JPEG quality to fit within [min_kb, max_kb]
        low_q = 15
        high_q = 95
        best_output = None
        best_size_kb = 0

        for _ in range(12):  # Fast binary search convergence
            mid_q = (low_q + high_q) // 2
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=mid_q, optimize=True)
            size_kb = buffer.tell() / 1024.0

            if min_kb <= size_kb <= max_kb:
                best_output = buffer.getvalue()
                best_size_kb = size_kb
                break
            elif size_kb < min_kb:
                # Need higher quality to increase size
                low_q = mid_q + 1
                best_output = buffer.getvalue()
                best_size_kb = size_kb
            else:
                # Need lower quality to decrease size
                high_q = mid_q - 1
                best_output = buffer.getvalue()
                best_size_kb = size_kb

        # If best output is slightly under min_kb, append safe zero comment padding
        if best_size_kb < min_kb and best_output:
            needed_bytes = int((min_kb + 1.0) * 1024) - len(best_output)
            if needed_bytes > 0:
                comment_padding = b" " * needed_bytes
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=high_q, optimize=False, comment=comment_padding)
                best_output = buf.getvalue()
                best_size_kb = len(best_output) / 1024.0

        # Save to disk
        output_path = os.path.join(UPLOADS_DIR, output_filename)
        with open(output_path, "wb") as f:
            f.write(best_output)

        b64 = base64.b64encode(best_output).decode("utf-8")
        return {
            "success": True,
            "file_type": "Signature",
            "file_path": output_path,
            "original_size_kb": round(original_size_kb, 2),
            "compressed_size_kb": round(best_size_kb, 2),
            "target_range_kb": f"{min_kb}KB - {max_kb}KB",
            "dimensions": f"{target_width}x{target_height} px",
            "original_dimensions": f"{orig_dims[0]}x{orig_dims[1]} px",
            "format": "JPEG",
            "in_spec": min_kb <= best_size_kb <= max_kb,
            "data_uri": f"data:image/jpeg;base64,{b64}"
        }

    @classmethod
    def compress_photograph(
        cls,
        image_bytes: bytes,
        target_width: int = 350,
        target_height: int = 350,
        min_kb: float = 20.0,
        max_kb: float = 50.0,
        output_filename: str = "compressed_photo.jpg"
    ) -> Dict[str, Any]:
        """
        Compresses candidate photograph deterministically to 20KB - 50KB JPEG (350x350 px).
        """
        original_size_kb = len(image_bytes) / 1024.0
        img = Image.open(io.BytesIO(image_bytes))
        orig_dims = img.size

        # Convert to RGB
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Center-crop to square before resizing to maintain aspect ratio
        w, h = img.size
        min_dim = min(w, h)
        left = (w - min_dim) / 2
        top = (h - min_dim) / 2
        right = (w + min_dim) / 2
        bottom = (h + min_dim) / 2
        img = img.crop((left, top, right, bottom))

        # Resize to target 350x350
        img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
        img = cls._strip_exif(img)

        # Binary search for JPEG quality
        low_q = 20
        high_q = 95
        best_output = None
        best_size_kb = 0

        for _ in range(12):
            mid_q = (low_q + high_q) // 2
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=mid_q, optimize=True)
            size_kb = buffer.tell() / 1024.0

            if min_kb <= size_kb <= max_kb:
                best_output = buffer.getvalue()
                best_size_kb = size_kb
                break
            elif size_kb < min_kb:
                low_q = mid_q + 1
                best_output = buffer.getvalue()
                best_size_kb = size_kb
            else:
                high_q = mid_q - 1
                best_output = buffer.getvalue()
                best_size_kb = size_kb

        # Pad safely if undersized
        if best_size_kb < min_kb and best_output:
            needed = int((min_kb + 2.0) * 1024) - len(best_output)
            if needed > 0:
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=high_q, optimize=False, comment=b" " * needed)
                best_output = buf.getvalue()
                best_size_kb = len(best_output) / 1024.0

        output_path = os.path.join(UPLOADS_DIR, output_filename)
        with open(output_path, "wb") as f:
            f.write(best_output)

        b64 = base64.b64encode(best_output).decode("utf-8")
        return {
            "success": True,
            "file_type": "Passport Photograph",
            "file_path": output_path,
            "original_size_kb": round(original_size_kb, 2),
            "compressed_size_kb": round(best_size_kb, 2),
            "target_range_kb": f"{min_kb}KB - {max_kb}KB",
            "dimensions": f"{target_width}x{target_height} px",
            "original_dimensions": f"{orig_dims[0]}x{orig_dims[1]} px",
            "format": "JPEG",
            "in_spec": min_kb <= best_size_kb <= max_kb,
            "data_uri": f"data:image/jpeg;base64,{b64}"
        }

    @classmethod
    def generate_sample_assets(cls):
        """Generates realistic test photo and signature if user hasn't uploaded yet."""
        photo_path = os.path.join(UPLOADS_DIR, "candidate_photo.jpg")
        sig_path = os.path.join(UPLOADS_DIR, "candidate_signature.jpg")

        if not os.path.exists(photo_path):
            # Create a clean passport photo graphic
            img = Image.new("RGB", (400, 400), (220, 235, 245))
            # Draw simple passport silhouette
            from PIL import ImageDraw
            draw = ImageDraw.Draw(img)
            # Head circle
            draw.ellipse([150, 80, 250, 180], fill=(230, 190, 160), outline=(50, 50, 50), width=2)
            # Hair
            draw.arc([150, 70, 250, 140], start=180, end=360, fill=(30, 25, 20), width=15)
            # Body/Suit
            draw.polygon([(80, 400), (140, 220), (260, 220), (320, 400)], fill=(35, 45, 65))
            # Text tag
            draw.text((110, 360), "AMAN K. SHARMA", fill=(255, 255, 255))
            
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            cls.compress_photograph(buf.getvalue(), output_filename="candidate_photo.jpg")

        if not os.path.exists(sig_path):
            # Create realistic signature graphic
            sig = Image.new("RGB", (300, 120), (255, 255, 255))
            from PIL import ImageDraw
            draw = ImageDraw.Draw(sig)
            # Smooth signature ink stroke
            points = [
                (30, 80), (60, 30), (80, 75), (95, 45), (120, 70), 
                (140, 60), (160, 75), (190, 55), (210, 80), (250, 40), (270, 85)
            ]
            draw.line(points, fill=(10, 20, 90), width=4, joint="curve")
            draw.line([(40, 95), (260, 92)], fill=(10, 20, 90), width=3)
            
            buf = io.BytesIO()
            sig.save(buf, format="JPEG", quality=85)
            cls.compress_signature(buf.getvalue(), output_filename="candidate_signature.jpg")
