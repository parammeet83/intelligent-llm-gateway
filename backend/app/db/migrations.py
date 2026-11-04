from __future__ import annotations

from functools import lru_cache

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.config import BACKEND_ROOT


def alembic_config() -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return cfg


@lru_cache
def expected_head() -> str | None:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()
