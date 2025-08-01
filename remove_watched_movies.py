import os
import requests
import argparse
import json 
from datetime import datetime, timedelta
from plexapi.server import PlexServer
import urllib3
from urllib3.exceptions import InsecureRequestWarning

# Suppress the InsecureRequestWarning
urllib3.disable_warnings(InsecureRequestWarning)

RADARR_URL = os.environ.get("RADARR_URL")
RADARR_API_KEY = os.environ.get("RADARR_API_KEY")
PLEX_URL = os.environ.get("PLEX_URL")
PLEX_TOKEN = os.environ.get("PLEX_TOKEN")

# Define the tags that will exclude movies from deletion/processing
EXCLUDE_TAG_NAMES = ["keep", "donotdelete"]
# This will store the numerical IDs of these tags after fetching from Radarr
EXCLUDE_TAG_IDS = [] 

# --- Authentication Check Function ---
def check_radarr_api_auth():
    """
    Performs a basic authentication check against the Radarr API.
    Attempts to get system status.
    """
    if not RADARR_URL or not RADARR_API_KEY:
        print("Error: Radarr URL or API Key not found in environment variables. Cannot perform auth check.")
        return False

    headers = {"X-Api-Key": RADARR_API_KEY}
    test_url = f"{RADARR_URL}/api/v3/system/status"

    print(f"\n--- Performing Radarr API Authentication Check ({test_url})... ---")
    try:
        response = requests.get(test_url, headers=headers, verify=False, timeout=10)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        print("Radarr API authentication successful!")
        return True
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            print(f"Radarr API Authentication Failed: 401 Unauthorized. Please check your RADARR_API_KEY.")
        elif e.response.status_code == 403:
            print(f"Radarr API Authentication Failed: 403 Forbidden. Please check your API key permissions.")
        else:
            print(f"Radarr API Authentication Failed: HTTP Error {e.response.status_code}. Response: {e.response.text}")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"Radarr API Connection Error: Could not connect to {RADARR_URL}. Is Radarr running and URL correct? Error: {e}")
        return False
    except requests.exceptions.Timeout:
        print(f"Radarr API Connection Timeout: Request to {RADARR_URL} timed out.")
        return False
    except Exception as e:
        print(f"An unexpected error occurred during Radarr API authentication check: {e}")
        return False

# --- Helper Function for Tags ---
def get_radarr_tag_ids(tag_names):
    """
    Fetches the numerical IDs for a list of Radarr tag names.

    Args:
        tag_names (list): A list of tag names (strings) to look up.

    Returns:
        dict: A dictionary mapping tag names to their IDs, e.g., {'keep': 1, 'donotdelete': 5}.
              Returns an empty dict if tags cannot be fetched or found.
    """
    if not RADARR_URL or not RADARR_API_KEY:
        print("Error: Radarr URL or API Key not found. Cannot fetch tag IDs.")
        return {}

    headers = {"X-Api-Key": RADARR_API_KEY}
    url = f"{RADARR_URL}/api/v3/tag"
    tag_map = {}

    print(f"--- Fetching Radarr tag IDs... ---")
    try:
        response = requests.get(url, headers=headers, verify=False, timeout=10)
        response.raise_for_status()
        tags_data = response.json()

        for tag in tags_data:
            if tag.get("label") and tag.get("id"):
                if tag["label"].lower() in [name.lower() for name in tag_names]:
                    tag_map[tag["label"].lower()] = tag["id"]
        
        if tag_map:
            print(f"Found IDs for requested tags: {tag_map}")
        else:
            print(f"No IDs found for tags: {tag_names}. Ensure they exist in Radarr.")
            
        return tag_map

    except requests.exceptions.RequestException as e:
        print(f"Error fetching Radarr tags from {url}: {e}")
        return {}
    except Exception as e:
        print(f"An unexpected error occurred while fetching Radarr tags: {e}")
        return {}


# --- Plex Functions ---

