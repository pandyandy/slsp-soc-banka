import streamlit as st

st.title("Debug App - Step by Step")

# Step 1: Basic Streamlit
st.write("✅ Step 1: Basic Streamlit works")

# Step 2: Add imports
try:
    import json
    import pandas as pd
    import time
    from datetime import date, datetime, timezone, timedelta
    from PIL import Image
    st.write("✅ Step 2: Basic imports work")
except Exception as e:
    st.error(f"❌ Step 2: Import error: {e}")

# Step 3: Add database imports
try:
    import database.snowflake_manager
    from database.snowflake_manager import get_db_manager
    st.write("✅ Step 3: Database imports work")
except Exception as e:
    st.error(f"❌ Step 3: Database import error: {e}")

# Step 4: Try to get database manager
try:
    db_manager = get_db_manager()
    st.write("✅ Step 4: Database manager created")
except Exception as e:
    st.error(f"❌ Step 4: Database manager error: {e}")

# Step 5: Try to get connection
try:
    conn = db_manager.get_connection()
    if conn:
        st.write("✅ Step 5: Database connection successful")
    else:
        st.write("⚠️ Step 5: Database connection returned None")
except Exception as e:
    st.error(f"❌ Step 5: Database connection error: {e}")

# Step 6: Try to initialize table
try:
    if conn:
        table_initialized = db_manager.initialize_table()
        if table_initialized:
            st.write("✅ Step 6: Table initialization successful")
        else:
            st.write("⚠️ Step 6: Table initialization failed")
    else:
        st.write("⚠️ Step 6: Skipped table initialization (no connection)")
except Exception as e:
    st.error(f"❌ Step 6: Table initialization error: {e}")

st.write("---")
st.write("If you see this message, the basic app structure works.")
st.write("The 90-second restart issue is likely in the complex form logic or AI processing.")
