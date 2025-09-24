"""
Optimized Snowflake Database Manager
Handles all database operations with connection pooling and retry logic
"""
import streamlit as st
import snowflake.connector
import json
import pandas as pd
import time
from typing import Optional, Dict, Any, List
import logging
from contextlib import contextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SnowflakeManager:
    """Optimized Snowflake connection and operation manager"""
    
    def __init__(self):
        self.connection = None
        self.max_retries = 3
        
    @st.cache_resource
    def _create_connection(_self):
        """Create a new Snowflake connection with caching"""
        try:
            conn = snowflake.connector.connect(
                account=st.secrets["account"],
                user=st.secrets["user"],
                password=st.secrets["password"],
                warehouse=st.secrets["warehouse"],
                database=st.secrets["database"],
                schema=st.secrets["schema"],
                client_session_keep_alive=True,
                #login_timeout=60,
                #network_timeout=60,
                # Optimization: disable autocommit for batch operations
                autocommit=True
            )
            logger.info("Snowflake connection established successfully")
            return conn
        except Exception as e:
            logger.error(f"Failed to create Snowflake connection: {str(e)}")
            return None
    
    
    
    @contextmanager
    def get_cursor(self):
        """Context manager for database cursor operations"""
        # Create the connection if missing; otherwise reuse it
        if not self.connection:
            self.connection = self._create_connection()
        conn = self.connection
        if not conn:
            raise Exception("Unable to establish database connection")
        
        cursor = None
        try:
            cursor = conn.cursor()
            yield cursor
            conn.commit()  # Commit on successful operation
        except Exception as e:
            if conn:
                conn.rollback()  # Rollback on error
            logger.error(f"Database operation failed: {str(e)}")
            raise
        finally:
            if cursor:
                cursor.close()
    
    def execute_with_retry(self, operation_func, *args, **kwargs):
        """Execute database operation with retry logic"""
        for attempt in range(self.max_retries):
            try:
                return operation_func(*args, **kwargs)
            except Exception as e:
                error_msg = str(e).lower()
                if ("connection" in error_msg or "timeout" in error_msg) and attempt < self.max_retries - 1:
                    logger.warning(f"Database operation failed (attempt {attempt + 1}), retrying...")
                    # Clear connection to force reconnect
                    self.connection = None
                    time.sleep(1)  # Brief pause before retry
                    continue
                else:
                    logger.error(f"Database operation failed after {attempt + 1} attempts: {str(e)}")
                    raise
    
    def save_form_data(self, cid: str, form_data: Dict[str, Any], phase: int = None) -> bool:
        """Optimized form data save operation with proper data sanitization"""
        def _save_operation():
            with self.get_cursor() as cursor:
                # Check if record exists
                cursor.execute("SELECT CID FROM SLSP_DEMO WHERE CID = %s", (cid,))
                exists = cursor.fetchone() is not None
                
                # Sanitize form data before JSON serialization
                sanitized_data = self.sanitize_form_data(form_data)
                
                # Use parameterized query to avoid SQL injection issues
                json_data = json.dumps(sanitized_data, default=str, ensure_ascii=False)
                
                if exists:
                    if phase is not None:
                        cursor.execute(
                            "UPDATE SLSP_DEMO SET DATA = %s, PHASE = %s, LAST_UPDATED = CURRENT_TIMESTAMP() WHERE CID = %s",
                            (json_data, phase, cid)
                        )
                    else:
                        cursor.execute(
                            "UPDATE SLSP_DEMO SET DATA = %s, LAST_UPDATED = CURRENT_TIMESTAMP() WHERE CID = %s",
                            (json_data, cid)
                        )
                else:
                    if phase is not None:
                        cursor.execute(
                            "INSERT INTO SLSP_DEMO (CID, DATA, PHASE, CREATED_AT, LAST_UPDATED) VALUES (%s, %s, %s, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())",
                            (cid, json_data, phase)
                        )
                    else:
                        cursor.execute(
                            "INSERT INTO SLSP_DEMO (CID, DATA, CREATED_AT, LAST_UPDATED) VALUES (%s, %s, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())",
                            (cid, json_data)
                        )
                return True
        
        try:
            return self.execute_with_retry(_save_operation)
        except Exception as e:
            logger.error(f"Failed to save form data for CID {cid}: {str(e)}")
            return False
    
    def process_json_data(self, raw_data: str) -> Optional[Dict[str, Any]]:
        """Process raw JSON data with error handling and cleaning"""
        if not raw_data:
            return None
            
        try:
            # Try to parse as-is first
            return json.loads(raw_data)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parsing failed, attempting to clean data: {str(e)}")
            
            # Try cleaning the data with better newline handling
            try:
                cleaned_data = self.clean_json_data_advanced(raw_data)
                return json.loads(cleaned_data)
            except json.JSONDecodeError as e2:
                logger.error(f"JSON parsing failed even after cleaning: {str(e2)}")
                return None

    def clean_json_data(self, raw_data: str) -> str:
        """Clean JSON data by removing or replacing problematic characters"""
        # Remove control characters except for \n, \r, \t
        import re
        # Replace control characters with spaces (except newlines, carriage returns, tabs)
        cleaned = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', ' ', raw_data)
        return cleaned
    
    def clean_json_data_advanced(self, raw_data: str) -> str:
        """Advanced JSON cleaning specifically for newline issues"""
        # More aggressive approach - replace all newlines, tabs, and carriage returns
        cleaned = raw_data.replace('\n', '\\n')
        cleaned = cleaned.replace('\t', '\\t')
        cleaned = cleaned.replace('\r', '\\r')
        return cleaned
    
    def sanitize_form_data(self, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize form data to prevent JSON corruption"""
        import re
        sanitized = {}
        
        for key, value in form_data.items():
            if isinstance(value, str):
                # For string values, ensure they don't contain problematic characters
                # that could break JSON structure
                sanitized_value = value
                
                # Step 1: Replace newlines, tabs, and carriage returns with spaces
                sanitized_value = sanitized_value.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
                
                # Step 2: Replace any remaining control characters with spaces
                sanitized_value = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', ' ', sanitized_value)
                
                # Step 3: Clean up multiple spaces and trim
                sanitized_value = re.sub(r' +', ' ', sanitized_value).strip()
                
                # Step 4: Remove all quotes to prevent JSON corruption
                sanitized_value = sanitized_value.replace('"', '').replace('"', '').replace('"', '')
                sanitized_value = sanitized_value.replace(''', '').replace(''', '')
                
                sanitized[key] = sanitized_value
            elif isinstance(value, list):
                # For lists, sanitize each item
                sanitized_list = []
                for item in value:
                    if isinstance(item, dict):
                        sanitized_list.append(self.sanitize_form_data(item))
                    elif isinstance(item, str):
                        # Apply same sanitization to list items
                        item_clean = item.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
                        item_clean = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', ' ', item_clean)
                        item_clean = re.sub(r' +', ' ', item_clean).strip()
                        item_clean = item_clean.replace('"', '').replace('"', '').replace('"', '')
                        item_clean = item_clean.replace(''', '').replace(''', '')
                        sanitized_list.append(item_clean)
                    else:
                        sanitized_list.append(item)
                sanitized[key] = sanitized_list
            else:
                # For other types, keep as-is
                sanitized[key] = value
        
        return sanitized
    
    def fix_corrupted_record(self, cid: str) -> bool:
        """Fix a corrupted record by cleaning its JSON data"""
        def _fix_operation():
            with self.get_cursor() as cursor:
                # Get the raw data
                cursor.execute("SELECT DATA FROM SLSP_DEMO WHERE CID = %s", (cid,))
                row = cursor.fetchone()
                if not row:
                    return False
                
                raw_data = row[0]
                
                # Try to parse the JSON
                try:
                    parsed_data = json.loads(raw_data)
                    # If it parses successfully, sanitize and save
                    sanitized_data = self.sanitize_form_data(parsed_data)
                    fixed_json = json.dumps(sanitized_data, default=str, ensure_ascii=False)
                    
                    # Update the database
                    cursor.execute(
                        "UPDATE SLSP_DEMO SET DATA = %s, LAST_UPDATED = CURRENT_TIMESTAMP() WHERE CID = %s",
                        (fixed_json, cid)
                    )
                    return True
                    
                except json.JSONDecodeError:
                    # If JSON is corrupted, try to clean it
                    try:
                        # Use the advanced cleaning method
                        cleaned_data = self.clean_json_data_advanced(raw_data)
                        parsed_data = json.loads(cleaned_data)
                        
                        # Sanitize and save
                        sanitized_data = self.sanitize_form_data(parsed_data)
                        fixed_json = json.dumps(sanitized_data, default=str, ensure_ascii=False)
                        
                        # Update the database
                        cursor.execute(
                            "UPDATE SLSP_DEMO SET DATA = %s, LAST_UPDATED = CURRENT_TIMESTAMP() WHERE CID = %s",
                            (fixed_json, cid)
                        )
                        return True
                        
                    except Exception as e:
                        logger.error(f"Failed to fix corrupted record for CID {cid}: {str(e)}")
                        return False
        
        try:
            return self.execute_with_retry(_fix_operation)
        except Exception as e:
            logger.error(f"Failed to fix corrupted record for CID {cid}: {str(e)}")
            return False
    
    def debug_database_connection(self) -> Dict[str, Any]:
        """Debug method to check database connection and contents"""
        def _debug_operation():
            with self.get_cursor() as cursor:
                # Check if table exists
                cursor.execute("SHOW TABLES LIKE 'SLSP_DEMO'")
                tables = cursor.fetchall()
                
                # Get table info
                cursor.execute("DESCRIBE TABLE SLSP_DEMO")
                columns = cursor.fetchall()
                
                # Get record count
                cursor.execute("SELECT COUNT(*) FROM SLSP_DEMO")
                count = cursor.fetchone()[0]
                
                # Get sample CIDs
                cursor.execute("SELECT CID FROM SLSP_DEMO LIMIT 5")
                sample_cids = [row[0] for row in cursor.fetchall()]
                
                return {
                    'table_exists': len(tables) > 0,
                    'columns': [col[0] for col in columns],
                    'total_records': count,
                    'sample_cids': sample_cids
                }
        
        try:
            return self.execute_with_retry(_debug_operation)
        except Exception as e:
            logger.error(f"Database debug failed: {str(e)}")
            return {'error': str(e)}

    def get_all_records_dataframe(self) -> Optional[pd.DataFrame]:
        """Get all records from SLSP_DEMO table as pandas DataFrame"""
        def _get_all_dataframe_operation():
            with self.get_cursor() as cursor:
                # Get all records
                cursor.execute("SELECT * FROM SLSP_DEMO ORDER BY CID")
                rows = cursor.fetchall()
                
                if rows:
                    # Get column names
                    cursor.execute("DESCRIBE TABLE SLSP_DEMO")
                    columns_info = cursor.fetchall()
                    column_names = [col[0] for col in columns_info]
                    
                    # Create DataFrame with all rows
                    df = pd.DataFrame(rows, columns=column_names)
                    return df
                return None
        
        try:
            return self.execute_with_retry(_get_all_dataframe_operation)
        except Exception as e:
            logger.error(f"Failed to get all records DataFrame: {str(e)}")
            return None

    def get_raw_data(self, cid: str) -> Optional[Dict[str, Any]]:
        """Get raw data for a given CID without JSON parsing"""
        def _get_raw_operation():
            with self.get_cursor() as cursor:
                cid_escaped = cid.replace("'", "''")
                logger.info(f"Executing query for CID: {cid_escaped}")
                
                # First, let's check if the record exists at all
                cursor.execute(f"SELECT COUNT(*) FROM SLSP_DEMO WHERE CID = '{cid_escaped}'")
                count = cursor.fetchone()[0]
                logger.info(f"Found {count} records for CID {cid}")
                
                if count == 0:
                    # Let's see what CIDs actually exist
                    cursor.execute("SELECT CID FROM SLSP_DEMO LIMIT 10")
                    existing_cids = cursor.fetchall()
                    logger.info(f"Sample existing CIDs: {[row[0] for row in existing_cids]}")
                    return None
                
                # Now get the actual data
                cursor.execute(f"SELECT DATA, LAST_UPDATED, PHASE FROM SLSP_DEMO WHERE CID = '{cid_escaped}'")
                row = cursor.fetchone()
                logger.info(f"Query returned row: {row is not None}")
                
                if row:
                    return {
                        'raw_data': row[0],  # The raw JSON string
                        'last_updated': row[1],
                        'phase': row[2],
                        'data_length': len(row[0]) if row[0] else 0
                    }
                return None
        
        try:
            return self.execute_with_retry(_get_raw_operation)
        except Exception as e:
            logger.error(f"Failed to get raw data for CID {cid}: {str(e)}")
            return None

    def get_cid_dataframe(self, cid: str) -> Optional[pd.DataFrame]:
        """Get all columns for a given CID and return as pandas DataFrame"""
        def _get_dataframe_operation():
            with self.get_cursor() as cursor:
                cid_escaped = cid.replace("'", "''")
                # Get all columns from the table
                cursor.execute(f"SELECT * FROM SLSP_DEMO WHERE CID = '{cid_escaped}'")
                row = cursor.fetchone()
                
                if row:
                    # Get column names
                    cursor.execute("DESCRIBE TABLE SLSP_DEMO")
                    columns_info = cursor.fetchall()
                    column_names = [col[0] for col in columns_info]
                    
                    # Create DataFrame with the row data
                    df = pd.DataFrame([row], columns=column_names)
                    return df
                return None
        
        try:
            return self.execute_with_retry(_get_dataframe_operation)
        except Exception as e:
            logger.error(f"Failed to get DataFrame for CID {cid}: {str(e)}")
            return None

    def load_form_data(self, cid: str) -> Optional[Dict[str, Any]]:
        """Load form data for given CID"""
        def _load_operation():
            with self.get_cursor() as cursor:
                cid_escaped = cid.replace("'", "''")
                logger.info(f"load_form_data: Searching for CID '{cid}' (escaped: '{cid_escaped}')")
                
                # Debug: Check if record exists
                cursor.execute(f"SELECT COUNT(*) FROM SLSP_DEMO WHERE CID = '{cid_escaped}'")
                count = cursor.fetchone()[0]
                logger.info(f"load_form_data: Found {count} records for CID {cid}")
                
                cursor.execute(f"SELECT DATA, LAST_UPDATED, PHASE FROM SLSP_DEMO WHERE CID = '{cid_escaped}'")
                row = cursor.fetchone()
                logger.info(f"load_form_data: Query returned row: {row is not None}")
                
                if row and row[0]:
                    raw_data = row[0]
                    logger.info(f"Raw data loaded for CID {cid}, length: {len(raw_data)}")
                    
                    # Process the JSON data
                    data = self.process_json_data(raw_data)
                    if data is not None:
                        # Add metadata to the data if they exist
                        if row[1] is not None:  # LAST_UPDATED
                            data['_last_updated'] = str(row[1])
                        if row[2] is not None:  # PHASE
                            data['_phase'] = row[2]
                        return data
                    else:
                        logger.error(f"Failed to process JSON data for CID {cid}")
                        return None
                return None
        
        try:
            return self.execute_with_retry(_load_operation)
        except Exception as e:
            logger.error(f"Failed to load form data for CID {cid}: {str(e)}")
            return None
    
    
    
    def initialize_table(self) -> bool:
        """Initialize the SLSP_DEMO table if it doesn't exist"""
        def _init_operation():
            with self.get_cursor() as cursor:
                # Check if table exists
                cursor.execute("""
                    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES 
                    WHERE TABLE_NAME = 'SLSP_DEMO' AND TABLE_SCHEMA = CURRENT_SCHEMA()
                """)
                
                if cursor.fetchone()[0] == 0:
                    # Create table
                    cursor.execute("""
                        CREATE TABLE SLSP_DEMO (
                            CID VARCHAR(16777216) PRIMARY KEY,
                            DATA VARCHAR(16777216),
                            LAST_UPDATED TIMESTAMP_LTZ(9) DEFAULT CURRENT_TIMESTAMP(),
                            CREATED_AT TIMESTAMP_LTZ(9) DEFAULT CURRENT_TIMESTAMP(),
                            PHASE NUMBER(38,0)
                        )
                    """)
                    logger.info("SLSP_DEMO table created successfully")
                else:
                    # Add missing columns if they don't exist
                    try:
                        cursor.execute("ALTER TABLE SLSP_DEMO ADD COLUMN IF NOT EXISTS CREATED_AT TIMESTAMP_LTZ(9) DEFAULT CURRENT_TIMESTAMP()")
                        cursor.execute("ALTER TABLE SLSP_DEMO ADD COLUMN IF NOT EXISTS LAST_UPDATED TIMESTAMP_LTZ(9) DEFAULT CURRENT_TIMESTAMP()")
                        cursor.execute("ALTER TABLE SLSP_DEMO ADD COLUMN IF NOT EXISTS PHASE NUMBER(38,0)")
                    except Exception:
                        pass  # Columns might already exist
                
                return True
        
        try:
            return self.execute_with_retry(_init_operation)
        except Exception as e:
            logger.error(f"Failed to initialize table: {str(e)}")
            return False
    


# Global database manager instance
@st.cache_resource
def get_db_manager():
    """Get singleton database manager instance"""
    return SnowflakeManager()
