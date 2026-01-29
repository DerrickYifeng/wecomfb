"""
Initialize Unity Catalog table for feedback storage

This script creates the user_feedback table in Unity Catalog
Run this once before deploying the application
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
DATABRICKS_HOST = os.getenv("DATABRICKS_HOST")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN")
UC_CATALOG = os.getenv("UC_CATALOG", "dev")
UC_SCHEMA = os.getenv("UC_SCHEMA", "inner_feedback")
TABLE_NAME = os.getenv("TABLE_NAME", "user_feedback")
FULL_TABLE_NAME = f"{UC_CATALOG}.{UC_SCHEMA}.{TABLE_NAME}"


def create_table():
    """Create the feedback table in Unity Catalog"""
    try:
        from databricks.connect import DatabricksSession
        
        print(f"🔌 Connecting to Databricks: {DATABRICKS_HOST}")
        
        # Create Databricks session
        spark = DatabricksSession.builder \
            .remote(
                host=DATABRICKS_HOST,
                token=DATABRICKS_TOKEN
            ) \
            .getOrCreate()
        
        print(f"✅ Connected successfully!")
        
        # Create catalog if not exists
        print(f"\n📦 Creating catalog: {UC_CATALOG}")
        spark.sql(f"CREATE CATALOG IF NOT EXISTS {UC_CATALOG}")
        print(f"✅ Catalog ready: {UC_CATALOG}")
        
        # Create schema if not exists
        print(f"\n📁 Creating schema: {UC_CATALOG}.{UC_SCHEMA}")
        spark.sql(f"CREATE SCHEMA IF NOT EXISTS {UC_CATALOG}.{UC_SCHEMA}")
        print(f"✅ Schema ready: {UC_CATALOG}.{UC_SCHEMA}")
        
        # Create table
        print(f"\n📊 Creating table: {FULL_TABLE_NAME}")
        
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {FULL_TABLE_NAME} (
            feedback_id STRING NOT NULL,
            user_name STRING NOT NULL,
            user_id STRING,
            group_name STRING,
            group_id STRING,
            feedback_content STRING NOT NULL,
            feedback_type STRING,
            created_at TIMESTAMP NOT NULL,
            raw_message STRING,
            is_processed BOOLEAN DEFAULT FALSE,
            processed_at TIMESTAMP,
            notes STRING
        )
        USING DELTA
        COMMENT 'User feedback collected from WeCom groups'
        """
        
        spark.sql(create_table_sql)
        print(f"✅ Table created: {FULL_TABLE_NAME}")
        
        # Show table info
        print(f"\n📋 Table information:")
        spark.sql(f"DESCRIBE TABLE {FULL_TABLE_NAME}").show()
        
        # Check if table has data
        count = spark.table(FULL_TABLE_NAME).count()
        print(f"\n📊 Current row count: {count}")
        
        print(f"\n🎉 Initialization complete!")
        print(f"\n📝 Table details:")
        print(f"   Catalog: {UC_CATALOG}")
        print(f"   Schema: {UC_SCHEMA}")
        print(f"   Table: {TABLE_NAME}")
        print(f"   Full name: {FULL_TABLE_NAME}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


def test_connection():
    """Test Databricks connection"""
    try:
        from databricks.connect import DatabricksSession
        
        print(f"🧪 Testing connection to: {DATABRICKS_HOST}")
        
        spark = DatabricksSession.builder \
            .remote(
                host=DATABRICKS_HOST,
                token=DATABRICKS_TOKEN
            ) \
            .getOrCreate()
        
        # Test query
        result = spark.sql("SELECT current_timestamp() as now").collect()
        print(f"✅ Connection successful!")
        print(f"   Server time: {result[0]['now']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


def main():
    """Main entry point"""
    print("=" * 60)
    print("🚀 Unity Catalog Table Initialization")
    print("=" * 60)
    print()
    
    # Check configuration
    if not DATABRICKS_HOST or not DATABRICKS_TOKEN:
        print("❌ Error: Missing Databricks configuration")
        print("   Please set DATABRICKS_HOST and DATABRICKS_TOKEN in .env")
        return
    
    print(f"Configuration:")
    print(f"  Host: {DATABRICKS_HOST}")
    print(f"  Catalog: {UC_CATALOG}")
    print(f"  Schema: {UC_SCHEMA}")
    print(f"  Table: {TABLE_NAME}")
    print()
    
    # Test connection
    print("Step 1: Testing connection...")
    if not test_connection():
        return
    
    print()
    
    # Create table
    print("Step 2: Creating table...")
    if not create_table():
        return
    
    print()
    print("=" * 60)
    print("✨ All done! You can now deploy your application.")
    print("=" * 60)


if __name__ == "__main__":
    main()
