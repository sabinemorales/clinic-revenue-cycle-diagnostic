import pytest

from up4u_audit.generator import generate


@pytest.fixture(scope="session")
def book():
    return generate(7)
