"""
Optimized Snowflake Database Manager using Snowpark
Handles all database operations with connection pooling and retry logic
"""
import streamlit as st
from snowflake.snowpark import Session
from snowflake.snowpark.context import get_active_session
import json
import pandas as pd
import time
import os
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
import logging
from contextlib import contextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SnowflakeDBManager:
    """Database manager class for Snowflake operations"""
    
    def __init__(self):
        self.session = None
        self._initialize_session_state()
    
    def _initialize_session_state(self):
        """Initialize session state for Snowflake session"""
        if 'snowflake_session' not in st.session_state:
            st.session_state['snowflake_session'] = None
    
    def get_session(self):
        """Get or create Snowflake session"""
        return get_snowflake_session()
    
    def initialize_table(self):
        """Initialize the main table if it doesn't exist"""
        try:
            session = self.get_session()
            if not session:
                return False
            
            # Check if table exists and create if needed
            table_name = st.secrets.get("WORKSPACE_SOURCE_TABLE_ID", "SLSP_DEMO")
            check_table_query = f"SHOW TABLES LIKE '{table_name}'"
            result = session.sql(check_table_query).collect()
            
            if not result:
                # Create table if it doesn't exist
                create_table_query = f"""
                CREATE TABLE IF NOT EXISTS "{table_name}" (
                    "CID" VARCHAR(255) PRIMARY KEY,
                    "DATA" VARIANT,
                    "LAST_UPDATED" TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
                    "CREATED_AT" TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
                    "PHASE" INTEGER DEFAULT 0
                )
                """
                session.sql(create_table_query).collect()
                logger.info(f"Created table {table_name}")
            
            return True
        except Exception as e:
            logger.error(f"Failed to initialize table: {e}")
            return False
    
    def read_row_by_cid(self, cid: str, table_name: str = None):
        """Read a specific row by CID"""
        try:
            session = self.get_session()
            if not session:
                return None
            
            if not table_name:
                table_name = st.secrets.get("WORKSPACE_SOURCE_TABLE_ID", "SLSP_DEMO")
            
            query = f'SELECT * FROM "{table_name}" WHERE "CID" = \'{cid}\''
            result = session.sql(query).collect()
            
            if result:
                # Convert to pandas DataFrame
                df = pd.DataFrame([row.asDict() for row in result])
                return df
            return None
            
        except Exception as e:
            logger.error(f"Failed to read row by CID {cid}: {e}")
            return None
    
    def insert_or_update_data(self, cid: str, data: dict, table_name: str = None):
        """Insert new data or update existing data for a CID"""
        try:
            session = self.get_session()
            if not session:
                return False
            
            if not table_name:
                table_name = st.secrets.get("WORKSPACE_SOURCE_TABLE_ID", "SLSP_DEMO")
            
            # Check if CID exists
            existing_row = self.read_row_by_cid(cid, table_name)
            
            if existing_row is not None and not existing_row.empty:
                # Update existing row
                data_json = json.dumps(data)
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                
                update_query = f"""
                UPDATE "{table_name}" 
                SET "DATA" = PARSE_JSON('{data_json}'),
                    "LAST_UPDATED" = '{current_time}',
                    "PHASE" = 1
                WHERE "CID" = '{cid}'
                """
                session.sql(update_query).collect()
                logger.info(f"Updated row for CID: {cid}")
            else:
                # Insert new row
                data_json = json.dumps(data)
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                
                insert_query = f"""
                INSERT INTO "{table_name}" ("CID", "DATA", "LAST_UPDATED", "CREATED_AT", "PHASE")
                VALUES ('{cid}', PARSE_JSON('{data_json}'), '{current_time}', '{current_time}', 1)
                """
                session.sql(insert_query).collect()
                logger.info(f"Inserted new row for CID: {cid}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to insert/update data for CID {cid}: {e}")
            return False

    # ==============================
    # Compatibility methods used by app_ws.py
    # ==============================
    def get_session_for_direct_use(self):
        """Return the underlying Snowflake session (for direct SQL use)."""
        return self.get_session()

    def load_form_data(self, cid: str, table_name: str = None) -> Optional[Dict[str, Any]]:
        """Load form data as a Python dict for a given CID with metadata.

        Returns a dict of the DATA column plus metadata keys:
          - _last_updated (ISO string)
          - _created_at (ISO string)
          - _phase (int)
        Returns None if no record exists.
        """
        try:
            if not table_name:
                table_name = st.secrets.get("WORKSPACE_SOURCE_TABLE_ID", "SLSP_DEMO")

            df = self.read_row_by_cid(cid, table_name)
            if df is None or df.empty:
                return None

            row = df.iloc[0]
            data_value = row.get("DATA")
            if isinstance(data_value, str):
                try:
                    data_obj = json.loads(data_value)
                except Exception:
                    # If it's a plain string not JSON, store as a simple field
                    data_obj = {"_raw_data": data_value}
            elif isinstance(data_value, (dict, list)):
                data_obj = data_value
            else:
                # Snowpark might return a variant-like object; convert via json.dumps if possible
                try:
                    data_obj = json.loads(json.dumps(data_value))
                except Exception:
                    data_obj = {}

            # Attach metadata
            last_updated = row.get("LAST_UPDATED")
            created_at = row.get("CREATED_AT")
            phase = row.get("PHASE", 0)

            if isinstance(last_updated, datetime):
                last_updated_iso = last_updated.replace(microsecond=0).isoformat() + "Z"
            else:
                last_updated_iso = str(last_updated) if last_updated is not None else None

            if isinstance(created_at, datetime):
                created_at_iso = created_at.replace(microsecond=0).isoformat() + "Z"
            else:
                created_at_iso = str(created_at) if created_at is not None else None

            data_obj["_last_updated"] = last_updated_iso
            data_obj["_created_at"] = created_at_iso
            data_obj["_phase"] = int(phase) if pd.notna(phase) else 0

            return data_obj
        except Exception as e:
            logger.error(f"Failed to load form data for CID {cid}: {e}")
            return None

    def save_form_data(self, cid: str, data_to_save: Dict[str, Any], table_name: str = None) -> bool:
        """Save form data; inserts or updates as needed. Returns True on success."""
        try:
            # Remove internal metadata keys before saving
            cleaned = {k: v for k, v in data_to_save.items() if not str(k).startswith("_")}
            return self.insert_or_update_data(cid, cleaned, table_name)
        except Exception as e:
            logger.error(f"Failed to save form data for CID {cid}: {e}")
            return False

    def fix_corrupted_record(self, cid: str, table_name: str = None) -> bool:
        """Attempt to fix a corrupted JSON record by re-serializing and saving it."""
        try:
            existing = self.load_form_data(cid, table_name)
            if existing is None:
                # Nothing to fix
                return False

            # Basic cleanup: ensure the DATA is JSON-serializable and remove problematic characters
            def _clean_obj(obj):
                if isinstance(obj, str):
                    return obj.replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')
                if isinstance(obj, list):
                    return [_clean_obj(x) for x in obj]
                if isinstance(obj, dict):
                    return {str(_clean_obj(k)): _clean_obj(v) for k, v in obj.items()}
                return obj

            cleaned = {k: v for k, v in existing.items() if not str(k).startswith("_")}
            cleaned = _clean_obj(cleaned)
            return self.insert_or_update_data(cid, cleaned, table_name)
        except Exception as e:
            logger.error(f"Failed to fix corrupted record for CID {cid}: {e}")
            return False

