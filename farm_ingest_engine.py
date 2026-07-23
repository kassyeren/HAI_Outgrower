import os
import geopandas as gpd
import fiona
from shapely.geometry import Polygon
from supabase import create_client, Client

# Enable KML driver layer inside fiona
fiona.drvsupport.supported_drivers['KML'] = 'rw'

SUPABASE_URL = https://zuuwkfxphpknuenmavta.supabase.co/rest/v1/
SUPABASE_KEY = sb_publishable_ZvAEDqVPsJpPdrP9NkAQHQ_XKMbCxcD # Service role key bypasses RLS rules during backend import
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def Ingest_Farm_Data(farmer_name: str, farm_loc: str, farm_dist: str, kml_path: str, id_image_path: str):
    print(f"🚜 Running Farm Ingestion Pipeline for: {farmer_name}")
    
    # --- STEP 1: Parse Spatial KML & Calculate Acreage ---
    if not os.path.exists(kml_path):
        raise FileNotFoundError(f"KML file missing at {kml_path}")
        
    gdf = gpd.read_file(kml_path, driver='KML')
    raw_geom = gdf.geometry.iloc[0]
    
    if not isinstance(raw_geom, Polygon):
        raise ValueError("Provided spatial layout in KML must be a valid Polygon boundary.")
        
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)
        raw_geom = gdf.geometry.iloc[0]

    wkt_geometry = raw_geom.wkt
    
    # Calculate geometric surface space area in Acres
    # 1 square meter = 0.000247105 acres
    sq_meters_area = gdf.to_crs(epsg=3857).geometry.iloc[0].area 
    calculated_acres = round(sq_meters_area * 0.000247105, 2)
    print(f"📐 Boundary parsed. Computed size: {calculated_acres} Acres")

    # --- STEP 2: Upload Government ID Image to Supabase S3 Storage ---
    if not os.path.exists(id_image_path):
        raise FileNotFoundError(f"ID card scan file missing at {id_image_path}")
        
    file_extension = os.path.splitext(id_image_path)[1].lower()
    safe_farmer_id = farmer_name.lower().replace(" ", "_")
    storage_destination_path = f"gov_ids/{safe_farmer_id}_id{file_extension}"
    
    print("📤 Sending ID file copy to Supabase Private Bucket...")
    with open(id_image_path, 'rb') as f:
        file_buffer = f.read()
        
    supabase.storage.from_("gov_ids").upload(
        path=storage_destination_path,
        file=file_buffer,
        file_options={"content-type": f"image/{file_extension.replace('.', '')}", "x-upsert": "true"}
    )

    # --- STEP 3: Write Transactions to database tables ---
    print("💾 Committing attributes and boundary records to database tables...")
    try:
        # 1. Populate Core Farmer Profile
        farmer_payload = {
            "farmer_name": farmer_name,
            "farm_dist": farm_dist
        }
        supabase.table("farmer_profiles").upsert(farmer_payload).execute()
        
        # 2. Populate Document Metadata Reference
        doc_payload = {
            "farmer_name": farmer_name,
            "storage_path": storage_destination_path
        }
        supabase.table("farmer_documents").upsert(doc_payload).execute()
        
        # 3. Populate Spatial Farm Parcel Row
        spatial_payload = {
            "farmer_name": farmer_name,
            "farm_loc": farm_loc,
            "farm_size": calculated_acres, # Injected value generated from calculation step
            "geom": f"SRID=4326;{wkt_geometry}"
        }
        supabase.table("farm_parcels").upsert(spatial_payload).execute()
        
        print(f"✨ Successfully integrated records for {farmer_name}'s farm plot!")
        
    except Exception as db_err:
        print(f"❌ Transaction Failure: {str(db_err)}")
        raise db_err

# --- Run Application Pipeline Code Execution ---
if __name__ == "__main__":
    Ingest_Farm_Data(
        farmer_name="Kwame Mensah",
        farm_loc="Sefwi Wiawso Road, Plot 4",
        farm_dist="Sefwi-Wiawso",
        kml_path="farm_boundary.kml",
        id_image_path="farmer_passport.jpg"
    )
