from flask import render_template
from . import bp


@bp.route("/welcome")
def landing():
    return render_template("landing/index.html")
