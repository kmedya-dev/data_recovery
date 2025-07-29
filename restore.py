

import os
import json
import zipfile
from datetime import datetime
from pathlib import Path

def restore_backup(zip_path, metadata_path, restore_to_path):
    """Restores a backup from a zip file and metadata."""
    print(f"Extracting {zip_path} to {restore_to_path}...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(restore_to_path)

    with open(metadata_path, 'r') as f:
        metadata = json.load(f)

    for relative_path, data in metadata.items():
        file_path = restore_to_path / relative_path
        if file_path.exists():
            access_time = datetime.fromisoformat(data['access_time']).timestamp()
            modified_time = datetime.fromisoformat(data['modified_time']).timestamp()
            print(f"Restoring timestamps for {relative_path}...")
            os.utime(file_path, (access_time, modified_time))

    print("\nRestore completed successfully!")

def main():
    """Main function to run the restore script."""
    zip_file = input("Enter the path to the backup .zip file: ")
    metadata_file = input("Enter the path to the metadata.json file: ")
    restore_location = input("Enter the directory to restore to (e.g., /path/to/restore): ")

    zip_path = Path(zip_file)
    metadata_path = Path(metadata_file)
    restore_to_path = Path(restore_location)

    if not zip_path.is_file() or not metadata_path.is_file():
        print("Error: Backup or metadata file not found.")
        return

    restore_to_path.mkdir(parents=True, exist_ok=True)

    restore_backup(zip_path, metadata_path, restore_to_path)

if __name__ == "__main__":
    main()

