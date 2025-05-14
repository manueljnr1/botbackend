#!/usr/bin/env python3
"""
Update main.py to use custom WhatsApp integration
"""
import os
import re
import shutil

def backup_file(file_path):
    """Create a backup of a file"""
    backup_path = f"{file_path}.bak.custom"
    shutil.copy2(file_path, backup_path)
    print(f"Created backup: {backup_path}")
    return True

def update_main_file():
    """Update main.py to use custom WhatsApp integration"""
    main_file = os.path.join(os.getcwd(), "app", "main.py")
    
    if not os.path.exists(main_file):
        print(f"Main file not found: {main_file}")
        return False
    
    # Backup the file
    backup_file(main_file)
    
    # Read the file
    with open(main_file, 'r') as f:
        content = f.read()
    
    # Add import for custom integration
    if "from app.custom_integrations.whatsapp_handler import register_whatsapp_routes" not in content:
        # Find the imports section
        import_pattern = r"(from fastapi import.*?\n)"
        import_section = re.search(import_pattern, content)
        
        if import_section:
            # Add our import after the FastAPI import
            modified_content = re.sub(
                import_pattern,
                r"\1from app.custom_integrations.whatsapp_handler import register_whatsapp_routes\n",
                content
            )
            
            # Add a route registration
            if "register_whatsapp_routes(app)" not in modified_content:
                # Find where to add the route registration
                app_pattern = r"(app = FastAPI\(.*?\))"
                app_section = re.search(app_pattern, modified_content, re.DOTALL)
                
                if app_section:
                    # Add our route registration after the app initialization
                    modified_content = re.sub(
                        app_pattern,
                        r"\1\n\n# Register custom WhatsApp integration\nregister_whatsapp_routes(app)",
                        modified_content
                    )
            
            # Write the modified content back
            with open(main_file, 'w') as f:
                f.write(modified_content)
            
            print("Added custom WhatsApp integration to main.py")
            return True
        else:
            print("Could not find proper import section in main.py")
            return False
    else:
        print("Custom WhatsApp integration already imported in main.py")
        return True

if __name__ == "__main__":
    update_main_file()
    print("\nDon't forget to restart your server after this change.")
