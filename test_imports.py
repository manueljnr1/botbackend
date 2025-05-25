# test_imports.py - Test if all models import correctly
import sys
import traceback

def test_live_chat_imports():
    """Test importing live chat models"""
    print("🧪 Testing live chat model imports...")
    
    try:
        print("  📦 Importing basic models...")
        from app.live_chat.models import AgentStatus, ChatStatus, MessageType
        print("    ✅ Enums imported successfully")
        
        print("  📦 Importing Agent model...")
        from app.live_chat.models import Agent
        print("    ✅ Agent model imported successfully")
        
        print("  📦 Importing LiveChat model...")
        from app.live_chat.models import LiveChat
        print("    ✅ LiveChat model imported successfully")
        
        print("  📦 Importing LiveChatMessage model...")
        from app.live_chat.models import LiveChatMessage
        print("    ✅ LiveChatMessage model imported successfully")
        
        print("  📦 Importing AgentSession model...")
        from app.live_chat.models import AgentSession
        print("    ✅ AgentSession model imported successfully")
        
        print("  📦 Importing ChatQueue model...")
        from app.live_chat.models import ChatQueue
        print("    ✅ ChatQueue model imported successfully")
        
        print("\n✅ All live chat models imported successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Import failed: {e}")
        print(f"📍 Error details:")
        traceback.print_exc()
        return False

def test_manager_imports():
    """Test importing live chat manager"""
    print("\n🧪 Testing live chat manager imports...")
    
    try:
        print("  📦 Importing LiveChatManager...")
        from app.live_chat.manager import LiveChatManager
        print("    ✅ LiveChatManager imported successfully")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Manager import failed: {e}")
        print(f"📍 Error details:")
        traceback.print_exc()
        return False

def test_websocket_imports():
    """Test importing websocket manager"""
    print("\n🧪 Testing websocket manager imports...")
    
    try:
        print("  📦 Importing ConnectionManager...")
        from app.live_chat.websocket_manager import connection_manager, LiveChatWebSocketHandler
        print("    ✅ WebSocket components imported successfully")
        
        return True
        
    except Exception as e:
        print(f"\n❌ WebSocket import failed: {e}")
        print(f"📍 Error details:")
        traceback.print_exc()
        return False

def test_router_imports():
    """Test importing live chat router"""
    print("\n🧪 Testing live chat router imports...")
    
    try:
        print("  📦 Importing live chat router...")
        from app.live_chat.router import router
        print("    ✅ Router imported successfully")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Router import failed: {e}")
        print(f"📍 Error details:")
        traceback.print_exc()
        return False

def test_database_connection():
    """Test database connection and model creation"""
    print("\n🧪 Testing database connection...")
    
    try:
        print("  📦 Testing database connection...")
        from app.database import get_db, engine
        from sqlalchemy.orm import Session
        
        # Test database connection
        db = next(get_db())
        print("    ✅ Database connection successful")
        
        # Test if we can create tables
        from app.database import Base
        Base.metadata.create_all(bind=engine)
        print("    ✅ Tables creation successful")
        
        db.close()
        return True
        
    except Exception as e:
        print(f"\n❌ Database test failed: {e}")
        print(f"📍 Error details:")
        traceback.print_exc()
        return False

def main():
    """Run all import tests"""
    print("🚀 Live Chat Import Test Suite")
    print("=" * 50)
    
    tests = [
        ("Models", test_live_chat_imports),
        ("Manager", test_manager_imports), 
        ("WebSocket", test_websocket_imports),
        ("Router", test_router_imports),
        ("Database", test_database_connection)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n💥 Test '{test_name}' crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 TEST RESULTS SUMMARY:")
    print("=" * 50)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {test_name:12} : {status}")
        if result:
            passed += 1
        else:
            failed += 1
    
    print(f"\n📈 Total: {passed + failed} tests")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! Your live chat system is ready!")
        print("🚀 You can now start your FastAPI server:")
        print("   python -m uvicorn app.main:app --reload")
        return True
    else:
        print(f"\n⚠️  {failed} tests failed. Please fix the issues above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)