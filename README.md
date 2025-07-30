# Termux Backup & Sync System

This comprehensive system provides robust backup, synchronization, and restore capabilities for your Termux environment, leveraging `7z` for efficient compression and encryption, and `rclone` or Google Drive API for cloud integration.

## Features

*   **Advanced Compression**: Utilizes `7z` with maximum compression (`-mx=9`) and encrypted headers (`-mhe=on`) for secure and space-efficient archives.
*   **Google Drive Integration**: Automatically uploads backups to a designated `Backups` folder in your Google Drive.
*   **Intelligent Cleanup**: Optionally deletes old backups from Google Drive to maintain a specified storage limit.
*   **Local Cleanup**: Option to delete local archives after successful upload or restore.
*   **Detailed Logging**: Logs every step, including compression details, upload status, and errors, with timestamps.
*   **File Integrity Check**: Verifies uploaded files on Google Drive using direct API verification (Python scripts) or checksums (shell script).
*   **Flexible Operation**: Supports both interactive CLI usage and headless automation (e.g., via cron).
*   **Modular & Configurable**: Uses separate configuration files for easy customization.
*   **Non-Root Operation**: Designed to work entirely within Termux without requiring root privileges.
*   **Restore Functionality**:
    *   Lists available backups directly from Google Drive.
    *   Allows selection and download of a specific backup.
    *   Extracts archives while preserving original file timestamps.
    *   Logs the entire restore process.

## Prerequisites

Before you begin, ensure you have the following installed in your Termux environment:

### Termux Packages

Run this one-liner in your Termux terminal:

```bash
pkg install p7zip rclone python python-pip
```

*   `p7zip`: Provides the `7z` command for compression and decompression.
*   `rclone`: A powerful command-line tool for managing files on cloud storage (used by `backup_sync_restore.sh`).
*   `python`: The Python interpreter.
*   `python-pip`: Python's package installer.

### Python Libraries

Install the required Python libraries using `pip`:

```bash
pip install google-api-python-client google-auth google-auth-oauthlib
```

### Google Cloud Project & `credentials.json`

To allow the Python scripts (`backup.py`, `restore.py`) to interact with Google Drive, you need to obtain `credentials.json`.

