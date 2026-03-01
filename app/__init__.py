from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate

from .config import Config
from .models import db, Account, Partner

login_manager = LoginManager()
login_manager.login_view = "auth.login"
migrate = Migrate()


@login_manager.user_loader
def load_user(user_id):
    if ":" in str(user_id):
        prefix, uid = user_id.split(":", 1)
        uid = int(uid)
        if prefix == "account":
            return db.session.get(Account, uid)
        elif prefix == "partner":
            return db.session.get(Partner, uid)
    # Fallback for legacy sessions without prefix
    return db.session.get(Account, int(user_id))


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    from .auth import bp as auth_bp
    from .dashboard import bp as dashboard_bp
    from .lines import bp as lines_bp
    from .webhooks import bp as webhooks_bp
    from .upload import bp as upload_bp
    from .partners import bp as partners_bp
    from .settings import bp as settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(lines_bp)
    app.register_blueprint(webhooks_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(partners_bp)
    app.register_blueprint(settings_bp)

    return app
