import azure.functions as func
import logging
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
import json
import datetime
import time
import os
import paramiko
import pgpy
from azure.identity import DefaultAzureCredential
from azure.keyvault.keys import KeyClient
from azure.keyvault.secrets import SecretClient


credential = DefaultAzureCredential()

sftp_host = os.getenv("SFTP_HOST_NAME")
sftp_port = int(os.getenv("SFTP_PORT"))
sftp_username = os.getenv("SFTP_USERNAME") 
sftp_password = os.getenv("SFTP_PASSWORD")

dest_container_name = "sftp"
dest_connection_string = os.getenv("DESTINATION_CONNECTION_STRING")

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

        # Destination Blob Storage
        dest_blob_service_client = BlobServiceClient.from_connection_string(dest_connection_string)

        # Time range: last 30 minutes
        now = time.time()
        thirty_minutes_ago = now - (30 * 60)

        # Connect to SFTP
        transport = paramiko.Transport((sftp_host, sftp_port))
        transport.connect(username=sftp_username, password=sftp_password)
        sftp = paramiko.SFTPClient.from_transport(transport)

        # Set working directory - Landing Page is currently sftp/Spotify
        # target_dir = "ETrade/Inbound"
        target_dir = "/Spotify_KPMG/Files_To_ETrade/Inbound" #should be a request body
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
                            blob=f"Spotify/Etrade/Inbound/{file_name}" #should be a request body
                        )
                        dest_blob_client.upload_blob(file_data, overwrite=True)
                        logging.info(f"Uploaded {file_name} to blob storage.")

                        # Delete from SFTP (optional)
                        sftp.remove(remote_file_path)
                        logging.info(f"Deleted {file_name} from SFTP.")

                        processed_files.append(file_name)

                    #handle decryption here - call decryption function here?

                except FileNotFoundError:
                    logging.warning(f"File not found during processing: {remote_file_path}")

        sftp.close()
        transport.close()

        # handle copy to archive storage account 

        logging.info(f"Processed files: {', '.join(processed_files)}")
        if processed_files:
            return func.HttpResponse(f"Processed files: {', '.join(processed_files)}", status_code=200)
        else:
            return func.HttpResponse("No new files found in the last 30 minutes.", status_code=200)
        
    except Exception as e:
        logging.error(f"Error during file copy: {str(e)}")
        return func.HttpResponse(f"Error during file copy: {str(e)}", status_code=500)
    

