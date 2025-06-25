from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from models import RawProductScrapeMeta, RawProductScrape
import re
import httpx
import json
from supabase import create_client, Client
from config import  get_settings
from typing import Optional, List
import uuid
from fastapi.responses import StreamingResponse
import csv
import io
import requests
import pandas as pd
from io import BytesIO
from urllib.parse import urlparse, parse_qs
from enum import Enum
import datetime
from ui import router


app = FastAPI()
settings = get_settings()

app.include_router(router)
app.mount("/templates", StaticFiles(directory="templates"), name="templates")


class SourceIDEnum(str, Enum):
    foxway = 'Foxway'
    komsa = 'Komsa'
    compa = 'Compa'
    dipli = 'Dipli'
    

def get_supabase_client() -> Client:
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def log_to_supabase(log_level: str, message: str, context: Optional[dict] = None, user_id: Optional[str] = None, source: Optional[str] = None):
    supabase_client = get_supabase_client()
    log_entry = {
        "log_level": log_level,
        "message": message,
        "context": context,
        "user_id": user_id,
        "source": source
    }
    response = supabase_client.table("logs").insert(log_entry).execute()
    return response


@app.get("/download/lookup_table", tags=['Download'])
def get_sku_lookup_table():
    sheet_id = '1B1TLvZJoP8TRpJnek7oc_f5j6KvbdCqE4tJ2rqH99Fw'
    sheet_gid = '0' # e.g., '0' for the first sheet

    export_url = f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={sheet_gid}'

    try:
        response = requests.get(export_url)
        response.raise_for_status()  # Raises an exception for HTTP errors

        csv_data_string = response.text
        return csv_data_string
    except Exception as e:
        print(e)
        


def fetch_excel_as_df(excel_url: str) -> pd.DataFrame:
    
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

    # print(f"Attempting to download and convert data from: {direct_excel_link}")

        # Use requests to get the actual Excel file content
    response = requests.get(direct_excel_link)
    response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)

        # Use BytesIO to create an in-memory binary stream from the content
    excel_file_bytes = BytesIO(response.content)
    
    df = pd.read_excel(excel_file_bytes, engine='openpyxl')
    return df


def create_db_row(data: RawProductScrape):
    """Creates a dictionary for a database row from a RawProductScrape model."""
    row = data.dict()
    # Ensure storage_capacity is uppercase
    row['storage_capacity'] = row['storage_capacity'].upper()
    return row


def load_data_from_disk(filename):
    json_filename = filename
    with open(json_filename, "r") as f:
        loaded_data = json.load(f)
    return loaded_data
    
    