def get_watched_movies_older_than(days_ago):
    """
    Connects to Plex and lists movies watched longer than the specified number of days ago.
    Returns a list of dictionaries, each containing 'title', 'tmdb_id', and 'year'.

    Args:
        days_ago (int): The number of days. Movies watched before this threshold will be listed.

    Returns:
        list: A list of dictionaries, e.g., [{'title': 'Movie Title', 'tmdb_id': '12345', 'year': 2023}].
    """
    if not PLEX_URL or not PLEX_TOKEN:
        print("Error: Plex URL or Token not found in environment variables.")
        return []

    try:
        plex = PlexServer(PLEX_URL, PLEX_TOKEN)
        
        # Make sure 'Films' is the EXACT name of your movie library section in Plex.
        movies = plex.library.section('Films').search(unwatched=False) 
        
        watched_movies_data = []
        threshold_date = datetime.now() - timedelta(days=days_ago)

        for movie in movies:
            if hasattr(movie, 'lastViewedAt') and movie.lastViewedAt and movie.lastViewedAt < threshold_date:
                plex_tmdb_id = None
                # Iterate through GUIDs to find the TMDb ID
                if hasattr(movie, 'guids') and movie.guids:
                    for guid in movie.guids:
                        if guid.id.startswith('tmdb://'):
                            plex_tmdb_id = guid.id.split('//')[1]
                            break
                
                # Get the year from Plex movie object
                plex_movie_year = movie.year if hasattr(movie, 'year') and movie.year else 0 # Default to 0 if not found

                if plex_tmdb_id and plex_movie_year > 0: # Ensure we have valid TMDb ID and Year
                    watched_movies_data.append({
                        'title': movie.title,
                        'tmdb_id': plex_tmdb_id,
                        'year': plex_movie_year
                    })
                else:
                    print(f"  Warning: Skipping '{movie.title}' from Plex (TMDb ID: {plex_tmdb_id}, Year: {plex_movie_year}). Missing valid TMDb ID or Year for Radarr matching/exclusion.")
        
        return watched_movies_data

    except Exception as e:
        print(f"An error occurred while connecting to Plex or retrieving movies: {e}")
        return []

# --- Radarr Functions ---

def get_radarr_movie_details_for_processing(plex_movie_data):
    """
    Searches Radarr for a movie by its TMDb ID and returns its Radarr ID, TMDb ID, title, and tags.
    
    Args:
        plex_movie_data (dict): A dictionary containing 'title', 'tmdb_id', and 'year' from Plex.

    Returns:
        tuple: (Radarr ID (int), TMDb ID (int), Radarr Title (str), Radarr Tags (list of int)) if found, otherwise (None, None, None, None).
    """
    plex_title = plex_movie_data['title']
    plex_tmdb_id = plex_movie_data['tmdb_id']

    if not RADARR_URL or not RADARR_API_KEY:
        print("Error: Radarr URL or API Key not found in environment variables.")
        return None, None, None, None
    if not plex_tmdb_id:
        print(f"  Error: Cannot search Radarr for '{plex_title}', TMDb ID is missing.")
        return None, None, None, None

    headers = {"X-Api-Key": RADARR_API_KEY}
    url = f"{RADARR_URL}/api/v3/movie" # Endpoint to get all movies
    
    try:
        response = requests.get(url, headers=headers, verify=False)
        response.raise_for_status()
        movies = response.json()

        for movie in movies:
            # Match primarily by TMDb ID
            if movie.get("tmdbId") and str(movie["tmdbId"]) == str(plex_tmdb_id):
                radarr_id = movie["id"]
                tmdb_id = movie["tmdbId"] # This is Radarr's TMDb ID, should match Plex's
                radarr_title = movie.get("title")
                radarr_tags = movie.get("tags", []) # Get the list of tag IDs
                
                print(f"  - Matched '{plex_title}' (Plex TMDb: {plex_tmdb_id}) with Radarr ID {radarr_id} ('{radarr_title}', Radarr TMDb: {tmdb_id}). Tags: {radarr_tags}")
                return radarr_id, tmdb_id, radarr_title, radarr_tags
        
        print(f"  - No matching movie found in Radarr for '{plex_title}' (Plex TMDb ID: {plex_tmdb_id})")
        return None, None, None, None

    except requests.exceptions.RequestException as e:
        print(f"Error communicating with Radarr API for '{plex_title}': {e}")
        return None, None, None, None
    except Exception as e:
        print(f"An unexpected error occurred while searching Radarr for '{plex_title}': {e}")
        return None, None, None, None

def delete_radarr_movie_and_files(radarr_movie_id):
    """
    Deletes a movie from Radarr by its Radarr ID, including its associated files.
    
    Args:
        radarr_movie_id (int): The ID of the movie in Radarr.

    Returns:
        bool: True if deletion was successful, False otherwise.
    """
    if not RADARR_URL or not RADARR_API_KEY:
        print("Error: Radarr URL or API Key not found in environment variables.")
        return False

    headers = {"X-Api-Key": RADARR_API_KEY}
    url = f"{RADARR_URL}/api/v3/movie/{radarr_movie_id}"
    params = {"deleteFiles": "true"} # Parameter to also delete files from disk
    
    try:
        print(f"  - Attempting to delete Radarr movie ID {radarr_movie_id} (and files)...")
        response = requests.delete(url, headers=headers, params=params, verify=False)
        response.raise_for_status()
        print(f"  - Successfully deleted Radarr movie ID {radarr_movie_id} and its files.")
        return True

    except requests.exceptions.RequestException as e:
        print(f"Error deleting Radarr movie ID {radarr_movie_id}: {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred while deleting Radarr movie ID {radarr_movie_id}: {e}")
        return False

