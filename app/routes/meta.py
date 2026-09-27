"""Organisational metadata: folders and templates (paginated)."""

from flask import Blueprint, g, jsonify, request
from pydantic import ValidationError

from app import pagination
from app.extensions import get_session, token_required
from app.repositories import folders_repo, templates_repo
from app.schemas import (
    FolderCreateRequest, TemplateCreateRequest, first_error,
)

meta = Blueprint("meta", __name__)


@meta.route("/api/folders", methods=["GET","POST"])
@meta.route("/api/v1/folders", methods=["GET","POST"])
@token_required
def folders():
    s=get_session()
    if request.method=="POST":
        try:
            req = FolderCreateRequest.model_validate(request.get_json(silent=True) or {})
        except ValidationError as e:
            s.close()
            return jsonify({"error": first_error(e)}), 400
        name = req.name
        out = folders_repo.create_for_user(s, g.user_id, name)
        s.close()
        return jsonify(out)
    else:
        paginated, limit, offset, err = pagination.parse_pagination(request.args)
        if err:
            s.close()
            return jsonify({"error": err}), 400
        if paginated:
            total = folders_repo.count_for_user(s, g.user_id)
            rows = folders_repo.list_for_user(s, g.user_id, limit, offset)
            s.close()
            return jsonify({"items": rows, "total": total, "limit": limit, "offset": offset})
        rows = folders_repo.list_for_user(s, g.user_id)
        s.close()
        return jsonify(rows)


@meta.route("/api/templates", methods=["GET","POST"])
@meta.route("/api/v1/templates", methods=["GET","POST"])
@token_required
def templates():
    s=get_session()
    if request.method=="POST":
        try:
            req = TemplateCreateRequest.model_validate(request.get_json(silent=True) or {})
        except ValidationError as e:
            s.close()
            return jsonify({"error": first_error(e)}), 400
        name = req.name
        config = req.config if req.config is not None else {}
        out = templates_repo.create_for_user(s, g.user_id, name, config)
        s.close()
        return jsonify(out)
    else:
        paginated, limit, offset, err = pagination.parse_pagination(request.args)
        if err:
            s.close()
            return jsonify({"error": err}), 400
        if paginated:
            total = templates_repo.count_for_user(s, g.user_id)
            rows = templates_repo.list_for_user(s, g.user_id, limit, offset)
            s.close()
            return jsonify({"items": rows, "total": total, "limit": limit, "offset": offset})
        rows = templates_repo.list_for_user(s, g.user_id)
        s.close()
        return jsonify(rows)