# Global instance
_db_manager = None

def get_db_manager():
    """Get or create the global database manager instance"""
    global _db_manager
    if _db_manager is None:
        _db_manager = SnowflakeDBManager()
    return _db_manager

def map_json_to_snowflake_type(json_type: str) -> str:
    """Map JSON schema types to Snowflake data types"""
    type_mapping = {
        'str': 'VARCHAR(16777216)',
        'int': 'INTEGER',
        'float': 'FLOAT',
        'bool': 'BOOLEAN',
        'datetime': 'TIMESTAMP_NTZ',
        'date': 'DATE'
    }
    return type_mapping.get(json_type, 'VARCHAR(16777216)')

def get_snowflake_session():
    """Create and return a Snowflake session using Snowpark."""
    if 'snowflake_session' not in st.session_state or st.session_state['snowflake_session'] is None:
        # Set up Snowflake connection parameters from st.secrets
        try:
            snowflake_config = {
                "account": st.secrets["account"],
                "user": st.secrets["user"],
                "password": st.secrets["password"],
                "warehouse": st.secrets["warehouse"],
                "database": st.secrets["database"],
                "schema": st.secrets["schema"]
            }

            # Create and store the session in session state
            st.session_state["snowflake_session"] = Session.builder.configs(snowflake_config).create()
            #client.create_event(message='Streamlit App Snowflake Init Connection', event_type='keboola_data_app_snowflake_init')
        except Exception as e:
            st.error(f"Error creating Snowflake session: {e}")
            return None

        return st.session_state["snowflake_session"]
    # Return the existing session if already created
    return st.session_state["snowflake_session"]



