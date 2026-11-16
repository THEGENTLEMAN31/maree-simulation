import pytest

from maree.v3.agents.catalog import _PROVIDERS


@pytest.fixture(autouse=True)
def _reset_providers():
    # sauvegarder l'état avant chaque test et restaurer après
    old = _PROVIDERS.copy()
    yield
    _PROVIDERS.clear()
    _PROVIDERS.update(old)