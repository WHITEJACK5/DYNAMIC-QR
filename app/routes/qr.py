"""QR lifecycle: generate, preview, list, read, update, delete, bulk, duplicate, export, health."""

import base64, io, json, os, secrets
from io import BytesIO

import sqlalchemy.exc
from app.config import logger
from flask import Blueprint, g, jsonify, request, send_file
from pydantic import ValidationError
from PIL import Image
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app import cache as _qr_cache
from app.extensions import (
    get_base_url,
    get_session,
    optional_auth,
    rate_limit,
    token_required,
)
from app import jobs
from app.jobs import get_queue  # noqa: F401 — kept for callers that import from here
from app.repositories import qr_repo, users_repo
from app.schemas import (
    BulkFormRequest, GenerateFormRequest, GenerateRequest, PreviewRequest,
    QRUpdateRequest, first_error,
)
from app.services import storage as _storage
from app.services.render import create_qr_image, create_qr_svg, image_to_base64
from app.utils import build_qr_content, generate_short_code

qr = Blueprint("qr", __name__)


@qr.route("/api/generate", methods=["POST"])
@qr.route("/api/v1/generate", methods=["POST"])
@rate_limit(limit=20, window=60)
def generate():
    if request.content_type and "multipart/form-data" in request.content_type:
        # Phase 2b: the multipart branch is validated by an explicit schema
        # too. It used to read request.form raw, which meant it accepted
        # input the JSON path rejects — fg_color="not-a-colour" returned 200
        # here and 400 over JSON. One endpoint must not have two contracts,
        # least of all where the looser one is what a browser sends.
        try:
            freq = GenerateFormRequest.model_validate(
                {k: v for k, v in request.form.items()})
        except ValidationError as e:
            return jsonify({"error": first_error(e)}), 400
        qr_type = freq.type
        data_json = freq.data
        try:
            data = json.loads(data_json)
        except Exception:
            data = {"url": data_json}
        is_dynamic = freq.is_dynamic
        fg_color = freq.fg_color
        bg_color = freq.bg_color
        pattern = freq.pattern
        eye_style = freq.eye_style
        frame_text = freq.frame_text
        frame_color = freq.frame_color
        gradient = freq.gradient
        name = freq.name or "My QR"
        logo_file = request.files.get("logo")
    else:
        try:
            req = GenerateRequest.model_validate(request.get_json(silent=True) or {})
        except ValidationError as e:
            return jsonify({"error": first_error(e)}), 400
        qr_type, data, is_dynamic = req.type, req.data, req.is_dynamic
        fg_color, bg_color = req.fg_color, req.bg_color
        pattern, eye_style = req.pattern, req.eye_style
        frame_text, frame_color = req.frame_text, req.frame_color
        gradient, name = req.gradient, req.name
        logo_b64 = req.logo_base64
        logo_file = None
        if logo_b64:
            try:
                header, b64data = logo_b64.split(",",1) if "," in logo_b64 else ("", logo_b64)
                img_data = base64.b64decode(b64data)
                # Validate via PIL in memory (no temp file needed)
                try:
                    im = Image.open(io.BytesIO(img_data))
                    im.verify()
                    if im.format not in ("PNG","JPEG","JPG","WEBP","SVG"):
                        logger.warning("Logo format not allowed: %s", im.format)
                except Exception as e:
                    logger.warning("Logo validation failed: %s", e)
                    raise
                logo_ref_tmp = _storage.save_logo(img_data)
            except (_storage.StorageNotConfigured, _storage.StorageUnavailable) as e:
                # Object storage is unavailable: say so instead of 500 or,
                # worse, quietly writing the logo to ephemeral local disk.
                logger.error("Logo storage unavailable: %s", e)
                return jsonify({"error": str(e)}), 503
            except Exception as e:
                logger.warning("Logo b64 processing failed: %s", e)
                logo_ref_tmp = None
        else:
            logo_ref_tmp = None

    logo_path = None
    if 'logo_file' in locals() and logo_file:
        # MIME whitelist
        allowed_ext = {".png",".jpg",".jpeg",".webp",".svg"}
        ext = os.path.splitext(secure_filename(logo_file.filename or "logo.png"))[1].lower()
        if ext not in allowed_ext:
            return jsonify({"error": f"Logo type not allowed: {ext}"}), 400
        logo_bytes = logo_file.read()
        # Validate via PIL before persisting anywhere
        try:
            im = Image.open(io.BytesIO(logo_bytes))
            im.verify()
        except Exception as e:
            logger.warning("Logo file validation failed: %s", e)
            return jsonify({"error":"Invalid image file"}), 400
        try:
            logo_path = _storage.save_logo(logo_bytes, ext)
        except _storage.StorageNotConfigured as e:
            logger.error("Logo storage not configured: %s", e)
            return jsonify({"error": str(e)}), 503
        except _storage.StorageUnavailable:
            logger.error("Logo storage unavailable")
            return jsonify({"error": "logo storage is unavailable"}), 503
    elif 'logo_ref_tmp' in locals() and logo_ref_tmp:
        logo_path = logo_ref_tmp

    content = build_qr_content(qr_type, data)

    user_id = optional_auth()
    short_code = None
    final_content = content
    if is_dynamic:
        # Phase 4d: dynamic QRs are a paid-shaped feature that costs real
        # infrastructure, so they require a confirmed email address.
        # Static QRs stay available to everyone.
        if user_id is not None:
            s_chk = get_session()
            try:
                verified = users_repo.is_verified(s_chk, user_id)
            finally:
                s_chk.close()
            if not verified:
                return jsonify({
                    "error": "Verify your email address before creating dynamic QR codes",
                    "code": "email_unverified",
                    "resend": "/api/resend-verification",
                }), 403
        # Unique short code (unchecked fresh fallback on repeated collision)
        s_tmp = get_session()
        short_code = qr_repo.mint_unique_short(s_tmp, 10)
        s_tmp.close()
        final_content = f"{get_base_url(request)}/r/{short_code}"

    # Access-control options: validated by GenerateRequest on the JSON path
    # and by GenerateFormRequest on the multipart path. Both reject bad
    # values now; the old multipart branch swallowed a non-numeric
    # scan_limit and turned it into "no limit".
    if request.is_json:
        password = getattr(req, "password", None)
        scan_limit = getattr(req, "scan_limit", None)
        expiry_date = getattr(req, "expiry_date", None)
    else:
        password = freq.password
        scan_limit = freq.scan_limit
        expiry_date = freq.expiry_date

    pwd_hash = generate_password_hash(password) if password else None

    try:
        img = create_qr_image(
            content=final_content,
            fg_color=fg_color,
            bg_color=bg_color,
            pattern=pattern,
            eye_style=eye_style,
            gradient=gradient,
            logo_path=logo_path,
            frame_text=frame_text,
            frame_color=frame_color,
            size=900
        )
        b64 = image_to_base64(img, "PNG")
        qr_id = None
        if user_id:
            s = get_session()
            # Use transaction with try for UNIQUE violation
            try:
                qr_id = qr_repo.create_full(
                    s, user_id=user_id, name=name, type=qr_type, content=content,
                    data_json=json.dumps(data), is_dynamic=1 if is_dynamic else 0,
                    short_code=short_code, fg_color=fg_color, bg_color=bg_color,
                    gradient=gradient, pattern=pattern, eye_style=eye_style,
                    frame_text=frame_text, frame_color=frame_color, logo_path=logo_path,
                    has_password=1 if pwd_hash else 0, password_hash=pwd_hash,
                    expiry_date=expiry_date, scan_limit=scan_limit)
            except sqlalchemy.exc.IntegrityError as e:
                s.rollback()
                logger.warning("Short code collision, retry: %s", e)
                # Retry once with new code if dynamic
                if is_dynamic:
                    short_code = generate_short_code(8)
                    final_content = f"{get_base_url(request)}/r/{short_code}"
                    # Regenerate image with new URL
                    img = create_qr_image(final_content, fg_color, bg_color, pattern, eye_style, gradient, logo_path, frame_text, frame_color, size=900)
                    b64 = image_to_base64(img, "PNG")
                    qr_id = qr_repo.create_full(
                        s, user_id=user_id, name=name, type=qr_type, content=content,
                        data_json=json.dumps(data), is_dynamic=1,
                        short_code=short_code, fg_color=fg_color, bg_color=bg_color,
                        gradient=gradient, pattern=pattern, eye_style=eye_style,
                        frame_text=frame_text, frame_color=frame_color, logo_path=logo_path,
                        has_password=1 if pwd_hash else 0, password_hash=pwd_hash,
                        expiry_date=expiry_date, scan_limit=scan_limit)
                else:
                    raise
            finally:
                s.close()
        return jsonify({
            "success": True,
            "content": final_content,
            "original_content": content,
            "image_base64": f"data:image/png;base64,{b64}",
            "short_code": short_code,
            "qr_id": qr_id,
            "is_dynamic": is_dynamic,
            "type": qr_type
        })
    except Exception as e:
        logger.exception("Generate failed: %s", e)
        return jsonify({"error": "Generation failed"}), 500


