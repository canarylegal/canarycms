"""PDF snapshot conversion and stamping for Canary Sign."""

from __future__ import annotations

import base64
import io
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pikepdf
from fastapi import HTTPException, status
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session

from app.file_storage import FILES_ROOT, ensure_files_root, path_is_under_files_root
from app.models import File as DbFile, User
from app.quote_portal_pdf import convert_case_file_to_pdf_bytes_via_onlyoffice

log = logging.getLogger(__name__)

_PDF_MIME = "application/pdf"
_OFFICE_EXTS = {".doc", ".docx", ".odt", ".rtf", ".xls", ".xlsx", ".ods", ".ppt", ".pptx", ".odp"}
_FONTS_DIR = Path(__file__).resolve().parent / "fonts"

MSG_CONVERT_FOR_SIGNING = (
    "Could not convert this document for signing. Try a PDF, or check ONLYOFFICE is available."
)
MSG_PDF_PREPARE_FAILED = "This PDF could not be prepared for signing."


def http_exception_for_pdf_snapshot_failure(exc: BaseException) -> HTTPException:
    """Map OnlyOffice/httpx/pikepdf failures to client-safe details (caller should log.exception)."""
    text = str(exc).strip().lower()
    module = type(exc).__module__ or ""

    bad_pdf = (
        module.startswith("pikepdf")
        or "not a valid pdf" in text
        or "invalid pdf" in text
        or "pdf syntax" in text
    )
    unsupported = "unsupported format" in text
    if bad_pdf:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=MSG_PDF_PREPARE_FAILED)
    if unsupported:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=MSG_CONVERT_FOR_SIGNING)

    oo_or_unavailable = (
        module.startswith("httpx")
        or isinstance(exc, (ConnectionError, TimeoutError, FileNotFoundError))
        or "onlyoffice" in text
        or "timed out" in text
        or "timeout" in text
        or "connection" in text
    )
    if oo_or_unavailable:
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=MSG_CONVERT_FOR_SIGNING)

    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=MSG_CONVERT_FOR_SIGNING)


def http_exception_for_pdf_prepare_failure(_exc: BaseException | None = None) -> HTTPException:
    """Fill/stamp/flatten failures — never leak library messages to clients."""
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=MSG_PDF_PREPARE_FAILED)


@dataclass
class PdfStamp:
    """Stamp placement: percentages are from the top-left of the page (0–100)."""

    page: int  # 1-based
    x_pct: float
    y_pct: float
    w_pct: float
    h_pct: float
    png_bytes: bytes | None = None
    text: str | None = None
    style: str | None = None  # "signature" uses script font for text


def ensure_snapshot_pdf_bytes(
    db: Session,
    source: DbFile,
    actor: User,
    conversion_key: str,
) -> bytes:
    """Return PDF bytes for the source file (pass-through PDF, or OnlyOffice convert)."""
    ensure_files_root()
    abs_path = (FILES_ROOT / source.storage_path).resolve()
    if not path_is_under_files_root(abs_path) or not abs_path.is_file():
        raise FileNotFoundError("Source file missing on disk")

    ext = Path(source.original_filename or "").suffix.lower()
    mime = (source.mime_type or "").strip().lower()
    if mime == _PDF_MIME or ext == ".pdf":
        raw = abs_path.read_bytes()
        if not raw.startswith(b"%PDF"):
            raise RuntimeError("Source file is not a valid PDF")
        return raw

    if ext not in _OFFICE_EXTS:
        raise RuntimeError(f"Unsupported format for Canary Sign: {source.original_filename}")

    return convert_case_file_to_pdf_bytes_via_onlyoffice(
        db,
        source=source,
        user=actor,
        conversion_key=conversion_key,
    )


def _font_path(*names: str) -> Path | None:
    for name in names:
        path = _FONTS_DIR / name
        if path.is_file():
            return path
    return None


def _truetype(size: int, *names: str) -> ImageFont.ImageFont:
    path = _font_path(*names)
    if path is not None:
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            pass
    for fallback in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(fallback, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _load_font(size: int) -> ImageFont.ImageFont:
    return _truetype(size, "DejaVuSans.ttf")


def _load_bold_font(size: int) -> ImageFont.ImageFont:
    return _truetype(size, "DejaVuSans-Bold.ttf", "DejaVuSans.ttf")


def _load_script_font(size: int, file_name: str | None = None) -> ImageFont.ImageFont:
    names: tuple[str, ...]
    if file_name:
        names = (file_name, "GreatVibes-Regular.ttf", "DejaVuSans.ttf")
    else:
        names = (
            "GreatVibes-Regular.ttf",
            "Allura-Regular.ttf",
            "Sacramento-Regular.ttf",
            "HomemadeApple-Regular.ttf",
            "Satisfy-Regular.ttf",
            "DejaVuSans.ttf",
        )
    return _truetype(size, *names)


def _fit_text_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    max_width: int,
    max_height: int,
    load_font,
    start_size: int,
    min_size: int = 10,
) -> ImageFont.ImageFont:
    font = load_font(start_size)
    for size in range(start_size, min_size - 1, -2):
        font = load_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if tw <= max_width and th <= max_height:
            break
    return font


