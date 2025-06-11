from fastapi import FastAPI, Request
import re
import httpx
import json
from supabase import create_client, Client
from config import get_settings
from typing import Optional
import uuid
from fastapi.responses import StreamingResponse
import csv
import io
from datetime import datetime

app = FastAPI()
settings = get_settings()


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


@app.get("/")
async def root():
    return {"greeting": "Hello, World!", "message": "Welcome to FastAPI!"}


# @app.get("/scrape_foxway")
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


# @app.get("/write_scrape_to_supabase")
async def write_scrape_to_supabase(manufacturer:str, partial_vat:bool, data:dict, scrape_instance: Optional[uuid.UUID] = None):

        
    # we know manufactureer id Huawei is 137 and vat margin is False
    supabase_client = get_supabase_client()
    
    supabase_schema='''
        create table public.raw_product_scrapes (
            scrape_id uuid not null default gen_random_uuid (),
            source_id uuid null,
            entry_date timestamp with time zone null default CURRENT_TIMESTAMP,
            make text not null,
            model text not null,
            storage_capacity text null,
            grade text null,
            colour text null,
            ce_mark boolean null,
            partial_vat boolean null,
            purchase_price numeric(10, 2) null,
            trade_in_price numeric(10, 2) null,
            stock_count integer null,
            meta_data text null,
            scrape_instance uuid null,
            constraint raw_product_scrapes_pkey primary key (scrape_id),
            constraint raw_product_scrapes_source_id_fkey foreign KEY (source_id) references sources (source_id) on delete RESTRICT
        ) TABLESPACE pg_default;
    '''
    example_data ='''    {
        "ProductName": "Huawei Honor 10 128GB",
        "ItemVariantId": 18797,
        "ItemGroupId": 1,
        "ItemGroupName": "Mobiles",
        "DimensionGroupId": 1,
        "DimensionGroupName": "Mobile devices",
        "Quantity": 1,
        "Price": 80.0,
        "CurrencyIsoCode": "EUR",
        "SKU": "00101879700111",
        "Dimension": [
            {
                "Key": "Color",
                "Value": "Blue"
            },
            {
                "Key": "Cloud Lock",
                "Value": "CloudOFF"
            },
            {
                "Key": "Appearance",
                "Value": "Grade AB"
            },
            {
                "Key": "Functionality",
                "Value": "Working"
            },
            {
                "Key": "Boxed",
                "Value": "Unboxed"
            }
        ],
        "Ean": null,
        "Mpn": "51092LYY"
    },'''

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
            
# Placeholder for a more robust model code generation/lookup
# This will be the most complex part to get right and will need your detailed rules/mappings
def get_model_code(make: str, model_name: str) -> str:
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

@app.get("/scrape_all_foxway")
async def scrape_all_foxway(request:Request, do_scrape: bool = False, caller: Optional[str] = None):
    caller = caller or "Unknown Caller"
    if not do_scrape:
        log_to_supabase("warning", "Scraping is disabled", {"do_scrape": do_scrape, "request_client": str(request.client), "caller":caller}, source="FastAPI - scrape_all_foxway")
        return {"message": "Scraping is disabled. Set do_scrape to True to enable."}
    manufacturers = ["huawei", "apple", "samsung"]
    partial_vat = [True, False]  # Example values for partial VAT
    scrape_instance = uuid.uuid4()  #uuid
    
    log_to_supabase("info", "Starting scrape for all manufacturers and VAT settings", {"manufacturers": manufacturers, "partial_vat": partial_vat, "scrape_instance": str(scrape_instance), "request_client": str(request.client), "caller": caller}, source="FastAPI - scrape_all_foxway")
    
    for manufacturer in manufacturers:
        for vat in partial_vat:
            await scrape_foxway(manufacturer, vat, scrape_instance)
    
    log_to_supabase("info", "Completed scrape for all manufacturers and VAT settings", {"manufacturers": manufacturers, "partial_vat": partial_vat, "scrape_instance": str(scrape_instance), "request_client": str(request.client), "caller": caller}, source="FastAPI - scrape_all_foxway")
    
    return {"message": "API Scrape Completed"}
    
        

