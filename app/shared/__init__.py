from flask import Blueprint

bp = Blueprint("shared", __name__)

from . import routes  # noqa: E402, F401