def read_data_snowflake(table_id):
    """Read data from Snowflake table into a Pandas DataFrame using Snowpark."""
    try:
        # Get the reusable Snowflake session
        session = get_snowflake_session()

        # Check if session is None
        if session is None:
            st.error("Snowflake session could not be created.")
            return
            
        # Load data from Snowflake table into a Pandas DataFrame
        columns = ['CID', 'DATA', 'LAST_UPDATED', 'CREATED_AT', 'PHASE']
        
        df_snowflake = session.table(table_id).select(columns).to_pandas()
        #client.create_event(message='Streamlit App Snowflake Read Table', event_type='keboola_data_app_snowflake_read_table', event_data=f'table_id: {table_id}')

        # Store in session state
        st.session_state['df'] = df_snowflake
        #st.write(df_snowflake)

    except Exception as e:
        st.error(f"Failed to load data from Snowflake: {e}")
        st.stop()


def execute_query_snowflake(query: str, return_result=False):
    # Step 3: Write the filter incrementally to the database using Snowpark
    try:
        # Get Snowflake session
        session = get_snowflake_session()
        result = session.sql(query).collect()
        #client.create_event(message='Streamlit App Snowflake Query', event_type='keboola_data_app_snowflake_query', event_data=f'Query: {query}')
        
        if return_result:
            return result
    except Exception as e:
        st.error(f"Failed to execute a query: {e}")
        if return_result:
            return None


def write_data_snowflake(df: pd.DataFrame, table_name: str, auto_create_table: bool = False, overwrite: bool = False) -> None:
    try:
        # Get Snowflake session
        session = get_snowflake_session()
        session.write_pandas(df=df, table_name=table_name, auto_create_table=auto_create_table, overwrite=overwrite).collect()
        #client.create_event(message='Streamlit App Snowflake Write Table', event_type='keboola_data_app_snowflake_write_table', event_data=f'table_id: {table_name}')
    except Exception as e:
        st.error(f"Failed to execute a query: {e}")


