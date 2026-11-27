from pathlib import Path

import pytest

from portfolio_lab.contracts import ContractError
from portfolio_lab.dashboard_services import endpoint, launch


@pytest.mark.parametrize("url", ["https://example.com:8501", "http://evil:8502", "http://localhost:80", "http://u:p@localhost:8501", "file:///tmp/a"])
def test_no_remote_or_privileged_dashboard_launch(url):
    with pytest.raises(ContractError):
        endpoint(url)


def test_ipv6_local_endpoint():
    assert endpoint("http://[::1]:8516") == ("::1", 8516)


def test_no_arbitrary_executable(tmp_path):
    with pytest.raises(ContractError, match="allowlisted"):
        launch(Path(tmp_path), "arbitrary", "http://localhost:8516")