@app.get("/download/latest_device_scrape_csv")
async def download_latest_device_scrape_csv():
    supabase_client = get_supabase_client()

    # 1. Identify the latest scrape_instance
    latest_log_response = (
        supabase_client.table("logs")
        .select("context, created_at")
        .eq("log_level", "info")  # Assuming we want to filter by log level
        .eq("source", "FastAPI - scrape_all_foxway")  # Filter by source
        .not_.is_("context", "null") # Ensure context is not null
        # .not_.is_("context->>'scrape_instance'", "null") # Check if scrape_instance key exists and is not null
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not latest_log_response.data:
        log_to_supabase("error", "No suitable log entry found to determine the latest scrape instance.", source="FastAPI - download_latest_device_scrape_csv")
        return {"message": "No completed scrape instance found in logs."}

    log_entry_data = latest_log_response.data[0]
    latest_scrape_instance_id = log_entry_data.get("context", {}).get("scrape_instance")
    log_created_at_str = log_entry_data.get("created_at")

    if not latest_scrape_instance_id:
        log_to_supabase("error", "Latest log entry found but does not contain a scrape_instance ID.", {"log_data": latest_log_response.data[0]}, source="FastAPI - download_latest_device_scrape_csv")
        return {"message": "Latest scrape instance ID could not be determined."}

    # 2. Retrieve device scrapes for the latest_scrape_instance_id
    #    Selecting only the specified columns
    columns_to_select = "make, model, storage_capacity, grade, purchase_price, stock_count, colour, ce_mark, partial_vat"
    all_device_scrapes = []
    page_size = 1000  # Align with suspected server-side limit
    offset = 0
    
    while True:
        current_page_response = (
            supabase_client.table("raw_product_scrapes")
            .select(columns_to_select)
            .eq("scrape_instance", latest_scrape_instance_id)
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

    # 3. Format data as CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    header = ["make", "model", "storage_capacity", "grade", "purchase_price", "stock_count", "colour", "ce_mark", "partial_vat", "SKU"]
    writer.writerow(header)

    if not all_device_scrapes:
        log_to_supabase("info", f"No device scrapes found for scrape_instance_id: {latest_scrape_instance_id}", source="FastAPI - download_latest_device_scrape_csv")
        # Return an empty CSV if no data
    else:
        # Write data rows
        for row_data in all_device_scrapes:
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
    
    output.seek(0) # Reset buffer position to the beginning

    # 4. Serve the CSV file for download
    if log_created_at_str:
        # Supabase returns ISO 8601 format, e.g., "2023-10-26T10:30:00.123456+00:00"
        try:
            log_datetime = datetime.fromisoformat(log_created_at_str)
            filename_timestamp = log_datetime.strftime("%Y%m%d_%H%M%S")
        except ValueError:
            # Fallback if parsing fails
            filename_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_to_supabase("warning", f"Could not parse log_created_at: {log_created_at_str}. Using current time for filename.", source="FastAPI - download_latest_device_scrape_csv")
    else:
        # Fallback if created_at is not available
        filename_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_to_supabase("warning", "log_created_at not found in log entry. Using current time for filename.", source="FastAPI - download_latest_device_scrape_csv")

    filename = f"foxway_latest_device_scrape_{filename_timestamp}.csv"
    
    log_to_supabase("info", f"Successfully generated CSV for scrape_instance_id: {latest_scrape_instance_id}. Filename: {filename}", {"rows_exported": len(all_device_scrapes)}, source="FastAPI - download_latest_device_scrape_csv")

    return StreamingResponse(
        iter([output.getvalue()]), # iter() is used as StreamingResponse expects an iterator
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
