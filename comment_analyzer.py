"""
Analyzes GitHub PR review comments using the Hugging Face Inference API
for zero-shot text classification to determine category and severity.
Generates developer guidelines based on these classifications.
Caches results to avoid redundant API calls and saves analysis to a CSV file.
"""
import os
import csv
import time
import json # For JSON file-based caching
import pandas as pd # Added for Excel I/O

# Third-party imports
import requests
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()
HF_TOKEN = os.getenv("HF_TOKEN")
# Using facebook/bart-large-mnli as it's a commonly used zero-shot model
API_URL_ZERO_SHOT = "https://api-inference.huggingface.co/models/facebook/bart-large-mnli"
# Fallback model if needed: "https://api-inference.huggingface.co/models/valhalla/distilbart-mnli-12-3"

# Cache Handling Globals/Constants
CACHE_FILE = "data/ai_analysis_cache.json"

# Global Definitions
CATEGORIES = [
    "Logic Error", "Code Style/Formatting", "Naming Convention", "Security Vulnerability",
    "Missing Test Coverage", "Documentation (Code Comments / Docstrings)", "Performance Issue",
    "Readability/Clarity", "Error Handling", "Configuration Issue", "Best Practice Violation", "Other"
]

SEVERITIES = ["High", "Medium", "Low"]

GUIDELINE_TEMPLATES = {
    ("Logic Error", "High"): "Critical logic error found. Prioritize fixing this issue immediately to prevent system failure or incorrect behavior. Thoroughly test the fix.",
    ("Logic Error", "Medium"): "A medium severity logic error has been identified. Address this after critical issues. Ensure test cases cover this scenario.",
    ("Security Vulnerability", "High"): "High-priority security vulnerability detected. This must be fixed urgently to protect user data and system integrity. Consult security best practices.",
    ("Code Style/Formatting", "Low"): "Minor code style/formatting issue. Please correct to maintain code consistency as per project guidelines.",
    ("Missing Test Coverage", "Medium"): "Important test coverage is missing for this section of code. Please add relevant unit/integration tests.",
    ("Documentation (Code Comments / Docstrings)", "Low"): "Documentation can be improved. Add or clarify code comments/docstrings for better maintainability.",
    ("Performance Issue", "High"): "Significant performance issue identified. This could impact system responsiveness or resource usage. Investigate and optimize.",
    ("Readability/Clarity", "Medium"): "The code's readability or clarity can be improved. Consider refactoring for better understanding.",
    ("Error Handling", "Medium"): "Error handling for this case is missing or insufficient. Implement robust error handling to prevent unexpected crashes or behavior."
}
DEFAULT_GUIDELINE = "Review the comment and address the issue based on project standards and best practices."

MAX_RETRIES = 3 # Maximum number of retries for API calls


