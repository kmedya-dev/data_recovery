import os
import json # Still needed for potential future use or if other parts of the system rely on it
import argparse
from datetime import datetime
from pathlib import Path
import time
import subprocess
import pickle

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import io
import re
import sys

# --- CONFIGURATION ---
SCOPES = ['https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/drive.readonly']
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.pkl'
DRIVE_FOLDER_NAME = 'Backups'

# IMPORTANT: Set the same strong password used for 7z archive encryption in backup.py.
COMPRESSION_PASSWORD = "YourSecure7zPasswordHere"

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

def list_drive_backups(credentials, drive_folder_name):
    """Lists .7z backup files in the specified Google Drive folder."""
    try:
        service = build('drive', 'v3', credentials=credentials)

        # Find the 'Backups' folder ID
        results = service.files().list(
            q=f"name='{drive_folder_name}' and mimeType='application/vnd.google-apps.folder'",
            spaces='drive',
            fields='files(id)'
        ).execute()
        
        items = results.get('files', [])
        if not items:
            print(f"Error: '{drive_folder_name}' folder not found in Google Drive.")
            return []
        folder_id = items[0]['id']

        # List .7z files within the 'Backups' folder
        print(f"Listing .7z files in '{drive_folder_name}'...")
        results = service.files().list(
            q=f"'{folder_id}' in parents and mimeType='application/x-7z-compressed'",
            spaces='drive',
            fields='files(id, name, size, modifiedTime)'
        ).execute()
        
        backups = results.get('files', [])
        return sorted(backups, key=lambda x: x['modifiedTime'], reverse=True)

    except Exception as e:
        print(f"An error occurred while listing Drive backups: {e}")
        return []

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

def download_file_from_drive(file_id, file_name, destination_path, credentials, file_size):
    """Downloads a file from Google Drive."""
    try:
        service = build('drive', 'v3', credentials=credentials)
        request = service.files().get_media(fileId=file_id)
        fh = io.FileIO(destination_path, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        print(f"Downloading '{file_name}'...")
        start_time = time.time()
        downloaded_bytes = 0
        last_printed_percentage = -1 # Initialize for print_progress_bar

        while done is False:
            status, done = downloader.next_chunk()
            if status:
                downloaded_bytes = status.resumable_progress
                last_printed_percentage = print_progress_bar(
                    downloaded_bytes, file_size, start_time, last_printed_percentage, prefix="Downloading"
                )

        sys.stdout.write("\r✅ Download complete!          \n") # Clear the line and print final message
        sys.stdout.flush()
        print(f" Downloaded to: {destination_path}")
        return True
    except Exception as e:
        print(f"Error downloading file '{file_name}': {e}")
        return False

    

def restore_backup(archive_file_path, target_dir, password):
    """Restores a backup from a .7z file to the target directory."""
    archive_path = Path(archive_file_path)
    target_path = Path(target_dir)

    if not archive_path.is_file():
        print(f"Error: 7z archive file not found at {archive_path}")
        return

    target_path.mkdir(parents=True, exist_ok=True)

    print(f"Extracting {archive_path} to {target_path}...")
    try:
        # 7z x: extract with full paths, -p: password, -aoa: overwrite all existing files
        # Timestamps are preserved by default with 7z extraction
        command = [
            "7z", "x",
            f"-p{password}",
            str(archive_path),
            f"-o{target_path}",
            "-aoa" # Overwrite all existing files without prompt
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        print(result.stdout)
        if result.stderr:
            print(f"7z stderr: {result.stderr}")
        print("Extraction complete.")

        print("\nRestore process complete!")

    except subprocess.CalledProcessError as e:
        print(f"Error: 7z extraction failed. Return code: {e.returncode}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
    except FileNotFoundError:
        print("Error: '7z' command not found. Please ensure p7zip is installed and in your PATH.")
    except Exception as e:
        print(f"An unexpected error occurred during restore: {e}")

def main():
    parser = argparse.ArgumentParser(description="Restore a backup from a .7z file.")
    parser.add_argument("--archive_file", help="Path to a local .7z archive to restore.")
    parser.add_argument("--target_dir", default=str(Path.cwd() / "restored_data"),
                        help="The directory where the backup should be restored (default: current_dir/restored_data)")
    parser.add_argument("--from_drive", action="store_true",
                        help="List and download a backup from Google Drive before restoring.")
    
    args = parser.parse_args()

    if args.from_drive:
        creds = authenticate_google_drive()
        if not creds:
            print("Google Drive authentication failed. Cannot list/download from Drive.")
            return

        backups = list_drive_backups(creds, DRIVE_FOLDER_NAME)
        if not backups:
            print("No .7z backups found in Google Drive.")
            return

        print("\nAvailable Backups on Google Drive:")
        for i, b in enumerate(backups):
            size_gb = float(b.get('size', 0)) / (1024**3)
            mod_time = datetime.fromisoformat(b.get('modifiedTime').replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M:%S')
            print(f"{i+1}) {b.get('name')} (Size: {size_gb:.2f} GB, Modified: {mod_time})")
        
        while True:
            try:
                choice = int(input("Enter the number of the backup to restore: "))
                if 1 <= choice <= len(backups):
                    selected_backup = backups[choice - 1]
                    break
                else:
                    print("Invalid choice. Please enter a number within the range.")
            except ValueError:
                print("Invalid input. Please enter a number.")

        download_path = Path(args.target_dir).parent / selected_backup['name'] # Download to parent of target_dir
        Path(args.target_dir).parent.mkdir(parents=True, exist_ok=True)

        if download_file_from_drive(selected_backup['id'], selected_backup['name'], download_path, creds, int(selected_backup['size'])):
            restore_backup(download_path, args.target_dir, COMPRESSION_PASSWORD)
            # Optional: Clean up downloaded archive after successful restore
            if download_path.exists():
                os.remove(download_path)
                print(f"Cleaned up downloaded archive: {download_path}")
        else:
            print("Failed to download backup from Google Drive.")

    elif args.archive_file:
        restore_backup(Path(args.archive_file), Path(args.target_dir), COMPRESSION_PASSWORD)
    else:
        parser.print_help()
        print("\nError: You must specify either --archive_file or --from_drive.")

if __name__ == "__main__":
    main()