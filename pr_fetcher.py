"""
Fetches Pull Request data, including comments, authors, and reviewers,
from a specified GitHub repository. It also attempts to identify Code Owners.
The fetched data is saved into CSV files in the 'data/' directory.
"""
import os
import csv
import pandas as pd
import argparse
from datetime import datetime
import time # For adding delays
import base64 # Needed for decoding file content

# Third-party imports
from dotenv import load_dotenv
import requests

load_dotenv()

def get_github_data(api_url, headers, accept_header=None):
    if accept_header:
        headers['Accept'] = accept_header
    response = requests.get(api_url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"GitHub API error {response.status_code}: {response.text}")
    # If requesting raw content, return text
    if headers.get('Accept', '').startswith('application/vnd.github.v3.raw'):
        return response.text
    # Otherwise, try to parse as JSON
    try:
        return response.json()
    except Exception:
        raise Exception(f"Failed to parse JSON from GitHub API: {response.text}")

def fetch_code_owners(owner, repo, headers):
    """Fetches and parses the .github/CODEOWNERS file."""
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/.github/CODEOWNERS"
    data = get_github_data(api_url, headers, accept_header="application/vnd.github.v3.raw") # Request raw content

    code_owner_usernames = set()
    # If data is a string, it's the raw file content
    if isinstance(data, str):
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
    # If data is a dict and has 'content', handle as before (base64-encoded)
    elif data and isinstance(data, dict) and data.get('content'):
        try:
            decoded_content = base64.b64decode(data['content']).decode('utf-8')
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
            print(f"Successfully fetched and parsed CODEOWNERS. Found: {code_owner_usernames}")
        except Exception as e:
            print(f"Error decoding or parsing CODEOWNERS content: {e}")
    elif data is None:
        print(f"Warning: Could not fetch .github/CODEOWNERS file. It might not exist or access is denied.")
    else:
        print(f"Warning: .github/CODEOWNERS content not found in response or response was unexpected: {data}")

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

    # Define Excel file path
    excel_file_path = os.path.join(data_dir, "intermediate_data.xlsx")

    with pd.ExcelWriter(excel_file_path, engine='openpyxl') as writer:
        # Write PRs to "PRList" sheet
        if prs:
            pr_df = pd.DataFrame(prs)
            pr_df.to_excel(writer, sheet_name='PRList', index=False)
            print(f"Successfully wrote {len(prs)} PRs to 'PRList' sheet in {excel_file_path}")
        else:
            pd.DataFrame(columns=['PR Number', 'PR Heading', 'PR Date', 'Author', 'Status']).to_excel(writer, sheet_name='PRList', index=False)
            print(f"No PRs fetched. 'PRList' sheet created with headers in {excel_file_path}")

        # Write Authors to "AuthorList" sheet
        if authors:
            # Convert set of tuples to list of dicts for DataFrame creation
            authors_list_of_dicts = [{'Author': login, 'Author Name': name} for login, name in sorted(list(authors))]
            authors_df = pd.DataFrame(authors_list_of_dicts)
            authors_df.to_excel(writer, sheet_name='AuthorList', index=False)
            print(f"Successfully wrote {len(authors_df)} authors to 'AuthorList' sheet.")
        else:
            pd.DataFrame(columns=['Author', 'Author Name']).to_excel(writer, sheet_name='AuthorList', index=False)
            print(f"No authors found. 'AuthorList' sheet created with headers.")

        # Write Reviewers to "ReviewerList" sheet
        if all_reviewers_set:
            reviewers_list_of_dicts = []
            for login, name in sorted(list(all_reviewers_set)):
                is_code_owner = "Yes" if login in code_owners else "No"
                reviewers_list_of_dicts.append({'Reviewer': login, 'Reviewer Name': name, 'IsCodeOwner': is_code_owner})
            reviewers_df = pd.DataFrame(reviewers_list_of_dicts)
            reviewers_df.to_excel(writer, sheet_name='ReviewerList', index=False)
            print(f"Successfully wrote {len(reviewers_df)} unique reviewers to 'ReviewerList' sheet.")
        else:
            pd.DataFrame(columns=['Reviewer', 'Reviewer Name', 'IsCodeOwner']).to_excel(writer, sheet_name='ReviewerList', index=False)
            print(f"No reviewers found. 'ReviewerList' sheet created with headers.")

        # Write Review Comments to "ReviewList" sheet
        if all_review_comments:
            reviews_df = pd.DataFrame(all_review_comments)
            # Ensure correct column order, matching old CSV if necessary, though for Excel it's less critical unless specified
            # Defaulting to DataFrame's column order or specify columns=['Review Comment', 'Reviewer', 'Reviewer Date', 'PR Number']
            reviews_df.to_excel(writer, sheet_name='ReviewList', index=False)
            print(f"Successfully wrote {len(all_review_comments)} review comments to 'ReviewList' sheet.")
        else:
            pd.DataFrame(columns=['Review Comment', 'Reviewer', 'Reviewer Date', 'PR Number']).to_excel(writer, sheet_name='ReviewList', index=False)
            print(f"No review comments fetched. 'ReviewList' sheet created with headers.")

    print(f"\nData fetching complete. Excel file is at '{os.path.abspath(excel_file_path)}'")


if __name__ == "__main__":
    main()