@qr.route("/api/preview", methods=["POST"])
@qr.route("/api/v1/preview", methods=["POST"])
def preview():
    try:
        req = PreviewRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": first_error(e)}), 400
    content = req.content or build_qr_content(req.type, req.data)
    if not content:
        return jsonify({"error":"Content required"}), 400
    fg, bg, pat, eye = req.fg_color, req.bg_color, req.pattern, req.eye_style
    grad, frame, fcol = req.gradient, req.frame_text, req.frame_color
    logo_b64 = req.logo_base64
    # Phase 2h: identical preview inputs skip regeneration (X-Cache HIT).
    _pkey = _qr_cache.key_for("preview", {
        "content": content, "fg": fg, "bg": bg, "pat": pat, "eye": eye,
        "grad": grad, "frame": frame, "fcol": fcol, "logo": logo_b64,
    })
    _hit = _qr_cache.cache_get(_pkey)
    if _hit:
        _resp = jsonify({"image_base64": _hit})
        _resp.headers["X-Cache"] = "HIT"
        return _resp
    logo_path = None
    logo_bytes = None
    if logo_b64:
        try:
            h, d = logo_b64.split(",",1) if "," in logo_b64 else ("", logo_b64)
            img_data = base64.b64decode(d)
            if len(img_data) > 5*1024*1024:
                return jsonify({"error":"Logo too large"}), 400
            # Validate
            try:
                im = Image.open(io.BytesIO(img_data))
                im.verify()
            except Exception as e:
                logger.warning("Preview logo invalid: %s", e)
                return jsonify({"error":"Invalid logo image"}), 400
            # Preview logos are never persisted — bytes go straight to the renderer
            logo_bytes = img_data
        except Exception as e:
            logger.warning("Preview logo decode failed: %s", e)
            return jsonify({"error":"Invalid logo"}), 400
    try:
        img = create_qr_image(content, fg, bg, pat, eye, grad, logo_path, frame, fcol, size=800, logo_bytes=logo_bytes)
        b64 = image_to_base64(img)
        _data_url = f"data:image/png;base64,{b64}"
        _qr_cache.cache_set(_pkey, _data_url, 3600)
        _resp = jsonify({"image_base64": _data_url})
        _resp.headers["X-Cache"] = "MISS"
        return _resp
    except Exception as e:
        logger.exception("Preview failed: %s", e)
        return jsonify({"error":"Preview failed"}), 500


