from flask import Blueprint

bp = Blueprint("partners", __name__, url_prefix="/partners")

from . import routes  # noqa: E402, F401
