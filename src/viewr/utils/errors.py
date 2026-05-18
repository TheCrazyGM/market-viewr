import logging

from flask import render_template
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


def register_error_handlers(app):
    """Register custom error handlers."""

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template("error_404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("error_500.html"), 500

    @app.errorhandler(Exception)
    def handle_exception(e):
        if isinstance(e, HTTPException):
            return e

        logger.error(f"Unhandled exception: {str(e)}")
        return (
            render_template(
                "error_generic.html",
                code="500 - Server Error",
                message="An unexpected error occurred. Please try again later.",
            ),
            500,
        )
