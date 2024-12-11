import os
import subprocess
import pytest

def run_mist_exporter(api_token, org_id):
    return run_mist_exporter_all(api_token, org_id, baseurl="")

def run_mist_exporter_all(api_token, org_id, baseurl):
    """Runs mist_exporter.py and returns its output."""
    try:
        myargs = [
                "python",
                "mist_exporter.py",
                "--api_token",
                api_token,
                "--org_id",
                org_id,
                "--ignore_ssl",
                "--log_fullpath",
                "./logs/mist_exporter.log",
            ]
        if baseurl:
            myargs.append("--baseurl")
            myargs.append(baseurl)
        process = subprocess.run(
            myargs,
            capture_output=True,
            text=True,
            check=True,
        )
        return process.stdout
    except subprocess.CalledProcessError as e:
        pytest.fail(
            f"mist_exporter.py failed with return code {e.returncode}:\n{e.stderr}"
        )
    except FileNotFoundError:
        pytest.fail("mist_exporter.py not found.")


def test_wrong_url_should_error(api_token, org_id):
    output = run_mist_exporter_all(api_token, org_id, "https://api.eu.mist.com/api/wrongendpoint")
    assert "mist_exporter_status 0" in output

def test_successful_exporter_status(mist_api_output):
    assert "mist_exporter_status 1" in mist_api_output

def test_no_empty_hostnames(mist_api_output):
    assert 'mist_device_uptime_seconds{hostname=""}' not in mist_api_output

# Pytest Fixture to get API token and Org ID from environment variables
@pytest.fixture(scope="session")
def api_token():
    try:
        return os.environ["API_TOKEN"]
    except KeyError:
        pytest.fail("API_TOKEN environment variable not set")

# This fixture is will cache the outpout of the exporter for all tests in this session
@pytest.fixture(scope="session")
def mist_api_output(api_token, org_id):
    output = run_mist_exporter(api_token, org_id)
    return output


@pytest.fixture(scope="session")
def org_id():
    try:
        return os.environ["ORG_ID"]
    except KeyError:
        pytest.fail("ORG_ID environment variable not set")
