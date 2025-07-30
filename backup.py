import os
import json # Still needed for potential future use or if other parts of the system rely on it
import argparse
import pickle
from datetime import datetime
from pathlib import Path
import time
import subprocess
import uuid
import re
import sys

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request, AuthorizedSession
from google_auth_oauthlib.flow import InstalledAppFlow

# --- CONFIGURATION ---
SCOPES = ['https://www.googleapis.com/auth/drive.file']
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.pkl'
DRIVE_FOLDER_NAME = 'Backups'

# IMPORTANT: Set a strong password for 7z archive encryption.
# For production, consider reading this from an environment variable or secure prompt.
COMPRESSION_PASSWORD = "YourSecure7zPasswordHere"

def generate_label(source_path):
    # Remove trailing slash if present and get the last component of the path
    normalized_path = os.path.normpath(source_path)
    path_parts = Path(normalized_path).parts

    # Consider the last two parts for more specific labels
    # Ensure there are at least two parts to avoid index errors for short paths
    if len(path_parts) >= 2:
        # Join the last two parts with a '/' to match mapping keys like "WhatsApp/Media"
        last_two_parts = f"{path_parts[-2]}/{path_parts[-1]}"
    else:
        last_two_parts = None # Not enough parts for a two-part label

    # Get the last folder name for single-folder labels or fallback
    last_folder = path_parts[-1] if path_parts else ""

    # Manual mappings for specific folder combinations or single folders
    mapping = {
        "WhatsApp/Media": "wa-media",
        "DCIM/Camera": "dcim-photos",
        "Download/Documents": "d-doc", # New specific mapping for this combination
        "Documents": "doc", # General mapping for "Documents" if not part of "Download/Documents"
        "Media": "wa-media", # General mapping for "Media" if not part of "WhatsApp/Media"
        "Camera": "dcim-photos", # General mapping for "Camera" if not part of "DCIM/Camera"
        "Download": "dl",
        "Pictures": "pics",
        "Movies": "vids",
        "Music": "audio",
        "Android": "android-data",
        "DCIM": "dcim",
        "WhatsApp": "wa",
        "Telegram": "tg",
        "Signal": "signal",
        "Viber": "viber",
        "Snapchat": "snap",
        "Instagram": "ig",
        "Facebook": "fb",
        "Twitter": "x",
        "TikTok": "tiktok",
        "Downloads": "dl",
        "Screenshots": "ss",
        "Recordings": "recs",
        "Audio": "audio",
        "Video": "video",
        "Books": "books",
        "Archives": "archives",
        "Backups": "backups",
        "Configs": "configs",
        "Logs": "logs",
        "Temp": "temp",
        "System": "sys",
        "Data": "data",
        "Files": "files",
        "Other": "other",
    }

    # Try to match the last two parts first (most specific)
    if last_two_parts and last_two_parts in mapping:
        return mapping[last_two_parts]
    # Then try to match just the last folder (less specific)
    elif last_folder in mapping:
        return mapping[last_folder]
    # Fallback to generic conversion (lowercase, replace spaces with hyphens)
    else:
        return last_folder.lower().replace(" ", "-")


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
        # To ensure the 7z progress bar renders correctly, we'll execute it via a temporary shell script.
        # This helps ensure it has a proper TTY context for rendering the progress bar.
        command_str = f"7z a -t7z -mx=9 -mhe=on -bsp1 -p'{password}' '{str(archive_file_path)}' '{str(source_path)}'"
        
        script_path = Path(destination_dir) / f"temp_backup_command_{uuid.uuid4().hex}.sh"
        with open(script_path, "w") as f:
            f.write("#!/bin/bash\n")
            f.write(command_str + "\n")
            
        # Make the script executable
        os.chmod(script_path, 0o755)

        print(f"Creating backup: {archive_file_path} using 7z...")
        
        # Execute the script, letting its output go directly to the terminal.
        process = subprocess.run([str(script_path)])

        # Clean up the temporary script
        os.remove(script_path)

        if process.returncode != 0:
            print(f"\nError: 7z compression failed. See output above for details.")
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
            creds = flow.run_local_server(port=0, open_browser=False, success_message='Authentication complete. You can close this tab.')
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)
    return creds

import sys

def upload_to_drive(service, file_path, folder_id):
    file_name = os.path.basename(file_path)

    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }

    media = MediaFileUpload(file_path, mimetype='application/x-7z-compressed', resumable=True)

    request = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    )

    file_size = os.path.getsize(file_path)
    start_time = time.time()
    last_printed_percentage = -1 # Initialize for print_progress_bar

    print(f"Uploading '{file_name}' to Google Drive...")

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            uploaded_bytes = status.resumable_progress
            last_printed_percentage = print_progress_bar(
                uploaded_bytes, file_size, start_time, last_printed_percentage, prefix="Uploading"
            )

    sys.stdout.write("\r✅ Upload complete!          \n") # Clear the line and print final message
    sys.stdout.flush()
    print(" Web view link:", response.get("webViewLink"))
    return response.get("webViewLink")