@qr.route("/api/qrcodes", methods=["GET"])
@qr.route("/api/v1/qrcodes", methods=["GET"])
@token_required
def list_qrcodes():
    """List own QRs. Pagination: ?limit=50&offset=0 -> {items,total,limit,offset}.

    Backwards-compat: no query params -> legacy bare JSON array (dashboard.html
    relies on it). Paginated envelope is the documented path going forward
    (limit/offset chosen over cursor: simple, sufficient for personal-scale
    SQLite; stable order by created_at DESC, id DESC).
    """
    raw_limit = request.args.get("limit")
    raw_offset = request.args.get("offset")
    paginated = raw_limit is not None or raw_offset is not None
    if paginated:
        try:
            limit = int(raw_limit) if raw_limit is not None else 50
            offset = int(raw_offset) if raw_offset is not None else 0
        except (TypeError, ValueError):
            return jsonify({"error": "limit/offset must be integers"}), 400
        if not 1 <= limit <= 200:
            return jsonify({"error": "limit must be 1..200"}), 400
        if offset < 0:
            return jsonify({"error": "offset must be >= 0"}), 400
    else:
        limit, offset = None, None
    s = get_session()
    if paginated:
        total = qr_repo.count_owned(s, g.user_id)
        rows = qr_repo.list_owned(s, g.user_id, limit, offset)
    else:
        rows = qr_repo.list_owned(s, g.user_id)
    s.close()
    out = [qr_repo.to_public(r) for r in rows]
    if paginated:
        return jsonify({"items": out, "total": total, "limit": limit, "offset": offset})
    return jsonify(out)


