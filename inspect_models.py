# inspect_models.py
from app.database import SessionLocal
from app.tenants.models import Tenant
from app.auth.models import TenantCredentials  # Adjust if needed
from sqlalchemy import inspect

def inspect_models():
    db = SessionLocal()
    try:
        # Inspect Tenant model
        tenant_inspector = inspect(Tenant)
        print("=== Tenant Model ===")
        print("Table name:", Tenant.__tablename__)
        print("Columns:")
        for column in tenant_inspector.columns:
            print(f"  - {column.name}: {column.type}")
        
        print("\nRelationships:")
        for rel in tenant_inspector.relationships:
            print(f"  - {rel.key} -> {rel.target}")
        
        # Try to inspect TenantCredentials model
        try:
            cred_inspector = inspect(TenantCredentials)
            print("\n=== TenantCredentials Model ===")
            print("Table name:", TenantCredentials.__tablename__)
            print("Columns:")
            for column in cred_inspector.columns:
                print(f"  - {column.name}: {column.type}")
            
            print("\nRelationships:")
            for rel in cred_inspector.relationships:
                print(f"  - {rel.key} -> {rel.target}")
        except Exception as e:
            print("\nCouldn't inspect TenantCredentials model:", str(e))
        
        # Check database tables
        print("\n=== Database Tables ===")
        from sqlalchemy import MetaData
        metadata = MetaData()
        metadata.reflect(bind=db.bind)
        for table_name in metadata.tables:
            print(f"  - {table_name}")
        
        # Check if credentials are being stored directly in Tenant model
        print("\n=== Checking Tenant records ===")
        tenants = db.query(Tenant).all()
        if tenants:
            tenant = tenants[0]
            print(f"First tenant: {tenant.name} (ID: {tenant.id})")
            print("Attributes:")
            for key in dir(tenant):
                if not key.startswith('_') and key not in ['metadata']:
                    try:
                        value = getattr(tenant, key)
                        if not callable(value):
                            print(f"  - {key}: {value}")
                    except:
                        print(f"  - {key}: <Error retrieving value>")
    finally:
        db.close()

if __name__ == "__main__":
    inspect_models()