
import pandas as pd
import matplotlib.pyplot as plt
import os

def visualize_review_length(input_csv_path, output_image_path):
    """
    Reads a CSV file, calculates the length of each review, and plots a histogram
    of the review lengths.

    Args:
        input_csv_path (str): The path to the input CSV file.
        output_image_path (str): The path to save the output histogram image.
    """
    print(f"Reading data from {input_csv_path}...")
    try:
        df = pd.read_csv(input_csv_path)
    except FileNotFoundError:
        print(f"Error: Input file not found at {input_csv_path}")
        return

    # Handle potential missing values in the 'review' column
    df.dropna(subset=['review'], inplace=True)

    # Calculate review lengths
    review_lengths = df['review'].str.len()

    # Plot the distribution
    plt.figure(figsize=(10, 6))
    plt.hist(review_lengths, bins=50, edgecolor='black')
    plt.title('Distribution of Review Lengths')
    plt.xlabel('Review Length (number of characters)')
    plt.ylabel('Frequency')
    plt.grid(True)

    # Save the plot
    plt.savefig(output_image_path)
    print(f"Saved plot to {output_image_path}")

if __name__ == '__main__':
    # Get the directory of the current script to build relative paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir) # Go up one level from EDA/

    # Define paths relative to the project root
    input_csv = os.path.join(project_root, 'database', '7 Days to Die.csv')
    output_image = os.path.join(project_root, 'review_length_distribution.png')

    visualize_review_length(input_csv, output_image)
