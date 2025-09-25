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
from typing import Optional, Dict, Any, List
import logging
from contextlib import contextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SnowflakeManager:
    """Optimized Snowflake connection and operation manager using Snowpark"""
    
    def __init__(self):
        self.session = None
        self.last_activity = None
        self.connection_timeout = 1800  # 30 minutes
        self.max_retries = 3
        
    #@st.cache_resource
    def _create_session(_self):
        """Create a new Snowpark session with caching"""
        try:
            connection_parameters = {
                "account": st.secrets["account"],
                "user": st.secrets["user"],
                "password": st.secrets["password"],
                "warehouse": st.secrets["warehouse"],
                "database": st.secrets["database"],
                "schema": st.secrets["schema"],
            }
            
            session = Session.builder.configs(connection_parameters).create()
            logger.info("Snowpark session established successfully")
            return session
        except Exception as e:
            logger.error(f"Failed to create Snowpark session: {str(e)}")
            return None
    
    def get_session(self) -> Optional[Session]:
        """Get active session or create new one"""
        current_time = time.time()
        
        # Check if session exists and is not expired
        if (self.session and 
            self.last_activity and 
            (current_time - self.last_activity) < self.connection_timeout):
            
            # Quick session test (lightweight)
            if self._is_session_alive():
                self.last_activity = current_time
                return self.session
        
        # Create new session
        self.session = self._create_session()
        self.last_activity = current_time if self.session else None
        return self.session
    
    def _is_session_alive(self) -> bool:
        """Lightweight session test"""
        try:
            if not self.session:
                return False
            # Use a simple query to test session
            self.session.sql("SELECT CURRENT_TIMESTAMP()").collect()
            return True
        except Exception:
            return False
    
    @contextmanager
    def get_session_context(self):
        """Context manager for database session operations"""
        session = self.get_session()
        if not session:
            raise Exception("Unable to establish database session")
        
        try:
            yield session
        except Exception as e:
            logger.error(f"Database operation failed: {str(e)}")
            raise
    
    def execute_with_retry(self, operation_func, *args, **kwargs):
        """Execute database operation with retry logic"""
        for attempt in range(self.max_retries):
            try:
                return operation_func(*args, **kwargs)
            except Exception as e:
                error_msg = str(e).lower()
                if ("connection" in error_msg or "timeout" in error_msg or "session" in error_msg) and attempt < self.max_retries - 1:
                    logger.warning(f"Database operation failed (attempt {attempt + 1}), retrying...")
                    # Clear session to force reconnect
                    self.session = None
                    time.sleep(1)  # Brief pause before retry
                    continue
                else:
                    logger.error(f"Database operation failed after {attempt + 1} attempts: {str(e)}")
                    raise
    
    def save_form_data(self, cid: str, form_data: Dict[str, Any], phase: int = None) -> bool:
        """Optimized form data save operation with proper data sanitization"""
        def _save_operation():
            with self.get_session_context() as session:
                # Check if record exists
                result = session.sql("SELECT CID FROM SLSP_DEMO WHERE CID = :cid", params={"cid": cid}).collect()
                exists = len(result) > 0
                
                # Sanitize form data before JSON serialization
                sanitized_data = self.sanitize_form_data(form_data)
                
                # Use parameterized query to avoid SQL injection issues
                json_data = json.dumps(sanitized_data, default=str, ensure_ascii=False)
                
                if exists:
                    if phase is not None:
                        session.sql(
                            "UPDATE SLSP_DEMO SET DATA = :json_data, PHASE = :phase, LAST_UPDATED = CURRENT_TIMESTAMP() WHERE CID = :cid",
                            params={"json_data": json_data, "phase": phase, "cid": cid}
                        ).collect()
                    else:
                        session.sql(
                            "UPDATE SLSP_DEMO SET DATA = :json_data, LAST_UPDATED = CURRENT_TIMESTAMP() WHERE CID = :cid",
                            params={"json_data": json_data, "cid": cid}
                        ).collect()
                else:
                    if phase is not None:
                        session.sql(
                            "INSERT INTO SLSP_DEMO (CID, DATA, PHASE, CREATED_AT, LAST_UPDATED) VALUES (:cid, :json_data, :phase, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())",
                            params={"cid": cid, "json_data": json_data, "phase": phase}
                        ).collect()
                    else:
                        session.sql(
                            "INSERT INTO SLSP_DEMO (CID, DATA, CREATED_AT, LAST_UPDATED) VALUES (:cid, :json_data, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())",
                            params={"cid": cid, "json_data": json_data}
                        ).collect()
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
            with self.get_session_context() as session:
                # Get the raw data
                result = session.sql("SELECT DATA FROM SLSP_DEMO WHERE CID = :cid", params={"cid": cid}).collect()
                if not result:
                    return False
                
                raw_data = result[0][0]
                
                # Try to parse the JSON
                try:
                    parsed_data = json.loads(raw_data)
                    # If it parses successfully, sanitize and save
                    sanitized_data = self.sanitize_form_data(parsed_data)
                    fixed_json = json.dumps(sanitized_data, default=str, ensure_ascii=False)
                    
                    # Update the database
                    session.sql(
                        "UPDATE SLSP_DEMO SET DATA = :fixed_json, LAST_UPDATED = CURRENT_TIMESTAMP() WHERE CID = :cid",
                        params={"fixed_json": fixed_json, "cid": cid}
                    ).collect()
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
                        session.sql(
                            "UPDATE SLSP_DEMO SET DATA = :fixed_json, LAST_UPDATED = CURRENT_TIMESTAMP() WHERE CID = :cid",
                            params={"fixed_json": fixed_json, "cid": cid}
                        ).collect()
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
            with self.get_session_context() as session:
                # Check if table exists
                tables = session.sql("SHOW TABLES LIKE 'SLSP_DEMO'").collect()
                
                # Get table info
                columns = session.sql("DESCRIBE TABLE SLSP_DEMO").collect()
                
                # Get record count
                count_result = session.sql("SELECT COUNT(*) FROM SLSP_DEMO").collect()
                count = count_result[0][0] if count_result else 0
                
                # Get sample CIDs
                sample_cids_result = session.sql("SELECT CID FROM SLSP_DEMO LIMIT 5").collect()
                sample_cids = [row[0] for row in sample_cids_result]
                
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
            with self.get_session_context() as session:
                # Get all records using Snowpark DataFrame
                snowpark_df = session.table("SLSP_DEMO").order_by("CID")
                
                # Convert to pandas DataFrame
                pandas_df = snowpark_df.to_pandas()
                
                return pandas_df if not pandas_df.empty else None
        
        try:
            return self.execute_with_retry(_get_all_dataframe_operation)
        except Exception as e:
            logger.error(f"Failed to get all records DataFrame: {str(e)}")
            return None

    def get_raw_data(self, cid: str) -> Optional[Dict[str, Any]]:
        """Get raw data for a given CID without JSON parsing"""
        def _get_raw_operation():
            with self.get_session_context() as session:
                logger.info(f"Executing query for CID: {cid}")
                
                # First, let's check if the record exists at all
                count_result = session.sql("SELECT COUNT(*) FROM SLSP_DEMO WHERE CID = :cid", params={"cid": cid}).collect()
                count = count_result[0][0] if count_result else 0
                logger.info(f"Found {count} records for CID {cid}")
                
                if count == 0:
                    # Let's see what CIDs actually exist
                    existing_cids_result = session.sql("SELECT CID FROM SLSP_DEMO LIMIT 10").collect()
                    existing_cids = [row[0] for row in existing_cids_result]
                    logger.info(f"Sample existing CIDs: {existing_cids}")
                    return None
                
                # Now get the actual data
                result = session.sql("SELECT DATA, LAST_UPDATED, PHASE FROM SLSP_DEMO WHERE CID = :cid", params={"cid": cid}).collect()
                logger.info(f"Query returned row: {len(result) > 0}")
                
                if result:
                    row = result[0]
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
            with self.get_session_context() as session:
                # Get all columns from the table using Snowpark DataFrame
                snowpark_df = session.table("SLSP_DEMO").filter(f"CID = '{cid}'")
                
                # Convert to pandas DataFrame
                pandas_df = snowpark_df.to_pandas()
                
                return pandas_df if not pandas_df.empty else None
        
        try:
            return self.execute_with_retry(_get_dataframe_operation)
        except Exception as e:
            logger.error(f"Failed to get DataFrame for CID {cid}: {str(e)}")
            return None

    def load_form_data(self, cid: str) -> Optional[Dict[str, Any]]:
        """Load form data for given CID"""
        def _load_operation():
            with self.get_session_context() as session:
                logger.info(f"load_form_data: Searching for CID '{cid}'")
                
                # Debug: Check if record exists
                count_result = session.sql("SELECT COUNT(*) FROM SLSP_DEMO WHERE CID = :cid", params={"cid": cid}).collect()
                count = count_result[0][0] if count_result else 0
                logger.info(f"load_form_data: Found {count} records for CID {cid}")
                
                result = session.sql("SELECT DATA, LAST_UPDATED, PHASE FROM SLSP_DEMO WHERE CID = :cid", params={"cid": cid}).collect()
                logger.info(f"load_form_data: Query returned row: {len(result) > 0}")
                
                if result and result[0][0]:
                    row = result[0]
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
            with self.get_session_context() as session:
                # Check if table exists
                result = session.sql("""
                    SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES 
                    WHERE TABLE_NAME = 'SLSP_DEMO' AND TABLE_SCHEMA = CURRENT_SCHEMA()
                """).collect()
                
                if result[0][0] == 0:
                    # Create table
                    session.sql("""
                        CREATE TABLE SLSP_DEMO (
                            CID VARCHAR(16777216) PRIMARY KEY,
                            DATA VARCHAR(16777216),
                            LAST_UPDATED TIMESTAMP_LTZ(9) DEFAULT CURRENT_TIMESTAMP(),
                            CREATED_AT TIMESTAMP_LTZ(9) DEFAULT CURRENT_TIMESTAMP(),
                            PHASE NUMBER(38,0)
                        )
                    """).collect()
                    logger.info("SLSP_DEMO table created successfully")
                else:
                    # Add missing columns if they don't exist
                    try:
                        session.sql("ALTER TABLE SLSP_DEMO ADD COLUMN IF NOT EXISTS CREATED_AT TIMESTAMP_LTZ(9) DEFAULT CURRENT_TIMESTAMP()").collect()
                        session.sql("ALTER TABLE SLSP_DEMO ADD COLUMN IF NOT EXISTS LAST_UPDATED TIMESTAMP_LTZ(9) DEFAULT CURRENT_TIMESTAMP()").collect()
                        session.sql("ALTER TABLE SLSP_DEMO ADD COLUMN IF NOT EXISTS PHASE NUMBER(38,0)").collect()
                    except Exception:
                        pass  # Columns might already exist
                
                return True
        
        try:
            return self.execute_with_retry(_init_operation)
        except Exception as e:
            logger.error(f"Failed to initialize table: {str(e)}")
            return False
    


# Global database manager instance
#@st.cache_resource
def get_db_manager():
    """Get singleton database manager instance"""
    return SnowflakeManager()
