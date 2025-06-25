import requests

# --- Replace with your actual SHEET_ID and GID ---
sheet_id = '13EqetTRWlpS7XAUyQP0mOrZb-AR6c3AvgFGWFRgpq00'
sheet_gid = '0' # e.g., '0' for the first sheet

export_url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={sheet_gid}'

print(f"Attempting to download from: {export_url}")

try:
    response = requests.get(export_url)
    response.raise_for_status()  # Raises an exception for HTTP errors

    csv_data_string = response.text
    print("\nSuccessfully fetched CSV data (first 500 characters):")
    print(csv_data_string[:500]) # Print first 500 chars as a sample

    # You can then parse it using the csv module
    # For example, print each row:
    # lines = csv_data_string.splitlines()
    # reader = csv.reader(lines)
    # print("\nParsed CSV rows:")
    # for row in reader:
    #     print(row)

except requests.exceptions.RequestException as e:
    print(f"\nError downloading the CSV: {e}")
    print("Please double-check:")
    print("1. The SHEET_ID and SHEET_GID are correct.")
    print("2. The sheet's sharing settings are 'Anyone with the link can view'.")
    print("3. You have an active internet connection.")
except Exception as e:
    print(f"An unexpected error occurred: {e}")