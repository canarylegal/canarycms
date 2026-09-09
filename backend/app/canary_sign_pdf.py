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
    x = max(pad_x, (iw - tw) // 2 - bbox[0])
    y = max(pad_y, (ih - th) // 2 - bbox[1])
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


def _png_to_stamp_pdf(png_bytes: bytes, width_pt: float, height_pt: float, *, dpi: int = 144) -> bytes:
    """Build a one-page PDF containing the PNG sized in points at the given DPI."""
    pil = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    tw = max(8, int(width_pt * dpi / 72))
    th = max(8, int(height_pt * dpi / 72))
    if pil.size != (tw, th):
        pil = pil.resize((tw, th), Image.Resampling.LANCZOS)
    bg = Image.new("RGB", (tw, th), (255, 255, 255))
    bg.paste(pil, (0, 0), pil)

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
                stamp_pdf_bytes = _png_to_stamp_pdf(png, w, h, dpi=216)
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


def extract_acroform_fields(pdf_bytes: bytes) -> list[dict[str, Any]]:
    """
    Discover fillable AcroForm widgets for portal filling.

    Coordinates are top-left percentages (same as Canary Sign overlays).
    Skips pushbuttons and digital-signature fields (signing uses Canary Sign overlays).
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
        seen: set[str] = set()
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
                if not name or name in seen:
                    continue
                seen.add(name)
                # pikepdf Annotation exposes .rect (Rectangle), not dict .get("/Rect")
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
                # Normalize inverted rects
                rx0, rx1 = min(x0, x1), max(x0, x1)
                ry0, ry1 = min(y0, y1), max(y0, y1)
                x_pct = max(0.0, min(100.0, ((rx0 - left) / page_w) * 100.0))
                y_top = page_h - (ry1 - bottom)
                y_pct = max(0.0, min(100.0, (y_top / page_h) * 100.0))
                w_pct = max(0.5, min(100.0 - x_pct, ((rx1 - rx0) / page_w) * 100.0))
                h_pct = max(0.5, min(100.0 - y_pct, ((ry1 - ry0) / page_h) * 100.0))

                if field.is_checkbox:
                    kind = "checkbox"
                elif field.is_radio_button:
                    kind = "radio"
                elif field.is_choice:
                    kind = "choice"
                else:
                    kind = "text"

                options: list[str] = []
                try:
                    choices = list(field.choices or [])
                    options = [str(c) for c in choices if str(c).strip()]
                except Exception:
                    options = []

                label = (field.alternate_name or field.mapping_name or name or "").strip() or name
                current = ""
                try:
                    current = str(field.value_as_string or "")
                except Exception:
                    current = ""

                out.append(
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
                        "multiline": bool(getattr(field, "is_multiline", False))
                        if hasattr(field, "is_multiline")
                        else False,
                    }
                )
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


def fill_and_flatten_acroform(pdf_bytes: bytes, responses: dict[str, Any] | None) -> bytes:
    """Write AcroForm values, generate appearances, and flatten widgets into page content."""
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

        form = Form(pdf, DefaultAppearanceStreamGenerator)
        for name, raw in responses.items():
            key = str(name).strip()
            if not key:
                continue
            try:
                field = form[key]
            except Exception:
                continue
            try:
                if isinstance(field, CheckboxField):
                    field.checked = bool(raw) and str(raw).lower() not in ("0", "false", "off", "no", "")
                elif isinstance(field, ChoiceField):
                    field.value = "" if raw is None else str(raw)
                elif isinstance(field, TextField):
                    field.value = "" if raw is None else str(raw)
                else:
                    # Radio / other — best effort via underlying set_value
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

        try:
            pdf.flatten_annotations("all")
        except Exception:
            log.exception("flatten_annotations failed")

        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()
