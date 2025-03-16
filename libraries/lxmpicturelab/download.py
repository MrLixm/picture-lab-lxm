import http.client
import logging
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

LOGGER = logging.getLogger(__name__)


def extract_zip(zip_path: Path, remove_zip: bool = True):
    """
    Extract the given zip archive content in the directory it is stored in.
    """
    extract_root = zip_path.parent
    LOGGER.debug(f"unzipping '{zip_path}'")
    with zipfile.ZipFile(zip_path, "r") as zip_file:
        zip_file.extractall(extract_root)

    if remove_zip:
        zip_path.unlink()

    return extract_root


def download_file(url: str, dst_path: Path):
    """
    Download a file from a web URL to the given local path.
    """
    LOGGER.debug(f"downloading '{url}' to '{dst_path}'")
    urllib.request.urlretrieve(url, dst_path)


def download_file_advanced(url: str, dst_path: Path, params: dict, headers: dict):
    """
    Download a file from a web URL to the given local path.

    Perform a POST request with specific parameters.
    """
    url = url.split("://", 1)[-1]
    host, endpoint = url.split("/", 1)
    endpoint = "/" + endpoint
    params = urllib.parse.urlencode(params)

    connection = http.client.HTTPSConnection(host)
    connection.request("POST", endpoint, body=params, headers=headers)
    response = connection.getresponse()

    if response.status == 200:
        LOGGER.debug(f"downloading '{url}' to '{dst_path}'")
        with dst_path.open("wb") as file:
            file.write(response.read())
    else:
        raise ConnectionError(
            f"Failed to download {response.status}: {response.reason}"
        )
    connection.close()
