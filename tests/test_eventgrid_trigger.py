import sys
import os
import json
import logging
from unittest.mock import patch, MagicMock

# Setup the path to import function_app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from function_app import UploadFileEventTrigger

class MockEventGridEvent:
    def __init__(self, event_json):
        self._json = event_json
        self.id = "fake-id"
        self.topic = "fake-topic"
        self.subject = "fake-subject"
        self.event_type = "Microsoft.Storage.BlobCreated"

    def get_json(self):
        return self._json

@patch("function_app.BlobServiceClient")
def test_upload_file_event_trigger_success(mock_blob_service_client, caplog):
    # Arrange
    caplog.set_level(logging.INFO)

    event_data = {
        "url": "https://altosftpstorageacc.blob.core.windows.net/sftp/testfile.txt"
    }

    mock_event = MockEventGridEvent(event_data)

    mock_blob_client = MagicMock()
    mock_blob_service = MagicMock()
    mock_blob_service.get_blob_client.return_value = mock_blob_client
    mock_blob_service_client.from_connection_string.return_value = mock_blob_service

    mock_blob_client.start_copy_from_url.return_value = {
        "copy_status": "success"
    }

    # Act
    UploadFileEventTrigger(mock_event)

    # Assert
    assert "Copy operation started. Status: success" in caplog.text