def load_cache(cache_file_path):
    """Loads analysis cache from a JSON file."""
    if os.path.exists(cache_file_path):
        try:
            with open(cache_file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            print(f"Warning: Error loading cache file {cache_file_path}: {e}. Starting with an empty cache.")
            return {}
    return {}

def save_cache(cache_data, cache_file_path):
    """Saves analysis cache to a JSON file."""
    try:
        # Ensure the data directory exists
        os.makedirs(os.path.dirname(cache_file_path), exist_ok=True)
        with open(cache_file_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=4)
        print(f"Cache saved to {cache_file_path}")
    except IOError as e:
        print(f"Error: Could not save cache to {cache_file_path}: {e}")


def query_hf_zeroshot(comment_text, candidate_labels, hf_token, retries=MAX_RETRIES):
    """
    Queries the Hugging Face zero-shot classification API.
    Includes retry logic for model loading (503 errors).
    """
    headers = {"Authorization": f"Bearer {hf_token}"}
    # Ensure multi_label is False if we want a single category/severity.
    # If the model or task benefits from it, this could be True, and then logic to pick the "best" label is needed.
    payload = {
        "inputs": comment_text,
        "parameters": {"candidate_labels": candidate_labels, "multi_label": False},
    }

    for attempt in range(retries):
        try:
            response = requests.post(API_URL_ZERO_SHOT, headers=headers, json=payload)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 503: # Model loading
                # The response might contain an 'estimated_time' field
                error_json = response.json()
                estimated_time = error_json.get("estimated_time", 20) # Default to 20s if not provided
                if not isinstance(estimated_time, (int, float)) or estimated_time < 0:
                    estimated_time = 20 # Fallback for unexpected value
                if estimated_time > 60 : estimated_time = 60 # Cap wait time to 1 minute

                print(f"Model is loading, retrying in {estimated_time:.2f} seconds... (Attempt {attempt + 1}/{retries})")
                time.sleep(estimated_time)
            elif response.status_code == 429: # Rate limit
                print(f"Rate limit hit. Retrying in 60 seconds... (Attempt {attempt + 1}/{retries})")
                time.sleep(60)
            else:
                print(f"Error querying Hugging Face API: {response.status_code} - {response.text}")
                return None # Non-retryable error for this attempt
        except requests.exceptions.RequestException as e:
            print(f"RequestException during Hugging Face API call: {e} (Attempt {attempt + 1}/{retries})")
            if attempt < retries - 1:
                time.sleep(5) # Wait a bit before retrying on network errors
            else:
                return None # All retries failed
        except Exception as e: # Catch any other unexpected errors
            print(f"An unexpected error occurred: {e} (Attempt {attempt + 1}/{retries})")
            return None

    print(f"Failed to get a successful response from Hugging Face API after {retries} retries.")
    return None

def analyze_comment(comment_text, hf_token, cache):
    """
    Analyzes a single comment to predict its category and severity, and generate a guideline.
    Uses a cache to avoid re-analyzing already processed comments.
    """
    if not comment_text or not isinstance(comment_text, str) or not comment_text.strip():
        print("Warning: Empty or invalid comment text provided. Skipping analysis.")
        return "Other", "Low", DEFAULT_GUIDELINE

    # Cache Check
    if comment_text in cache:
        cached_result = cache[comment_text]
        print(f"Cache hit for comment: '{comment_text[:100].replace('\n', ' ')}...'")
        # Ensure consistent return type with non-cached path (including api_called flag)
        return cached_result['category'], cached_result['severity'], cached_result['guideline'], False

    print(f"Cache miss. Calling API for comment: '{comment_text[:100].replace('\n', ' ')}...'")

    predicted_category = "Other" # Default
    predicted_severity = "Low"   # Default
    api_called = False

    # Get Category
    # print("Querying for category...") # Reduced verbosity for API calls
    category_response = query_hf_zeroshot(comment_text, CATEGORIES, hf_token)
    api_called = True # Assume API is called for category
    if category_response and isinstance(category_response, dict) and \
       category_response.get('labels') and category_response.get('scores'):
        predicted_category = category_response['labels'][0]
        # print(f"Predicted category: {predicted_category} (Score: {category_response['scores'][0]:.2f})")
    else:
        print(f"Could not determine category for comment, defaulting to '{predicted_category}'.")
        if category_response: print(f"HF Response (Category): {str(category_response)[:200]}")

    # Get Severity
    # print("Querying for severity...") # Reduced verbosity
    severity_response = query_hf_zeroshot(comment_text, SEVERITIES, hf_token)
    api_called = True # Assume API is called for severity
    if severity_response and isinstance(severity_response, dict) and \
       severity_response.get('labels') and severity_response.get('scores'):
        predicted_severity = severity_response['labels'][0]
        # print(f"Predicted severity: {predicted_severity} (Score: {severity_response['scores'][0]:.2f})")
    else:
        print(f"Could not determine severity for comment, defaulting to '{predicted_severity}'.")
        if severity_response: print(f"HF Response (Severity): {str(severity_response)[:200]}")

    # Get Guideline
    guideline = GUIDELINE_TEMPLATES.get((predicted_category, predicted_severity), DEFAULT_GUIDELINE)
    if guideline == DEFAULT_GUIDELINE:
        guideline = GUIDELINE_TEMPLATES.get((predicted_category, "Medium"),
                    GUIDELINE_TEMPLATES.get((predicted_category, "Low"), DEFAULT_GUIDELINE))

    # Store in Cache
    cache[comment_text] = {'category': predicted_category, 'severity': predicted_severity, 'guideline': guideline}

    # Return api_called status along with results to manage sleep in main
    return predicted_category, predicted_severity, guideline, api_called


def main():
    if not HF_TOKEN:
        print("Error: Hugging Face API token (HF_TOKEN) not found in environment variables.")
        print("Please ensure it's set in your .env file or environment.")
        exit(1)

    input_excel_path = "data/intermediate_data.xlsx" # Changed from CSV to XLSX
    output_excel_path = "data/intermediate_data.xlsx" # Output to the same Excel file
    input_sheet_name = "ReviewList"
    output_sheet_name = "ReviewAnalysis"

    # Load Cache
    ai_cache = load_cache(CACHE_FILE)
    print(f"Loaded {len(ai_cache)} items from cache file {CACHE_FILE}")

    print(f"Attempting to read comments from sheet '{input_sheet_name}' in: {input_excel_path}")

    analyzed_results = []
    comments_df = None

    try:
        # Read the specific sheet from the Excel file
        comments_df = pd.read_excel(input_excel_path, sheet_name=input_sheet_name)
        required_columns = ['Review Comment', 'PR Number']
        if not all(col in comments_df.columns for col in required_columns):
            print(f"Error: Excel sheet '{input_sheet_name}' in {input_excel_path} must contain {required_columns} columns.")
            save_cache(ai_cache, CACHE_FILE)
            return

        # Convert DataFrame to list of dictionaries for existing processing logic
        # Note: It might be more efficient to process directly from DataFrame rows if performance is critical
        rows_for_processing = comments_df.to_dict('records')
        print(f"Found {len(rows_for_processing)} total comments to process from '{input_sheet_name}'.")

        for i, row in enumerate(rows_for_processing):
            comment_text = str(row.get("Review Comment", "")).strip() # Ensure string type
            pr_number = str(row.get("PR Number", "N/A")).strip() # Ensure string type

            if not comment_text:
                print(f"Skipping empty comment in row {i+1} (PR: {pr_number}).")
                continue

            category, severity, guideline, api_called = analyze_comment(comment_text, HF_TOKEN, ai_cache)

            analyzed_results.append({
                'PR Number': pr_number,
                'Review Comment': comment_text,
                'Category': category,
                'Severity': severity,
                'Developer Guideline': guideline
            })

            if api_called:
                time.sleep(1) # Simple delay per comment analysis if API was hit

    except FileNotFoundError:
        print(f"Error: The Excel file {input_excel_path} was not found.")
        save_cache(ai_cache, CACHE_FILE)
        return
    except (KeyError, ValueError) as e: # Catches errors if sheet_name is not found or other pandas read errors
        print(f"Error reading sheet '{input_sheet_name}' from {input_excel_path}: {e}. Ensure the sheet exists and is correctly named.")
        save_cache(ai_cache, CACHE_FILE)
        return
    except Exception as e: # General exception for other unforeseen errors during read/process
        print(f"An unexpected error occurred while reading or processing data: {e}")
        save_cache(ai_cache, CACHE_FILE)
        return

    # Write to Excel
    if analyzed_results:
        print(f"\nWriting {len(analyzed_results)} analyzed comments to sheet '{output_sheet_name}' in {output_excel_path}...")
        try:
            # Convert results to DataFrame
            results_df = pd.DataFrame(analyzed_results)

            # Ensure data directory exists
            os.makedirs(os.path.dirname(output_excel_path), exist_ok=True)

            # Use ExcelWriter to append to the existing file and replace sheet if it exists
            with pd.ExcelWriter(output_excel_path, mode='a', engine='openpyxl', if_sheet_exists='replace') as writer:
                results_df.to_excel(writer, sheet_name=output_sheet_name, index=False)

            print(f"Analysis complete. Results saved to sheet '{output_sheet_name}' in {output_excel_path}")
        except FileNotFoundError: # ExcelWriter in append mode might expect the file to exist.
             # Let's try creating it if it doesn't exist, or handle this case more gracefully.
             # For now, assuming pr_fetcher.py creates it. If not, this would be an issue.
             # A robust solution might involve checking existence and using mode='w' if not found,
             # but that would overwrite other sheets if called first.
             # The task implies pr_fetcher.py already created intermediate_data.xlsx.
            print(f"Error: The output Excel file {output_excel_path} was not found. Ensure it's created by a prior step.")
        except Exception as e: # Broader exception for other Excel writing errors
            print(f"Error: Could not write results to {output_excel_path} (sheet: '{output_sheet_name}'): {e}")
    else:
        print("No comments were analyzed or no results to write.")

    # Save Cache
    save_cache(ai_cache, CACHE_FILE)

if __name__ == "__main__":
    main()
