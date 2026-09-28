"""QR rendering: PNG (styled), real SVG, and base64 encoding (Phase 2 route split).

Pure rendering — no HTTP, no database. Logo input may be raw bytes (preview),
an s3:// storage reference, or a legacy local path.
"""
import base64
import io
from io import BytesIO

import qrcode
from PIL import Image, ImageDraw, ImageFont
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.colormasks import (
    RadialGradiantColorMask,
    SolidFillColorMask,
    SquareGradiantColorMask,
)
from qrcode.image.styles.moduledrawers import (
    CircleModuleDrawer,
    GappedSquareModuleDrawer,
    RoundedModuleDrawer,
    SquareModuleDrawer,
)
from qrcode.image.svg import SvgPathImage

from app.config import logger
from app.services import storage as _storage
from app.utils import hex_to_rgb


def create_qr_image(content, fg_color="#0A0A0A", bg_color="#FFFFFF", pattern="square",
                    eye_style="square", gradient=None, logo_path=None, frame_text=None,
                    frame_color="#00FF88", size=1000,
                    error_correction=qrcode.constants.ERROR_CORRECT_H, logo_bytes=None):
    if pattern == "dots" or pattern == "dot":
        drawer = CircleModuleDrawer()
        eye_drawer = CircleModuleDrawer()
    elif pattern == "rounded":
        drawer = RoundedModuleDrawer()
        eye_drawer = RoundedModuleDrawer()
    elif pattern == "gapped":
        drawer = GappedSquareModuleDrawer()
        eye_drawer = GappedSquareModuleDrawer()
    elif pattern == "extra-rounded":
        drawer = RoundedModuleDrawer(radius_ratio=0.8)
        eye_drawer = RoundedModuleDrawer()
    else:
        drawer = SquareModuleDrawer()
        eye_drawer = SquareModuleDrawer()

    if eye_style == "circle":
        eye_drawer = CircleModuleDrawer()
    elif eye_style == "rounded":
        eye_drawer = RoundedModuleDrawer()
    elif eye_style == "leaf":
        eye_drawer = RoundedModuleDrawer()

    try:
        fg_rgb = hex_to_rgb(fg_color) if fg_color else (10, 10, 10)
        bg_rgb = hex_to_rgb(bg_color) if bg_color else (255, 255, 255)
    except Exception as e:
        logger.warning(f"Color parse failed {fg_color}/{bg_color}: {e}")
        fg_rgb = (10, 10, 10)
        bg_rgb = (255, 255, 255)

    qr = qrcode.QRCode(version=None, error_correction=error_correction, box_size=10, border=4)
    qr.add_data(content)
    qr.make(fit=True)

    if gradient and gradient != "none" and gradient != "solid":
        try:
            if gradient == "radial":
                color_mask = RadialGradiantColorMask(
                    back_color=bg_rgb, center_color=fg_rgb, edge_color=hex_to_rgb("#00FF88"))
            else:
                color_mask = SquareGradiantColorMask(
                    back_color=bg_rgb, center_color=fg_rgb, edge_color=hex_to_rgb("#00FF88"))
        except Exception as e:
            logger.warning(f"Gradient mask failed: {e}")
            color_mask = SolidFillColorMask(back_color=bg_rgb, front_color=fg_rgb)
    else:
        color_mask = SolidFillColorMask(back_color=bg_rgb, front_color=fg_rgb)

    img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=drawer,
        eye_drawer=eye_drawer,
        color_mask=color_mask,
    ).convert("RGBA")
    img = img.resize((size, size), Image.LANCZOS)

    # Logo: raw bytes (preview, never persisted), an s3:// storage ref, or a
    # local path (legacy rows).
    logo = None
    if logo_bytes:
        try:
            logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
        except Exception as e:
            logger.warning(f"logo bytes decode failed: {e}")
    elif logo_path and str(logo_path).startswith(_storage.S3_PREFIX):
        logo = _storage.load_logo_image(logo_path)
    elif logo_path:
        # A non-s3 reference is a local/legacy path. Reading it goes through
        # storage so the opt-in rule is enforced in one place.
        try:
            logo = _storage.load_logo_image(logo_path)
        except Exception as e:
            logger.warning(f"logo load failed: {e}")
    if logo is not None:
        try:
            logo_size = int(size * 0.22)
            logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
            bg_size = logo_size + 20
            logo_bg = Image.new("RGBA", (bg_size, bg_size), (255, 255, 255, 255))
            mask = Image.new("L", (bg_size, bg_size), 0)
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle([0, 0, bg_size, bg_size], radius=18, fill=255)
            logo_bg.putalpha(mask)
            pos_bg = ((size - bg_size) // 2, (size - bg_size) // 2)
            img.paste(logo_bg, pos_bg, logo_bg)
            pos = ((size - logo_size) // 2, (size - logo_size) // 2)
            img.paste(logo, pos, logo)
        except Exception as e:
            logger.warning(f"logo overlay failed: {e}")

    if frame_text:
        try:
            frame_h = int(size * 0.14)
            new_h = size + frame_h
            try:
                fc = hex_to_rgb(frame_color) if frame_color else hex_to_rgb("#00FF88")
            except Exception:
                fc = (0, 255, 136)
            framed = Image.new("RGBA", (size, new_h), fc + (255,))
            framed.paste(img, (0, 0))
            draw = ImageDraw.Draw(framed)
            # Font fallback chain
            font = None
            for fp in ["arial.ttf", "DejaVuSans.ttf",
                       "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                       "/Library/Fonts/Arial.ttf",
                       "C:\\Windows\\Fonts\\arial.ttf"]:
                try:
                    font = ImageFont.truetype(fp, size=int(frame_h * 0.45))
                    break
                except Exception:
                    continue
            if font is None:
                font = ImageFont.load_default()
            text = frame_text[:32]
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = (size - tw) // 2
            ty = size + (frame_h - th) // 2 - 4
            brightness = (fc[0] * 299 + fc[1] * 587 + fc[2] * 114) / 1000
            text_color = (0, 0, 0) if brightness > 150 else (255, 255, 255)
            draw.text((tx, ty), text, fill=text_color, font=font)
            img = framed
        except Exception as e:
            logger.warning(f"frame render failed: {e}")

    return img


def create_qr_svg(content, fg_color="#0A0A0A", bg_color="#FFFFFF", size=400):
    """Real vector SVG (SvgPathImage) — not a PNG with the wrong name."""
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=10, border=4)
    qr.add_data(content)
    qr.make(fit=True)
    buf = BytesIO()
    try:
        img = qr.make_image(image_factory=SvgPathImage)
        img.save(buf)
        svg_data = buf.getvalue().decode()
        try:
            fg = fg_color if fg_color else "#0A0A0A"
            bg = bg_color if bg_color else "#FFFFFF"
            if "background" not in svg_data.lower():
                svg_data = svg_data.replace('fill="#000000"', f'fill="{fg}"')
                svg_data = svg_data.replace("#000000", fg)
                svg_data = svg_data.replace("#000", fg)
            else:
                svg_data = svg_data.replace("#FFFFFF", bg).replace("#ffffff", bg)
                svg_data = svg_data.replace("#000000", fg).replace("#000", fg)
        except Exception as e:
            logger.debug(f"SVG color inject failed: {e}")
        return svg_data
    except Exception as e:
        logger.warning(f"SVG generation failed, fallback: {e}")
        return f'<svg xmlns="http://www.w3.org/2000/svg"><text>{content}</text></svg>'


def image_to_base64(img, fmt="PNG"):
    buf = BytesIO()
    img.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode()