def save_data_to_disk(data, source:str):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{source}_{timestamp}.csv"

    if isinstance(data, list) and data:
        # Flatten dicts if needed, or just use pandas for convenience
        df = pd.DataFrame(data)
        df.to_csv(filename, index=False)
        print(f"Data saved to {filename}")
        return filename 
    else:
        # Save as JSON if not a list of dicts
        json_filename = f"{source}_{timestamp}.json"
        with open(json_filename, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Data saved to {json_filename}")
        return json_filename


async def scrape_foxway(manufacturer:str, partial_vat:bool, scrape_instance: Optional[uuid.UUID] = None):
    
    # lookup table for manufacturer_id
    manufacturer_ids = {
        "huawei": 137,
        "apple": 116,
        "samsung": 153,
    }
    manufacturer_id = manufacturer_ids.get(manufacturer.lower())
    
    
    url_slug ='working'
    dimension_group_id = 1
    item_group_id = 1
    vat_margin = partial_vat
    
    url = f"https://foxway.shop/api/v1/catalogs/{url_slug}/pricelist"
    params = {
        "dimensionGroupId": dimension_group_id,
        "itemGroupId": item_group_id,
        "manufacturerId": manufacturer_id,
        "vatMargin": vat_margin,
    }
    headers = {
        "accept": "text/plain",
        "X-ApiKey": settings.FOXWAY_API_KEY,
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, headers=headers)
    
    json_data = response.json()

    
    await write_scrape_to_supabase(manufacturer, partial_vat, json_data, scrape_instance=scrape_instance)


async def write_scrape_to_supabase(manufacturer:str, partial_vat:bool, data:dict, scrape_instance: Optional[uuid.UUID] = None):

        
    # we know manufactureer id Huawei is 137 and vat margin is False
    supabase_client = get_supabase_client()

    insert_rows = []
    for line in data:
        # Find the grade value in the Dimension list robustly
        grade = next((d["Value"] for d in line.get("Dimension", []) if d.get("Key", "").lower() == "appearance"), None)
        
        if not grade:
            grade = ''
        else:
            grade = grade.replace("Grade ", "")
            
        storage = line["ProductName"]
        if "128GB" in storage:
            storage = "128GB"
        elif "64GB" in storage:
            storage = "64GB"
        elif "32GB" in storage:
            storage = "32GB"
        elif "256GB" in storage:
            storage = "256GB"
        elif "512GB" in storage:
            storage = "512GB"
        elif "16GB" in storage:
            storage = "16GB"
        elif "8GB" in storage:
            storage = "8GB"
        elif "4GB" in storage:
            storage = "4GB"
        elif "2GB" in storage:
            storage = "2GB"
        elif "1TB" in storage:
            storage = "1TB"
        elif "2TB" in storage:
            storage = "2TB"
        elif "4TB" in storage:
            storage = "4TB"
        else:
            storage = "Unknown Storage"
            
        model = line["ProductName"]
        # remove the storage from the model name
        for size in ["128GB", "64GB", "32GB", "256GB", "512GB", "16GB", "8GB", "4GB", "2GB", "1TB", "2TB", "4TB"]:
            model = model.replace(size, "").strip()
            
        # remove the word "Huawei" from the model name
        makes = ["Apple", "Samsung", "Huawei"]
        for make in makes:
            model = model.replace(make, "").strip()
            
        insert_rows.append({
            "source_id": settings.FOXWAY_SUPABASE_ID,  # Assuming you have a source ID for Foxway
            "make": manufacturer, 
            "model": model,
            "storage_capacity": storage,  # This is hardcoded, adjust as needed
            "grade": grade,  # Assuming this is the grade
            "colour": line["Dimension"][0]["Value"],
            "ce_mark": None, 
            "partial_vat": partial_vat,  # Adjust based on your data
            "purchase_price": line["Price"],
            "trade_in_price": None,  # Adjust if you have this data
            "stock_count": line["Quantity"],
            "meta_data": json.dumps(line),  # Store the entire item as metadata
            "scrape_instance": str(scrape_instance) if scrape_instance else None # Use the provided scrape instance or set to None
        })

    
            # insert into supabase
    response = supabase_client.table("raw_product_scrapes").insert(insert_rows).execute()
    return response

          
@app.get("/scrape_all", tags=['Scrape'])
async def scrape_all(request:Request, do_scrape: bool = False, caller: Optional[str] = None):
    
    #scrape foxway
    await scrape_all_foxway(request= request, do_scrape = do_scrape, caller = caller)
    
    # scrape Komsa
    await scrape_all_komsa(request= request, do_scrape = do_scrape, caller = caller)
    
    # scrape dipili
    # await scrape_all_dipli()
    
    # scrape compa recycle
    await scrape_all_compa_recycle()
    

@app.get("/scrape_all_foxway", tags=['Scrape'])
async def scrape_all_foxway(request:Request, do_scrape: bool = False, caller: Optional[str] = None):
    caller = caller or "Unknown Caller"
    if not do_scrape:
        log_to_supabase("warning", "Scraping is disabled", {"do_scrape": do_scrape, "request_client": str(request.client), "caller":caller}, source="FastAPI - scrape_all_foxway")
        return {"message": "Scraping is disabled. Set do_scrape to True to enable."}
    manufacturers = ["huawei", "apple", "samsung"]
    partial_vat = [True, False]  # Example values for partial VAT
    scrape_instance = uuid.uuid4()  #uuid
    
    log_to_supabase("info", "Starting scrape for all manufacturers and VAT settings", {"manufacturers": manufacturers, "partial_vat": partial_vat, "scrape_instance": str(scrape_instance), "request_client": str(request.client), "caller": caller}, source="FastAPI - scrape_all_foxway")
    
    # Iterate over manufacturers and VAT settings
    for manufacturer in manufacturers:
        for vat in partial_vat:
            await scrape_foxway(manufacturer, vat, scrape_instance)
    
    log_to_supabase("info", "Completed scrape for all manufacturers and VAT settings", {"manufacturers": manufacturers, "partial_vat": partial_vat, "scrape_instance": str(scrape_instance), "request_client": str(request.client), "caller": caller}, source="FastAPI - scrape_all_foxway")
    
    return {"message": "API Scrape Completed"}


@app.get("/download/latest_devices", tags=['Download'])
async def download_latest_devices(source:SourceIDEnum):
    """ Endpoint to download the latest Foxway devices scrape data.
    """
    supabase_client = get_supabase_client()

    if source.lower() == 'foxway':
        source_id = settings.FOXWAY_SUPABASE_ID
    elif source.lower() =='komsa':
        source_id = settings.KOMSA_SUPABASE_ID
    elif source.lower() =='compa':
        source_id = settings.COMPA_SUPABASE_ID
    elif source.lower() == 'dipli':
        source_id = settings.DIPLI_RECYCLE_SUPABASE_ID
    else:
        return {"message": "Invalid source specified.", "success": False}
    
    # 1. Identify the latest scrape_instance by fetching the most recent foxway scrape entry
    latest_scrape_response = (
        supabase_client.table("raw_product_scrapes")
        .select("scrape_instance")
        .eq("source_id", source_id)  # Filter by Foxway source ID
        .order("entry_date", desc=True)
        .limit(1)
        .execute()
    )
    if not latest_scrape_response.data:
        log_to_supabase("error", "No scrape entries found for Foxway.", source="FastAPI - download_latest_foxway_devices")
        return {"message": "No scrape entries found for Foxway."}
    
    latest_scrape_instance_uuid = latest_scrape_response.data[0].get("scrape_instance")

    devices = get_devices_by_scrape_id(latest_scrape_instance_uuid)

    if not devices:
        return {"message": "No devices found."}
    

    # 2. Format data as CSV
    output, filename = create_downloadable_csv(devices, source=source)
    
    log_to_supabase("info", f"Successfully generated CSV for latest Foxway devices scrape. Filename: {filename}", {"rows_exported": len(devices)}, source="FastAPI - download_latest_foxway_devices")
    
    return StreamingResponse(
        iter([output.getvalue()]),  # iter() is used as StreamingResponse expects an iterator
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def create_downloadable_csv(devices, source):
    ''' Create a downloadable CSV from the device data.'''
    output = io.StringIO()
    writer = csv.writer(output)
    # Write header
    header = ["make", "model", "storage_capacity", "grade", "purchase_price", "stock_count", "colour", "ce_mark", "partial_vat", "SKU"]
    writer.writerow(header)
    # Write data rows
    for row_data in devices:
        sku = generate_sku(
            make=row_data.get("make"),
            model_name=row_data.get("model"),
            storage_capacity=row_data.get("storage_capacity"),
            colour=row_data.get("colour"),
            grade=row_data.get("grade")
        )
        writer.writerow([
            row_data.get("make"),
            row_data.get("model"),
            row_data.get("storage_capacity"),
            row_data.get("grade"),
            row_data.get("purchase_price"),
            row_data.get("stock_count"),
            row_data.get("colour"),
            row_data.get("ce_mark"),
            row_data.get("partial_vat"),
            sku,
        ])  
    output.seek(0)  # Reset buffer position to the beginning
    # 3. Serve the CSV file for download
    # get the datetime from the firtst row
    latest_scrape_datetime = devices[0].get("entry_date")
    filename = f"latest_devices_{source}_{latest_scrape_datetime}.csv"
    return output,filename
    

def get_devices_by_scrape_id(scrape_instance_id):
    supabase_client = get_supabase_client()
    
    columns_to_select = "make, model, storage_capacity, grade, purchase_price, stock_count, colour, ce_mark, partial_vat"
    all_device_scrapes = []
    page_size = 1000  # Align with suspected server-side limit
    offset = 0
    
    while True:
        current_page_response = (
            supabase_client.table("raw_product_scrapes")
            .select(columns_to_select)
            .eq("scrape_instance", scrape_instance_id)
            .limit(page_size)
            .offset(offset)
            .execute()
        )
        
        if current_page_response.data:
            all_device_scrapes.extend(current_page_response.data)
            if len(current_page_response.data) < page_size:
                # Last page fetched
                break
            offset += page_size
        else:
            # No more data or an error occurred on this page
            break
    return all_device_scrapes


# Placeholder for a more robust model code generation/lookup
# This will be the most complex part to get right and will need your detailed rules/mappings
def get_model_code(make: str, model_name: str) -> str:
    
    model_code_csv = get_sku_lookup_table()
    
    
    example_model_codes = '''
    make,model,Adapt SKU
    apple,iPhone 11,IP11X
    apple,iPhone 11 Pro,IP11P
    apple,iPhone 11 Pro Max,IP11PM
    apple,iPhone 12,IP12X
    apple,iPhone 12 Mini,IP12M
    apple,iPhone 12 Pro,IP12P
    apple,iPhone 12 Pro Max,IP12PM
    apple,iPhone 13,IP13X
    apple,iPhone 13 Mini,IP13M
    apple,iPhone 13 Pro,IP13P
    apple,iPhone 13 Pro Max,IP13PM
    apple,iPhone 14,IP14X
    apple,iPhone 14 (USA),
    apple,iPhone 14 Plus,IP14PL
    apple,iPhone 14 Plus (USA),
    apple,iPhone 14 Pro,IP14P
    apple,iPhone 14 Pro (USA),
    apple,iPhone 14 Pro Max,IP14PM
    apple,iPhone 14 Pro Max (USA),
    apple,iPhone 15,IP15X
    apple,iPhone 15 (USA),
    '''
    
    make_lower = make.lower()
    model_lower = model_name.lower()
    
    # VERY ROUGH initial attempt based on limited examples
    if "apple" in make_lower and "iphone" in model_lower:
        match = re.search(r'iphone\s*([\d]+)', model_lower) # Gets numbers like 8, 12, 13
        if match:
            return "IP" + match.group(1)
        # Add more specific Apple rules here (e.g., for SE, Pro, Max, Plus)
        return "IPXXXX" # Fallback for unhandled Apple models

    elif "samsung" in make_lower and "galaxy" in model_lower:
        if "s24" in model_lower: # Example: Samsung Galaxy S24
            return "SAS24D" 
        elif "s22 ultra" in model_lower: # Example: Samsung Galaxy S22 Ultra 5G Duos
            return "SS22UD"
        elif "s20" in model_lower: # Example: Samsung Galaxy S20
            return "SAS20D" 
        # Add more specific Samsung rules here
        return "SAXXXX" # Fallback for unhandled Samsung models
    
    # Fallback for other makes or unhandled models
    # Consider taking first few chars of make and model or a generic code
    # Ensure the fallback is not too long by default
    fallback_make = make_lower[:2].upper()
    fallback_model_cleaned = re.sub(r'[^a-z0-9]', '', model_lower) # Remove non-alphanumeric
    fallback_model = fallback_model_cleaned[:3].upper()
    return fallback_make + fallback_model


def generate_sku(make: str, model_name: str, storage_capacity: str, colour: str, grade: str) -> str:
    colour_code_map = {
        "Blue": "BL", "Black": "BK", "Midnight": "MN", "White": "WH",
        "Phantom White": "WH", "Green": "GR"
        # User to add more colour mappings here
    }
    grade_code_map = {
        "A": "AX", "A+": "AA", "B": "BX", "C": "CX"
        # User to add more grade mappings here
    }

    # 1. Get Model Code
    raw_model_code = get_model_code(make if make else "", model_name if model_name else "")

    # 2. Determine Capacity Code
    cap_code = ""
    storage_input_str = str(storage_capacity if storage_capacity else "").upper() # Normalize input
    if "TB" in storage_input_str:
        num_match = re.search(r'(\d+)', storage_input_str)
        cap_code = num_match.group(1) if num_match else "X" # e.g. "1" for 1TB
    elif "GB" in storage_input_str:
        num_match = re.search(r'(\d+)', storage_input_str)
        cap_code = num_match.group(1) if num_match else "XXX" # e.g. "64", "128"
    if not cap_code: # If still empty (e.g. input was just "Unknown Storage" or empty)
        cap_code = "XXX" # Fallback

    # 3. Determine Colour Code
    normalized_colour_key = (colour if colour else "").strip() 
    col_code = "XX" # Default fallback
    # Case-insensitive lookup for colour
    for map_key, map_val in colour_code_map.items():
        if map_key.lower() == normalized_colour_key.lower():
            col_code = map_val
            break
    
    # 4. Determine Grade Code
    normalized_grade_key = (grade if grade else "").strip()
    grd_code = "XX" # Default fallback
    # Case-insensitive lookup for grade
    for map_key, map_val in grade_code_map.items():
        if map_key.lower() == normalized_grade_key.lower(): # Compare normalized keys
            grd_code = map_val
            break

    # 5. Assemble SKU with Padding
    prefix = "M-"
    
    model_code_segment = prefix + raw_model_code.upper()
    suffix_segment = cap_code.upper() + col_code.upper() + grd_code.upper()
    
    padding_len = 15 - (len(model_code_segment) + len(suffix_segment))
    
    padding_segment = ""
    if padding_len > 0:
        padding_segment = "X" * padding_len
    elif padding_len < 0:
        # Components are too long, truncate raw_model_code.
        max_raw_model_len = 15 - len(prefix) - len(suffix_segment)
        if max_raw_model_len < 0: max_raw_model_len = 0 

        if len(raw_model_code) > max_raw_model_len:
            raw_model_code = raw_model_code[:max_raw_model_len]
        
        model_code_segment = prefix + raw_model_code.upper()
        padding_len = 15 - (len(model_code_segment) + len(suffix_segment))
        padding_segment = "X" * padding_len if padding_len > 0 else ""

    final_sku = model_code_segment + padding_segment + suffix_segment
    
    if len(final_sku) > 15:
        final_sku = final_sku[:15]
    elif len(final_sku) < 15:
        final_sku = final_sku.ljust(15, 'X')

    return final_sku.upper()


@app.get("/scrape_all_komsa", tags=['Scrape'])
async def scrape_all_komsa(request: Request, do_scrape: bool = False, caller: Optional[str] = None):
    caller = caller or "Unknown Caller"
    if not do_scrape:
        # log_to_supabase("warning", "Scraping is disabled", {"do_scrape": do_scrape, "request_client": str(request.client), "caller": caller}, source="FastAPI - scrape_all_komsa")
        return {"message": "Scraping is disabled. Set do_scrape to True to enable."}
    scrape_instance = uuid.uuid4()  #uuid
    
    # Placeholder for actual scraping logic
    log_to_supabase("info", "Scraping Komsa initiated", {"do_scrape": do_scrape, "request_client": str(request.client), "caller": caller, "scrape_instrance":scrape_instance}, source="FastAPI - scrape_all_komsa")
    
    # Simulate scraping process
    await scrape_komsa_excel(str(scrape_instance))
    log_to_supabase("info", "Scraping Komsa completed", {"do_scrape": do_scrape, "request_client": str(request.client), "caller": caller}, source="FastAPI - scrape_all_komsa")
    return {"message": "Komsa scrape completed successfully."}


async def scrape_komsa_excel(scrape_instance:str):
    try:
        # fetch the komsa df from the excel online file
        df = fetch_excel_as_df(settings.KOMSA_URL)        
            
        # prepare the dataframe for insertion
        df.columns = [col.strip() for col in df.columns]  # Clean column names
        df = df.rename(columns={
            "Artikelnummer": "Item number",
            "Bezeichnung": "Description",
            "verfügbar": "stock_count",
            "Preis": "purchase_price",
            "Zustand": "grade",
            "EAN": "ean",
            "Shop": "source"
        })
        # Convert the DataFrame to a list of dictionaries
        data_to_insert = df.to_dict(orient='records')

        insert_rows = []
        for line in data_to_insert: 
            try:
                # Extract manufacturer from the description
                manufacturer, model, storage, grade, colour = parse_komsa_info(line)
                
                stock_count = line["stock_count"] if isinstance(line["stock_count"], int) else 0  # Ensure stock_count is an integer
                
                # remove any non-numeric characters from stock_count such as >100
                if isinstance(stock_count, str):
                    stock_count = re.sub(r'\D', '', stock_count)
                    stock_count = int(stock_count) if stock_count.isdigit() else 0
                    
                row_data = RawProductScrape(
                    source_id=settings.KOMSA_SUPABASE_ID,
                    make=manufacturer,
                    model=model,
                    storage_capacity=storage,
                    grade=grade,
                    colour=colour,
                    ce_mark=None,
                    partial_vat=False,
                    purchase_price=line["purchase_price"],
                    trade_in_price=None,
                    stock_count=stock_count,
                    meta_data=json.dumps(line),
                    scrape_instance=str(scrape_instance) if scrape_instance else None,
                )

                # append the row to the insert list
                row = create_db_row(data=row_data)
                insert_rows.append(row)
                
            except Exception as e:
                # log_to_supabase("error", f"Error processing line {line}: {e}", 
                #                 {"line": line, "scrape_instance": scrape_instance}, 
                #                 source="FastAPI - scrape_komsa")
                print(f"Error processing line {line}: {e}")
        
        # Insert the data into Supabase
        supabase_client = get_supabase_client()
        response = supabase_client.table("raw_product_scrapes").insert(insert_rows).execute()
        
        
        # log_to_supabase("info", f"Successfully inserted {len(insert_rows)Generated SKU} rows into raw_product_scrapes table.", 
        #                 {"rows_inserted": len(insert_rows), "scrape_instance": scrape_instance}, 
        #                 source="FastAPI - scrape_komsa")
        
        return response
                
        
        
    except requests.exceptions.RequestException as e:
        log_to_supabase("error", f"Error downloading the Excel file: {e}", source="FastAPI - scrape_komsa")
        print(f"Error downloading the Excel file: {e}")
    except ValueError as e:
        log_to_supabase("error", f"URL parsing error: {e}", source="FastAPI - scrape_komsa")
        print(f"URL parsing error: {e}")
    except Exception as e:
        log_to_supabase("error", f"An error occurred during processing: {e}", source="FastAPI - scrape_komsa")
        print(f"An error occurred during processing: {e}")


def parse_komsa_info(line):
    manufacturer = line["Description"].split()[0].lower()  # Assuming the first word is the manufacturer
    
    # Handle specific cases for manufacturers
    if manufacturer == "airpods":
        manufacturer = "apple"
                
    # Clean up the model name
    model = line["Description"].lower()  # Convert to lowercase 
    # remove manufacturer from model name
    model = model.replace(manufacturer, "").strip()
                
    # Determine storage capacity from the description
    storage = "Unknown Storage"  # Default value if not found
    storage_matches = [size for size in [" 128gb", " 64gb", " 32gb", " 256gb", " 512gb", " 16gb", " 8gb", " 4gb", " 2gb", " 1tb", " 2tb", " 4tb"] if size in model]

    if len(storage_matches) == 1: # If exactly one storage size is found, else leave as "Unknown Storage"
        storage = storage_matches[0]
        model = model.replace(storage, "").strip()  # Remove size from model name
        
    if manufacturer == "apple":
        print(f"Model: {model}, Storage: {storage}")
                
    # Clean up the grade
    grade = line["grade"].replace("Grade ", "") if line["grade"] else ""
    
    # translate grades from German to English
    grade_translation = {
        "Neuwertig": "Excellent",
        "Wie Neu": "Like New",
        "Gut": "Good",
        "Akzeptabel": "Acceptable",
        "Sehr Gut": "Very Good"
    }
    grade = grade_translation.get(grade, grade)  # Default to original if not found in translation
    
    # Map various possible colour names to a simplified set
    colour_map = {
        #longer names first
        "titanium black": "black",
        "titanium blue": "black",
        "natural titanium": "natural titanium",
        "desert titanium": "desert titanium",
        "deep purple": "Purple",
        "sky blue": "Blue",
        "midnight green": "Green",
        "space gray": "Grey",
        "rose gold": "Gold",
        
        # German to English
        "space grau": "Grey",
        "grau": "Grey",
        "gelb": "Yellow",
        "rot": "Red",
        "orange": "Orange",
        "grun": "Green",
        "grün": "Green",
        "Blau": "Blue",
        "blau": "Blue",
        "Schwarz": "Black",
        "Weiß": "White",
        "weiß": "White",
        "Grün": "Green",
        "silber": "Silver",
        "schwarz": "Black",
        "space schwarz": "Black",
        "violett": "Purple",
        "rosé": "Pink",
        "mitternacht": "Black",
        'wüstensand': "Desert Sand",
        
        # English variants
        "black": "Black",
        "white": "White",
        "green": "Green",
        "blue": "Blue",
        "midnight": "Black",
        "yellow": "Yellow",
        "red": "Red",
        "pink": "Pink",
        "purple": "Purple",
        "orange": "Orange",
        "grey": "Grey",
        "gray": "Grey",
        "silver": "Silver",
        "gold": "Gold",
        "starlight": "Gold",
        "graphite": "Grey",
        "titanium": "Titanium",
        "teal": "Teal",
    }
    # Try to extract a colour from the model/description
    colour = "Unknown"

    for key, simple_colour in colour_map.items():
        if key.lower() in model:
            colour = simple_colour
            model = model.replace(key, "").strip()
            break
    
    return manufacturer,model,storage,grade, colour


@app.get("/scrape_dipli", tags=['Scrape'])
async def scrape_all_dipli():
    
    scrape_instance = uuid.uuid4()

    data = await get_dipli_data()
    
    # for testing if we dont want to continueously hit thier server
    # filename = save_data_to_disk(data, 'dipli)
    # loaded_data = load_data_from_disk(filename)
    
    insert_rows = []
    for line in data['result']: 
        # print(f"Processing line: {line} ----------------------------------------------")
        try:
            # Extract manufacturer from the description
            
            manufacturer = line.get("brand", "")
            # Try to extract storage from the model name or grouped_name
            storage = "Unknown Storage"
            for size in ["128GB", "64GB", "32GB", "256GB", "512GB", "16GB", "8GB", "4GB", "2GB", "1TB", "2TB", "4TB", "128", "64", "32", "256", "512", "16", "8", "4", "2"]:
                if size in line.get("name", ""):
                    storage = size if "GB" in size or "TB" in size else f"{size}GB"
                    break
                elif size in line.get("grouped_name", ""):
                    storage = size if "GB" in size or "TB" in size else f"{size}GB"
                    break

            model = line.get("name", "")
            if manufacturer and manufacturer.lower() in model.lower():
                pattern = re.compile(re.escape(manufacturer), re.IGNORECASE)
                model = pattern.sub("", model).strip()
            # Remove storage from model name, handling both with and without GB/TB
            if storage and storage != "Unknown Storage":
                storage_variants = [storage]
                # If storage ends with GB or TB, also consider just the number
                if storage.endswith("GB") or storage.endswith("TB"):
                    storage_number = storage.replace("GB", "").replace("TB", "").strip()
                    storage_variants.append(storage_number)
                for variant in storage_variants:
                    model = model.replace(variant, "").strip()
                    
            
            grade = line.get("grade", "").replace("Grade ", "")
            
            # Prefer English colour name if available
            colour = line.get("color", {}).get("name_en") or line.get("color", {}).get("name") or "Unknown"
            
            stock_count = line.get("stock", 0)
            purchase_price = line.get("final_price", 0)
            purchase_price = purchase_price/100

            ce_mark = None
            partial_vat = False
            trade_in_price = None

            db_row_data = RawProductScrape(
                source_id=settings.DIPLI_RECYCLE_SUPABASE_ID,
                make=manufacturer,
                model=model,
                storage_capacity=storage,
                grade=grade,
                colour=colour,
                ce_mark=ce_mark,
                partial_vat=partial_vat,
                purchase_price=purchase_price,
                trade_in_price=trade_in_price,
                stock_count=stock_count,
                meta_data=json.dumps(line),
                scrape_instance=str(scrape_instance) if scrape_instance else None,
            )
            row = create_db_row(data=db_row_data)
            insert_rows.append(row)
            
        except Exception as e:
            # log_to_supabase("error", f"Error processing line {line}: {e}", 
            #                 {"line": line, "scrape_instance": scrape_instance}, 
            #                 source="FastAPI - scrape_komsa")
            print(f"Error processing line {line}: {e}")
    
    # Insert the data into Supabase
    supabase_client = get_supabase_client()
    response = supabase_client.table("raw_product_scrapes").insert(insert_rows).execute()

    return response


async def get_dipli_data():
    api_key = settings.DIPLI_RECYCLE_API_KEY
    page_size = 100
    url_base = settings.DIPLI_RECYCLE_URL
    headers = {
        "apikey": api_key
    }

    all_results = []
    page = 1

    while True:
        url = f"{url_base}?pageSize={page_size}&page={page}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
        results = data.get("result", [])
        all_results.extend(results)
        if len(results) < page_size:
            break
        page += 1

    # Return the full data structure, or just the results if you prefer
    return {"result": all_results}


@app.get("/scrape_compa_recycle", tags=['Scrape'])
async def scrape_all_compa_recycle():
    
    scrape_instance = uuid.uuid4()
    data = await get_compa_data()
    
    # For testing, you can save and load from disk
    # filename = save_data_to_disk(data, 'compa_recycle')
    # data = load_data_from_disk(filename)

    insert_rows = []
    for line in data.get('results', []):
        try:
            manufacturer = line.get("manufacturer", "")
            if manufacturer.lower() not in ["apple", "samsung"]:
                continue

            model = line.get("product_model", "")
            
            # Extract storage from 'product' field, e.g., "iPhone 11 64Go"
            storage_match = re.search(r'(\d+)\s*(Go|GB)', line.get("product", ""), re.IGNORECASE)
            storage = f"{storage_match.group(1)}GB" if storage_match else "Unknown Storage"

            # These fields are not in the Compa data structure
            colour = "Unknown"
            stock_count = 0  # Defaulting to 0 as it's not available
            ce_mark = None
            partial_vat = False
            trade_in_price = None

            # Iterate through the product's keys to find all available grades and their prices
            for key, value in line.items():
                # Match keys like "best price grade A", "best price grade B", etc.
                match = re.match(r'best price grade (.+)', key)
                if match:
                    grade = match.group(1).strip()
                    try:
                        purchase_price = float(value)
                    except (ValueError, TypeError):
                        purchase_price = 0

                    # Skip this grade if the purchase price is 0
                    if purchase_price > 0:
                        db_row_data = RawProductScrape(
                            source_id=settings.COMPA_SUPABASE_ID,
                            make=manufacturer,
                            model=model,
                            storage_capacity=storage,
                            grade=grade,
                            colour=colour,
                            ce_mark=ce_mark,
                            partial_vat=partial_vat,
                            purchase_price=purchase_price,
                            trade_in_price=trade_in_price,
                            stock_count=stock_count,
                            meta_data=json.dumps(line),
                            scrape_instance=str(scrape_instance) if scrape_instance else None,
                        )
                        row = create_db_row(data=db_row_data)
                        insert_rows.append(row)

        except Exception as e:
            # Basic error logging
            print(f"Error processing line {line}: {e}")
            # For production, consider logging to Supabase as in other scrapers
            # log_to_supabase("error", f"Error processing Compa line: {e}", {"line": line, "scrape_instance": scrape_instance}, source="FastAPI - scrape_all_compa_recycle")

    if insert_rows:
        # supabase_client = get_supabase_client()
        # response = supabase_client.table("raw_product_scrapes").insert(insert_rows).execute()
        # return response
        print(len(insert_rows))

    return {"message": "Completed scrape, no data to insert."}


async def get_compa_data():
    url = f"{settings.COMPA_URL}/Argus/getList"
    headers = {
        "accept": "application/json",
        "X-PUBLIC-API-KEY": settings.COMPA_PUBLIC_KEY,
        "X-PRIVATE-API-KEY": settings.COMPA_PRIVATE_KEY,
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        
        data = response.json()
    return data
  


async def scrape_callisto():
    pass


@app.get("/parse_text_with_ai", tags=['AI'])
async def parse_text_with_ai(prompt:str, supplier:Optional[ str| None] = None):
    '''This endpoint take the input'''
    from agents import agent, get_deps    
    
    scrape_instance = uuid.uuid4()  #uuid
    
    deps = get_deps('str','str')
    
    result = await agent.run(
        deps= deps,
        user_prompt=prompt
    )
    
    # insert the results
    # print(result.output)
    
    return result.output