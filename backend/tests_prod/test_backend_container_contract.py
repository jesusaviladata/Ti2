from pathlib import Path


DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


def test_backend_container_applies_migrations_before_starting_api():
    text = DOCKERFILE.read_text(encoding="utf-8")

    assert "alembic upgrade head" in text
    assert "exec uvicorn app.main:app" in text