@app.route(route="decryption")
def decryption(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Starting decryption of files uploaded in the last 30 minutes")

    secret_client = SecretClient(vault_url="https://alto-pgp-test-kv.vault.azure.net/", credential=credential)

    # STORAGE_CONNECTION_STRING = secret_client.get_secret("storage-account-connection-string").value
    STORAGE_CONNECTION_STRING = os.getenv("DESTINATION_CONNECTION_STRING")

    # Initialize BlobServiceClient
    blob_service_client = BlobServiceClient.from_connection_string(STORAGE_CONNECTION_STRING)

    # Get the PGP key location (either from file path or KeyVault)
    pgp_key = secret_client.get_secret("public-key-2").value

    pgp_private_key = secret_client.get_secret("private-key-2").value

    passphrase = secret_client.get_secret("passphrase").value

    container_name = dest_container_name
    blob_prefix = "Spotify/Etrade/Inbound/" #should be a request body
    # container_name = req.params.get('containerName')
    # logging.info(f'Params.get {container_name}')

    # if not container_name:
    #     try:
    #         req_body = req.get_json()
    #         container_name = req_body.get('containerName')
    #         logging.info(f'req.get_json {req_body}')
    #         logging.info(f'req_body.get in try {container_name}')
    #     except ValueError:
    #         pass
    # else:
    #     container_name = req_body.get('containerName')
    #     logging.info(f'req_body.get {container_name}')

    try:
        container_client = blob_service_client.get_container_client(container_name)
        blobs = list(container_client.list_blobs(name_starts_with=blob_prefix))

        if not blobs:
            return func.HttpResponse(f"No blobs found in '{blob_prefix}'", status_code=404)
        
        now = datetime.datetime.now(datetime.timezone.utc)
        thirty_minutes_ago = now - datetime.timedelta(minutes=180)

        recent_pgp_blobs = [
            blob for blob in blobs
            if blob.name.lower().endswith(".pgp") and blob.creation_time >= thirty_minutes_ago
        ]

        if not recent_pgp_blobs:
            return func.HttpResponse("No .pgp files uploaded in the last 30 minutes.", status_code=200)
        
        private_key, _ = pgpy.PGPKey.from_blob(pgp_private_key)
        decrypted_count = 0

        for blob in recent_pgp_blobs:
            blob_name = blob.name
            logging.info(f"Decrypting blob: {blob_name} (uploaded: {blob.creation_time})")

            try:
                blob_client = container_client.get_blob_client(blob_name)
                blob_data = blob_client.download_blob().readall()

                if private_key.is_protected:
                    with private_key.unlock(passphrase):
                        logging.info("PGP private key unlocked with passphrase.")

                        # Load encrypted message properly
                        message = pgpy.PGPMessage.from_blob(blob_data)

                        # Decrypt
                        decrypted_message = private_key.decrypt(message)

                        # Convert to bytes for upload
                        decrypted_bytes = (
                            decrypted_message.message.encode("utf-8")
                            if isinstance(decrypted_message.message, str)
                            else bytes(decrypted_message.message)
                        )

                # Remove only the final `.pgp` extension
                if blob_name.lower().endswith(".pgp"):
                    decrypted_blob_name = blob_name[:-4]  # Strip `.pgp`
                else:
                    decrypted_blob_name = blob_name  # fallback

                decrypted_blob_client = container_client.get_blob_client(decrypted_blob_name)
                decrypted_blob_client.upload_blob(decrypted_bytes, overwrite=True)

                # Delete the original .pgp file
                container_client.delete_blob(blob_name)
                logging.info(f"Deleted original encrypted blob: {blob_name}")

                decrypted_count += 1
                logging.info(f"Decrypted and uploaded: {decrypted_blob_name}")

            except Exception as file_err:
                logging.error(f"Failed to decrypt {blob_name}: {str(file_err)}")

        return func.HttpResponse(f"Decrypted {decrypted_count} file(s).", status_code=200)
    
    except Exception as e:
        logging.error(f"General error: {str(e)}")
        return func.HttpResponse("Failed to complete decryption process.", status_code=500)



@app.route(route="OutboundTransferFile")
def OutboundTransferFile(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Outbound Function App Triggered and Processed a request')

    fileName = req.params.get('fileName')
    logging.info(f'Params.get {fileName}')
    folderPath = req.params.get('folderPath')
    logging.info(f'Params.get {folderPath}')
    if not fileName or not folderPath:
        try:
            req_body = req.get_json()
            fileName = req_body.get('fileName')
            folderPath = req_body.get('folderPath')
            logging.info(f'req.get_json {req_body}')
            logging.info(f'req_body.get in try {fileName}, {folderPath}')
        except ValueError:
            pass
    else:
        fileName = req_body.get('fileName')
        folderPath = req_body.get('folderPath')
        logging.info(f'req_body.get {fileName}, {folderPath}')

    # Function to copy file uploaded in Spotify/Etrade/Outbound to Archive/Spotify/Etrade/Outbound 
    # both folders in sftp container 

    # Function also moves the file to SFTP server from Spotify/Etrade/Outbound

    source_conn_string = os.getenv("OUTBOUND_SOURCE_CONNECTION_STRING")
    container_name = "sftp" #should be a request body
    source_blob_path = f"Spotify/Etrade/Outbound/{fileName}" #should be a request body

    # Date automatically generated from python in this format - YYYY-MM-DD and appended to path 
    dest_blob_path = "Archive/Spotify/Etrade/Outbound" #should be a request body
    date_folder = datetime.date.today().isoformat()
    full_path = f"{dest_blob_path}/{date_folder}/{fileName}"
    logging.info(f"full path - {full_path}")

    try:
        blob_service_client = BlobServiceClient.from_connection_string(source_conn_string)
        container_client = blob_service_client.get_container_client(container_name)

        source_blob_client = container_client.get_blob_client(source_blob_path)
        source_blob_url = source_blob_client.url

        dest_blob_client = container_client.get_blob_client(full_path)

        # download blob to memory
        blob_data = source_blob_client.download_blob().readall()

        # Upload to archive folder
        dest_blob_client.upload_blob(blob_data, overwrite=True)
        logging.info(f"Copied blob to archive path: {dest_blob_path}")

        # copy_operation = dest_blob_client.start_copy_from_url(source_blob_url)
        # logging.info(f"Copy started. Status: {copy_operation['copy_status']}")
        # logging.info(f"Copied from {source_blob_path} to {full_path}")


        # Upload to SFTP 
        # Connect to SFTP
        sftp_target_dir = "/Spotify_KPMG/Files_To_ETrade/Outbound"
        transport = paramiko.Transport((sftp_host, sftp_port))
        transport.connect(username=sftp_username, password=sftp_password)
        sftp = paramiko.SFTPClient.from_transport(transport)

        # try:
        
        sftp.chdir(sftp_target_dir)
        # except IOError:
        #     sftp.mkdir(sftp_target_dir)
        #     sftp.chdir(sftp_target_dir)

        sftp_file_path = f"{sftp_target_dir}/{fileName}"
        logging.info(f"SFTP File Path - {sftp_file_path}")
        with sftp.file(sftp_file_path, "wb") as sftp_file:
            sftp_file.write(blob_data)
            logging.info(f"Uploaded file to SFTP path: {sftp_file_path}")
        
        sftp.close()
        transport.close()

        return func.HttpResponse(f"Copied blob to archive to to {full_path} and uploaded to SFTP successfully: {sftp_file_path}", status_code=200)
    
    except Exception as e:
        logging.error(f"Error during file copy: {str(e)}")
        return func.HttpResponse(f"Error during file copy: {str(e)}", status_code=500)


@app.route(route="copyfiletoarchive")
def copyfiletoarchive(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Copying Files to Archive Container')

    # Destination Blob Storage
    dest_blob_service_client = BlobServiceClient.from_connection_string(dest_connection_string)

    archive_blob_path = "Archive/Spotify/Etrade/Inbound" #should be a request body
    normal_blob_path = "Spotify/Etrade/Inbound/" #should be a request body
    date_folder = datetime.date.today().isoformat()
    container_name = "sftp" #should be a request body
    file_extension = ".csv" # should be a request body

    try:
        container_client = dest_blob_service_client.get_container_client(container_name)
        blobs = list(container_client.list_blobs(name_starts_with=normal_blob_path))

        if not blobs:
            logging.info(f"No blobs found in '{normal_blob_path}'", status_code=404)
            return func.HttpResponse(f"No blobs found in '{normal_blob_path}'", status_code=404)
        
        now = datetime.datetime.now(datetime.timezone.utc)
        thirty_minutes_ago = now - datetime.timedelta(minutes=30)

        recent_file_blobs = [
            blob for blob in blobs
            if blob.name.lower().endswith(file_extension) and blob.creation_time >= thirty_minutes_ago
        ]

        logging.info(f"Found {len(recent_file_blobs)} {file_extension} files modified in the last 30 minutes")

        copied_blobs = []

        if recent_file_blobs:

            for blob in recent_file_blobs:
                blob_name = blob.name
                
                logging.info(f"blob name - {blob_name}")

                relative_name = blob_name.replace(normal_blob_path, "", 1)

                full_path = f"{archive_blob_path}/{date_folder}/{relative_name}"

                logging.info(f"full path - {full_path}")

                blob_client = container_client.get_blob_client(blob_name)
                blob_data = blob_client.download_blob().readall()

                archive_blob_client = container_client.get_blob_client(full_path)

                # Upload to archive folder
                archive_blob_client.upload_blob(blob_data, overwrite=True)
                logging.info(f"Copied blob to archive path: {full_path}")
                copied_blobs.append(full_path)
        else:
            logging.info(f"No recent blobs in the last 30 minutes - {recent_file_blobs}")
            return func.HttpResponse(f"No recent blobs in the last 30 minutes", status_code=404)

        return func.HttpResponse(f"Copied {len(copied_blobs)} file(s) to archive:\n" + "\n".join(copied_blobs),status_code=200)
    
    except Exception as e:
        logging.error(f"Error during file copy: {str(e)}")
        return func.HttpResponse(f"Error during file copy: {str(e)}", status_code=500)