@qr.route("/api/qrcodes/<int:qr_id>", methods=["GET"])
@qr.route("/api/v1/qrcodes/<int:qr_id>", methods=["GET"])
@token_required
def get_qrcode(qr_id):
    s = get_session()
    row = qr_repo.get_owned(s, qr_id, g.user_id)
    s.close()
    if not row:
        return jsonify({"error":"Not found"}),404
    return jsonify(qr_repo.to_public(row))


@qr.route("/api/qrcodes/<int:qr_id>", methods=["PUT"])
@qr.route("/api/v1/qrcodes/<int:qr_id>", methods=["PUT"])
@token_required
def update_qrcode(qr_id):
    s = get_session()
    if not qr_repo.get_owned(s, qr_id, g.user_id):
        s.close()
        return jsonify({"error":"Not found"}),404
    body=request.get_json() or {}
    try:
        QRUpdateRequest.model_validate(body)
    except ValidationError as e:
        s.close()
        return jsonify({"error": first_error(e)}), 400
    try:
        updated = qr_repo.apply_update(s, qr_id, g.user_id, body)
    except Exception as e:
        logger.exception("Update failed for %s: %s", qr_id, e)
        s.close()
        return jsonify({"error":"Update failed"}), 500
    s.close()
    return jsonify(updated)


@qr.route("/api/qrcodes/<int:qr_id>", methods=["DELETE"])
@qr.route("/api/v1/qrcodes/<int:qr_id>", methods=["DELETE"])
@token_required
def delete_qrcode(qr_id):
    s = get_session()
    try:
        found = qr_repo.delete_owned(s, qr_id, g.user_id)
    except Exception as e:
        logger.exception("Delete failed: %s", e)
        s.close()
        return jsonify({"error":"Delete failed"}), 500
    s.close()
    if not found:
        return jsonify({"error":"Not found"}),404
    logger.info("QR %s deleted by user %s", qr_id, g.user_id)
    return jsonify({"success":True})


