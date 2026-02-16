from notebooklm_conector.math import add


def test_add() -> None:
    assert add(1, 2) == 3
    assert add(-1, 1) == 0
