import os
import json
import zipfile
from datetime import datetime
from pathlib import Path

# --- CONFIGURATION ---
# The directory to back up.
SOURCE_DIR = str(Path.home()) # Example: /data/data/com.termux/files/home

# The directory to store the backup files.
DESTINATION_DIR = str(Path.cwd()) # Example: /root/DEVICE_BACKUP

# The name of the backup file (without extension).
BACKUP_NAME = f"backup_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"

def get_file_metadata(file_path):
    """Gets the metadata for a file."""
    stat = file_path.stat()
    return {
        "access_time": datetime.fromtimestamp(stat.st_atime).isoformat(),
        "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }

def create_backup(source, destination, backup_name):
    """Creates a backup of the source directory."""
    metadata = {}
    zip_path = Path(destination) / f"{backup_name}.zip"
    metadata_path = Path(destination) / f"{backup_name}.metadata.json"

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(source):
            for file in files:
                file_path = Path(root) / file
                relative_path = file_path.relative_to(source)
                print(f"Adding {relative_path} to backup...")
                zipf.write(file_path, relative_path)
                metadata[str(relative_path)] = get_file_metadata(file_path)

    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=4)

    print(f"\nBackup created successfully!")
    print(f"  - Archive: {zip_path}")
    print(f"  - Metadata: {metadata_path}")

def main():
    """Main function to run the backup script."""
    source_path = Path(SOURCE_DIR)
    destination_path = Path(DESTINATION_DIR)

    if not source_path.is_dir():
        print(f"Error: Source directory not found at {source_path}")
        return

    destination_path.mkdir(parents=True, exist_ok=True)

    create_backup(source_path, destination_path, BACKUP_NAME)

if __name__ == "__main__":
    main()