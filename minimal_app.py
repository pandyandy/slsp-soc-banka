import streamlit as st
import json
import pandas as pd
import time
from datetime import date, datetime, timezone, timedelta

# Force reload the database manager to get the latest version
import importlib
import database.snowflake_manager
from database.snowflake_manager import get_db_manager

# Load and encode logo
import os
import base64
from PIL import Image

mini_logo_path = os.path.join(os.path.dirname(__file__), "static", "logo_mini.png")
logo_path = os.path.join(os.path.dirname(__file__), "static", "logo.png")

MINI_LOGO = Image.open(mini_logo_path)

# Load and encode logo
with open(logo_path, "rb") as f:
    logo_data = base64.b64encode(f.read()).decode()

st.set_page_config(
    page_title="Sociálna banka – Dotazník (Minimal)", 
    page_icon=MINI_LOGO, 
    layout="wide")

def background_color(background_color, text_color, header_text, text=None):
    content = f'<div style="font-size:20px;margin:0px 0;">{header_text}</div>'
    if text:
        content += f'<div style="font-size:16px;margin-top:5px;">{text}</div>'
    
    st.markdown(f'<div style="background-color:{background_color};color:{text_color};border-radius:0px;padding:10px;margin:0px 0;">{content}</div>', unsafe_allow_html=True)

def initialize_connection_once():
    """Initialize database connection and check table status (runs only once per session)"""
    # Check if already initialized in session state
    if "db_manager" in st.session_state and "connection_initialized" in st.session_state:
        return st.session_state.db_manager, True, "✅ Using cached database connection"
    
    try:
        db_manager = get_db_manager()
        
        # Test connection
        conn = db_manager.get_connection()
        if not conn:
            return None, False, "❌ Failed to connect to Snowflake workspace"
        
        # Initialize table if needed (only once)
        table_initialized = db_manager.initialize_table()
        if not table_initialized:
            return db_manager, False, "⚠️ Connected but failed to initialize SLSP_DEMO table"
        
        # Cache in session state
        st.session_state.db_manager = db_manager
        st.session_state.connection_initialized = True
        
        return db_manager, True, "✅ Connected to workspace and SLSP_DEMO table ready"
        
    except Exception as e:
        return None, False, f"❌ Connection error: {str(e)}"

def main():
    st.markdown(f"""
        <div style="
            background-color: #2870ed; 
            padding: 20px; 
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        ">
            <div>
                <div style="color: white; font-size: 32px; font-weight: bold;">
                    Sociálna banka – Dotazník (Minimal)
                </div>
            </div>
            <div>
                <img src="data:image/png;base64,{logo_data}" style="height: 60px;" />
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with st.sidebar:
        st.header("Vyhľadať CID")
        
        # CID input and lookup section
        cid = st.text_input(
            "CID", 
            placeholder="Zadajte CID klienta",
            label_visibility="collapsed",
        )
        lookup_clicked = st.button(
            "Vyhľadať",
            type="primary",
            use_container_width=True)
    
    # Initialize session state for CID lookup
    if "cid_checked" not in st.session_state:
        st.session_state.cid_checked = False
    if "cid_exists" not in st.session_state:
        st.session_state.cid_exists = False
    if "existing_data" not in st.session_state:
        st.session_state.existing_data = {}
    if "current_cid" not in st.session_state:
        st.session_state.current_cid = ""
    
    # Handle CID lookup
    if lookup_clicked and cid.strip():
        st.write("🔍 Searching for CID...")
        
        # Initialize database connection only when user clicks "Vyhľadať"
        if "db_manager" not in st.session_state:
            db_manager, conn_status, conn_message = initialize_connection_once()
        else:
            db_manager, conn_status, conn_message = initialize_connection_once()
        
        # Check if connection was successful
        if not db_manager:
            st.error("❌ Failed to connect to database. Please try again.")
            st.stop()
        
        st.write(f"📊 Connection status: {conn_message}")
        
        # Use the optimized database manager method to get data with metadata
        existing_data = db_manager.load_form_data(cid.strip())
        
        if existing_data:
            cid_exists = True
            # Remove metadata from form data before storing in session
            form_data = {k: v for k, v in existing_data.items() if not k.startswith('_')}
            message = f"✅ CID '{cid}' found in database"
        else:
            cid_exists = False
            form_data = {}
            message = f"📝 No record found for CID '{cid}'. A new form will be created."
        
        st.session_state.cid_checked = True
        st.session_state.cid_exists = cid_exists
        st.session_state.existing_data = form_data
        st.session_state.current_cid = cid.strip()
        st.session_state.last_updated_info = existing_data.get('_last_updated', None) if existing_data else None
        
        # Display lookup result immediately
        if cid_exists is True:
            st.sidebar.success(f"Formulár nájdený")
        elif cid_exists is False:
            st.sidebar.info(f"Nový formulár bude vytvorený")
        
        st.success(message)
    
    # Reset if CID changed
    if cid.strip() != st.session_state.current_cid:
        st.session_state.cid_checked = False
    
    # Show simple form only after CID is checked
    if st.session_state.cid_checked and cid.strip() and "db_manager" in st.session_state:
        st.markdown("---")
        st.write("## Simple Form")
        
        # Simple form fields
        meno_priezvisko = st.text_input("Meno a priezvisko klienta:", value=st.session_state.existing_data.get("meno_priezvisko", ""))
        pribeh = st.text_area("Príbeh klienta:", value=st.session_state.existing_data.get("pribeh", ""), height=100)
        
        # Simple save button
        if st.button("💾 Save Data", type="primary"):
            if not cid.strip():
                st.error("❌ CID is required")
            else:
                # Create simple data to save
                data_to_save = {
                    "meno_priezvisko": meno_priezvisko,
                    "pribeh": pribeh,
                    "timestamp": datetime.now().isoformat()
                }
                
                # Save data
                db_manager = st.session_state.get("db_manager")
                if db_manager:
                    success = db_manager.save_form_data(cid.strip(), data_to_save)
                    if success:
                        st.success("✅ Data saved successfully!")
                    else:
                        st.error("❌ Failed to save data")
                else:
                    st.error("❌ Database not connected")
    
    elif cid.strip():
        st.markdown("---")
        st.info("💡 Kliknite na 'Vyhľadať' pre prístup k formuláru")
    else:
        st.markdown("---")
        st.info("💡 Vložte CID a kliknite na 'Vyhľadať' pre prístup k formuláru")

if __name__ == "__main__":
    main()
