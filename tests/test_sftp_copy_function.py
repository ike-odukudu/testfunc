import sys
import os
from unittest.mock import patch, MagicMock

# Ensure the function_app module can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from function_app import transferfile

class MockRequest:
    def __init__(self, json_data):
        self._json = json_data

    def get_json(self):
        return self._json

@patch("function_app.BlobServiceClient")
def test_transferfile_success(mock_blob_service_client):
    # Arrange
    mock_req = MockRequest({
        "source_container": "sftp2",
        "source_blob": "test.txt",
        "dest_container": "sftp",
        "dest_blob": "test_copy.txt"
    })

    # Mock BlobServiceClient and its get_blob_client behavior
    mock_blob_client = MagicMock()
    mock_blob_service = MagicMock()
    mock_blob_service.get_blob_client.return_value = mock_blob_client
    mock_blob_service_client.from_connection_string.return_value = mock_blob_service

    mock_blob_client.start_copy_from_url.return_value = {
        "copy_status": "success",
        "copy_id": "12345"
    }

    # Act
    response = transferfile(mock_req)

    # Assert
    assert response.status_code == 200
    assert "File copy operation status" in response.get_body().decode()
