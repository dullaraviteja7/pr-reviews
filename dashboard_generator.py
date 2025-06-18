"""
Generates an interactive web dashboard using Plotly Dash to visualize
GitHub PR review analysis data. It loads data from pre-generated CSV files
(expected to be in the 'data/' directory) and displays various charts and tables.
"""
import os

# Third-party imports
import dash
from dash import html, dcc, dash_table # Modern Dash imports, explicitly adding dash_table
import plotly.express as px
import pandas as pd

# File Paths & Data Loading
DATA_DIR = "data/"
PR_LIST_FILE = os.path.join(DATA_DIR, "sample-pr-list.csv")
REVIEWER_LIST_FILE = os.path.join(DATA_DIR, "sample-reviewer-list.csv")
AUTHOR_LIST_FILE = os.path.join(DATA_DIR, "sample-author-list.csv")
REVIEWS_LIST_FILE = os.path.join(DATA_DIR, "sample-reviews-list.csv")
REVIEWS_ANALYSIS_FILE = os.path.join(DATA_DIR, "sample-reviews-analysis.csv")

def load_data(file_path):
    """Loads a CSV file into a pandas DataFrame."""
    try:
        df = pd.read_csv(file_path)
        print(f"Successfully loaded data from {file_path}")
        return df
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
        return None
    except pd.errors.EmptyDataError:
        print(f"Error: File at {file_path} is empty.")
        return None
    except Exception as e:
        print(f"Error loading data from {file_path}: {e}")
        return None

# Load all dataframes
df_pr_list = load_data(PR_LIST_FILE)
df_reviewer_list = load_data(REVIEWER_LIST_FILE)
df_author_list = load_data(AUTHOR_LIST_FILE)
df_reviews = load_data(REVIEWS_LIST_FILE)
df_reviews_analysis = load_data(REVIEWS_ANALYSIS_FILE)

# Critical data check
if df_reviews_analysis is None:
    print("Error: Critical data (reviews analysis) could not be loaded. Dashboard cannot start.")
    # In a real app, you might set a flag to display an error in the dashboard layout.
    # For this setup, exiting is acceptable.
    exit(1)
    # critical_data_loaded = False # Example for alternative handling

# Initialize Dash App
app = dash.Dash(__name__)
# Note: For custom CSS, you might add: external_stylesheets=['assets/custom.css']
# and create an 'assets' folder with your CSS file.
server = app.server # Expose server for potential WSGI use


# --- Chart and Table Creation ---

# Placeholder figures/data for robustness
fig_categories = px.bar(title='Distribution of Comment Categories (No Data)')
fig_severities = px.bar(title='Distribution of Comment Severities (No Data)')
pr_high_severity_counts = pd.DataFrame(columns=['PR Number', 'High Severity Count'])
fig_reviewer_load = px.bar(title='Review Load per Reviewer (No Data)')


if df_reviews_analysis is not None and not df_reviews_analysis.empty:
    # Chart 1: Distribution of Comment Categories
    if 'Category' in df_reviews_analysis.columns:
        category_counts = df_reviews_analysis['Category'].value_counts().reset_index()
        category_counts.columns = ['Category', 'Count']
        fig_categories = px.bar(category_counts, x='Category', y='Count', title='Distribution of Comment Categories')
    else:
        print("Warning: 'Category' column not found in df_reviews_analysis for category distribution chart.")

    # Chart 2: Distribution of Comment Severities
    if 'Severity' in df_reviews_analysis.columns:
        severity_counts = df_reviews_analysis['Severity'].value_counts().reset_index()
        severity_counts.columns = ['Severity', 'Count']
        fig_severities = px.bar(severity_counts, x='Severity', y='Count', title='Distribution of Comment Severities')
    else:
        print("Warning: 'Severity' column not found in df_reviews_analysis for severity distribution chart.")

    # Table 1: PRs with Most "High" Severity Comments
    if 'PR Number' in df_reviews_analysis.columns and 'Severity' in df_reviews_analysis.columns:
        high_severity_reviews = df_reviews_analysis[df_reviews_analysis['Severity'] == 'High']
        if not high_severity_reviews.empty:
            pr_high_severity_counts = high_severity_reviews.groupby('PR Number').size().reset_index(name='High Severity Count')
            pr_high_severity_counts = pr_high_severity_counts.sort_values(by='High Severity Count', ascending=False)
        # else: pr_high_severity_counts remains an empty DataFrame as initialized
    else:
        print("Warning: 'PR Number' or 'Severity' column not found in df_reviews_analysis for high severity PRs table.")
else:
    print("Info: df_reviews_analysis is None or empty. Using placeholder data for related charts/tables.")


# Chart 3: Review Load per Reviewer
if df_reviews is not None and not df_reviews.empty:
    if 'Reviewer' in df_reviews.columns:
        reviewer_load_counts = df_reviews['Reviewer'].value_counts().reset_index()
        reviewer_load_counts.columns = ['Reviewer', 'Review Count']
        fig_reviewer_load = px.bar(reviewer_load_counts, x='Reviewer', y='Review Count', title='Review Load per Reviewer')
    else:
        print("Warning: 'Reviewer' column not found in df_reviews. Cannot create reviewer load chart.")
else:
    print("Info: df_reviews is None or empty. Using placeholder for reviewer load chart.")


# --- App Layout ---
# The className attributes (e.g., 'row', 'six columns') are for logical structure
# and can be styled if a CSS framework (like Bootstrap) or custom CSS is added.
app.layout = html.Div(children=[
    html.H1(children='PR Review Analysis Dashboard'),

    html.Div(className='row', style={'padding': '10px'}, children=[ # Added padding to row
        html.Div(children='Overview of review comments and their AI-driven analysis.')
    ]),

    html.Div(className='row', style={'display': 'flex', 'marginBottom': '20px'}, children=[
        html.Div(className='six columns', style={'width': '50%', 'padding': '10px'}, children=[
            dcc.Graph(id='categories-distribution-chart', figure=fig_categories)
        ]),
        html.Div(className='six columns', style={'width': '50%', 'padding': '10px'}, children=[
            dcc.Graph(id='severities-distribution-chart', figure=fig_severities)
        ])
    ]),

    html.Div(className='row', style={'marginBottom': '20px'}, children=[
        html.Div(className='twelve columns', style={'padding': '10px'}, children=[ # Added padding
            html.H3("PRs with Most High Severity Comments"),
            dash_table.DataTable(
                id='high-severity-prs-table',
                columns=[{"name": i, "id": i} for i in pr_high_severity_counts.columns],
                data=pr_high_severity_counts.to_dict('records'),
                page_size=5, # Smaller page size for this table
                style_cell={'textAlign': 'left'},
                style_header={'backgroundColor': 'lightgrey', 'fontWeight': 'bold'}
            )
        ])
    ]),

    html.Div(className='row', style={'marginBottom': '20px'}, children=[
        html.Div(className='twelve columns', style={'padding': '10px'}, children=[
            dcc.Graph(id='reviewer-load-chart', figure=fig_reviewer_load)
        ])
    ]),

    html.Div(className='row', children=[
         html.H2("Further analyses can be added here.") # Updated placeholder text
    ])
])

# Run Server
if __name__ == '__main__':
    # Be mindful of port conflicts if other services are running on 8050.
    # You can change the port: app.run_server(debug=True, port=8051)
    app.run_server(debug=True)
