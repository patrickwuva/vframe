from flask import Blueprint, render_template, url_for


bp = Blueprint("player", __name__)


@bp.get("/player")
def player_view():
    return render_template(
        "player/player.html",
        status_url=url_for("api.status"),
    )
