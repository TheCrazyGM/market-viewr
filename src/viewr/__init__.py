import logging

from flask import Flask

from .config import config_by_name
from .extensions import cache
from .utils.errors import register_error_handlers
from .utils.formatters import register_filters


def create_app(config_name="dev"):
    """Application factory."""
    app = Flask(
        __name__, static_folder="../../static", template_folder="../../templates"
    )

    app.config.from_object(config_by_name[config_name])

    # Initialize cache with dynamic config
    app.config["CACHE_TYPE"] = config_by_name[config_name].get_cache_config()

    cache.init_app(app)

    # Setup Logger
    logging.basicConfig(level=logging.INFO)
    app.logger.setLevel(logging.INFO)

    # Register utilities
    register_filters(app)
    register_error_handlers(app)

    # Register blueprints
    from .routes.api import api_bp
    from .routes.main import main_bp
    from .routes.pools import pools_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(pools_bp)

    return app
