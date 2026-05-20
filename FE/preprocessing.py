import pandas as pd
import os
import re

def preprocess_reviews(input_path, output_dir):
    """
    Reads a CSV file of Steam reviews, splits it by game title, removes outliers,
    and preprocesses the review text.

    Args:
        input_path (str): The path to the input CSV file.
        output_dir (str): The directory to save the processed CSV files.
    """
    print(f"Reading data from {input_path}...")
    try:
        df = pd.read_csv(input_path)
    except FileNotFoundError:
        print(f"Error: Input file not found at {input_path}")
        return

    # Group by game title
    grouped = df.groupby('game_title')

    print(f"Found {len(grouped)} games. Processing each game...")

    for game_title, group in grouped:
        print(f"  - Processing {game_title}...")

        # Remove outliers based on weighted_vote_score using IQR
        q1 = group['weighted_vote_score'].quantile(0.25)
        q3 = group['weighted_vote_score'].quantile(0.75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        cleaned_group = group[(group['weighted_vote_score'] >= lower_bound) & (group['weighted_vote_score'] <= upper_bound)].copy()

        # --- Text Preprocessing ---
        # Handle potential missing values
        cleaned_group.loc[:, 'review'] = cleaned_group['review'].fillna('')

        # Filter by review length
        cleaned_group = cleaned_group[cleaned_group['review'].str.len() > 0]
        cleaned_group = cleaned_group[cleaned_group['review'].str.len() <= 500]

        # Convert to lowercase
        cleaned_group.loc[:, 'review'] = cleaned_group['review'].str.lower()

        # Remove special characters
        cleaned_group.loc[:, 'review'] = cleaned_group['review'].str.replace(r'[^a-z0-9\s]', '', regex=True)

        # Save the cleaned data to a new CSV file
        # Sanitize the filename
        safe_filename = "".join([c for c in game_title if c.isalpha() or c.isdigit() or c==' ']).rstrip()
        output_filename = os.path.join(output_dir, f"{safe_filename}.csv")
        
        cleaned_group.to_csv(output_filename, index=False)
        print(f"    - Saved cleaned data to {output_filename}")

if __name__ == '__main__':
    # Get the directory of the current script to build relative paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir) # Go up one level from FE/

    # Define paths relative to the project root
    input_csv_path = os.path.join(project_root, 'database', 'steam_reviews.csv')
    output_directory = os.path.join(project_root, 'database')

    # Create the output directory if it doesn't exist
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    # Run the preprocessing
    preprocess_reviews(input_csv_path, output_directory)