def add_to_radarr_exclusion_list(tmdb_id, movie_title, movie_year):
    """
    Adds a movie to Radarr's general exclusion list using its TMDb ID, title, and year.
    This uses the POST /api/v3/exclusions endpoint.
    
    Args:
        tmdb_id (int): The TMDb ID of the movie.
        movie_title (str): The title of the movie.
        movie_year (int): The release year of the movie.

    Returns:
        bool: True if added to exclusion successfully, False otherwise.
    """
    if not RADARR_URL or not RADARR_API_KEY:
        print("Error: Radarr URL or API Key not found in environment variables.")
        return False
    if not tmdb_id or not movie_title or not movie_year or movie_year <= 0:
        print(f"  Error: Cannot add to exclusion list. Missing/invalid TMDb ID ({tmdb_id}), Title ('{movie_title}'), or Year ({movie_year}).")
        return False

    headers = {"X-Api-Key": RADARR_API_KEY, "Content-Type": "application/json"}
    url = f"{RADARR_URL}/api/v3/exclusions" 
    
    payload = {
        "tmdbId": int(tmdb_id),     
        "movieTitle": movie_title,  
        "movieYear": int(movie_year),
        "foreignId": str(tmdb_id), 
        "foreignIdType": "tmdbId"
    }

    try:
        print(f"  - Attempting to add '{movie_title}' (TMDb ID: {tmdb_id}, Year: {movie_year}) to Radarr exclusion list...")
        response = requests.post(url, headers=headers, data=json.dumps(payload), verify=False)
        response.raise_for_status() 
        print(f"  - Successfully added '{movie_title}' to Radarr exclusion list.")
        return True
    except requests.exceptions.HTTPError as e: 
        print(f"Error adding '{movie_title}' to Radarr exclusion list: {e}")
        if response.status_code == 400:
            print(f"  Radarr API responded with 400 Bad Request. Response body: {response.text}")
            try:
                error_details = response.json()
                if any(err.get("errorCode") == "ImportListExclusionExistsValidator" for err in error_details):
                    print(f"  Note: '{movie_title}' might already be in the exclusion list (via API response).")
                    return True 
            except json.JSONDecodeError:
                pass 
        return False 
    except requests.exceptions.RequestException as e:
        print(f"Error adding '{movie_title}' to Radarr exclusion list: {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred while adding '{movie_title}' to exclusion list: {e}")
        return False


# --- Main Script Logic ---

