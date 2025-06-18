"""
Fetches Pull Request data, including comments, authors, and reviewers,
from a specified GitHub repository. It also attempts to identify Code Owners.
The fetched data is saved into CSV files in the 'data/' directory.
"""
import os
import csv
import argparse
from datetime import datetime
import time # For adding delays
import base64 # Needed for decoding file content

# Third-party imports
from dotenv import load_dotenv
import requests

load_dotenv()

def get_github_data(api_url, headers, accept_header=None):
    """Helper function to make GitHub API calls."""
    if accept_header:
        headers['Accept'] = accept_header
    response = requests.get(api_url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error fetching {api_url}: {response.status_code} - {response.text}")
        return None

def fetch_code_owners(owner, repo, headers):
    """Fetches and parses the .github/CODEOWNERS file."""
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/.github/CODEOWNERS"
    data = get_github_data(api_url, headers, accept_header="application/vnd.github.v3.raw") # Request raw content

    code_owner_usernames = set()
    if data and data.get('content'):
        try:
            decoded_content = base64.b64decode(data['content']).decode('utf-8')
            for line in decoded_content.splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                # Basic parsing: look for @username patterns
                parts = line.split()
                for part in parts:
                    if part.startswith('@'):
                        username = part[1:]
                        # Handle potential /team-name in @org/team-name
                        if '/' in username:
                            username = username.split('/')[-1]
                        code_owner_usernames.add(username)
            print(f"Successfully fetched and parsed CODEOWNERS. Found: {code_owner_usernames}")
        except Exception as e:
            print(f"Error decoding or parsing CODEOWNERS content: {e}")
            # Try to get content directly if raw failed or if it's not base64 encoded (should not happen for /contents api)
            # For this, we'd need to re-fetch without the specific accept header or handle non-JSON response if 'data' is string
            if isinstance(data, str): # If raw endpoint returned plain text
                decoded_content = data
                for line in decoded_content.splitlines():
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split()
                    for part in parts:
                        if part.startswith('@'):
                            username = part[1:]
                            if '/' in username:
                                username = username.split('/')[-1]
                            code_owner_usernames.add(username)
                print(f"Successfully parsed CODEOWNERS (direct text). Found: {code_owner_usernames}")

    elif data is None: # get_github_data returned None due to HTTP error
        print(f"Warning: Could not fetch .github/CODEOWNERS file. It might not exist or access is denied.")
    else: # No 'content' field, or other unexpected response
        print(f"Warning: .github/CODEOWNERS content not found in response or response was unexpected: {data}")
        # Attempt to fetch with raw content type if previous attempt was not specific enough
        # This part is a bit redundant if the initial call to get_github_data already used the raw accept header
        # and would only be useful if the content was directly in the response body as a string.
        api_url_raw = f"https://raw.githubusercontent.com/{owner}/{repo}/master/.github/CODEOWNERS" # Or main branch
        # This requires a different handling as it gives raw text, not JSON
        response_raw = requests.get(api_url_raw, headers=headers)
        if response_raw.status_code == 200:
            decoded_content = response_raw.text
            for line in decoded_content.splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split()
                for part in parts:
                    if part.startswith('@'):
                        username = part[1:]
                        if '/' in username:
                            username = username.split('/')[-1]
                        code_owner_usernames.add(username)
            print(f"Successfully fetched and parsed CODEOWNERS from raw URL. Found: {code_owner_usernames}")
        else:
            print(f"Warning: Could not fetch .github/CODEOWNERS from raw URL either. Status: {response_raw.status_code}")


    return code_owner_usernames


def fetch_pull_requests(owner, repo, headers):
    """Fetches pull requests and extracts relevant data."""
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls?state=all&per_page=100" # Get all PRs, 100 per page
    # Add pagination logic here if more than 100 PRs are expected
    data = get_github_data(api_url, headers)

    pr_data_list = []
    authors_set = set()
    reviewers_set = set() # Stores (login, name) tuples

    if data:
        for pr in data:
            pr_number = pr['number']
            pr_title = pr['title']
            # Ensure datetime objects are handled correctly, convert to string if necessary
            pr_date_str = pr['created_at']
            try:
                # Attempt to parse and reformat if needed, or just use as is
                dt_obj = datetime.fromisoformat(pr_date_str.replace('Z', '+00:00'))
                pr_date = dt_obj.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                pr_date = pr_date_str # Keep original if parsing fails

            author_login = pr['user']['login']
            # Attempt to get a display name, fall back to login
            # For a more robust solution, one might query the user profile endpoint: /users/{username}
            author_name = pr.get('user', {}).get('name', author_login) # This might be None
            if not author_name: # if 'name' field is missing or empty
                 # We could call get_github_data(f"https://api.github.com/users/{author_login}", headers)
                 # to get more user details, but for now, stick to login for simplicity
                 author_name = author_login


            status = pr['state']

            pr_data_list.append({
                'PR Number': pr_number,
                'PR Heading': pr_title,
                'PR Date': pr_date,
                'Author': author_login,
                'Status': status
            })
            authors_set.add((author_login, author_name if author_name else author_login))

            if pr.get('requested_reviewers'):
                for reviewer in pr['requested_reviewers']:
                    reviewer_login = reviewer['login']
                    # Similar to author, attempt to get name, fallback to login
                    reviewer_name = reviewer.get('name', reviewer_login) # This might be None
                    if not reviewer_name:
                        reviewer_name = reviewer_login
                    reviewers_set.add((reviewer_login, reviewer_name if reviewer_name else reviewer_login))
        print(f"Fetched {len(pr_data_list)} PRs.")
    else:
        print("No PR data received or error in fetching PRs.")
    return pr_data_list, authors_set, reviewers_set


def fetch_reviews_for_pr(owner, repo, pr_number, headers):
    """Fetches review comments for a specific pull request."""
    # Using /pulls/{pr_number}/comments endpoint for review comments on the diff
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments?per_page=100"
    # Consider pagination if a PR can have more than 100 review comments.
    data = get_github_data(api_url, headers)

    review_comments_data = []
    new_reviewers_set = set()

    if data:
        for comment in data:
            comment_body = comment['body']
            reviewer_login = comment['user']['login']
            # Attempt to get a display name, fall back to login
            reviewer_name = comment.get('user', {}).get('name', reviewer_login)
            if not reviewer_name: # if 'name' field is missing or empty
                reviewer_name = reviewer_login

            review_date_str = comment['created_at']
            try:
                dt_obj = datetime.fromisoformat(review_date_str.replace('Z', '+00:00'))
                review_date = dt_obj.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                review_date = review_date_str # Keep original if parsing fails

            pr_num = pr_number

            review_comments_data.append({
                'Review Comment': comment_body,
                'Reviewer': reviewer_login,
                'Reviewer Date': review_date,
                'PR Number': pr_num
            })
            new_reviewers_set.add((reviewer_login, reviewer_name))
        print(f"Fetched {len(review_comments_data)} review comments for PR #{pr_number}.")
    elif data == []: # Explicitly check for empty list vs None (error)
        print(f"No review comments found for PR #{pr_number}.")
    else: # Error occurred
        print(f"Could not fetch review comments for PR #{pr_number}.")

    return review_comments_data, new_reviewers_set


def main():
    parser = argparse.ArgumentParser(description="Fetch GitHub Pull Request data.")
    parser.add_argument("--owner", help="GitHub repository owner.")
    parser.add_argument("--repo", help="GitHub repository name.")
    args = parser.parse_args()

    github_token = os.getenv("GITHUB_TOKEN")
    repo_owner = args.owner if args.owner else os.getenv("REPO_OWNER")
    repo_name = args.repo if args.repo else os.getenv("REPO_NAME")

    if not github_token:
        print("Error: GITHUB_TOKEN not found in environment variables.")
        exit(1)
    if not repo_owner:
        print("Error: REPO_OWNER not found in environment variables or as command-line argument.")
        exit(1)
    if not repo_name:
        print("Error: REPO_NAME not found in environment variables or as command-line argument.")
        exit(1)

    headers = {"Authorization": f"token {github_token}", "Accept": "application/vnd.github.v3+json"}

    # Create data directory if it doesn't exist
    data_dir = "data"
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        print(f"Created directory: {data_dir}")

    # Fetch CODEOWNERS
    print(f"Fetching CODEOWNERS for {repo_owner}/{repo_name}...")
    code_owners = fetch_code_owners(repo_owner, repo_name, headers.copy()) # Pass a copy of headers
    if code_owners:
        print(f"Found {len(code_owners)} code owner(s): {', '.join(sorted(list(code_owners)))}")
    else:
        print("No code owners found or CODEOWNERS file does not exist.")

    # Fetch Pull Requests, Authors, and requested Reviewers from PRs
    print(f"Fetching pull requests for {repo_owner}/{repo_name}...")
    prs, authors, requested_reviewers_set = fetch_pull_requests(repo_owner, repo_name, headers.copy()) # Pass a copy

    all_review_comments = []
    all_reviewers_set = requested_reviewers_set.copy()

    # Iterate through PRs to fetch their review comments
    # For testing, you might want to process only a slice, e.g., prs[:5]
    print(f"\nFetching review comments for {len(prs)} PR(s)...")
    for pr_info in prs: # Consider prs[:5] for initial testing to avoid rate limits
        pr_number = pr_info['PR Number']
        print(f"Fetching review comments for PR #{pr_number}...")
        # Pass a copy of headers to avoid modification issues if any
        review_comments, new_reviewers = fetch_reviews_for_pr(repo_owner, repo_name, pr_number, headers.copy())
        all_review_comments.extend(review_comments)
        all_reviewers_set.update(new_reviewers)
        # Optional: Be polite to the API
        time.sleep(0.5) # 0.5 second delay

    # Write pr-list.csv
    pr_list_path = os.path.join(data_dir, "pr-list.csv")
    if prs:
        with open(pr_list_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['PR Number', 'PR Heading', 'PR Date', 'Author', 'Status']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(prs)
        print(f"Successfully wrote {len(prs)} PRs to {pr_list_path}")
    else:
        print(f"No PRs fetched for {repo_owner}/{repo_name}. {pr_list_path} will be empty or only have headers.")
        # Create empty file with headers if no PRs
        with open(pr_list_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['PR Number', 'PR Heading', 'PR Date', 'Author', 'Status']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()


    # Write author-list.csv
    author_list_path = os.path.join(data_dir, "author-list.csv")
    with open(author_list_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Author', 'Author Name']) # Write headers
        if authors:
            writer.writerows(sorted(list(authors)))
            print(f"Successfully wrote {len(authors)} authors to {author_list_path}")
        else:
            print(f"No authors found. {author_list_path} will only have headers.")


    # Write reviewer-list.csv (now using all_reviewers_set)
    reviewer_list_path = os.path.join(data_dir, "reviewer-list.csv")
    with open(reviewer_list_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Reviewer', 'Reviewer Name', 'IsCodeOwner']) # Write headers
        if all_reviewers_set:
            processed_reviewers_count = 0
            for login, name in sorted(list(all_reviewers_set)):
                is_code_owner = "Yes" if login in code_owners else "No"
                writer.writerow([login, name, is_code_owner])
                processed_reviewers_count += 1
            print(f"Successfully wrote {processed_reviewers_count} unique reviewers to {reviewer_list_path}")
        else:
            print(f"No reviewers found. {reviewer_list_path} will only have headers.")


    # Write reviews-list.csv
    reviews_list_path = os.path.join(data_dir, "reviews-list.csv")
    if all_review_comments:
        with open(reviews_list_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['Review Comment', 'Reviewer', 'Reviewer Date', 'PR Number']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_review_comments)
        print(f"Successfully wrote {len(all_review_comments)} review comments to {reviews_list_path}")
    else:
        print(f"No review comments fetched. {reviews_list_path} will be empty or only have headers.")
        # Create empty file with headers if no review comments
        with open(reviews_list_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['Review Comment', 'Reviewer', 'Reviewer Date', 'PR Number']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

    print(f"\nData fetching complete. CSV files are in '{os.path.abspath(data_dir)}'")


if __name__ == "__main__":
    main()