1.  Go to [Google Cloud Console](https://console.cloud.google.com/).
2.  Create a new project or select an existing one.
3.  Enable the "Google Drive API" for your project (APIs & Services -> Enabled APIs & Services).
4.  Go to "APIs & Services" -> "Credentials".
5.  Click "+ CREATE CREDENTIALS" and select "OAuth client ID".
6.  If prompted, configure the OAuth consent screen (User Type: External, fill required fields).
7.  For "Application type", select "Desktop app".
8.  Give it a name and click "Create".
9.  Download the JSON file. Rename it to `credentials.json` and place it in the root of this project directory (`/root/DEVICE_BACKUP/`).

### `rclone` Configuration

For the `backup_sync_restore.sh` script, you need to configure `rclone` to connect to your Google Drive.

1.  Run `rclone config` in your Termux terminal.
2.  Follow the interactive prompts:
    *   Choose `n` for new remote.
    *   Give it a name (e.g., `gdrive_backup`). Remember this name, as you'll use it in `config.sh`.
    *   Select `drive` (Google Drive) from the list.
    *   Accept default options for `client_id`, `client_secret`, `scope`, `root_folder_id`, `service_account_file`.
    *   For `config_is_local`, choose `n` (no).
    *   `rclone` will provide a URL. Copy this URL and open it in a web browser on any device where you can log into your Google account.
    *   Grant `rclone` access.
    *   Copy the authorization code provided by Google and paste it back into your Termux session.
    *   Confirm `y` for "Yes this is OK".
    *   Quit `rclone config`.

## Setup

1.  **Clone or Download**: Place all script files (`backup_sync_restore.sh`, `backup.py`, `restore.py`, `config.sh`) into your desired project directory (e.g., `/root/DEVICE_BACKUP/`).

2.  **Make Scripts Executable**:
    ```bash
    chmod +x backup_sync_restore.sh
    chmod +x backup.py
    chmod +x restore.py
    ```

3.  **Configure `config.sh`**:
    Open `config.sh` and customize the following variables:
    *   `LOCAL_BACKUPS_DIR`: Where local `.7z` archives are temporarily stored.
    *   `LOCAL_RESTORE_DIR`: Where restored files will be extracted.
    *   `LOG_DIR`: Where log files (`backup.log`, `restore.log`, `system.log`) will be stored.
    *   `UPLOAD_RETRIES`: Number of retries for network operations.
    *   `RCLONE_REMOTE_NAME`: The name you gave your Google Drive remote during `rclone config`.
    *   `RCLONE_DRIVE_FOLDER`: The name of the folder in Google Drive for backups (e.g., `Backups`).
    *   `CLEANUP_LOCAL_AFTER_UPLOAD`: `true` to delete local archive after successful upload.
    *   `CLEANUP_OLD_DRIVE_BACKUPS`: `true` to enable automatic cleanup of old backups on Drive.
    *   `DRIVE_SIZE_LIMIT_GB`: The maximum total size (in GB) for backups on Google Drive.
    *   `CLEANUP_LOCAL_AFTER_RESTORE`: `true` to delete downloaded archive after successful restore.

4.  **Configure Python Scripts (`backup.py`, `restore.py`)**:
    Open `backup.py` and `restore.py`. Locate the `COMPRESSION_PASSWORD` variable and **set a strong password here.** This password is used for 7z archive encryption and decryption. **Ensure this password is identical in both `backup.py` and `restore.py`.**

## Usage

This system offers both Python-based scripts (primary) and a shell script (utility) for backup and restore operations.

### Using `backup.py` (Primary Python-based backup)

This script focuses solely on backup and Google Drive upload using Python libraries.

```bash
python3 backup.py <source_directory> [--destination_dir <path>] [--cleanup] [--clean-all-zips] [--dry-run-cleanup]
```

*   `<source_directory>`: The folder to backup.
*   `--destination_dir`: (Optional) Where to store the local `.7z` file (defaults to current directory).
*   `--cleanup`: (Optional) Delete the newly created local `.7z` file after successful upload.
*   `--clean-all-zips`: (Optional) Delete *all* `.7z` files in the `destination_dir` after backup/upload.
*   `--dry-run-cleanup`: (Optional) Simulate `--clean-all-zips` without actual deletion.

### Using `restore.py` (Primary Python-based restore)

This script focuses solely on restore operations using Python libraries.

*   **Restore from Google Drive**:
    ```bash
    python3 restore.py --from_drive [--target_dir <path>]
    ```
    This will list available `.7z` backups from your Google Drive `Backups` folder, allow you to select one, download it, and then extract it to `--target_dir`.

*   **Restore from Local Archive**:
    ```bash
    python3 restore.py --archive_file /path/to/your/local_backup.7z [--target_dir <path>]
    ```
    This will extract the specified local `.7z` archive to `--target_dir`.

*   `--target_dir`: (Optional) The directory where the backup should be restored (defaults to `current_dir/restored_data`).

### Using `backup_sync_restore.sh` (Utility Shell Script)

This script provides a unified interface for backup and restore, useful for quick testing or specific automation needs.

*   **Interactive Mode**:
    Run without arguments to enter an interactive menu:
    ```bash
    ./backup_sync_restore.sh
    ```
    You will be prompted to choose between backup and restore, and then for necessary inputs.

*   **Headless Backup**:
    To perform a backup of a specific source directory:
    ```bash
    ./backup_sync_restore.sh backup /path/to/your/source_folder
    ```
    Replace `/path/to/your/source_folder` with the actual directory you want to back up.

*   **Headless Restore**:
    To perform a restore (will list backups from Drive and prompt for selection):
    ```bash
    ./backup_sync_restore.sh restore
    ```

## Logging

All operations are logged to files within the `LOG_DIR` specified in `config.sh`:
*   `backup.log`: For backup and upload activities.
*   `restore.log`: For restore and download activities.
*   `system.log`: For general system messages and dependency checks.

## Automation (Cron)

For automated backups, you can set up a cron job in Termux.

1.  Install `cron`: `pkg install cron`
2.  Start `crond`: `crond`
3.  Edit your crontab: `crontab -e`
4.  Add a line for your backup. For example, to run the shell script every day at 3:00 AM:
    ```cron
    0 3 * * * /path/to/your/backup_sync_restore.sh backup /path/to/your/source_folder >> /dev/null 2>&1
    ```
    (Replace `/path/to/your/` with the actual path to your script and source folder. `>> /dev/null 2>&1` redirects output to prevent spamming your terminal, so check the log files for status.)

## Security Considerations

*   **`COMPRESSION_PASSWORD`**: This is the most critical security aspect. Use a strong, unique password. Do not hardcode sensitive passwords in production environments; consider using environment variables or secure prompt methods. **Ensure this password is identical in both `backup.py` and `restore.py`.**
*   **`credentials.json`**: Keep this file secure. It grants access to your Google Drive. Do not share it or commit it to public repositories.
*   **`token.pkl`**: This file stores your Google Drive authentication tokens. Treat it with the same care as `credentials.json`.

## Troubleshooting

*   **"command not found"**: Ensure all prerequisites (`p7zip`, `rclone`, Python libraries) are installed correctly.
*   **`rclone` authentication issues**: Re-run `rclone config` and ensure you complete the authentication flow correctly.
*   **"Permission denied"**: Ensure your scripts are executable (`chmod +x script_name.sh`, `chmod +x backup.py`, `chmod +x restore.py`) and that Termux has storage permissions (`termux-setup-storage`).
*   **"could not locate runnable browser" (Python scripts)**: This is handled by the scripts printing a URL for manual authentication.
*   **7z password issues**: Ensure the `COMPRESSION_PASSWORD` is identical in `backup.py` and `restore.py`.

---
