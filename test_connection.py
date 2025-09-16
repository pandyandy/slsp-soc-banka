import streamlit as st

st.title("Test Snowflake Connection")

# Test connection with timeout protection
try:
    st.write("🔄 Testing Snowflake connection...")
    
    # Import and create database manager
    from database.snowflake_manager import get_db_manager
    db_manager = get_db_manager()
    
    # Try to get connection
    conn = db_manager.get_connection()
    
    if conn:
        st.success("✅ Connection successful!")
        
        # Test a simple query
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT CURRENT_TIMESTAMP()")
            result = cursor.fetchone()
            cursor.close()
            
            st.success(f"✅ Query successful! Current time: {result[0]}")
            
        except Exception as e:
            st.error(f"❌ Query failed: {e}")
            
    else:
        st.error("❌ Connection failed - returned None")
        
except Exception as e:
    st.error(f"❌ Connection test failed: {e}")

st.write("---")
st.write("If you see this message, the connection test completed.")
