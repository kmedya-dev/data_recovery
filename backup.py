import os
import json # Still needed for potential future use or if other parts of the system rely on it
import argparse
import pickle
from datetime import datetime
from pathlib import Path
import time
import subprocess
import re

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

# --- CONFIGURATION ---
SCOPES = ['https://www.googleapis.com/auth/drive.file']
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.pkl'
DRIVE_FOLDER_NAME = 'Backups'

# IMPORTANT: Set a strong password for 7z archive encryption.
# For production, consider reading this from an environment variable or secure prompt.
COMPRESSION_PASSWORD = "YourSecure7zPasswordHere"

def create_backup(source_dir, destination_dir, backup_name, password):
    """
    Creates a backup of the source directory into a .7z file.
    Returns the path to the created 7z file.
    """
    source_path = Path(source_dir)
    destination_path = Path(destination_dir)
    
    if not source_path.is_dir():
        print(f"Error: Source directory not found at {source_path}")
        return None

    destination_path.mkdir(parents=True, exist_ok=True)

    archive_file_path = destination_path / f"{backup_name}.7z"

    print(f"Creating backup: {archive_file_path} using 7z...")
    # 7z command: a (add), -t7z (7z format), -mx=9 (ultra compression), -mhe=on (encrypt headers)
    # -p (password)
    # 7z inherently preserves modification times (mtime) during compression and extraction.
    try:
        command = [
            "7z", "a", "-t7z", "-mx=9", "-mhe=on",
            f"-p{password}",
            str(archive_file_path),
            str(source_path)
        ]
        
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        last_reported_percentage = -1
        while True:
            line = process.stdout.readline()
            if not line:
                break
            
            # Look for lines like "  X%" or "  XX%"
            match = re.match(r"\s*(\d+)%", line)
            if match:
                percentage = int(match.group(1))
                if percentage > last_reported_percentage:
                    print(f"Compression progress: {percentage}%")
                    last_reported_percentage = percentage
            # You can also print other 7z output if needed
            # print(line.strip())

        stdout, stderr = process.communicate()

        if process.returncode != 0:
            print(f"Error: 7z compression failed. Return code: {process.returncode}")
            print(f"Stdout: {stdout}")
            print(f"Stderr: {stderr}")
            return None
        
        print(f"\nBackup created successfully at: {archive_file_path}")
        return archive_file_path
    except FileNotFoundError:
        print("Error: '7z' command not found. Please ensure p7zip is installed and in your PATH.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during 7z compression: {e}")
        return None

def authenticate_google_drive():
    """Authenticates with Google Drive API."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0, open_browser=False)
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)
    return creds

def upload_to_drive(file_path, credentials, drive_folder_name):
    """Uploads a file to Google Drive."""
    try:
        service = build('drive', 'v3', credentials=credentials)

        print(f"Searching for '{drive_folder_name}' folder in Google Drive...")
        results = service.files().list(
            q=f"name='{drive_folder_name}' and mimeType='application/vnd.google-apps.folder'",
            spaces='drive',
            fields='files(id, name)'
        ).execute()
        
        items = results.get('files', [])
        folder_id = None
        if not items:
            print(f"'{drive_folder_name}' folder not found. Creating it...")
            file_metadata = {
                'name': drive_folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = service.files().create(body=file_metadata, fields='id').execute()
            folder_id = folder.get('id')
            print(f"'{drive_folder_name}' folder created with ID: {folder_id}")
        else:
            folder_id = items[0]['id']
            print(f"Found '{drive_folder_name}' folder with ID: {folder_id}")

        file_name = Path(file_path).name
        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }
        _last_reported_progress = -1 # Reset for each new upload

        def progress_callback(current_bytes, total_bytes):
            nonlocal _last_reported_progress
            if total_bytes > 0:
                percentage = int((current_bytes / total_bytes) * 100)
                if percentage > _last_reported_progress:
                    print(f"Uploaded {percentage}%")
                    _last_reported_progress = percentage

        media = MediaFileUpload(file_path, mimetype='application/x-7z-compressed', resumable=True)
        
        print(f"Uploading '{file_name}' to Google Drive...")
        request = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink')
        response = None
        _last_reported_progress = -1
        while response is None:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                if progress > _last_reported_progress:
                    print(f"Upload progress: {progress}%")
                    _last_reported_progress = progress
        
        file = response 
        
        print(f"Upload complete! File ID: {file.get('id')}")
        print(f"View link: {file.get('webViewLink')}")
        return file.get('webViewLink')

    except Exception as e:
        print(f"An error occurred during Google Drive upload: {e}")
        return None

def cleanup_all_7z_files(directory, dry_run=False):
    """Deletes all .7z files in the specified directory."""
    target_path = Path(directory)

    if not target_path.is_dir():
        print(f"❌ Error: Directory not found at {directory}")
        return

    print(f"\n--- Starting 7z file cleanup in: {target_path} ---")
    archive_files_found = False

    for archive_file in target_path.glob('*.7z'):
        archive_files_found = True
        if dry_run:
            print(f"[Dry Run] Would delete: {archive_file}")
        else:
            try:
                os.remove(archive_file)
                print(f"🗑️ Deleted: {archive_file}")
            except OSError as e:
                print(f"❌ Failed to delete {archive_file}: {e}")
    
    if not archive_files_found:
        print("✅ No .7z files found.")
    elif dry_run:
        print("\nDry run complete. No files were actually deleted.")
    else:
        print("\nCleanup complete.")

def main():
    parser = argparse.ArgumentParser(description="Backup a folder and upload to Google Drive.")
    parser.add_argument("source_dir", help="The source directory to backup (e.g., /storage/emulated/0/MyFiles)")
    parser.add_argument("--destination_dir", default=str(Path.cwd()), 
                        help="The directory to store the local backup file (default: current working directory)")
    parser.add_argument("--cleanup", action="store_true", 
                        help="Delete the local .7z file after successful upload to Google Drive")
    parser.add_argument("--clean-all-zips", action="store_true", 
                        help="Delete all .7z files in the destination directory after backup/upload")
    parser.add_argument("--dry-run-cleanup", action="store_true", 
                        help="Perform a dry run for --clean-all-zips (simulate deletion)")
    
    args = parser.parse_args()

    backup_name = f"backup_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    
    # Part 1: Create Backup
    archive_file_path = create_backup(args.source_dir, args.destination_dir, backup_name, COMPRESSION_PASSWORD)
    if not archive_file_path:
        return

    # Part 3: Google Drive Upload
    print("\n--- Starting Google Drive Upload ---")
    try:
        credentials = authenticate_google_drive()
        if credentials:
            upload_link = upload_to_drive(archive_file_path, credentials, DRIVE_FOLDER_NAME)
            if upload_link and args.cleanup:
                # Part 4: Optional Cleanup (just the newly created 7z)
                print(f"Deleting local backup file: {archive_file_path}")
                os.remove(archive_file_path)
                print("Local backup file deleted.")
        else:
            print("Google Drive authentication failed. Skipping upload.")
    except Exception as e:
        print(f"An error occurred during Google Drive operations: {e}")

    # New: Comprehensive 7z cleanup
    if args.clean_all_zips:
        cleanup_all_7z_files(args.destination_dir, args.dry_run_cleanup)

if __name__ == "__main__":
    main()