def print_progress_bar(current_bytes, total_bytes, start_time, last_printed_percentage, prefix="Transferring"):
    """
    Prints a dynamic CLI progress bar for file transfers.

    Args:
        current_bytes (int): The number of bytes transferred so far.
        total_bytes (int): The total size of the file in bytes.
        start_time (float): The timestamp (time.time()) when the transfer started.
        last_printed_percentage (int): The last percentage (multiple of 5) that was printed.
                                       Pass -1 initially to print the 0% bar.
        prefix (str): The prefix for the progress bar (e.g., "Uploading", "Downloading").

    Returns:
        int: The updated last_printed_percentage.
    """
    if total_bytes == 0: # Avoid division by zero
        return last_printed_percentage

    progress_percent = int((current_bytes / total_bytes) * 100)

    # Only update on every 5% increment or if it's the very first update (0%)
    # This also ensures we don't print the same percentage multiple times if it stays at a multiple of 5
    if progress_percent % 5 == 0 and progress_percent >= last_printed_percentage:
        if progress_percent == last_printed_percentage and progress_percent != 0:
            return last_printed_percentage
        
        # Calculate speeds and ETA
        elapsed_time = time.time() - start_time
        if current_bytes > 0 and elapsed_time > 0:
            speed_bps = current_bytes / elapsed_time
            remaining_bytes = total_bytes - current_bytes
            eta_seconds = remaining_bytes / speed_bps
        else:
            eta_seconds = 0

        # Format ETA
        if eta_seconds < 60:
            eta_str = f"{int(eta_seconds)}s left"
        else:
            eta_minutes = int(eta_seconds / 60)
            eta_str = f"{eta_minutes}m {int(eta_seconds % 60)}s left"

        # Convert to MB/GB
        def format_bytes(bytes_val):
            if bytes_val is None:
                return "N/A"
            bytes_val = float(bytes_val)
            if bytes_val >= (1024**3):
                return f"{bytes_val / (1024**3):.1f}GB"
            elif bytes_val >= (1024**2):
                return f"{bytes_val / (1024**2):.0f}MB"
            elif bytes_val >= 1024:
                return f"{bytes_val / 1024:.0f}KB"
            else:
                return f"{bytes_val:.0f}B"

        current_size_str = format_bytes(current_bytes)
        total_size_str = format_bytes(total_bytes)

        # Progress bar
        bar_length = 20
        filled_blocks = int(bar_length * progress_percent / 100)
        empty_blocks = bar_length - filled_blocks
        bar = '█' * filled_blocks + '░' * empty_blocks

        # Construct the output string
        output_str = (
            f"{prefix}: {bar} {progress_percent}% "
            f"({current_size_str} / {total_size_str}) | ⏱️ {eta_str}"
        )
        sys.stdout.write(f"\r{output_str}")
        sys.stdout.flush()
        return progress_percent
    return last_printed_percentage

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

    label = generate_label(args.source_dir)
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    backup_name = f"backup_{label}_{timestamp}"
    
    # Part 1: Create Backup
    archive_file_path = create_backup(args.source_dir, args.destination_dir, backup_name, COMPRESSION_PASSWORD)
    if not archive_file_path:
        return

    # Part 3: Google Drive Upload
    print("\n--- Starting Google Drive Upload ---")
    try:
        credentials = authenticate_google_drive()
        if credentials:
            service = build('drive', 'v3', credentials=credentials)

            print(f"Searching for '{DRIVE_FOLDER_NAME}' folder in Google Drive...")
            results = service.files().list(
                q=f"name='{DRIVE_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder'",
                spaces='drive',
                fields='files(id, name)'
            ).execute()
            
            items = results.get('files', [])
            folder_id = None
            if not items:
                print(f"'{DRIVE_FOLDER_NAME}' folder not found. Creating it...")
                file_metadata = {
                    'name': DRIVE_FOLDER_NAME,
                    'mimeType': 'application/vnd.google-apps.folder'
                }
                folder = service.files().create(body=file_metadata, fields='id').execute()
                folder_id = folder.get('id')
                print(f"'{DRIVE_FOLDER_NAME}' folder created with ID: {folder_id}")
            else:
                folder_id = items[0]['id']
                print(f"Found '{DRIVE_FOLDER_NAME}' folder with ID: {folder_id}")

            upload_link = upload_to_drive(service, archive_file_path, folder_id)
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
