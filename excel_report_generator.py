import pandas as pd
import os

# Constants for data directory and Excel file name
DATA_DIR = "data/" # Retained as intermediate_data.xlsx is expected here
INTERMEDIATE_EXCEL_FILE = "intermediate_data.xlsx"
EXCEL_FILE_PATH = os.path.join(DATA_DIR, INTERMEDIATE_EXCEL_FILE)

# Sheet names mapping
SHEET_NAMES = {
    "pr_list": "PRList",
    "reviewer_list": "ReviewerList",
    "author_list": "AuthorList",
    "reviews_list": "ReviewList",
    "reviews_analysis": "ReviewAnalysis"
}

def load_sheet_from_excel(excel_path, sheet_name):
    """
    Loads a specific sheet from an Excel file into a pandas DataFrame.

    Args:
        excel_path (str): The path to the Excel file.
        sheet_name (str): The name of the sheet to load.

    Returns:
        pd.DataFrame: The loaded DataFrame, or None if an error occurs.
    """
    try:
        df = pd.read_excel(excel_path, sheet_name=sheet_name)
        print(f"Successfully loaded sheet '{sheet_name}' from {excel_path}")
        return df
    except FileNotFoundError:
        print(f"Error: Excel file not found at {excel_path}")
        return None
    except ValueError as e: # pd.read_excel can raise ValueError if sheet_name doesn't exist
        print(f"Error: Sheet '{sheet_name}' not found in {excel_path}. Details: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while loading sheet '{sheet_name}' from {excel_path}: {e}")
        return None

