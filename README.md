# Plex/Radarr Watched Movie Cleanup Script

A Python script to automate the cleanup of watched movies from your Plex and Radarr instances. It identifies movies that have been watched long enough ago, deletes them from Radarr (including their files), and adds them to Radarr's exclusion list to prevent them from being re-imported.

This script is designed for users who wish to automatically free up storage space from older, watched content while maintaining a clean library and preventing unwanted re-downloads.

## Features
* **Plex Integration:** Connects to your Plex Media Server to identify movies marked as "watched."
* **Watched Time Threshold:** Only processes movies watched longer than a configurable number of days ago.
* **Radarr Integration:** Deletes the corresponding movie entry (and its files) from Radarr.
* **Exclusion List Management:** Adds deleted movies to Radarr's general exclusion list to prevent them from being re-added via an import list.
* **Safe Deletion:** Supports a confirmation prompt before performing any deletions.
* **Automation-Friendly:** A `--no-prompt` flag allows the script to be run in automated environments (e.g., cron jobs, scheduled tasks) without requiring user interaction.
* **Tag-Based Exclusion:** Movies in Radarr with specific tags (e.g., `"keep"`, `"donotdelete"`) are automatically skipped, providing a safe way to protect content from deletion.
* **Robust Matching:** Uses TMDb IDs to reliably match movies between Plex and Radarr, avoiding common issues with title mismatches.

## Prerequisites

Before running the script, you'll need to install the required Python libraries.

```
pip install plexapi requests
```

You also need to set up your environment variables with the necessary API keys and URLs.

## Configuration

This script uses environment variables for configuration. This is a best practice to avoid hardcoding sensitive information directly into the script.

Set the following environment variables on the machine where you will run the script:

| Environment Variable | Description | Example |
| :--- | :--- | :--- |
| `PLEX_URL` | The full URL to your Plex Media Server. | `https://plex.example.com` |
| `PLEX_TOKEN` | Your Plex authentication token. | `xxXXxxXXxxXX` |
| `RADARR_URL` | The full URL to your Radarr instance. | `https://radarr.example.com` |
| `RADARR_API_KEY` | Your Radarr API key. | `YYyyYYyyYY` |

**Finding your tokens/keys:**

* **Plex Token:** Refer to the official [Plex support documentation](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/) for instructions on how to find your token.
* **Radarr API Key:** In your Radarr web interface, go to `Settings` -> `General` to find your API key.

## Usage

You can run the script from your terminal with various options.

### Basic Listing

To simply list movies that meet the criteria without performing any deletions, run the script with no arguments.
```
python plex_radarr_cleanup.py
```

### Deletion with Confirmation

To enable the deletion process, use the `--process-radarr` flag. The script will list the movies and then prompt you for confirmation before deleting anything.
```
python plex_radarr_cleanup.py --process-radarr
```

### Fully Automated Deletion

For use in cron jobs or other automated tasks, add the `--no-prompt` flag. This will bypass the confirmation prompt and proceed directly with deletion.
```
python plex_radarr_cleanup.py --process-radarr --no-prompt
```

### Customizing the Watched Threshold

By default, the script looks for movies watched more than 3 days ago. You can change this using the `--days` flag.
```
# Process movies watched more than 14 days ago
python plex_radarr_cleanup.py --days 14 --process-radarr
```

## How Tag-Based Exclusion Works

The script is configured to look for movies in Radarr with the tags `"keep"` or `"donotdelete"`. You can define these tags in the script's code:
```
# In the script, near the top
EXCLUDE_TAG_NAMES = ["keep", "donotdelete"]
```
If a movie has one of these tags, it will be listed as a watched movie from Plex, but the script will explicitly skip the deletion and exclusion steps, ensuring your permanent collection remains untouched.