def save_changed_rows_snowflake(df_original, changed_rows, debug, progress):
    """Save only the changed rows with new values to a CSV file or Snowflake."""
     
    # Step 1: Standardize Primary Key Column Data Types
    pk_columns = ['CID']
    for col in pk_columns:
        df_original[col] = df_original[col].astype(str if col == 'CID' else 'int32')
        changed_rows[col] = changed_rows[col].astype(str if col == 'CID' else 'int32')
    
    # Log who and when is changing the values
    #changed_rows['HIST_DATA_MODIFIED_BY'] = st.session_state['user_email']
    #changed_rows['HIST_DATA_MODIFIED_WHEN'] = datetime.now()
    
    # Step 2: Ensure Timestamp Columns Are Converted to String Format
    timestamp_columns = ['LAST_UPDATED', 'CREATED_AT']
    default_timestamp = "1970-01-01 00:00:00.000"
    
    for timestamp_col in timestamp_columns:
        if timestamp_col in changed_rows.columns:
            changed_rows[timestamp_col] = changed_rows[timestamp_col].fillna(default_timestamp).astype(str)
        if timestamp_col in df_original.columns:
            df_original[timestamp_col] = df_original[timestamp_col].fillna(default_timestamp).astype(str)

    # Step 3: Merge DataFrames and Fill NaNs
    # Merge changed_rows with df_original on PK columns
    merged_df = pd.merge(
        changed_rows,
        df_original,
        on=pk_columns,
        how='left',
        suffixes=('', '_orig')
    )
    #'VYKON_SYSTEM', 'HODNOTY_SYSTEM'
    columns_to_update = ['DATA', 'PHASE', 'LAST_UPDATED', 'CREATED_AT', 'PHASE', 
                         ]

    # For each column, fill NaNs in changed_rows with values from df_original
    for col in columns_to_update:
        if col in merged_df.columns and col + '_orig' in merged_df.columns:
            merged_df[col] = merged_df[col].fillna(merged_df[col + '_orig'])
    
    # Drop the original columns with '_orig' suffix
    cols_to_drop = [col for col in merged_df.columns if col.endswith('_orig')]
    merged_df.drop(columns=cols_to_drop, inplace=True)

    # Now, merged_df contains the updated rows with NaNs filled
    df_updated = merged_df.copy()

    # Step 4: Ensure Numeric Columns Are Properly Formatted
    for col in ['PHASE']: #'VYKON_SYSTEM', 'HODNOTY_SYSTEM'
        if col in df_updated.columns:
            df_updated[col] = pd.to_numeric(df_updated[col], errors='coerce').fillna(0).astype(int)

    # Step 5: Apply Conditional Logic to Update LOCKED_TIMESTAMP
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # Format with milliseconds
    df_updated.loc[df_updated['PHASE'] == 1, 
                   'LAST_UPDATED'] = current_time
    
    # Step 6: Align with Expected Schema and Convert Datetimes to Strings
    file_path = os.path.join(os.path.dirname(__file__), './static/expected_schema.json')
    with open(file_path, 'r', encoding='utf-8') as file: 
        expected_schema = json.load(file)  
    
    for col, dtype in expected_schema.items():
        if col not in df_updated.columns:
            df_updated[col] = default_timestamp if 'datetime' in dtype else ('' if dtype == 'str' else 0)
        else:
            if dtype == 'str':
                df_updated[col] = df_updated[col].astype(str)
            elif 'int' in dtype:
                df_updated[col] = pd.to_numeric(df_updated[col], errors='coerce').fillna(0).astype('int')
            elif 'datetime' in dtype:
                df_updated[col] = pd.to_datetime(df_updated[col], errors='coerce').fillna(default_timestamp).astype(str)

    df_updated = df_updated.drop(columns=['PHASE'])
    
    # Step 7: Save Data
    if debug:
        file_path = os.path.join(os.path.dirname(__file__), 'data', 'in', 'tables', 'anonymized_data.csv')
        df_anonymized = pd.read_csv(file_path)
        df_anonymized.set_index(pk_columns, inplace=True)
        df_updated.set_index(pk_columns, inplace=True)
        df_anonymized.update(df_updated)
        df_anonymized.reset_index(inplace=True)
        df_anonymized.to_csv(file_path, index=False)
    else:
        table_name = st.secrets["WORKSPACE_SOURCE_TABLE_ID"]
        temp_table_name = f"TEMP_STAGING_{st.session_state['user_email'].replace('@', '_').replace('.', '_')}_{uuid.uuid4().hex}"
        
        create_temp_table_sql = f"CREATE OR REPLACE TRANSIENT TABLE \"{temp_table_name}\" (\n"
        columns = [f'"{col}" {map_json_to_snowflake_type(dtype)}' for col, dtype in expected_schema.items()]
        create_temp_table_sql += ",\n".join(columns) + "\n);"
        
        progress.progress(50, text="**Probíhá zápis změn...**")
        execute_query_snowflake(create_temp_table_sql)
        #st.write(df_updated)
        write_data_snowflake(df_updated, temp_table_name, auto_create_table=False, overwrite=False)

        update_sql = f"""
            UPDATE "{table_name}" AS target
            SET { ', '.join([f'target."{col}" = source."{col}"' for col in columns_to_update]) }
            FROM "{temp_table_name}" AS source
            WHERE { ' AND '.join([f'target."{col}" = source."{col}"' for col in pk_columns]) };
        """
        drop_temp_table_sql = f'DROP TABLE IF EXISTS "{temp_table_name}";'
        progress.progress(60, text="**Ukládám...**")
        update_result = execute_query_snowflake(update_sql)
        #st.write(update_result)
#        execute_query_snowflake(drop_temp_table_sql, client=client)
        if update_result and len(update_result) > 0:
            # The update completed successfully
            pass
        
    # Clear tracked changes
    #st.session_state['changed_rows'] = pd.DataFrame()
    #st.session_state['unsaved_warning_displayed'] = False
    
    read_data_snowflake(st.secrets["WORKSPACE_SOURCE_TABLE_ID"])

    pk_columns = ['CID']
    st.session_state['df_original'] = st.session_state['df'].set_index(pk_columns).copy()
    st.session_state['df_last_saved'] = st.session_state['df_original'].copy()

    st.session_state['grid_refresh_timestamp'] = datetime.now().timestamp()
    
    st.success("Změny uloženy, aplikace bude obnovena.")
    #st.rerun()
    return df_updated