if __name__ == "__main__":
    pr_list_df = load_sheet_from_excel(EXCEL_FILE_PATH, SHEET_NAMES["pr_list"])
    reviewer_list_df = load_sheet_from_excel(EXCEL_FILE_PATH, SHEET_NAMES["reviewer_list"])
    author_list_df = load_sheet_from_excel(EXCEL_FILE_PATH, SHEET_NAMES["author_list"])
    reviews_list_df = load_sheet_from_excel(EXCEL_FILE_PATH, SHEET_NAMES["reviews_list"])
    reviews_analysis_df = load_sheet_from_excel(EXCEL_FILE_PATH, SHEET_NAMES["reviews_analysis"])

    # Initialize DataFrames for summaries to handle cases where loading fails
    df_author_summary = pd.DataFrame()
    df_category_distribution = pd.DataFrame({'Status': ["Data not loaded or processed"]})
    df_severity_distribution = pd.DataFrame({'Status': ["Data not loaded or processed"]})
    df_total_reviews_per_reviewer = pd.DataFrame({'Status': ["Data not loaded or processed"]})
    df_reviews_by_pr_and_reviewer = pd.DataFrame({'Status': ["Data not loaded or processed"]})
    df_code_owner_category_summary = pd.DataFrame({'Status': ["Data not loaded or processed"]})
    df_code_owner_severity_summary = pd.DataFrame({'Status': ["Data not loaded or processed"]})


    # --- Author Summary Calculation ---
    # Check if all required DataFrames for this section were loaded successfully
    if pr_list_df is not None and reviews_list_df is not None and author_list_df is not None:
        # Calculate total PRs per author
        author_total_prs = pr_list_df.groupby('Author')['PR Number'].count().rename('Total PRs')

        # Calculate open PRs per author
        author_open_prs = pr_list_df[pr_list_df['Status'] == 'open'].groupby('Author')['PR Number'].count().rename('Open PRs')

        # Calculate closed PRs per author
        author_closed_prs = pr_list_df[pr_list_df['Status'] == 'closed'].groupby('Author')['PR Number'].count().rename('Closed PRs')

        # Calculate review comments received
        # Merge PR list with reviews list to link comments to PR authors
        # Ensure the column name in reviews_list_df for comments is 'Review Comment'
        # and for PR identifier is 'PR Number'
        pr_reviews_merged_df = pd.merge(pr_list_df[['PR Number', 'Author']], reviews_list_df, on='PR Number', how='left')
        # Count comments per author, assuming the comment column in reviews_list_df is 'Review Comment'
        author_comments_received = pr_reviews_merged_df.groupby('Author')['Review Comment'].count().rename('Review Comments Received')

        # Combine all author statistics
        df_author_summary = pd.concat([author_total_prs, author_open_prs, author_closed_prs, author_comments_received], axis=1)

        # Merge with author_list_df to include author names (if available and needed)
        if author_list_df is not None:
            # Assuming author_list_df has 'Author_ID' and 'Author_Name'
            # And pr_list_df 'Author' column corresponds to 'Author_ID'
            # If 'Author' in pr_list_df is already the name, this merge might need adjustment or be skipped.
            # For this example, let's assume pr_list_df 'Author' is an ID that matches 'Author_ID' in author_list_df
            if 'Author_ID' in author_list_df.columns and 'Author_Name' in author_list_df.columns:
                 df_author_summary = pd.merge(df_author_summary, author_list_df[['Author_ID', 'Author_Name']], left_index=True, right_on='Author_ID', how='left')
                 # If Author_ID was the index, it might be duplicated as a column, so set Author_Name as index or re-index
                 # For simplicity, if Author_Name is present, we'll keep it as a column.
            elif 'Author' in author_list_df.columns and 'Name' in author_list_df.columns: # Alternative common naming
                 df_author_summary = pd.merge(df_author_summary, author_list_df[['Author', 'Name']], left_index=True, right_on='Author', how='left')


        # Fill NaN values with 0 (e.g., an author might have PRs but no comments)
        df_author_summary = df_author_summary.fillna(0)

        # Convert counts to integers
        count_columns = ['Total PRs', 'Open PRs', 'Closed PRs', 'Review Comments Received']
        for col in count_columns:
            if col in df_author_summary.columns:
                df_author_summary[col] = df_author_summary[col].astype(int)

        if 'Author_ID' in df_author_summary.columns and 'Author_Name' in df_author_summary.columns: # If merged with author names
            df_author_summary = df_author_summary.set_index('Author_Name') # Set Author_Name as index if available
            if 'Author_ID' in df_author_summary.columns : # remove Author_ID if it is not the index
                df_author_summary = df_author_summary.drop(columns=['Author_ID'])
        elif 'Author' in df_author_summary.columns and 'Name' in df_author_summary.columns: # Alternative if merged with author names
            df_author_summary = df_author_summary.set_index('Name')
            if 'Author' in df_author_summary.columns:
                 df_author_summary = df_author_summary.drop(columns=['Author'])


        print("\n--- Author Summary ---")
        print(df_author_summary)
        # This DataFrame (df_author_summary) will be written to an Excel sheet.
    else:
        print("Could not generate Author Summary because PR list or Reviews list data is missing.")

    # --- Review Comments Summary ---
    # df_category_distribution and df_severity_distribution initialized earlier
    if reviews_analysis_df is not None and not reviews_analysis_df.empty:
        if 'Category' in reviews_analysis_df.columns:
            df_category_distribution = reviews_analysis_df.groupby('Category')['PR Number'].count().rename('Count').reset_index()
            print("\n--- Review Comment Category Distribution ---")
            print(df_category_distribution)
            # This DataFrame (df_category_distribution) will be written to an Excel sheet.
        else:
            print("\n--- Review Comment Category Distribution ---")
            print("Category column not found in reviews analysis data.")
            df_category_distribution = pd.DataFrame({'Status': ["Category column not found"]})


        if 'Severity' in reviews_analysis_df.columns:
            df_severity_distribution = reviews_analysis_df.groupby('Severity')['PR Number'].count().rename('Count').reset_index()
            print("\n--- Review Comment Severity Distribution ---")
            print(df_severity_distribution)
            # This DataFrame (df_severity_distribution) will be written to an Excel sheet.
        else:
            print("\n--- Review Comment Severity Distribution ---")
            print("Severity column not found in reviews analysis data.")
            df_severity_distribution = pd.DataFrame({'Status': ["Severity column not found"]})

    else:
        print("\n--- Review Comments Summary ---")
        print("Reviews analysis data is missing or empty. Cannot generate comment category or severity distributions.")
        df_category_distribution = pd.DataFrame({'Status': ["Reviews analysis data not available"]})
        df_severity_distribution = pd.DataFrame({'Status': ["Reviews analysis data not available"]})

    # --- Reviews Summary ---
    # df_total_reviews_per_reviewer and df_reviews_by_pr_and_reviewer initialized earlier
    if reviews_list_df is not None and not reviews_list_df.empty and reviewer_list_df is not None: # Added reviewer_list_df check
        # Calculate total review comments per reviewer
        # Assuming 'Review Comment' column exists for counting
        if 'Review Comment' in reviews_list_df.columns and 'Reviewer' in reviews_list_df.columns:
            df_total_reviews_per_reviewer = reviews_list_df.groupby('Reviewer')['Review Comment'].count().rename('Total Review Comments').reset_index()

            # Merge with reviewer_list_df to include reviewer names
            if reviewer_list_df is not None and not reviewer_list_df.empty:
                # Check for actual column names in reviewer_list_df, e.g., 'Reviewer' and 'Reviewer Name'
                if 'Reviewer' in reviewer_list_df.columns and 'Reviewer Name' in reviewer_list_df.columns:
                    df_total_reviews_per_reviewer = pd.merge(df_total_reviews_per_reviewer, reviewer_list_df[['Reviewer', 'Reviewer Name']], on='Reviewer', how='left')
                elif 'Reviewer_ID' in reviewer_list_df.columns and 'Reviewer_Name' in reviewer_list_df.columns: # Original assumption
                    df_total_reviews_per_reviewer = pd.merge(df_total_reviews_per_reviewer, reviewer_list_df[['Reviewer_ID', 'Reviewer_Name']], left_on='Reviewer', right_on='Reviewer_ID', how='left')
                elif 'Reviewer_Login' in reviewer_list_df.columns and 'Reviewer_Name' in reviewer_list_df.columns: # Alternative common naming
                     df_total_reviews_per_reviewer = pd.merge(df_total_reviews_per_reviewer, reviewer_list_df[['Reviewer_Login', 'Reviewer_Name']], left_on='Reviewer', right_on='Reviewer_Login', how='left')

            print("\n--- Total Reviews Per Reviewer ---")
            print(df_total_reviews_per_reviewer)
            # This DataFrame (df_total_reviews_per_reviewer) will be written to an Excel sheet.
        else:
            print("\n--- Total Reviews Per Reviewer ---")
            print("Relevant columns ('Reviewer', 'Review Comment') not found in reviews list data.")
            df_total_reviews_per_reviewer = pd.DataFrame({'Status': ["Data missing for total reviews per reviewer."]})


        # Calculate breakdown of reviews by PR for each reviewer
        if 'Reviewer' in reviews_list_df.columns and 'PR Number' in reviews_list_df.columns and 'Review Comment' in reviews_list_df.columns:
            df_reviews_by_pr_and_reviewer = reviews_list_df.groupby(['Reviewer', 'PR Number'])['Review Comment'].count().rename('Comment Count').reset_index()

            # Merge with reviewer_list_df to include reviewer names
            if reviewer_list_df is not None and not reviewer_list_df.empty:
                if 'Reviewer' in reviewer_list_df.columns and 'Reviewer Name' in reviewer_list_df.columns:
                    df_reviews_by_pr_and_reviewer = pd.merge(df_reviews_by_pr_and_reviewer, reviewer_list_df[['Reviewer', 'Reviewer Name']], on='Reviewer', how='left')
                elif 'Reviewer_ID' in reviewer_list_df.columns and 'Reviewer_Name' in reviewer_list_df.columns: # Original
                    df_reviews_by_pr_and_reviewer = pd.merge(df_reviews_by_pr_and_reviewer, reviewer_list_df[['Reviewer_ID', 'Reviewer_Name']], left_on='Reviewer', right_on='Reviewer_ID', how='left')
                elif 'Reviewer_Login' in reviewer_list_df.columns and 'Reviewer_Name' in reviewer_list_df.columns: # Alternative
                    df_reviews_by_pr_and_reviewer = pd.merge(df_reviews_by_pr_and_reviewer, reviewer_list_df[['Reviewer_Login', 'Reviewer_Name']], left_on='Reviewer', right_on='Reviewer_Login', how='left')

            print("\n--- Review Breakdown by PR and Reviewer ---")
            print(df_reviews_by_pr_and_reviewer)
            # This DataFrame (df_reviews_by_pr_and_reviewer) will be written to an Excel sheet.
        else:
            print("\n--- Review Breakdown by PR and Reviewer ---")
            print("Relevant columns ('Reviewer', 'PR Number', 'Review Comment') not found for review breakdown.")
            df_reviews_by_pr_and_reviewer = pd.DataFrame({'Status': ["Data missing for review breakdown."]})

    else:
        print("\n--- Reviews Summary ---")
        print("Reviews list data is missing or empty. Cannot generate reviews summaries.")
        df_total_reviews_per_reviewer = pd.DataFrame({'Status': ["Reviews list data not available"]})
        df_reviews_by_pr_and_reviewer = pd.DataFrame({'Status': ["Reviews list data not available"]})

    # --- Code Owner Comments Summary ---
    # df_code_owner_category_summary and df_code_owner_severity_summary initialized earlier
    if reviewer_list_df is not None and not reviewer_list_df.empty and \
       reviews_list_df is not None and not reviews_list_df.empty and \
       reviews_analysis_df is not None and not reviews_analysis_df.empty:

        if 'IsCodeOwner' in reviewer_list_df.columns and 'Reviewer' in reviewer_list_df.columns:
            code_owners = reviewer_list_df[reviewer_list_df['IsCodeOwner'] == 'Yes']['Reviewer'].tolist()

            if not code_owners:
                print("\n--- Code Owner Comments Summary ---")
                print("No code owners found in the reviewer list.")
                df_code_owner_category_summary = pd.DataFrame({'Status': ["No code owners found"]})
                df_code_owner_severity_summary = pd.DataFrame({'Status': ["No code owners found"]})
            else:
                # Merge reviews_list (for Reviewer) with reviews_analysis_df (for Category, Severity)
                # Both need 'PR Number' and 'Review Comment' to uniquely identify a comment if PRs can have multiple identical comments.
                # However, sample-reviews-analysis.csv has 'Category', 'Severity' per comment, so it should be the base for this.
                # We need to add 'Reviewer' to reviews_analysis_df.
                # A direct merge of reviews_analysis_df with reviews_list_df might create duplicates if not careful.
                # Let's ensure reviews_list_df has unique Review Comment per PR Number for this merge or select distinct.
                # For this task, assume 'PR Number' and 'Review Comment' is a composite key for merging.

                # Select relevant columns and drop duplicates to avoid issues if one comment maps to multiple analyses (should not happen)
                # or one comment text appears multiple times for the same PR (could happen).
                # The instruction implies reviews_analysis_df is the source of truth for categories/severities.
                # And reviews_list_df is source of truth for who made the comment.

                if 'PR Number' in reviews_list_df.columns and 'Review Comment' in reviews_list_df.columns and 'Reviewer' in reviews_list_df.columns and \
                   'PR Number' in reviews_analysis_df.columns and 'Review Comment' in reviews_analysis_df.columns and \
                   'Category' in reviews_analysis_df.columns and 'Severity' in reviews_analysis_df.columns:

                    # Add Reviewer to reviews_analysis_df
                    # We need a key to merge. 'PR Number' and 'Review Comment' seems to be the best candidate.
                    # Let's use a left merge to keep all analysis entries and add reviewer information.
                    reviews_with_reviewer_df = pd.merge(
                        reviews_analysis_df,
                        reviews_list_df[['PR Number', 'Review Comment', 'Reviewer']],
                        on=['PR Number', 'Review Comment'],
                        how='left'
                    )

                    # Filter for comments made by code owners
                    df_code_owner_comments = reviews_with_reviewer_df[reviews_with_reviewer_df['Reviewer'].isin(code_owners)]

                    if not df_code_owner_comments.empty:
                        df_code_owner_category_summary = df_code_owner_comments.groupby('Category')['PR Number'].count().rename('Count').reset_index()
                        df_code_owner_severity_summary = df_code_owner_comments.groupby('Severity')['PR Number'].count().rename('Count').reset_index()

                        print("\n--- Code Owner Comment Category Summary ---")
                        print(df_code_owner_category_summary)
                        # This DataFrame will be written to an Excel sheet.

                        print("\n--- Code Owner Comment Severity Summary ---")
                        print(df_code_owner_severity_summary)
                        # This DataFrame will be written to an Excel sheet.
                    else:
                        print("\n--- Code Owner Comments Summary ---")
                        print("No comments found from code owners.")
                        df_code_owner_category_summary = pd.DataFrame({'Status': ["No comments from code owners"]})
                        df_code_owner_severity_summary = pd.DataFrame({'Status': ["No comments from code owners"]})
                else:
                    print("\n--- Code Owner Comments Summary ---")
                    print("Required columns for merging or analysis are missing from DFs.")
                    df_code_owner_category_summary = pd.DataFrame({'Status': ["Required columns missing"]})
                    df_code_owner_severity_summary = pd.DataFrame({'Status': ["Required columns missing"]})
        else:
            print("\n--- Code Owner Comments Summary ---")
            print("'IsCodeOwner' or 'Reviewer' column not found in reviewer list.")
            df_code_owner_category_summary = pd.DataFrame({'Status': ["Reviewer list format error"]})
            df_code_owner_severity_summary = pd.DataFrame({'Status': ["Reviewer list format error"]})
    else:
        print("\n--- Code Owner Comments Summary ---")
        print("One or more required DataFrames (reviewer_list_df, reviews_list_df, reviews_analysis_df) are missing or empty.")
        df_code_owner_category_summary = pd.DataFrame({'Status': ["Required DFs missing"]})
        df_code_owner_severity_summary = pd.DataFrame({'Status': ["Required DFs missing"]})

    # --- Write to Excel ---
    excel_file_path = "pr_analysis_report.xlsx"
    try:
        with pd.ExcelWriter(excel_file_path, engine='openpyxl') as writer:
            # Check if df_author_summary was successfully computed (not None and not empty)
            if df_author_summary is not None and not df_author_summary.empty:
                df_author_summary.to_excel(writer, sheet_name='Author Summary', index=True)

            # For other DFs, check they are not the placeholder 'Status' DFs
            if not ('Status' in df_category_distribution.columns and df_category_distribution.shape[0] == 1 and "Data not loaded" in df_category_distribution['Status'].iloc[0]):
                df_category_distribution.to_excel(writer, sheet_name='Comment Category Distribution', index=False)

            if not ('Status' in df_severity_distribution.columns and df_severity_distribution.shape[0] == 1 and "Data not loaded" in df_severity_distribution['Status'].iloc[0]):
                df_severity_distribution.to_excel(writer, sheet_name='Comment Severity Distribution', index=False)

            if not ('Status' in df_total_reviews_per_reviewer.columns and df_total_reviews_per_reviewer.shape[0] == 1 and "Data not loaded" in df_total_reviews_per_reviewer['Status'].iloc[0]):
                df_total_reviews_per_reviewer.to_excel(writer, sheet_name='Total Reviews per Reviewer', index=False)

            if not ('Status' in df_reviews_by_pr_and_reviewer.columns and df_reviews_by_pr_and_reviewer.shape[0] == 1 and "Data not loaded" in df_reviews_by_pr_and_reviewer['Status'].iloc[0]):
                df_reviews_by_pr_and_reviewer.to_excel(writer, sheet_name='Reviews by PR and Reviewer', index=False)

            if not ('Status' in df_code_owner_category_summary.columns and df_code_owner_category_summary.shape[0] == 1 and "Data not loaded" in df_code_owner_category_summary['Status'].iloc[0]):
                df_code_owner_category_summary.to_excel(writer, sheet_name='Code Owner Category Summary', index=False)

            if not ('Status' in df_code_owner_severity_summary.columns and df_code_owner_severity_summary.shape[0] == 1 and "Data not loaded" in df_code_owner_severity_summary['Status'].iloc[0]):
                df_code_owner_severity_summary.to_excel(writer, sheet_name='Code Owner Severity Summary', index=False)

        print(f"\nExcel report generated successfully: {excel_file_path}")

    except Exception as e:
        print(f"Error writing to Excel file: {e}")
