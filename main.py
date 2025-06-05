from math import log
import re
from fastapi import FastAPI, Request
import httpx
from httpx import AsyncClient, Response
import json
from supabase import create_client, Client
from config import get_settings
from typing import Optional
import uuid

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
        # foxway_data = response.text
    
    json_data = response.json()
    # print(json_data)
    
    # write this json to disk temporarily
    # with open("foxway_data.json", "w") as file:
    #     file.write(json.dumps(json_data, indent=4))
    
    await write_scrape_to_supabase(manufacturer, partial_vat, json_data, scrape_instance=scrape_instance)


# @app.get("/write_scrape_to_supabase")
async def write_scrape_to_supabase(manufacturer:str, partial_vat:bool, data:dict, scrape_instance: Optional[uuid.UUID] = None):
    # read the scraped data from disk
    # with open("foxway_data.json", "r") as file:
    #     foxway_data = json.loads(file.read())
        
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
    # print(f"Processing item {manufacturer} for partial_vat {partial_vat} ----------------")
    for line,i in zip(data, range(len(data))):

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
            

@app.get("/scrape_all_foxway")
async def scrape_all_foxway(request:Request, do_scrape: bool = False):
    if not do_scrape:
        log_to_supabase("warning", "Scraping is disabled", {"do_scrape": do_scrape}, source="FastAPI - scrape_all_foxway")
        return {"message": "Scraping is disabled. Set do_scrape to True to enable."}
    manufacturers = ["huawei", "apple", "samsung"]
    partial_vat = [True, False]  # Example values for partial VAT
    scrape_instance = uuid.uuid4()  #uuid
    
    log_to_supabase("info", "Starting scrape for all manufacturers and VAT settings", {"manufacturers": manufacturers, "partial_vat": partial_vat, "scrape_instance": str(scrape_instance), "request_client": str(request.client)}, source="FastAPI - scrape_all_foxway")
    
    for manufacturer in manufacturers:
        for vat in partial_vat:
            await scrape_foxway(manufacturer, vat, scrape_instance)
    
    log_to_supabase("info", "Completed scrape for all manufacturers and VAT settings", {"manufacturers": manufacturers, "partial_vat": partial_vat, "scrape_instance": str(scrape_instance)}, source="FastAPI - scrape_all_foxway")
    
    return {"message": "API Scrape Completed"}
    
        