@qr.route("/api/qrcodes/bulk", methods=["POST"])
@qr.route("/api/v1/qrcodes/bulk", methods=["POST"])
@token_required
def bulk_generate():
    if "file" not in request.files:
        return jsonify({"error":"CSV file required"}),400
    file=request.files["file"]
    try:
        form = BulkFormRequest.model_validate(request.form.to_dict())
    except ValidationError as e:
        return jsonify({"error": first_error(e)}), 400
    typ, fg, bg = form.type, form.fg_color, form.bg_color
    try:
        data=file.read().decode('utf-8')
    except Exception as e:
        logger.exception("Bulk failed: %s", e)
        return jsonify({"error":"Bulk failed"}),500
    lines=[l.strip() for l in data.splitlines() if l.strip()]
    header=lines[0].lower() if lines else ""
    start=1 if "url" in header or "name" in header else 0
    rows=[]
    for line in lines[start:]:
        parts=[p.strip() for p in line.split(",")]
        url=parts[0] if parts else ""
        name=parts[1] if len(parts)>1 else f"Bulk {secrets.token_hex(2)}"
        if not url:
            continue
        rows.append((url, name))
        if len(rows) >= 3000:
            break
    # Phase 2o: RQ when configured (202 + status poll), else inline (200).
    # Local dev / CI without REDIS_URL always takes the inline path, so the
    # dashboard's sync {created,count} contract is unchanged there.

    queue = jobs.get_queue()
    if queue is not None:
        try:
            job = queue.enqueue(
                _bulk_job, g.user_id, rows, typ, fg, bg, get_base_url(request),
                meta={"user_id": g.user_id}, result_ttl=86400,
            )
            return jsonify({"job_id": job.id, "status_url": f"/api/v1/qrcodes/bulk/{job.id}"}), 202
        except Exception as e:
            logger.warning("Bulk enqueue failed, inline fallback: %s", e)
    try:
        s=get_session()
        try:
            created = _bulk_insert_rows(s, g.user_id, rows, typ, fg, bg, get_base_url(request))
        finally:
            s.close()
        logger.info("Bulk generated %s for user %s", len(created), g.user_id)
        return jsonify({"created":created, "count":len(created)})
    except Exception as e:
        logger.exception("Bulk failed: %s", e)
        return jsonify({"error":"Bulk failed"}),500



def _bulk_insert_rows(s, user_id, rows, typ, fg, bg, base_url):
    """Shared by the inline path and the RQ worker. Returns created list."""
    created=[]
    for url, name in rows[:3000]:
        content=build_qr_content(typ, {"url":url})
        short = qr_repo.mint_unique_short(s, 5)
        try:
            qr_repo.create_full(
                s, user_id=user_id, name=name, type=typ, content=content,
                data_json=json.dumps({"url":url}), is_dynamic=1, short_code=short,
                fg_color=fg, bg_color=bg, pattern="square", eye_style="square")
            created.append({"name":name,"url":url,"short_code":short,"qr_url":f"{base_url}/r/{short}"})
        except sqlalchemy.exc.IntegrityError as e:
            s.rollback()
            logger.warning("Bulk insert collision for %s: %s", url, e)
            continue
        except Exception as e:
            s.rollback()
            logger.warning("Bulk insert failed for %s: %s", url, e)
            continue
        if len(created) >= 3000:
            break
    return created



def _bulk_job(user_id, rows, typ, fg, bg, base_url):
    """RQ entrypoint (module-level so workers can import it)."""
    s = get_session()
    try:
        created = _bulk_insert_rows(s, user_id, rows, typ, fg, bg, base_url)
        logger.info("Bulk job generated %s for user %s", len(created), user_id)
        return {"created": created, "count": len(created)}
    finally:
        s.close()


@qr.route("/api/qrcodes/bulk/<job_id>", methods=["GET"])
@qr.route("/api/v1/qrcodes/bulk/<job_id>", methods=["GET"])
@token_required
def bulk_status(job_id):

    queue = jobs.get_queue()
    if queue is None:
        return jsonify({"error":"Job queue not configured"}), 404
    try:
        from rq.job import Job

        job = Job.fetch(job_id, connection=queue.connection)
    except Exception:
        return jsonify({"error":"Job not found"}), 404
    try:
        meta = job.meta or {}
    except Exception:
        meta = {}
    if meta.get("user_id") != g.user_id:
        return jsonify({"error":"Job not found"}), 404
    try:
        status = job.get_status()
    except Exception:
        status = "unknown"
    if status == "finished":
        try:
            result = job.result or {}
        except Exception:
            result = {}
        return jsonify({"status":"finished","count":result.get("count",0),"created":result.get("created",[])})
    if status == "failed":
        return jsonify({"status":"failed"}), 500
    return jsonify({"status":status})


