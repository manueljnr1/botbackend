#!/usr/bin/env python3
"""
Simple diagnostic script to check migration status
"""

import sys
import traceback
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Database URL
DATABASE_URL = "postgresql://chatbot_hhjv_user:dYXguSEwpwZl3Yt2R3ACsfvmM5lLIgSD@dpg-d10sp295pdvs73afujf0-a.oregon-postgres.render.com/chatbot_hhjv"

def check_database_status():
    """Check the current status of the database"""
    print("🔍 DATABASE STATUS CHECK")
    print("=" * 40)
    
    try:
        # Create engine and session
        engine = create_engine(DATABASE_URL)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        print("✅ Database connection successful")
        
        # 1. Check tenant counts
        print("\n📊 TENANT STATISTICS:")
        result = session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN id < 100000000 THEN 1 END) as insecure,
                COUNT(CASE WHEN id >= 100000000 THEN 1 END) as secure
            FROM tenants
        """)).first()
        
        total, insecure, secure = result
        security_percentage = (secure / total * 100) if total > 0 else 0
        
        print(f"   Total tenants: {total}")
        print(f"   Secure IDs (9+ digits): {secure}")
        print(f"   Insecure IDs (< 9 digits): {insecure}")
        print(f"   Security level: {security_percentage:.1f}%")
        
        # 2. Check backup table
        print("\n💾 BACKUP TABLE STATUS:")
        try:
            backup_count = session.execute(text("""
                SELECT COUNT(*) FROM tenant_id_migration_backup
            """)).scalar()
            
            print(f"   Backup table exists: ✅")
            print(f"   Backup entries: {backup_count}")
            
            if backup_count > 0:
                # Show backup status breakdown
                backup_status = session.execute(text("""
                    SELECT status, COUNT(*) as count 
                    FROM tenant_id_migration_backup 
                    GROUP BY status
                    ORDER BY status
                """)).fetchall()
                
                print("   Backup status breakdown:")
                for status, count in backup_status:
                    print(f"     {status}: {count} tenants")
                    
        except Exception as e:
            print(f"   Backup table exists: ❌ ({str(e)[:50]}...)")
        
        # 3. Check foreign key constraints
        print("\n🔗 FOREIGN KEY CONSTRAINTS:")
        try:
            fk_count = session.execute(text("""
                SELECT COUNT(*) FROM information_schema.table_constraints tc
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.constraint_name LIKE '%tenant_id_fkey'
            """)).scalar()
            
            print(f"   Tenant FK constraints: {fk_count}")
            
            # Show some examples
            fk_examples = session.execute(text("""
                SELECT tc.table_name, tc.constraint_name
                FROM information_schema.table_constraints tc
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.constraint_name LIKE '%tenant_id_fkey'
                LIMIT 5
            """)).fetchall()
            
            print("   Example constraints:")
            for table, constraint in fk_examples:
                print(f"     {table}: {constraint}")
            
            if len(fk_examples) == 5:
                remaining = fk_count - 5
                if remaining > 0:
                    print(f"     ... and {remaining} more")
                    
        except Exception as e:
            print(f"   FK constraint check failed: {e}")
        
        # 4. Show some sample tenant data
        print("\n👥 SAMPLE TENANT DATA:")
        try:
            sample_tenants = session.execute(text("""
                SELECT id, name, email, 
                       CASE WHEN id < 100000000 THEN 'INSECURE' ELSE 'SECURE' END as status
                FROM tenants 
                ORDER BY id 
                LIMIT 10
            """)).fetchall()
            
            print("   ID          | Name         | Email                    | Status")
            print("   " + "-" * 65)
            for tenant_id, name, email, status in sample_tenants:
                name_short = (name or 'Unknown')[:12]
                email_short = (email or 'unknown@example.com')[:24]
                print(f"   {tenant_id:<11} | {name_short:<12} | {email_short:<24} | {status}")
                
        except Exception as e:
            print(f"   Sample data fetch failed: {e}")
        
        # 5. Migration recommendations
        print("\n💡 RECOMMENDATIONS:")
        if insecure > 0:
            print(f"   🚨 URGENT: {insecure} tenants have insecure sequential IDs")
            print("   🔧 ACTION: Run the secure tenant ID migration")
            print("   📋 NEXT STEP: Use the fixed migration script")
        else:
            print("   ✅ All tenant IDs are secure!")
            print("   🎉 No migration needed")
        
        # 6. Next steps
        print("\n🚀 NEXT STEPS:")
        if insecure > 0:
            print("   1. Backup your database first!")
            print("   2. Run: python secure_migration.py --dry-run")
            print("   3. Review the preview carefully")
            print("   4. Run: python secure_migration.py --execute")
        else:
            print("   1. Consider implementing additional security measures")
            print("   2. Monitor for any new tenants with sequential IDs")
            print("   3. Update tenant registration to use secure IDs")
        
        session.close()
        return True
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print(f"   Error type: {type(e).__name__}")
        print(f"   Full error: {str(e)}")
        traceback.print_exc()
        return False


def check_script_issues():
    """Check for common script execution issues"""
    print("\n🔧 SCRIPT DIAGNOSTIC:")
    print("   Python version:", sys.version)
    
    # Check imports
    try:
        import sqlalchemy
        print(f"   SQLAlchemy version: {sqlalchemy.__version__}")
    except ImportError:
        print("   ❌ SQLAlchemy not installed!")
        return False
    
    try:
        import psycopg2
        print(f"   psycopg2 available: ✅")
    except ImportError:
        print("   ❌ psycopg2 not installed!")
        return False
    
    return True


def run_simple_migration_check():
    """Simple check to see what needs to be migrated"""
    print("\n🔍 SIMPLE MIGRATION CHECK")
    print("=" * 40)
    
    try:
        engine = create_engine(DATABASE_URL)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Get tenants that need migration
        insecure_tenants = session.execute(text("""
            SELECT id, name, business_name, email
            FROM tenants 
            WHERE id < 100000000 
            ORDER BY id
            LIMIT 20
        """)).fetchall()
        
        print(f"Found {len(insecure_tenants)} tenants with insecure IDs:")
        print()
        
        if insecure_tenants:
            print("ID   | Name              | Business           | Email")
            print("-" * 70)
            
            for tenant_id, name, business, email in insecure_tenants:
                name_short = (name or 'Unknown')[:15]
                business_short = (business or 'Unknown')[:15]
                email_short = (email or 'unknown@example.com')[:20]
                
                print(f"{tenant_id:<4} | {name_short:<15} | {business_short:<15} | {email_short}")
            
            print()
            print("🚨 These tenants need secure ID migration!")
            print("📝 Sequential IDs like 1, 2, 3... are easily guessable")
            print("🔒 Secure IDs should be 9-digit random numbers")
            
        else:
            print("✅ All tenant IDs are already secure!")
        
        session.close()
        
    except Exception as e:
        print(f"❌ Check failed: {e}")


if __name__ == "__main__":
    try:
        print("🔍 TENANT ID MIGRATION DIAGNOSTIC")
        print("=" * 50)
        
        # Check if we can run the script
        if not check_script_issues():
            print("\n❌ Script setup issues detected!")
            sys.exit(1)
        
        # Check database status
        if check_database_status():
            run_simple_migration_check()
        else:
            print("\n❌ Cannot proceed - database connection failed")
            sys.exit(1)
        
        print("\n" + "=" * 50)
        print("Diagnostic complete!")
        
    except KeyboardInterrupt:
        print("\n⚠️ Diagnostic interrupted by user")
    except Exception as e:
        print(f"\n❌ Diagnostic failed: {e}")
        traceback.print_exc()