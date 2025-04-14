import azure.functions as func
import logging
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
import json
import datetime
import time
import os
import paramiko

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="transferfile")
def transferfile(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Transfer files from SFTP to SCM storage account')

    try:

        # Checks sftp server for files that have been uploaded in the last 30 minutes 
        # For each file, upload to destination storage account 
        # Delete each file after upload 
        # create a log of files that have been uploaded and deleted

        # SFTP credentials
        logging.info(f"==================================================")
        logging.info(f"==================== SFTP LOGIN ==================")
        sftp_host = os.getenv("SFTP_HOST_NAME")
        sftp_port = int(os.getenv("SFTP_PORT"))
        sftp_username = os.getenv("SFTP_USERNAME") 
        sftp_password = os.getenv("SFTP_PASSWORD")

        # Destination Blob Storage
        dest_container_name = "sftp"
        dest_connection_string = os.getenv("DESTINATION_CONNECTION_STRING")
        dest_blob_service_client = BlobServiceClient.from_connection_string(dest_connection_string)

        # Time range: last 30 minutes
        now = time.time()
        thirty_minutes_ago = now - (30 * 60)

        # Connect to SFTP
        transport = paramiko.Transport((sftp_host, sftp_port))
        transport.connect(username=sftp_username, password=sftp_password)
        sftp = paramiko.SFTPClient.from_transport(transport)

        # Set working directory - Landing Page is currently sftp/Spotify
        target_dir = "ETrade"
        try:
            sftp.chdir(target_dir)
            logging.info(f"Changed to directory: {target_dir}")
        except FileNotFoundError:
            logging.warning(f"Directory {target_dir} does not exist on SFTP server.")
            return func.HttpResponse(f"Directory '{target_dir}' does not exist on SFTP server.", status_code=200)
        
        # List and filter files
        files = sftp.listdir_attr()
        if not files:
            logging.info(f"No files found in SFTP directory: {target_dir}")
            return func.HttpResponse(f"No files found in {target_dir}", status_code=200)

        processed_files = []

        for file_attr in files:
            file_name = file_attr.filename
            file_mtime = file_attr.st_mtime
            remote_file_path = f"{file_name}"

            # Only process .pgp files
            # if not file_name.lower().endswith(".pgp"):
            #     logging.info(f"Skipping non-.pgp file: {file_name}")
            #     continue

            if file_mtime >= thirty_minutes_ago:
                logging.info(f"Processing {file_name} (modified: {datetime.datetime.fromtimestamp(file_mtime)})")

                try:

                    with sftp.file(remote_file_path, "rb") as file_handle:
                        file_data = file_handle.read()

                        # Upload to Blob
                        dest_blob_client = dest_blob_service_client.get_blob_client(
                            container=dest_container_name,
                            blob=f"Spotify/ETrade/{file_name}"
                        )
                        dest_blob_client.upload_blob(file_data, overwrite=True)
                        logging.info(f"Uploaded {file_name} to blob storage.")

                        # Delete from SFTP (optional)
                        sftp.remove(remote_file_path)
                        logging.info(f"Deleted {file_name} from SFTP.")

                        processed_files.append(file_name)

                except FileNotFoundError:
                    logging.warning(f"File not found during processing: {remote_file_path}")

        sftp.close()
        transport.close()
        logging.info(f"Processed files: {', '.join(processed_files)}")
        if processed_files:
            return func.HttpResponse(f"Processed files: {', '.join(processed_files)}", status_code=200)
        else:
            return func.HttpResponse("No new files found in the last 30 minutes.", status_code=200)
        
    except Exception as e:
        logging.error(f"Error during file copy: {str(e)}")
        return func.HttpResponse(f"Error during file copy: {str(e)}", status_code=500)



# @app.event_grid_trigger(arg_name="azeventgrid")
# def UploadFileEventTrigger(azeventgrid: func.EventGridEvent):

#     try:
#         event_data = azeventgrid.get_json()
#         #Handling Blob Created Events to only use SftpCommit and not SftpCreate
#         api_type = event_data.get("api")

#         if api_type != "SftpCommit":
#             logging.info(f"Ignoring event with api: {api_type}")
#             return
        
#         logging.info(f"Event data: {event_data}")

#         result = json.dumps({
#             'id': azeventgrid.id,
#             'data': azeventgrid.get_json(),
#             'topic': azeventgrid.topic,
#             'subject': azeventgrid.subject,
#             'event_type': azeventgrid.event_type,
#         })

#         logging.info('Python EventGrid trigger processed an event: %s', result)

#         # Get source blob URL from event
#         blob_url = event_data.get("url")
#         logging.info(f"Blob URL from event: {blob_url}")

#         # Parse source container and blob name
#         split_url_parts = blob_url.replace("https://", "").split("/", 3)
#         source_account_name = split_url_parts[0].split(".")[0]
#         source_container_name = split_url_parts[1]
#         source_container_folder = split_url_parts[2]
#         source_blob_name = split_url_parts[3]

#         logging.info(f"Storage Account Name: {source_account_name}")
#         logging.info(f"Storage Container Name: {source_container_name}")
#         logging.info(f"Storage Container Folder: {source_container_folder}")
#         logging.info(f"Storage Blob Name: {source_blob_name}")

#         # SFTP credentials
#         logging.info(f"==================================================")
#         logging.info(f"==================== SFTP LOGIN ==================")
#         sftp_host = os.getenv("SFTP_HOST_NAME")
#         sftp_port = int(os.getenv("SFTP_PORT"))
#         sftp_username = os.getenv("SFTP_USERNAME")  # e.g., "sftpuser1"
#         sftp_password = os.getenv("SFTP_PASSWORD")

#         remote_file_path = f"./{source_blob_name}"  # this is the virtual path - the parent directory is /sftp/Spotify
#         dest_container_name = "sftp"
#         dest_blob_name = f"{source_container_folder}/{source_blob_name}"

#         # Destination blob storage connection
#         dest_connection_string = os.getenv("DESTINATION_CONNECTION_STRING")
#         dest_blob_service_client = BlobServiceClient.from_connection_string(dest_connection_string)
#         dest_blob_client = dest_blob_service_client.get_blob_client(container=dest_container_name, blob=dest_blob_name)

#         transport = paramiko.Transport((sftp_host, sftp_port))
#         transport.connect(username=sftp_username, password=sftp_password)

#         sftp = paramiko.SFTPClient.from_transport(transport)

#         with sftp.file(remote_file_path, "rb") as file_handle:
#             file_data = file_handle.read()
#             dest_blob_client.upload_blob(file_data, overwrite=True)
#             logging.info("File uploaded to blob successfully.")

#         # Delete the file from the SFTP server
#         sftp.remove(remote_file_path)
#         logging.info(f"Deleted source file: {remote_file_path}")

#         sftp.close()
#         transport.close()

#         # # Destination details
#         # destination_container_name = "sftp"
#         # destination_blob_name = source_blob_name  # keep same name or customize if needed

#         # # Construct source blob URL (already from event)
#         # source_connection_string = os.getenv("SOURCE_CONNECTION_STRING")
#         # source_blob_service = BlobServiceClient.from_connection_string(source_connection_string)
#         # source_blob_client = source_blob_service.get_blob_client(container=source_container_name, blob=source_blob_name)

#         # sas_token = generate_blob_sas(
#         #     account_name=source_account_name,
#         #     container_name=source_container_name,
#         #     blob_name=source_blob_name,
#         #     account_key=os.getenv("SOURCE_ACCOUNT_KEY"),
#         #     permission=BlobSasPermissions(read=True),
#         #     expiry=datetime.utcnow() + timedelta(minutes=10)
#         # )

#         # source_blob_url = f"{blob_url}?{sas_token}"
#         # # source_blob_url = blob_url

#         # # Destination account connection string (hardcoded, since no env var)
#         # dest_connection_string = os.getenv("DESTINATION_CONNECTION_STRING")

#         # # Copy blob
#         # dest_blob_service = BlobServiceClient.from_connection_string(dest_connection_string)
#         # dest_blob_client = dest_blob_service.get_blob_client(destination_container_name, destination_blob_name)
#         # copy_operation = dest_blob_client.start_copy_from_url(source_blob_url)

#         # logging.info(f"Copy operation started. Status: {copy_operation['copy_status']}")

#     except Exception as e:
#         logging.error(f"Error during file copy: {str(e)}")