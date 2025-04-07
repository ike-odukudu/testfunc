import azure.functions as func
import logging
from azure.storage.blob import BlobServiceClient
import json



# Define the source and destination details
# SOURCE_CONTAINER_NAME = "sftp2"
# SOURCE_BLOB_NAME = "test.txt"
# DESTINATION_CONTAINER_NAME = "sftp"
# DESTINATION_BLOB_NAME = "test3.txt"  # Keep the same name or change it

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="transferfile")
def transferfile(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')
    logging.info('Transfer files from source storage account to destination storage account')

    try:

        req_body = req.get_json()
        SOURCE_CONTAINER_NAME = req_body.get("source_container")
        SOURCE_BLOB_NAME = req_body.get("source_blob")
        DESTINATION_CONTAINER_NAME = req_body.get("dest_container")
        DESTINATION_BLOB_NAME = req_body.get("dest_blob")

        if not SOURCE_CONTAINER_NAME or not SOURCE_BLOB_NAME or not DESTINATION_CONTAINER_NAME or not DESTINATION_BLOB_NAME:
            return func.HttpResponse("Missing required parameters.", status_code=400)

        logging.info(f"Source container: {SOURCE_CONTAINER_NAME}, Source blob: {SOURCE_BLOB_NAME}")
        logging.info(f"Destination container: {DESTINATION_CONTAINER_NAME}, Destination blob: {DESTINATION_BLOB_NAME}")

        source_account_name = "altosftpstorageacc"
        source_connection_string = "<source connection string>"

        # Source
        source_container_name = SOURCE_CONTAINER_NAME
        source_file_path = SOURCE_BLOB_NAME
        # source_blob_service = BlobServiceClient.from_connection_string(source_connection_string)
        source_blob = (f"https://{source_account_name}.blob.core.windows.net/{source_container_name}/{source_file_path}")
        

        # dest_account_name = "altoscmstorageacc"
        dest_connection_string = "<destination connection string"

        # Target
        target_container_name = DESTINATION_CONTAINER_NAME
        target_file_path = DESTINATION_BLOB_NAME

        dest_blob_service = BlobServiceClient.from_connection_string(dest_connection_string)
        dest_blob_service_client = dest_blob_service.get_blob_client(target_container_name,target_file_path)

        # copied_blob = blob_service_client.get_blob_client(target_container_name, target_file_path)
        copy_operation = dest_blob_service_client.start_copy_from_url(source_blob)

        logging.info(f"Copy operation status: {copy_operation}")

        return func.HttpResponse(f"File copy operation status: {copy_operation}", status_code=200)
        
    except Exception as e:
        logging.error(f"Error during file copy: {str(e)}")
        return func.HttpResponse(f"Error during file copy: {str(e)}", status_code=500)



@app.event_grid_trigger(arg_name="azeventgrid")
def UploadFileEventTrigger(azeventgrid: func.EventGridEvent):

    event_data = azeventgrid.get_json()
    logging.info(f"Event data: {event_data}")

    result = json.dumps({
        'id': azeventgrid.id,
        'data': azeventgrid.get_json(),
        'topic': azeventgrid.topic,
        'subject': azeventgrid.subject,
        'event_type': azeventgrid.event_type,
    })

    logging.info('Python EventGrid trigger processed an event: %s', result)

    # Get source blob URL from event
    blob_url = event_data.get("url")
    logging.info(f"Blob URL from event: {blob_url}")

    # Parse source container and blob name
    split_url_parts = blob_url.replace("https://", "").split("/", 2)
    source_account_name = split_url_parts[0].split(".")[0]
    source_container_name = split_url_parts[1]
    source_blob_name = split_url_parts[2]

    logging.info(f"Storage Account Name: {source_account_name}")
    logging.info(f"Storage Container Name: {source_container_name}")
    logging.info(f"Storage Blob Name: {source_blob_name}")

    # Destination details
    destination_container_name = "sftp"
    destination_blob_name = source_blob_name  # keep same name or customize if needed

    # Construct source blob URL (already from event)
    source_blob_url = blob_url

    # Destination account connection string (hardcoded, since no env var)
    dest_connection_string = "<destination conn string>"

    # Copy blob
    dest_blob_service = BlobServiceClient.from_connection_string(dest_connection_string)
    dest_blob_client = dest_blob_service.get_blob_client(destination_container_name, destination_blob_name)
    copy_operation = dest_blob_client.start_copy_from_url(source_blob_url)

    logging.info(f"Copy operation started. Status: {copy_operation['copy_status']}")
