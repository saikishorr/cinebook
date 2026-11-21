from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.db import create_pool
from app.logging_config import configure_logging, RequestIdMiddleware
from app.routers import movies, shows, holds, bookings, chat_links, demo_phone, help, chat
from app.routers import cinemas, admin, admin_console, auth
from app.admin_auth import AdminNoCacheMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    # Create one shared connection pool for the server's lifetime.
    pool = create_pool(settings.database_url)
    pool.open()
    app.state.pool = pool
    try:
        from app.queue import sweep_local
        sweep_local()
        yield
    finally:
        pool.close()

api_prefix = settings.api_prefix
app = FastAPI(
    title="Movie Ticket Booking API",
    lifespan=lifespan,
    docs_url=f"{api_prefix}/docs",
    openapi_url=f"{api_prefix}/openapi.json",
)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list,
                   allow_credentials=False, allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["X-Request-ID"])
app.add_middleware(RequestIdMiddleware)
app.add_middleware(AdminNoCacheMiddleware, prefix=api_prefix)
app.include_router(movies.router, prefix=api_prefix)
app.include_router(cinemas.router, prefix=api_prefix)
app.include_router(admin.router, prefix=api_prefix)
app.include_router(admin_console.router, prefix=api_prefix)
app.include_router(auth.router, prefix=api_prefix)
app.include_router(shows.router, prefix=api_prefix)
app.include_router(holds.router, prefix=api_prefix)
app.include_router(bookings.router, prefix=api_prefix)
app.include_router(chat_links.router, prefix=api_prefix)   # Phase 2
app.include_router(demo_phone.router, prefix=api_prefix)   # Phase 2
app.include_router(help.router, prefix=api_prefix)         # Phase 3
app.include_router(chat.router, prefix=api_prefix)         # Phase 3

@app.get("/health")
def health(request: Request):
    # Checks the API and the database together.
    try:
        with request.app.state.pool.connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        return {"status": "ok", "database": "ok"}
    except Exception as error:
        raise HTTPException(status_code=503, detail="Database is unavailable") from error

if api_prefix:
    app.add_api_route(f"{api_prefix}/health", health, methods=["GET"], include_in_schema=False)