if __name__ == "__main__":
    # --- Perform Radarr API Authentication Check ---
    if not check_radarr_api_auth():
        print("\nExiting script due to Radarr API authentication failure.")
        exit(1) # Exit with an error code

    # --- Fetch Radarr Tag IDs for exclusion ---
    tag_ids_map = get_radarr_tag_ids(EXCLUDE_TAG_NAMES)
    for tag_name in EXCLUDE_TAG_NAMES:
        if tag_name.lower() not in tag_ids_map:
            print(f"Warning: Radarr tag '{tag_name}' not found. Movies with this tag will NOT be excluded from processing.")
    # Store the actual IDs we found globally for easy checking
    EXCLUDE_TAG_IDS = list(tag_ids_map.values())


    parser = argparse.ArgumentParser(
        description="Lists watched movies from Plex, then optionally deletes them from Radarr (including files) and adds them to the general exclusion list to prevent re-imports."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=3,
        help="Number of days ago a movie must have been watched to be considered (default: 3)."
    )
    parser.add_argument(
        "--process-radarr",
        action="store_true",
        help="Enable processing (delete from Radarr + add to exclusion) after listing. Requires confirmation unless --no-prompt is used. This removes the movie entry and its files."
    )
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Skip the confirmation prompt when processing movies (only effective with --process-radarr)."
    )

    args = parser.parse_args()

    days_threshold = args.days
    
    print(f"\nSearching for movies watched longer than {days_threshold} days ago in Plex...")
    
    plex_watched_movies_data = get_watched_movies_older_than(days_threshold) # Now returns list of dicts

    if not plex_watched_movies_data:
        print(f"No movies found that were watched longer than {days_threshold} days ago, or an error occurred with Plex.")
    else:
        print(f"\n--- Movies Watched Longer Than {days_threshold} Days Ago ---")
        for movie_data in plex_watched_movies_data:
            print(f"- {movie_data['title']} (TMDb ID: {movie_data['tmdb_id']}, Year: {movie_data['year']})")
        print("--------------------------------------------------")

        if args.process_radarr:
            print(f"\n--- Preparing for Radarr Processing ---")
            # Store {Plex Title: (Radarr ID, TMDb ID, Radarr Title, Movie Year from Plex, Radarr Tags)}
            movies_to_process_radarr = {} 

            print("Matching Plex watched movies with Radarr entries by TMDb ID:")
            for plex_movie_data in plex_watched_movies_data:
                radarr_id, tmdb_id, radarr_title, radarr_tags = get_radarr_movie_details_for_processing(plex_movie_data)
                
                if radarr_id: 
                    # Use Radarr's title if found, otherwise fall back to Plex's. 
                    # Pass the year from plex_movie_data
                    movies_to_process_radarr[plex_movie_data['title']] = (radarr_id, tmdb_id, radarr_title or plex_movie_data['title'], plex_movie_data['year'], radarr_tags)
            
            if not movies_to_process_radarr:
                print("No matching movies found in Radarr for processing.")
            else:
                print(f"\nFound {len(movies_to_process_radarr)} matching movies in Radarr for processing:")
                for title, (radarr_id, tmdb_id, radarr_title_for_exclusion, movie_year_for_exclusion, radarr_tags) in movies_to_process_radarr.items():
                    tag_labels = [name for name, _id in tag_ids_map.items() if _id in radarr_tags]
                    print(f"- '{title}' (Radarr ID: {radarr_id}, TMDb ID: {tmdb_id if tmdb_id else 'N/A'}, Year: {movie_year_for_exclusion}, Tags: {tag_labels if tag_labels else 'None'})")

                if not args.no_prompt:
                    confirmation = input("\nAre you sure you want to delete these movies from Radarr (including files) and add them to the general exclusion list? This will remove them from Radarr's database. (type 'yes' to confirm): ").strip().lower()
                    if confirmation != 'yes':
                        print("Processing cancelled by user.")
                        exit()
                else:
                    print("\n--no-prompt flag detected. Proceeding with processing without confirmation.")

                print("\n--- Processing Movies in Radarr ---")
                for title, (radarr_id, tmdb_id, radarr_title_for_exclusion, movie_year_for_exclusion, radarr_tags) in movies_to_process_radarr.items():
                    # Check for exclusion tags
                    should_skip_due_to_tag = False
                    for exclude_tag_id in EXCLUDE_TAG_IDS:
                        if exclude_tag_id in radarr_tags:
                            tag_label = next((name for name, _id in tag_ids_map.items() if _id == exclude_tag_id), str(exclude_tag_id))
                            print(f"  Skipping '{title}' (Radarr ID: {radarr_id}) because it has the tag '{tag_label}'.")
                            should_skip_due_to_tag = True
                            break
                    
                    if should_skip_due_to_tag:
                        continue # Skip to the next movie in the loop

                    print(f"Processing '{title}' (Radarr ID: {radarr_id})...")
                    
                    delete_success = delete_radarr_movie_and_files(radarr_id)
                    exclusion_success = False

                    # Only add to exclusion if deletion was attempted and we have valid TMDb ID and Year
                    if delete_success and tmdb_id and movie_year_for_exclusion and movie_year_for_exclusion > 0: 
                        exclusion_success = add_to_radarr_exclusion_list(tmdb_id, radarr_title_for_exclusion, movie_year_for_exclusion)
                    elif not tmdb_id:
                        print(f"  Skipping exclusion for '{title}' as TMDb ID is missing.")
                    elif not movie_year_for_exclusion or movie_year_for_exclusion <= 0:
                        print(f"  Skipping exclusion for '{title}' as Movie Year is missing or invalid.")

                    if delete_success and (exclusion_success or not tmdb_id or not movie_year_for_exclusion or movie_year_for_exclusion <= 0):
                        print(f"  Successfully processed '{title}'.")
                    else:
                        print(f"  Finished processing '{title}' with some issues (Deleted: {delete_success}, Excluded from list: {exclusion_success}).")
                print("-----------------------------------")
        else:
            print("\nRadarr processing is disabled. Use --process-radarr flag to enable.")
