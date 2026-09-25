# NOTICE: Modified by LayerToll contributors for OKX Dev Day 2026 (optional DATABASE_URL for lite mode).
# Original work: XPack MCP Marketplace, Apache-2.0, https://github.com/xpack-ai/XPack-MCP-Marketplace
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .config import Config
from .models.base import Base
import logging

logger = logging.getLogger(__name__)

# Build database engine configuration
engine_config = {
    "url": f"mysql+pymysql://{Config.MYSQL_USER}:{Config.MYSQL_PASSWORD}@{Config.MYSQL_HOST}:{Config.MYSQL_PORT}/{Config.MYSQL_DB}",
    "echo": Config.DEBUG,
    "pool_size": Config.DB_POOL_SIZE,
    "max_overflow": Config.DB_MAX_OVERFLOW,
    "pool_timeout": Config.DB_POOL_TIMEOUT,
    "pool_recycle": Config.DB_POOL_RECYCLE,
    "pool_pre_ping": Config.DB_POOL_PRE_PING,
    # MySQL specific settings
    "connect_args": {
        "connect_timeout": 10,
        "read_timeout": 30,
        "write_timeout": 30,
        "autocommit": False,
        "charset": "utf8mb4",
        "use_unicode": True,
    },
}

logger.info(f"Database pool config: pool_size={Config.DB_POOL_SIZE}, max_overflow={Config.DB_MAX_OVERFLOW}")

if Config.DATABASE_URL:
    # LayerToll lite mode: e.g. sqlite:////tmp/layertoll.db (MySQL settings above unused)
    from sqlalchemy import event

    _is_sqlite = Config.DATABASE_URL.startswith("sqlite")
    engine = create_engine(
        Config.DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False, "timeout": 30} if _is_sqlite else {},
    )
    if _is_sqlite:

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()
else:
    engine = create_engine(**engine_config)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_pool_status():
    """Get database connection pool status information"""
    try:
        pool = engine.pool
        # SQLAlchemy connection pool status
        status = {
            "pool_size": getattr(pool, "size", lambda: Config.DB_POOL_SIZE)(),
            "checked_in_connections": getattr(pool, "checkedin", lambda: 0)(),
            "checked_out_connections": getattr(pool, "checkedout", lambda: 0)(),
            "overflow_connections": getattr(pool, "overflow", lambda: 0)(),
            "invalid_connections": getattr(pool, "invalidated", lambda: 0)(),
            "pool_config": {
                "pool_size": Config.DB_POOL_SIZE,
                "max_overflow": Config.DB_MAX_OVERFLOW,
                "pool_timeout": Config.DB_POOL_TIMEOUT,
                "pool_recycle": Config.DB_POOL_RECYCLE,
                "pool_pre_ping": Config.DB_POOL_PRE_PING,
            },
        }

        # Calculate derived metrics
        checked_in = status["checked_in_connections"]
        checked_out = status["checked_out_connections"]
        status.update(
            {
                "total_connections": checked_in + checked_out,
                "available_connections": max(0, status["pool_size"] - checked_out),
                "utilization_rate": round(checked_out / max(1, status["pool_size"]) * 100, 2),
            }
        )

        return status
    except Exception as e:
        logger.error(f"Failed to get database pool status: {e}")
        return {
            "error": str(e),
            "pool_config": {
                "pool_size": Config.DB_POOL_SIZE,
                "max_overflow": Config.DB_MAX_OVERFLOW,
                "pool_timeout": Config.DB_POOL_TIMEOUT,
                "pool_recycle": Config.DB_POOL_RECYCLE,
                "pool_pre_ping": Config.DB_POOL_PRE_PING,
            },
        }


def init_db():
    """Initialize database and create all tables"""
    try:
        # Import all models to ensure they are registered
        from .models import user, user_wallet, user_wallet_history, user_access_token, sys_config, mcp_service, mcp_tool_api, user_apikey, resource_group

        # Create all tables
        Base.metadata.create_all(bind=engine)
        print("Database tables created successfully")
    except Exception as e:
        print(f"Database initialization failed: {e}")
        raise
