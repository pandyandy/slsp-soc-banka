import streamlit as st

st.title("Debug Connection Only")

# Test 1: Basic Streamlit
st.write("✅ Basic Streamlit works")

# Test 2: Import database module
try:
    import database.snowflake_manager
    st.write("✅ Database module imported")
except Exception as e:
    st.error(f"❌ Database module import failed: {e}")
    st.stop()

# Test 3: Import get_db_manager
try:
    from database.snowflake_manager import get_db_manager
    st.write("✅ get_db_manager imported")
except Exception as e:
    st.error(f"❌ get_db_manager import failed: {e}")
    st.stop()

# Test 4: Create database manager
try:
    st.write("🔄 Creating database manager...")
    db_manager = get_db_manager()
    st.write("✅ Database manager created")
except Exception as e:
    st.error(f"❌ Database manager creation failed: {e}")
    st.stop()

# Test 5: Try to get connection (this is likely where it fails)
try:
    st.write("🔄 Getting database connection...")
    st.write("This might take a moment...")
    
    conn = db_manager.get_connection()
    
    if conn:
        st.write("✅ Database connection successful")
    else:
        st.write("⚠️ Database connection returned None")
        
except Exception as e:
    st.error(f"❌ Database connection failed: {e}")
    st.write("This is likely where the 90-second restart happens!")

st.write("---")
st.write("If you see this message, the connection process completed.")
