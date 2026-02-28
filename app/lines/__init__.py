from flask import Blueprint

bp = Blueprint("lines", __name__, url_prefix="/lines")

from . import routes  # noqa: E402, F401
