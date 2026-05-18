import os


class Config:
    """Base configuration."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-change-me")
    CACHE_REDIS_URL = os.environ.get("CACHE_REDIS_URL", "redis://localhost:6379/1")
    # Cache configuration (prefers Redis, falls back to SimpleCache)
    CACHE_TYPE = "RedisCache"  # Default to Redis

    @staticmethod
    def get_cache_config():
        """Determine cache type based on Redis availability."""
        try:
            from redis import from_url

            from_url(Config.CACHE_REDIS_URL).ping()
            return "RedisCache"
        except Exception:
            return "SimpleCache"


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config_by_name = {
    "dev": DevelopmentConfig,
    "prod": ProductionConfig,
}
