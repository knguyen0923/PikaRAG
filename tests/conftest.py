import pytest

import bot.team_store
import rag.observability


@pytest.fixture(autouse=True)
def _isolate_team_store(monkeypatch):
    """Reset bot.team_store's module-level _store dict to empty before each
    test, so per-user team state stored by one test (e.g. via store_team or
    merge_scout) can never leak into another test that happens to reuse the
    same user id. Without this, two unrelated test files picking the same
    user id can silently pollute each other (as happened between a TeamView
    test and test_bot_main.py's stored-team fixture)."""
    monkeypatch.setattr(bot.team_store, "_store", {})


@pytest.fixture(autouse=True)
def _isolate_observability_db(tmp_path, monkeypatch):
    """Redirect every test's use of rag.observability to a tmp_path-based
    DB file, so running the suite never writes into the repo's real
    data/observability.db (which /debug-last reads on a deployed bot).

    log_ask and get_last_ask_log both declare `db_path: str = DEFAULT_DB_PATH`
    as a default *parameter* value -- Python evaluates that default once, at
    def-time, and binds the resulting string onto the function object's
    __defaults__. Patching the module-level `rag.observability.DEFAULT_DB_PATH`
    name after the fact does NOT change that already-bound default (verified:
    log_ask.__defaults__ == ('data/observability.db',) even after patching
    the module attribute). So we patch __defaults__ directly on both
    functions. bot/main.py does `from rag.observability import log_ask,
    get_last_ask_log`, which binds the *same* function objects into its own
    namespace, so patching here also covers `bot.main.log_ask` and
    `bot.main.get_last_ask_log` without needing to patch bot.main separately.
    """
    test_db_path = str(tmp_path / "observability.db")
    monkeypatch.setattr(rag.observability, "DEFAULT_DB_PATH", test_db_path)
    monkeypatch.setattr(rag.observability.log_ask, "__defaults__", (test_db_path,))
    monkeypatch.setattr(rag.observability.get_last_ask_log, "__defaults__", (test_db_path,))
