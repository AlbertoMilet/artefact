from pathlib import Path

import pytest

from emporio.data import carregar

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def catalogo():
    return carregar(RAIZ / "data")
