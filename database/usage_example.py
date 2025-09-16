"""
Example usage of the optimized SnowflakeManager
"""
from snowflake_manager import get_db_manager

def main():
    # Get the database manager instance
    db_manager = get_db_manager()
    
    # Initialize connection once at the beginning
    if not db_manager.initialize_connection():
        print("❌ Failed to initialize database connection")
        return
    
    print("✅ Database connection initialized and cached")
    
    # Initialize table (only needed once)
    if not db_manager.initialize_table():
        print("❌ Failed to initialize table")
        return
    
    print("✅ Table initialized")
    
    # Now you can read data by CID as many times as needed
    cid = "example_cid_123"
    
    # Read table data based on CID
    data = db_manager.read_table_by_cid(cid)
    if data:
        print(f"✅ Found data for CID: {cid}")
        print(f"Data keys: {list(data.keys())}")
    else:
        print(f"📝 No data found for CID: {cid}")
    
    # Save some example data
    example_data = {
        "name": "John Doe",
        "email": "john@example.com",
        "age": 30
    }
    
    if db_manager.save_form_data(cid, example_data):
        print(f"✅ Saved data for CID: {cid}")
    else:
        print(f"❌ Failed to save data for CID: {cid}")
    
    # Read the data back
    saved_data = db_manager.read_table_by_cid(cid)
    if saved_data:
        print(f"✅ Retrieved saved data: {saved_data}")

if __name__ == "__main__":
    main()
