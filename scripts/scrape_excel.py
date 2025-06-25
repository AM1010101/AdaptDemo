import pandas as pd
import requests
from io import BytesIO
from urllib.parse import urlparse, parse_qs

def excel_to_csv_from_url(excel_url, output_csv_filename="output_data.csv"):
    """
    Downloads an Excel file content from a URL (handling officeapps.live.com viewer links)
    and saves its first sheet as a CSV file.
    Explicitly uses 'openpyxl' engine for .xlsx files.

    Args:
        excel_url (str): The URL of the Excel file (can be a direct link or an officeapps.live.com viewer link).
        output_csv_filename (str): The name for the output CSV file.
    """
    try:
        print(f"Provided URL: {excel_url}")

        # Check if the URL is an officeapps.live.com viewer link
        if "view.officeapps.live.com" in excel_url:
            parsed_url = urlparse(excel_url)
            query_params = parse_qs(parsed_url.query)
            if 'src' in query_params:
                # Extract the direct Excel file URL from the 'src' parameter
                direct_excel_link = query_params['src'][0]
                print(f"Extracted direct Excel link: {direct_excel_link}")
            else:
                raise ValueError("Could not find 'src' parameter in the officeapps.live.com URL.")
        else:
            direct_excel_link = excel_url # Assume it's already a direct link

        print(f"Attempting to download and convert data from: {direct_excel_link}")

        # Use requests to get the actual Excel file content
        response = requests.get(direct_excel_link)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)

        # Use BytesIO to create an in-memory binary stream from the content
        excel_file_bytes = BytesIO(response.content)

        # Read the Excel file directly into a pandas DataFrame, specifying the engine
        # pandas will read the first sheet by default
        df = pd.read_excel(excel_file_bytes, engine='openpyxl')

        # Save the DataFrame to a CSV file
        df.to_csv(output_csv_filename, index=False, encoding='utf-8')
        print(f"Data successfully saved to {output_csv_filename}")

    except requests.exceptions.RequestException as e:
        print(f"Error downloading the Excel file: {e}")
    except ValueError as e:
        print(f"URL parsing error: {e}")
    except Exception as e:
        print(f"An error occurred during processing: {e}")

if __name__ == "__main__":
    # Your original URL that caused the issue
    komsa_excel_viewer_url = "https://view.officeapps.live.com/op/view.aspx?src=https://media.komsa.com/Media/upload/Angebote_Querbeet_RvP.xlsx?utm_campaign=E-Mail_Auswertung%2520RvP%2520News&utm_medium=email&_hsmi=269579916&_hsenc=p2ANqtz-9Xqrghvdx96oocj27Ca4wOzyw10emDhIoRFOVsnXfcxBK-4nmyOSqhiiInwOniyZrE90E4R_l5CVAy7gb8bF2Q&utm_content=269579916&utm_source=hs_email&wdOrigin=BROWSELINK"

    output_file = "komsa_offers.csv"

    excel_to_csv_from_url(komsa_excel_viewer_url, output_file)