@qr.route("/api/download/<int:qr_id>")
@qr.route("/api/v1/download/<int:qr_id>")
@token_required
def download_qr(qr_id):
    fmt=request.args.get("format","png").lower()
    s = get_session()
    _qr = qr_repo.get_owned(s, qr_id, g.user_id)
    row = qr_repo.to_public(_qr) if _qr is not None else None
    s.close()
    if not row:
        return jsonify({"error":"Not found"}),404
    if row["is_dynamic"]:
        content=f"{get_base_url(request)}/r/{row['short_code']}"
    else:
        content=row["content"]
    if fmt=="svg":
        # Real SVG
        try:
            svg_text = create_qr_svg(content, row["fg_color"], row["bg_color"])
            buf = BytesIO(svg_text.encode())
            return send_file(buf, mimetype="image/svg+xml", as_attachment=True, download_name=f"DRQR-{qr_id}.svg")
        except Exception as e:
            logger.exception("SVG download failed: %s", e)
            return jsonify({"error":"SVG generation failed"}), 500
    elif fmt=="pdf":
        # Use top-level imported reportlab
        try:
            img=create_qr_image(content, row["fg_color"], row["bg_color"], row["pattern"], row["eye_style"], row["gradient"], row["logo_path"], row["frame_text"], row["frame_color"], size=1200)
            pdf_buf=BytesIO()
            c=canvas.Canvas(pdf_buf, pagesize=A4)
            w,h=A4
            c.setFillColorRGB(0.04,0.04,0.04)
            c.setFont("Helvetica-Bold", 18)
            c.drawString(40, h-60, "DRQR \u2014 QR Code")
            c.setFont("Helvetica", 9)
            c.setFillColorRGB(0.5,0.5,0.5)
            c.drawString(40, h-75, f"Type: {row['type']} \u2022 {row['name']} \u2022 Generated {row['created_at'][:10]}")
            img_buf=BytesIO()
            img.save(img_buf, format="PNG")
            img_buf.seek(0)
            ir=ImageReader(img_buf)
            c.drawImage(ir, 120, h-500, width=350, height=350, preserveAspectRatio=True, mask='auto')
            c.setFillColorRGB(0,1,0.53)
            c.setFont("Helvetica-Bold", 10)
            c.drawCentredString(w/2, h-520, row["frame_text"] or "Scan Me \u2014 DRQR")
            c.showPage()
            c.save()
            pdf_buf.seek(0)
            return send_file(pdf_buf, mimetype="application/pdf", as_attachment=True, download_name=f"DRQR-{qr_id}.pdf")
        except Exception as e:
            logger.exception("PDF generation failed: %s", e)
            return jsonify({"error":"PDF failed"}), 500
    else:
        try:
            img=create_qr_image(content, row["fg_color"], row["bg_color"], row["pattern"], row["eye_style"], row["gradient"], row["logo_path"], row["frame_text"], row["frame_color"], size=1200)
            buf=BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            return send_file(buf, mimetype="image/png", as_attachment=True, download_name=f"DRQR-{qr_id}.png")
        except Exception as e:
            logger.exception("PNG download failed: %s", e)
            return jsonify({"error":"PNG failed"}), 500


@qr.route("/api/qrcodes/<int:qr_id>/duplicate", methods=["POST"])
@qr.route("/api/v1/qrcodes/<int:qr_id>/duplicate", methods=["POST"])
@token_required
def duplicate(qr_id):
    s = get_session()
    try:
        nid = qr_repo.duplicate_owned(s, qr_id, g.user_id)
    except Exception as e:
        logger.exception("Duplicate failed: %s", e)
        s.close()
        return jsonify({"error":"Duplicate failed"}), 500
    s.close()
    if nid is None:
        return jsonify({"error":"Not found"}),404
    return jsonify({"id":nid})

# Health


@qr.route("/api/health")
@qr.route("/api/v1/health")
def health():
    return jsonify({"status":"ok","service":"DRQR","version":"1.1.0","theme":"grid-white / black / amber"})

# Catch-all for frontend routes — safe