def _render_text_png(text: str, *, width: int, height: int, align: str = "center") -> bytes:
    """Standard (non-script) field text — printed name, date, etc."""
    width = max(32, width)
    height = max(16, height)
    scale = 3
    iw, ih = width * scale, height * scale
    img = Image.new("RGBA", (iw, ih), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    pad_x, pad_y = 4 * scale, 2 * scale
    font = _fit_text_font(
        draw,
        text,
        max_width=iw - pad_x * 2,
        max_height=ih - pad_y * 2,
        load_font=_load_font,
        start_size=max(12 * scale, min(ih - pad_y * 2, 42 * scale)),
        min_size=9 * scale,
    )
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if align == "left":
        x = pad_x - bbox[0]
    else:
        x = max(pad_x, (iw - tw) // 2 - bbox[0])
    y = max(pad_y, (ih - th) // 2 - bbox[1])
    draw.text((x, y), text, fill=(15, 23, 42, 255), font=font)
    img = img.resize((width, height), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _render_signature_script_png(
    text: str,
    *,
    width: int,
    height: int,
    font_file: str | None = None,
) -> bytes:
    """DocuSign-style typed signature: name in a script font on a transparent PNG."""
    width = max(64, width)
    height = max(32, height)
    scale = 2
    iw, ih = width * scale, height * scale
    img = Image.new("RGBA", (iw, ih), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    pad_x, pad_y = 8 * scale, 4 * scale

    def load(size: int) -> ImageFont.ImageFont:
        return _load_script_font(size, font_file)

    font = _fit_text_font(
        draw,
        text,
        max_width=iw - pad_x * 2,
        max_height=ih - pad_y * 2,
        load_font=load,
        start_size=max(24 * scale, min(ih - pad_y * 2, 96 * scale)),
        min_size=14 * scale,
    )
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    # Left-align with modest padding; sit slightly above the bottom so signature lines remain visible.
    x = pad_x - bbox[0]
    y = max(pad_y, ih - pad_y - th - bbox[1])
    draw.text((x, y), text, fill=(15, 23, 42, 255), font=font)
    if scale > 1:
        img = img.resize((width, height), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _render_checkbox_png(*, width: int, height: int, checked: bool) -> bytes:
    width = max(12, width)
    height = max(12, height)
    size = min(width, height)
    img = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    ox = (width - size) // 2
    oy = (height - size) // 2
    pad = max(1, size // 10)
    draw.rectangle(
        [ox + pad, oy + pad, ox + size - pad, oy + size - pad],
        outline=(30, 30, 30, 255),
        width=max(1, size // 12),
    )
    if checked:
        draw.line(
            [ox + pad * 2, oy + size // 2, ox + size // 2, oy + size - pad * 2],
            fill=(20, 100, 40, 255),
            width=max(2, size // 10),
        )
        draw.line(
            [ox + size // 2, oy + size - pad * 2, ox + size - pad * 2, oy + pad * 2],
            fill=(20, 100, 40, 255),
            width=max(2, size // 10),
        )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _png_to_stamp_pdf(
    png_bytes: bytes,
    width_pt: float,
    height_pt: float,
    *,
    dpi: int = 144,
    align: str = "left",
) -> bytes:
    """Build a one-page PDF containing the PNG fitted into the box (contain, no stretch)."""
    pil = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    tw = max(8, int(width_pt * dpi / 72))
    th = max(8, int(height_pt * dpi / 72))
    # Letterbox into the field so handwriting is not horizontally stretched.
    src_w, src_h = pil.size
    if src_w < 1 or src_h < 1:
        src_w, src_h = 1, 1
    # Left padding + extra bottom inset so printed signature lines stay visible.
    pad_x = max(2, tw // 28)
    pad_top = max(2, th // 20)
    pad_bottom = max(3, th // 5)
    avail_w = max(1, tw - pad_x * 2)
    avail_h = max(1, th - pad_top - pad_bottom)
    scale = min(avail_w / src_w, avail_h / src_h)
    nw = max(1, int(src_w * scale))
    nh = max(1, int(src_h * scale))
    if (nw, nh) != (src_w, src_h):
        pil = pil.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (tw, th), (255, 255, 255, 0))
    if align == "center":
        ox = (tw - nw) // 2
        oy = pad_top + (avail_h - nh) // 2
    else:
        ox = pad_x
        # Sit above the field baseline / underline rather than covering it.
        oy = max(pad_top, th - pad_bottom - nh)
    canvas.paste(pil, (ox, oy), pil)
    bg = Image.new("RGB", (tw, th), (255, 255, 255))
    bg.paste(canvas, (0, 0), canvas)

    pdf = pikepdf.Pdf.new()
    page = pdf.add_blank_page(page_size=(width_pt, height_pt))
    raw = bg.tobytes()
    image = pikepdf.Stream(
        pdf,
        raw,
        {
            "/Type": pikepdf.Name.XObject,
            "/Subtype": pikepdf.Name.Image,
            "/Width": tw,
            "/Height": th,
            "/ColorSpace": pikepdf.Name.DeviceRGB,
            "/BitsPerComponent": 8,
        },
    )
    resources = page.get("/Resources", None)
    if resources is None:
        resources = pikepdf.Dictionary({})
        page["/Resources"] = resources
    xobjects = resources.get("/XObject", None)
    if xobjects is None:
        xobjects = pikepdf.Dictionary({})
        resources["/XObject"] = xobjects
    xobjects["/Im0"] = image
    content = f"q {width_pt:.4f} 0 0 {height_pt:.4f} 0 0 cm /Im0 Do Q\n"
    page.contents_add(pikepdf.Stream(pdf, content.encode("ascii")))

    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def stamp_signed_pdf(pdf_bytes: bytes, stamps: list[PdfStamp]) -> bytes:
    """Overlay PNG/text stamps onto a PDF. Coordinates are top-left percentages."""
    if not stamps:
        return pdf_bytes

    with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
        for stamp in stamps:
            page_idx = max(1, int(stamp.page)) - 1
            if page_idx < 0 or page_idx >= len(pdf.pages):
                log.warning("Canary Sign stamp skipped: page %s out of range", stamp.page)
                continue
            page = pdf.pages[page_idx]
            mediabox = page.mediabox
            page_w = float(mediabox[2] - mediabox[0])
            page_h = float(mediabox[3] - mediabox[1])
            if page_w <= 0 or page_h <= 0:
                continue

            w = max(1.0, page_w * (float(stamp.w_pct) / 100.0))
            h = max(1.0, page_h * (float(stamp.h_pct) / 100.0))
            x = float(mediabox[0]) + page_w * (float(stamp.x_pct) / 100.0)
            y_top = page_h * (float(stamp.y_pct) / 100.0)
            y = float(mediabox[1]) + page_h - y_top - h

            png = stamp.png_bytes
            if png is None and stamp.text is not None:
                # Render at high pixel density so text scales cleanly into the field box
                px_w = max(120, int(w * 4))
                px_h = max(40, int(h * 4))
                if stamp.style == "signature":
                    png = _render_signature_script_png(stamp.text, width=px_w, height=px_h)
                else:
                    png = _render_text_png(stamp.text, width=px_w, height=px_h)
            if not png:
                continue

            try:
                stamp_pdf_bytes = _png_to_stamp_pdf(png, w, h, dpi=216, align="left")
                with pikepdf.open(io.BytesIO(stamp_pdf_bytes)) as stamp_pdf:
                    page.add_overlay(
                        stamp_pdf.pages[0],
                        rect=pikepdf.Rectangle(x, y, x + w, y + h),
                    )
            except Exception:
                log.exception("Canary Sign stamp failed on page %s", stamp.page)
                continue

        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()


def stamp_from_field_value(
    *,
    page: int,
    x_pct: float,
    y_pct: float,
    w_pct: float,
    h_pct: float,
    field_type: str,
    value: dict[str, Any] | None,
) -> PdfStamp | None:
    """Build a stamp from a filled field value."""
    if not value:
        return None
    if field_type in ("signature", "initials"):
        b64 = value.get("image_b64") or value.get("png_b64")
        if not b64:
            text = (value.get("text") or "").strip()
            if not text:
                return None
            return PdfStamp(
                page=page,
                x_pct=x_pct,
                y_pct=y_pct,
                w_pct=w_pct,
                h_pct=h_pct,
                text=text,
                style="signature",
            )
        raw = b64
        if isinstance(raw, str) and "," in raw and raw.strip().startswith("data:"):
            raw = raw.split(",", 1)[1]
        try:
            png = base64.b64decode(raw)
        except Exception:
            return None
        return PdfStamp(page=page, x_pct=x_pct, y_pct=y_pct, w_pct=w_pct, h_pct=h_pct, png_bytes=png)
    if field_type == "checkbox":
        checked = bool(value.get("checked"))
        w_px = max(12, int(600 * w_pct / 100))
        h_px = max(12, int(800 * h_pct / 100))
        return PdfStamp(
            page=page,
            x_pct=x_pct,
            y_pct=y_pct,
            w_pct=w_pct,
            h_pct=h_pct,
            png_bytes=_render_checkbox_png(width=w_px, height=h_px, checked=checked),
        )
    text = (value.get("text") or "").strip()
    if not text:
        return None
    return PdfStamp(page=page, x_pct=x_pct, y_pct=y_pct, w_pct=w_pct, h_pct=h_pct, text=text)


def _format_dt(value: datetime | str | None) -> str:
    if value is None:
        return "—"
    dt: datetime | None
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if not raw:
            return "—"
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return raw[:19].replace("T", " ")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.strftime("%d %B %Y, %H:%M UTC")


def _summarise_user_agent(ua: str | None) -> str | None:
    text = (ua or "").strip()
    if not text:
        return None
    browser = "Browser"
    if "Edg/" in text:
        browser = "Edge"
    elif "Chrome/" in text and "Chromium" not in text:
        browser = "Chrome"
    elif "Firefox/" in text:
        browser = "Firefox"
    elif "Safari/" in text and "Chrome/" not in text:
        browser = "Safari"
    device = "desktop"
    if "Android" in text:
        device = "Android"
    elif "iPhone" in text or "iPad" in text:
        device = "iOS"
    elif "Mobile" in text:
        device = "mobile"
    elif "Windows" in text:
        device = "Windows"
    elif "Macintosh" in text:
        device = "macOS"
    elif "Linux" in text:
        device = "Linux"
    return f"{browser} on {device}"


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = re.split(r"(\s+)", text)
    lines: list[str] = []
    current = ""
    for part in words:
        trial = current + part
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width or not current.strip():
            current = trial
            continue
        lines.append(current.rstrip())
        current = part.lstrip()
    if current.strip():
        lines.append(current.rstrip())
    return lines or [""]


def build_audit_certificate_pdf(
    *,
    subject: str,
    matter_label: str,
    signers: list[dict[str, Any]],
    completed_at: datetime | None,
    request_id: str,
) -> bytes:
    """Polished A4 certificate rendered at print DPI with bundled fonts."""
    # A4 at 200 DPI for crisp print/screen viewing
    dpi = 200
    width = int(210 / 25.4 * dpi)
    height = int(297 / 25.4 * dpi)
    margin = int(18 / 25.4 * dpi)
    content_w = width - margin * 2

    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    brand = (8, 145, 178)  # canary cyan
    ink = (15, 23, 42)
    muted = (100, 116, 139)
    rule = (226, 232, 240)

    # Top brand bar
    bar_h = int(8 / 25.4 * dpi)
    draw.rectangle([0, 0, width, bar_h], fill=brand)

    title_font = _load_bold_font(int(22 / 72 * dpi))
    h2_font = _load_bold_font(int(13 / 72 * dpi))
    body_font = _load_font(int(11 / 72 * dpi))
    small_font = _load_font(int(9.5 / 72 * dpi))
    label_font = _load_bold_font(int(9.5 / 72 * dpi))

    y = margin + bar_h
    draw.text((margin, y), "Canary Sign", fill=brand, font=h2_font)
    y += int(18 / 72 * dpi)
    draw.text((margin, y), "Certificate of Completion", fill=ink, font=title_font)
    y += int(34 / 72 * dpi)
    draw.line([(margin, y), (width - margin, y)], fill=rule, width=2)
    y += int(16 / 72 * dpi)

    meta = [
        ("Document", (subject or "Untitled").strip() or "Untitled"),
        ("Matter", (matter_label or "—").strip() or "—"),
        ("Request ID", request_id),
        ("Completed", _format_dt(completed_at)),
    ]
    for label, value in meta:
        draw.text((margin, y), label.upper(), fill=muted, font=label_font)
        y += int(14 / 72 * dpi)
        for line in _wrap_text(draw, value, body_font, content_w):
            draw.text((margin, y), line, fill=ink, font=body_font)
            y += int(16 / 72 * dpi)
        y += int(8 / 72 * dpi)

    y += int(4 / 72 * dpi)
    draw.rectangle([margin, y, width - margin, y + int(52 / 72 * dpi)], fill=(248, 250, 252))
    note_y = y + int(12 / 72 * dpi)
    for line in _wrap_text(
        draw,
        "England & Wales electronic signature record. This is not a deed execution certificate.",
        small_font,
        content_w - int(16 / 72 * dpi),
    ):
        draw.text((margin + int(10 / 72 * dpi), note_y), line, fill=muted, font=small_font)
        note_y += int(14 / 72 * dpi)
    y += int(64 / 72 * dpi)

    draw.text((margin, y), "Signers", fill=ink, font=h2_font)
    y += int(22 / 72 * dpi)

    for idx, s in enumerate(signers, start=1):
        name = (s.get("name") or "Signer").strip() or "Signer"
        email = (s.get("email") or "").strip()
        signed_at = _format_dt(s.get("signed_at"))
        ip = (s.get("ip") or "—").strip() or "—"
        ua_summary = _summarise_user_agent(s.get("user_agent"))

        box_top = y
        box_pad = int(12 / 72 * dpi)
        inner_x = margin + box_pad
        inner_w = content_w - box_pad * 2

        draw.text((inner_x, y + box_pad), f"{idx}. {name}", fill=ink, font=_load_bold_font(int(12 / 72 * dpi)))
        line_y = y + box_pad + int(18 / 72 * dpi)
        if email:
            draw.text((inner_x, line_y), email, fill=muted, font=small_font)
            line_y += int(14 / 72 * dpi)
        draw.text((inner_x, line_y), f"Signed: {signed_at}", fill=ink, font=body_font)
        line_y += int(16 / 72 * dpi)
        draw.text((inner_x, line_y), f"IP address: {ip}", fill=ink, font=body_font)
        line_y += int(16 / 72 * dpi)
        if ua_summary:
            draw.text((inner_x, line_y), f"Device: {ua_summary}", fill=ink, font=body_font)
            line_y += int(16 / 72 * dpi)
        line_y += box_pad
        draw.rectangle([margin, box_top, width - margin, line_y], outline=rule, width=2)
        y = line_y + int(12 / 72 * dpi)

    footer = "Generated by Canary Sign"
    fb = draw.textbbox((0, 0), footer, font=small_font)
    draw.text(((width - (fb[2] - fb[0])) // 2, height - margin), footer, fill=muted, font=small_font)

    png_buf = io.BytesIO()
    img.save(png_buf, format="PNG", optimize=True)
    # Page size in points (A4)
    return _png_to_stamp_pdf(png_buf.getvalue(), 595.27, 841.89, dpi=dpi)


def pdf_has_acroform(pdf_bytes: bytes) -> bool:
    try:
        with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
            return bool(pdf.acroform.exists)
    except Exception:
        return False


def _annot_on_state(annot_obj: Any) -> str:
    """Return the non-Off appearance state name for a widget (e.g. Included), or ''."""
    try:
        ap = annot_obj.get("/AP")
        n = ap.get("/N") if ap is not None else None
        # Button on-states live in a /N *dictionary*. A stream /N is a single appearance
        # (typical for text widgets) — do not treat stream keys like /Length as states.
        if n is None or not isinstance(n, pikepdf.Dictionary):
            return ""
        for key in n.keys():
            label = str(key).lstrip("/")
            if label and label.lower() != "off":
                return label
    except Exception:
        return ""
    return ""


_MULTILINE_FF = 1 << 12  # PDF Ff bit 13
_COMB_FF = 1 << 24  # PDF Ff bit 25


def _field_ff(field: Any) -> int:
    try:
        raw = field.get("/Ff") if hasattr(field, "get") else None
        if raw is None and hasattr(field, "obj"):
            raw = field.obj.get("/Ff")
        return int(raw or 0)
    except Exception:
        return 0


def _pdf_escape_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _parse_da(da: str) -> tuple[str, float]:
    """Return (font_name, size) from a DA string like '/Arial 11 Tf 0 g'."""
    font = "Helv"
    size = 10.0
    try:
        m = re.search(r"/([A-Za-z][A-Za-z0-9._+-]*)\s+([0-9]+(?:\.[0-9]+)?)\s+Tf", da or "")
        if m:
            font = m.group(1)
            size = float(m.group(2))
    except Exception:
        pass
    return font, size


def _approx_text_width(text: str, font_size: float) -> float:
    # Helvetica/Arial-ish average glyph width; good enough for fit/shrink.
    return max(0.0, len(text) * font_size * 0.5)


def _wrap_text_lines(text: str, font_size: float, max_width: float) -> list[str]:
    """Word-wrap (and hard-break long tokens) to fit max_width."""
    paragraphs = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines: list[str] = []
    for para in paragraphs:
        words = para.split(" ") if para else [""]
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if _approx_text_width(candidate, font_size) <= max_width or not current:
                if _approx_text_width(word, font_size) > max_width and not current:
                    # Hard-break an oversized token.
                    chunk = ""
                    for ch in word:
                        trial = chunk + ch
                        if chunk and _approx_text_width(trial, font_size) > max_width:
                            lines.append(chunk)
                            chunk = ch
                        else:
                            chunk = trial
                    current = chunk
                else:
                    current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines or [""]


def _widget_rect_size(field_obj: Any) -> tuple[float, float]:
    """Return (width, height) in points for a field or its first kid widget."""
    rect = field_obj.get("/Rect")
    if rect is None or len(rect) < 4:
        kids = field_obj.get("/Kids")
        if kids is not None and len(kids) > 0:
            try:
                rect = kids[0].get("/Rect")
            except Exception:
                rect = None
    if rect is None or len(rect) < 4:
        return 0.0, 0.0
    try:
        x0, y0, x1, y1 = float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3])
        return abs(x1 - x0), abs(y1 - y0)
    except Exception:
        return 0.0, 0.0


def _set_da(field_obj: Any, font: str, size: float) -> None:
    da = f"/{font} {size:g} Tf 0 g"
    field_obj["/DA"] = da
    kids = field_obj.get("/Kids")
    if kids is not None:
        for kid in kids:
            try:
                kid["/DA"] = da
            except Exception:
                pass


def _write_text_appearance(
    pdf: pikepdf.Pdf,
    field_obj: Any,
    text: str,
    *,
    multiline: bool,
    comb: bool,
    max_len: int,
) -> None:
    """Replace /AP with a fitted text appearance (wrap / shrink / comb)."""
    width, height = _widget_rect_size(field_obj)
    if width <= 1 or height <= 1:
        return

    da_raw = str(field_obj.get("/DA") or "/Helv 10 Tf 0 g")
    font, base_size = _parse_da(da_raw)
    pad_x = 2.0
    pad_y = 1.5
    inner_w = max(1.0, width - pad_x * 2)
    inner_h = max(1.0, height - pad_y * 2)
    value = "" if text is None else str(text)

    if comb and max_len > 0:
        # Comb boxes: one glyph per slot; keep spaces so UK postcodes align.
        chars = list(value[:max_len])
        while len(chars) < max_len:
            chars.append("")
        size = min(base_size, max(6.0, inner_h * 0.72))
        slot_w = width / float(max_len)
        parts = [
            "/Tx BMC",
            "q",
            "BT",
            f"/{font} {size:g} Tf 0 g",
        ]
        baseline = max(pad_y, (height - size) * 0.5)
        # Position each character centred in its slot.
        for i, ch in enumerate(chars):
            if not ch:
                continue
            glyph_w = _approx_text_width(ch, size)
            x = i * slot_w + max(0.0, (slot_w - glyph_w) / 2.0)
            parts.append(f"1 0 0 1 {x:.3f} {baseline:.3f} Tm")
            parts.append(f"({_pdf_escape_text(ch)}) Tj")
        parts.extend(["ET", "Q", "EMC"])
        content = "\n".join(parts) + "\n"
        _set_da(field_obj, font, size)
    elif multiline or "\n" in value or "\r" in value or height >= 36:
        # Fit as many wrapped lines as the box allows; shrink font if needed.
        size = base_size
        leading = size * 1.2
        lines: list[str] = []
        for _ in range(12):
            lines = _wrap_text_lines(value, size, inner_w)
            leading = size * 1.15
            if len(lines) * leading <= inner_h + 0.5 or size <= 6.0:
                break
            size = max(6.0, size - 0.5)
        # Drop overflowing lines only as a last resort after min font.
        max_lines = max(1, int(inner_h / max(leading, 1.0)))
        lines = lines[:max_lines]
        parts = [
            "/Tx BMC",
            "q",
            "BT",
            f"/{font} {size:g} Tf 0 g",
        ]
        # Start near top of box (PDF y grows upward).
        y = height - pad_y - size
        for i, line in enumerate(lines):
            if i == 0:
                parts.append(f"1 0 0 1 {pad_x:.3f} {y:.3f} Tm")
            else:
                parts.append(f"0 {-leading:.3f} Td")
            parts.append(f"({_pdf_escape_text(line)}) Tj")
        parts.extend(["ET", "Q", "EMC"])
        content = "\n".join(parts) + "\n"
        _set_da(field_obj, font, size)
        # Ensure Multiline bit so viewers also wrap if they regenerate.
        try:
            field_obj["/Ff"] = int(field_obj.get("/Ff") or 0) | _MULTILINE_FF
        except Exception:
            pass
    else:
        # Single-line: shrink font until the value fits the width.
        size = base_size
        compact = value.replace("\r", " ").replace("\n", " ")
        while size > 5.5 and _approx_text_width(compact, size) > inner_w:
            size -= 0.5
        baseline = max(pad_y, (height - size) * 0.35)
        content = (
            "/Tx BMC\n"
            "q\n"
            "BT\n"
            f"/{font} {size:g} Tf 0 g\n"
            f"1 0 0 1 {pad_x:.3f} {baseline:.3f} Tm\n"
            f"({_pdf_escape_text(compact)}) Tj\n"
            "ET\n"
            "Q\n"
            "EMC\n"
        )
        _set_da(field_obj, font, size)

    stream = pikepdf.Stream(
        pdf,
        content.encode("latin-1", errors="replace"),
        {
            "/Type": pikepdf.Name.XObject,
            "/Subtype": pikepdf.Name.Form,
            "/FormType": 1,
            "/BBox": pikepdf.Array([0, 0, width, height]),
            "/Resources": pikepdf.Dictionary({"/Font": pikepdf.Dictionary()}),
        },
    )
    # Reuse document default font resources when present.
    try:
        dr = pdf.Root.AcroForm.get("/DR")
        if dr is not None and "/Font" in dr:
            stream["/Resources"] = pikepdf.Dictionary({"/Font": dr["/Font"]})
    except Exception:
        pass

    ap = pikepdf.Dictionary({"/N": stream})
    field_obj["/AP"] = ap
    kids = field_obj.get("/Kids")
    if kids is not None and len(kids) > 0:
        for kid in kids:
            try:
                kid["/AP"] = ap
            except Exception:
                pass
    else:
        # Terminal field is also the widget.
        pass


def _improve_text_field_appearances(
    pdf: pikepdf.Pdf,
    field_objs: dict[str, Any],
    responses: dict[str, Any],
) -> None:
    """Fix multiline wrap, comb postcodes, and long single-line clipping."""
    for name, raw in responses.items():
        key = str(name).strip()
        field_obj = field_objs.get(key)
        if field_obj is None:
            continue
        try:
            ft = str(field_obj.get("/FT") or "")
        except Exception:
            continue
        if not ft.endswith("Tx"):
            continue
        ff = _field_ff(field_obj)
        try:
            max_len = int(field_obj.get("/MaxLen") or 0)
        except Exception:
            max_len = 0
        width, height = _widget_rect_size(field_obj)
        multiline = bool(ff & _MULTILINE_FF) or height >= 36
        comb = bool(ff & _COMB_FF) and max_len > 0
        try:
            _write_text_appearance(
                pdf,
                field_obj,
                "" if raw is None else str(raw),
                multiline=multiline,
                comb=comb,
                max_len=max_len,
            )
        except Exception:
            log.warning("Could not improve text appearance for %s", key, exc_info=True)


def extract_acroform_fields(pdf_bytes: bytes) -> list[dict[str, Any]]:
    """
    Discover fillable AcroForm widgets for portal filling.

    Coordinates are top-left percentages (same as Canary Sign overlays).
    Skips pushbuttons and digital-signature fields (signing uses Canary Sign overlays).

    Checkbox *groups* with multiple kids (Included / Excluded / None) emit one portal
    widget per kid so each column is clickable; ``export_value`` carries the on-state.
    """
    out: list[dict[str, Any]] = []
    try:
        pdf = pikepdf.open(io.BytesIO(pdf_bytes))
    except Exception:
        log.exception("Failed to open PDF for AcroForm extraction")
        return out

    with pdf:
        if not pdf.acroform.exists:
            return out

        # Pass 1: collect every widget annotation with geometry + on-state.
        collected: list[dict[str, Any]] = []
        for page_idx, page in enumerate(pdf.pages):
            mediabox = page.mediabox
            left = float(mediabox[0])
            bottom = float(mediabox[1])
            page_w = float(mediabox[2]) - left
            page_h = float(mediabox[3]) - bottom
            if page_w <= 0 or page_h <= 0:
                continue
            try:
                widgets = list(pdf.acroform.get_widget_annotations_for_page(page))
            except Exception:
                widgets = []
            for annot in widgets:
                try:
                    field = pdf.acroform.get_field_for_annotation(annot)
                except Exception:
                    continue
                if field.is_null:
                    continue
                if field.is_pushbutton:
                    continue
                ft = str(field.field_type or "")
                if ft.endswith("Sig") or ft == "/Sig":
                    continue
                name = (field.fully_qualified_name or field.partial_name or "").strip()
                if not name:
                    continue
                try:
                    r = annot.rect
                    x0, y0, x1, y1 = float(r.llx), float(r.lly), float(r.urx), float(r.ury)
                except Exception:
                    try:
                        rect = annot.obj.get("/Rect")
                        if rect is None or len(rect) < 4:
                            continue
                        x0, y0, x1, y1 = float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3])
                    except Exception:
                        continue
                rx0, rx1 = min(x0, x1), max(x0, x1)
                ry0, ry1 = min(y0, y1), max(y0, y1)
                x_pct = max(0.0, min(100.0, ((rx0 - left) / page_w) * 100.0))
                y_top = page_h - (ry1 - bottom)
                y_pct = max(0.0, min(100.0, (y_top / page_h) * 100.0))
                w_pct = max(0.5, min(100.0 - x_pct, ((rx1 - rx0) / page_w) * 100.0))
                h_pct = max(0.5, min(100.0 - y_pct, ((ry1 - ry0) / page_h) * 100.0))

                is_button = bool(field.is_checkbox or field.is_radio_button)
                export_value = _annot_on_state(annot.obj) if is_button else ""
                if is_button:
                    kind = "checkbox"
                elif field.is_choice:
                    kind = "choice"
                else:
                    kind = "text"

                options: list[str] = []
                try:
                    choices = list(field.choices or [])
                    options = [str(c).lstrip("/") for c in choices if str(c).strip()]
                except Exception:
                    options = []

                label = (field.alternate_name or field.mapping_name or name or "").strip() or name
                current = ""
                try:
                    current = str(field.value_as_string or "")
                except Exception:
                    current = ""

                ff = 0
                try:
                    ff = _field_ff(annot.obj)
                    parent = annot.obj.get("/Parent")
                    if parent is not None:
                        ff = ff or _field_ff(parent)
                except Exception:
                    ff = 0
                multiline = bool(ff & _MULTILINE_FF) or bool(
                    getattr(field, "is_multiline", False)
                )
                # Tall text widgets behave as multi-line even when Ff is wrong.
                if kind == "text" and h_pct >= 4.5:
                    multiline = True

                collected.append(
                    {
                        "name": name,
                        "label": label,
                        "field_type": kind,
                        "required": False,
                        "page": page_idx + 1,
                        "x_pct": round(x_pct, 4),
                        "y_pct": round(y_pct, 4),
                        "w_pct": round(w_pct, 4),
                        "h_pct": round(h_pct, 4),
                        "options": options,
                        "current_value": current,
                        "multiline": multiline,
                        "export_value": export_value,
                    }
                )

        # Pass 2: expand multi-state button groups (Included/Excluded/None) into one widget per kid.
        by_name: dict[str, list[dict[str, Any]]] = {}
        for item in collected:
            by_name.setdefault(item["name"], []).append(item)

        for name, items in by_name.items():
            export_states = [i["export_value"] for i in items if i.get("export_value")]
            unique_states = list(dict.fromkeys(export_states))
            is_button_group = items[0]["field_type"] == "checkbox" and len(unique_states) >= 2

            if is_button_group:
                for item in items:
                    if not item.get("export_value"):
                        continue
                    out.append(
                        {
                            **item,
                            "field_type": "radio",
                            "label": item["export_value"],
                            "options": unique_states,
                            "current_value": (
                                item["export_value"]
                                if str(item.get("current_value") or "").lstrip("/") == item["export_value"]
                                else ""
                            ),
                        }
                    )
                continue

            # Single widget (text / plain checkbox / choice): keep first only.
            first = items[0]
            if first["field_type"] == "checkbox" and first.get("export_value"):
                first = {**first, "options": [first["export_value"]] if first["export_value"] else []}
            out.append(first)

    return out


def strip_acroform_fields(pdf_bytes: bytes) -> bytes:
    """
    Remove interactive AcroForm widgets from a PDF snapshot.

    Bakes existing appearances into page content where possible, then drops
    the form so recipients cannot fill fields (signature-only Canary Sign).
    """
    try:
        pdf = pikepdf.open(io.BytesIO(pdf_bytes))
    except Exception:
        log.exception("Failed to open PDF for AcroForm strip")
        return pdf_bytes

    with pdf:
        if not pdf.acroform.exists:
            out = io.BytesIO()
            pdf.save(out)
            return out.getvalue()

        try:
            pdf.generate_appearance_streams()
        except Exception:
            log.warning("Appearance generation failed while stripping AcroForm", exc_info=True)

        try:
            pdf.flatten_annotations("all")
        except TypeError:
            try:
                pdf.flatten_annotations()
            except Exception:
                log.warning("flatten_annotations failed while stripping AcroForm", exc_info=True)
        except Exception:
            log.warning("flatten_annotations failed while stripping AcroForm", exc_info=True)

        # Drop catalog AcroForm even if flatten left remnants
        try:
            if "/AcroForm" in pdf.Root:
                del pdf.Root["/AcroForm"]
        except Exception:
            log.warning("Could not delete /AcroForm", exc_info=True)

        # Remove any leftover Widget annotations from pages
        for page in pdf.pages:
            try:
                annots = page.get("/Annots")
            except Exception:
                annots = None
            if annots is None:
                continue
            try:
                kept = []
                for annot in list(annots):
                    try:
                        obj = annot.get_object() if hasattr(annot, "get_object") else annot
                        subtype = str(obj.get("/Subtype", "")) if hasattr(obj, "get") else ""
                        if subtype.endswith("Widget") or subtype == "/Widget":
                            continue
                        kept.append(annot)
                    except Exception:
                        kept.append(annot)
                if kept:
                    page["/Annots"] = pikepdf.Array(kept)
                elif "/Annots" in page:
                    del page["/Annots"]
            except Exception:
                log.warning("Could not strip widget annotations from a page", exc_info=True)

        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()


def _walk_acroform_fields(pdf: pikepdf.Pdf) -> list[Any]:
    """Return terminal/parent field dictionaries that carry a /T name."""
    root = pdf.Root.get("/AcroForm")
    if root is None:
        return []
    fields = root.get("/Fields")
    if fields is None:
        return []
    out: list[Any] = []

    def walk(arr: Any) -> None:
        for ref in arr:
            obj = ref
            try:
                if hasattr(ref, "get_object"):
                    obj = ref.get_object()
            except Exception:
                obj = ref
            if not hasattr(obj, "get"):
                continue
            name = obj.get("/T")
            kids = obj.get("/Kids")
            if name is not None:
                out.append(obj)
            if kids is not None:
                walk(kids)

    walk(fields)
    return out


def _kid_on_state(kid: Any) -> str:
    return _annot_on_state(kid)


def _resolve_button_target(raw: Any, on_states: list[str]) -> str | None:
    """Map a stored response to an on-state name, or None for Off."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        if not raw:
            return None
        for preferred in ("Included", "Yes", "On", "1", "True"):
            if preferred in on_states:
                return preferred
        return on_states[0] if on_states else None

    text = str(raw).strip()
    if not text or text.lower() in ("0", "false", "off", "no", ""):
        return None
    if text.lower() in ("1", "true", "yes", "on"):
        for preferred in ("Included", "Yes", "On", "1", "True"):
            if preferred in on_states:
                return preferred
        return on_states[0] if on_states else None

    cleaned = text.lstrip("/")
    for state in on_states:
        if state == cleaned or state.lower() == cleaned.lower():
            return state
    return cleaned if cleaned in on_states else None


def _set_button_field_value(field_obj: Any, raw: Any) -> bool:
    """Set /V and kid /AS for a checkbox or radio-style Btn field. Returns True if applied."""
    kids = field_obj.get("/Kids")
    widgets: list[Any] = []
    if kids is not None and len(kids) > 0:
        widgets = list(kids)
    else:
        widgets = [field_obj]

    on_states: list[str] = []
    for w in widgets:
        state = _kid_on_state(w)
        if state and state not in on_states:
            on_states.append(state)

    target = _resolve_button_target(raw, on_states)
    try:
        if target:
            field_obj["/V"] = pikepdf.Name(f"/{target}")
        else:
            field_obj["/V"] = pikepdf.Name("/Off")
        for w in widgets:
            on = _kid_on_state(w)
            if target and on == target:
                w["/AS"] = pikepdf.Name(f"/{target}")
            else:
                w["/AS"] = pikepdf.Name("/Off")
        return True
    except Exception:
        log.warning("Could not set button field value", exc_info=True)
        return False


def fill_acroform(
    pdf_bytes: bytes,
    responses: dict[str, Any] | None,
    *,
    flatten: bool = False,
) -> bytes:
    """Write AcroForm values and generate appearances.

    When ``flatten`` is True, widgets are burned into page content (Canary Sign).
    When False, fields stay editable (e.g. Law Society protocol forms after compose prefill).

    Button groups (Included / Excluded / None) are set via /V + kid /AS — pikepdf's
    ``CheckboxField.checked`` fails when the parent has no /AP (common on Law Society forms).
    """
    responses = responses or {}
    try:
        pdf = pikepdf.open(io.BytesIO(pdf_bytes))
    except Exception:
        log.exception("Failed to open PDF for AcroForm fill")
        return pdf_bytes

    with pdf:
        if not pdf.acroform.exists:
            out = io.BytesIO()
            pdf.save(out)
            return out.getvalue()

        from pikepdf.form import (
            CheckboxField,
            ChoiceField,
            DefaultAppearanceStreamGenerator,
            Form,
            TextField,
        )

        # Index field objects by /T for reliable button-group writes.
        field_objs: dict[str, Any] = {}
        for obj in _walk_acroform_fields(pdf):
            try:
                name = str(obj.get("/T") or "").strip()
            except Exception:
                continue
            if name and name not in field_objs:
                field_objs[name] = obj

        form = Form(pdf, DefaultAppearanceStreamGenerator)
        button_writes: list[tuple[Any, Any]] = []

        for name, raw in responses.items():
            key = str(name).strip()
            if not key:
                continue

            field_obj = field_objs.get(key)
            ft = ""
            if field_obj is not None:
                try:
                    ft = str(field_obj.get("/FT") or "")
                except Exception:
                    ft = ""

            # Prefer low-level button handling for /Btn (checkbox groups + plain ticks).
            if field_obj is not None and ft.endswith("Btn"):
                if _set_button_field_value(field_obj, raw):
                    button_writes.append((field_obj, raw))
                    continue

            try:
                field = form[key]
            except Exception:
                continue
            try:
                if isinstance(field, CheckboxField):
                    # Fallback for simple checkboxes when low-level path missed them.
                    try:
                        field.checked = bool(raw) and str(raw).lower() not in ("0", "false", "off", "no", "")
                    except Exception:
                        if field_obj is not None and _set_button_field_value(field_obj, raw):
                            button_writes.append((field_obj, raw))
                elif isinstance(field, ChoiceField):
                    field.value = "" if raw is None else str(raw)
                elif isinstance(field, TextField):
                    field.value = "" if raw is None else str(raw)
                else:
                    underlying = getattr(field, "_field", None) or getattr(field, "field", None)
                    if underlying is not None and hasattr(underlying, "set_value"):
                        underlying.set_value(pikepdf.String(str(raw)) if raw is not None else pikepdf.String(""))
            except Exception:
                log.warning("Could not set AcroForm field %s", key, exc_info=True)

        try:
            form.generate_appearances()
        except Exception:
            try:
                pdf.generate_appearance_streams()
            except Exception:
                log.warning("Appearance generation failed; continuing with NeedAppearances", exc_info=True)
                try:
                    pdf.Root.AcroForm["/NeedAppearances"] = True
                except Exception:
                    pass

        # Appearance generation can reset kid /AS on multi-state Btn groups — re-apply.
        for field_obj, raw in button_writes:
            _set_button_field_value(field_obj, raw)

        # pikepdf's default generator draws multiline/comb as a single Tj — replace those.
        try:
            _improve_text_field_appearances(pdf, field_objs, responses)
        except Exception:
            log.warning("Text appearance improvement failed", exc_info=True)

        if flatten:
            try:
                pdf.flatten_annotations("all")
            except Exception:
                log.exception("flatten_annotations failed")
        else:
            try:
                pdf.Root.AcroForm["/NeedAppearances"] = True
            except Exception:
                pass

        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()


def fill_and_flatten_acroform(pdf_bytes: bytes, responses: dict[str, Any] | None) -> bytes:
    """Write AcroForm values, generate appearances, and flatten widgets into page content."""
    return fill_acroform(pdf_bytes, responses, flatten=True)
