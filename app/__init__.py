import json
import os
from collections import Counter
from datetime import datetime, timezone

from authlib.integrations.flask_client import OAuth
from flask import Flask, redirect, render_template, request, Response, abort, url_for
from flask_login import LoginManager, login_required, current_user
from flask_migrate import Migrate

from flask_wtf.csrf import CSRFProtect

from .config import Config
from .models import db, Account, Call
from .extensions import limiter

login_manager = LoginManager()
login_manager.login_view = "auth.login"
migrate = Migrate()
oauth = OAuth()
csrf = CSRFProtect()


@login_manager.user_loader
def load_user(user_id):
    if ":" in str(user_id):
        prefix, uid = user_id.split(":", 1)
        uid = int(uid)
        if prefix == "account":
            return db.session.get(Account, uid)
    # Fallback for legacy sessions without prefix
    return db.session.get(Account, int(user_id))


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)
    oauth.init_app(app)
    csrf.init_app(app)

    if app.config.get('GOOGLE_CLIENT_ID'):
        oauth.register(
            name='google',
            client_id=app.config['GOOGLE_CLIENT_ID'],
            client_secret=app.config['GOOGLE_CLIENT_SECRET'],
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid email profile'},
        )

    import pytz

    @app.template_filter('localtime')
    def localtime_filter(value, fmt='%A, %-d %B %Y at %-I:%M %p', tz=None):
        if value is None:
            return '\u2014'
        try:
            if tz:
                local_tz = tz if hasattr(tz, 'localize') else pytz.timezone(tz)
            else:
                from flask_login import current_user
                tz_name = getattr(current_user, 'timezone', None) or 'Australia/Adelaide'
                if current_user.user_type == 'partner':
                    account = db.session.get(Account, current_user.account_id)
                    tz_name = account.timezone if account else tz_name
                local_tz = pytz.timezone(tz_name)
        except Exception:
            local_tz = pytz.timezone('Australia/Adelaide')
        if value.tzinfo is None:
            value = pytz.utc.localize(value)
        return value.astimezone(local_tz).strftime(fmt)

    from .auth import bp as auth_bp
    from .dashboard import bp as dashboard_bp
    from .lines import bp as lines_bp
    from .webhooks import bp as webhooks_bp
    from .upload import bp as upload_bp
    from .partners import bp as partners_bp
    from .settings import bp as settings_bp
    from .landing import bp as landing_bp
    from .billing import bp as billing_bp
    from .onboarding import bp as onboarding_bp
    from .blog import bp as blog_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(lines_bp)
    app.register_blueprint(webhooks_bp)
    csrf.exempt(webhooks_bp)  # Webhooks receive external POSTs without CSRF tokens
    app.register_blueprint(upload_bp)
    app.register_blueprint(partners_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(landing_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(onboarding_bp)
    app.register_blueprint(blog_bp)

    from .shared import bp as shared_bp
    app.register_blueprint(shared_bp)

    # Global UTM capture — runs on every request so UTMs are captured
    # regardless of which page the visitor lands on
    from .utm_utils import capture_utm

    @app.before_request
    def redirect_www():
        """Redirect www.calloutcome.com to calloutcome.com (SEO: single canonical domain)."""
        if request.host.startswith('www.'):
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(request.url)
            new_host = parsed.netloc.replace('www.', '', 1)
            new_url = urlunparse(parsed._replace(netloc=new_host))
            return redirect(new_url, code=301)

    @app.before_request
    def global_utm_capture():
        capture_utm()

    @app.route('/')
    def index():
        """Serve landing page at root URL (SEO: canonical URL must return content, not redirect)."""
        if current_user.is_authenticated:
            return redirect(url_for('dashboard.index'))
        from sqlalchemy import func as sqlfunc
        total_calls = db.session.query(sqlfunc.count(Call.id)).filter(
            Call.classification.isnot(None)
        ).scalar() or 0
        jobs_booked = db.session.query(sqlfunc.count(Call.id)).filter(
            Call.classification == "JOB_BOOKED"
        ).scalar() or 0
        total_calls_display = max((total_calls // 10) * 10, 500)
        jobs_booked_display = max((jobs_booked // 10) * 10, 100)
        return render_template(
            'landing/index.html',
            total_calls=total_calls_display,
            jobs_booked=jobs_booked_display,
        )

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500

    @app.route('/privacy')
    def privacy():
        return render_template('legal/privacy.html')

    @app.route('/terms')
    def terms():
        return render_template('legal/terms.html')

    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        if request.is_secure or os.environ.get('RAILWAY_ENVIRONMENT'):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    @app.route('/health')
    def health_check():
        try:
            from sqlalchemy import text
            db.session.execute(text('SELECT 1'))
            return {'status': 'healthy'}, 200
        except Exception as e:
            app.logger.error("Health check failed: %s", e)
            return {'status': 'unhealthy'}, 500

    @app.route('/robots.txt')
    def robots_txt():
        body = (
            "User-agent: *\n"
            "Disallow: /dashboard\n"
            "Disallow: /auth/\n"
            "Disallow: /onboarding\n"
            "Disallow: /settings\n"
            "Disallow: /lines\n"
            "Disallow: /partners\n"
            "Disallow: /upload\n"
            "Disallow: /webhooks\n"
            "Disallow: /billing\n"
            "Disallow: /shared/\n"
            "\n"
            "Sitemap: https://calloutcome.com/sitemap.xml\n"
        )
        return Response(body, mimetype='text/plain')

    @app.route('/sitemap.xml')
    def sitemap_xml():
        urls = []
        urls.append({
            'loc': 'https://calloutcome.com/',
            'changefreq': 'weekly',
            'priority': '1.0',
        })
        urls.append({
            'loc': 'https://calloutcome.com/blog/',
            'changefreq': 'weekly',
            'priority': '0.8',
        })

        posts_dir = os.path.join(app.root_path, 'blog', 'posts')
        if os.path.isdir(posts_dir):
            for filename in sorted(os.listdir(posts_dir)):
                if filename.endswith('.md'):
                    slug = filename[:-3]
                    filepath = os.path.join(posts_dir, filename)
                    mtime = os.path.getmtime(filepath)
                    lastmod = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime('%Y-%m-%d')
                    urls.append({
                        'loc': f'https://calloutcome.com/blog/{slug}',
                        'lastmod': lastmod,
                        'changefreq': 'monthly',
                        'priority': '0.7',
                    })

        xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml_parts.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
        for url in urls:
            xml_parts.append('  <url>')
            xml_parts.append(f'    <loc>{url["loc"]}</loc>')
            if 'lastmod' in url:
                xml_parts.append(f'    <lastmod>{url["lastmod"]}</lastmod>')
            xml_parts.append(f'    <changefreq>{url["changefreq"]}</changefreq>')
            xml_parts.append(f'    <priority>{url["priority"]}</priority>')
            xml_parts.append('  </url>')
        xml_parts.append('</urlset>')

        return Response('\n'.join(xml_parts), mimetype='application/xml')

    @app.route('/admin/signups')
    @login_required
    def admin_signups():
        if not current_user.is_admin:
            abort(403)

        accounts = Account.query.order_by(Account.created_at.desc()).all()

        # Parse signup_source JSON and build summary
        signups = []
        source_counts = Counter()
        campaign_counts = Counter()
        for acct in accounts:
            source_data = {}
            if acct.signup_source:
                try:
                    source_data = json.loads(acct.signup_source)
                except (json.JSONDecodeError, TypeError):
                    source_data = {'raw': acct.signup_source}

            utm_source = source_data.get('utm_source', 'direct')
            utm_campaign = source_data.get('utm_campaign', '')
            utm_content = source_data.get('utm_content', '')
            source_counts[utm_source] += 1
            if utm_campaign:
                campaign_counts[f"{utm_source} / {utm_campaign}"] += 1

            signups.append({
                'id': acct.id,
                'name': acct.name,
                'email': acct.email,
                'plan': acct.stripe_plan or 'free',
                'created_at': acct.created_at,
                'utm_source': utm_source,
                'utm_medium': source_data.get('utm_medium', ''),
                'utm_campaign': utm_campaign,
                'utm_content': utm_content,
            })

        return render_template(
            'admin/signups.html',
            signups=signups,
            source_counts=source_counts.most_common(),
            campaign_counts=campaign_counts.most_common(),
            total=len(signups),
            active_page='admin',
        )

    return app
