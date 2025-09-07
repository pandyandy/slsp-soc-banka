"""
Optimized Snowflake Database Manager
Handles all database operations with connection pooling and retry logic
"""
import streamlit as st
import snowflake.connector
import json
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
        self.last_activity = None
        self.connection_timeout = 1800  # 30 minutes
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
    
    def get_connection(self) -> Optional[snowflake.connector.SnowflakeConnection]:
        """Get active connection or create new one"""
        current_time = time.time()
        
        # Check if connection exists and is not expired
        if (self.connection and 
            self.last_activity and 
            (current_time - self.last_activity) < self.connection_timeout):
            
            # Quick connection test (lightweight)
            if self._is_connection_alive():
                self.last_activity = current_time
                return self.connection
        
        # Create new connection
        self.connection = self._create_connection()
        self.last_activity = current_time if self.connection else None
        return self.connection
    
    def _is_connection_alive(self) -> bool:
        """Lightweight connection test"""
        try:
            if not self.connection:
                return False
            # Use a simple query instead of SELECT 1 for better performance
            cursor = self.connection.cursor()
            cursor.execute("SELECT CURRENT_TIMESTAMP()")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception:
            return False
    
    @contextmanager
    def get_cursor(self):
        """Context manager for database cursor operations"""
        conn = self.get_connection()
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
        """Optimized form data save operation"""
        def _save_operation():
            with self.get_cursor() as cursor:
                # Check if record exists
                cid_escaped = cid.replace("'", "''")
                cursor.execute(f"SELECT CID FROM SLSP_DEMO WHERE CID = '{cid_escaped}'")
                exists = cursor.fetchone() is not None
                
                json_data = json.dumps(form_data, default=str, ensure_ascii=False)
                # Escape single quotes for SQL
                json_data = json_data.replace("'", "''")
                
                if exists:
                    if phase is not None:
                        cursor.execute(
                            f"UPDATE SLSP_DEMO SET DATA = '{json_data}', PHASE = {phase}, LAST_UPDATED = CURRENT_TIMESTAMP() WHERE CID = '{cid_escaped}'"
                        )
                    else:
                        cursor.execute(
                            f"UPDATE SLSP_DEMO SET DATA = '{json_data}', LAST_UPDATED = CURRENT_TIMESTAMP() WHERE CID = '{cid_escaped}'"
                        )
                else:
                    if phase is not None:
                        cursor.execute(
                            f"INSERT INTO SLSP_DEMO (CID, DATA, PHASE, CREATED_AT, LAST_UPDATED) VALUES ('{cid_escaped}', '{json_data}', {phase}, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())"
                        )
                    else:
                        cursor.execute(
                            f"INSERT INTO SLSP_DEMO (CID, DATA, CREATED_AT, LAST_UPDATED) VALUES ('{cid_escaped}', '{json_data}', CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())"
                        )
                return True
        
        try:
            return self.execute_with_retry(_save_operation)
        except Exception as e:
            logger.error(f"Failed to save form data for CID {cid}: {str(e)}")
            return False
    
    def load_form_data(self, cid: str) -> Optional[Dict[str, Any]]:
        """Load form data for given CID"""
        def _load_operation():
            with self.get_cursor() as cursor:
                cid_escaped = cid.replace("'", "''")
                cursor.execute(f"SELECT DATA, LAST_UPDATED, PHASE FROM SLSP_DEMO WHERE CID = '{cid_escaped}'")
                row = cursor.fetchone()
                
                if row and row[0]:
                    try:
                        data = json.loads(row[0])
                        # Add metadata to the data if they exist
                        if row[1] is not None:  # LAST_UPDATED
                            data['_last_updated'] = str(row[1])
                        if row[2] is not None:  # PHASE
                            data['_phase'] = row[2]
                        return data
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON data for CID {cid}: {str(e)}")
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
