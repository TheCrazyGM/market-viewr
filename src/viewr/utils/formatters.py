from datetime import datetime
from decimal import Decimal, InvalidOperation


def register_filters(app):
    """Register custom Jinja2 filters."""

    @app.template_filter("timestamp_to_date")
    def timestamp_to_date(timestamp):
        """Convert a Unix timestamp to a local time string."""
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

    @app.template_filter("fmt")
    def fmt_number(value, spec=",.4f"):
        """Format a value as a number safely."""
        try:
            fval = Decimal(str(value))
            return format(fval, spec)
        except (InvalidOperation, ValueError, TypeError):
            return value
