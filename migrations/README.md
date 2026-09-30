# Alembic migrations

The application initializes a fresh SQLite database automatically. For schema evolution use:

`alembic revision --autogenerate -m "change"`

`alembic upgrade head`
