#!/usr/bin/env python3
"""
Script to add Nigerian food vendor FAQs to a specific tenant
"""
import sqlite3
import sys

def add_nigerian_food_faqs(api_key="sk-420a63812b9d4458937df4e223f4edaa"):
    """Add Nigerian food vendor FAQs to a tenant"""
    # Nigerian food vendor FAQs
    nigerian_food_faqs = [
        ("What Nigerian dishes do you offer?", "We offer a variety of authentic Nigerian dishes including Jollof Rice, Pounded Yam with Egusi Soup, Amala with Ewedu, Suya, Moi Moi, Akara, Pepper Soup, and many more traditional favorites."),
        ("How much is a plate of Jollof Rice?", "A regular plate of our delicious Jollof Rice costs ₦1,500, while a large plate costs ₦2,500. Prices may vary with additional protein options."),
        ("Do you offer food delivery services?", "Yes, we offer delivery services within Lagos. Delivery fees range from ₦500-₦1,500 depending on your location. We deliver within 45-60 minutes of ordering."),
        ("What are your business hours?", "We're open Monday to Saturday from 11 AM to 10 PM, and Sundays from 12 PM to 8 PM. Our kitchen may close 30 minutes before closing time."),
        ("How much is Pounded Yam with Egusi Soup?", "A regular serving of Pounded Yam with Egusi Soup costs ₦2,000, while a large serving costs ₦3,200. All soup options come with assorted meat."),
        ("Do you cater for events and parties?", "Yes, we provide catering services for events and parties. Please contact us at least 3 days in advance for small events and 7 days for large events. We offer special discount packages for orders above ₦50,000."),
        ("What payment methods do you accept?", "We accept cash, bank transfers, and all major cards. We also accept mobile payments through PayStack and Flutterwave."),
        ("How much is a plate of Amala with Ewedu and Gbegiri?", "Amala with Ewedu and Gbegiri costs ₦1,800 for a regular portion and ₦2,800 for a large portion. This comes with assorted meat (beef, shaki, and ponmo)."),
        ("Are your ingredients locally sourced?", "Yes, we use fresh, locally sourced ingredients for all our dishes. We partner with local farmers to ensure the highest quality produce for our customers."),
        ("How spicy is your food?", "Our food is prepared with authentic Nigerian spice levels, which can be quite hot. However, we can adjust the spice level according to your preference. Just let us know when placing your order."),
        ("What's the price for a serving of Suya?", "Our beef Suya costs ₦1,200 for a small serving, ₦2,000 for a regular serving, and ₦3,000 for a family size. Chicken Suya costs ₦1,500 for a regular serving."),
        ("Do you offer any vegetarian options?", "Yes, we offer vegetarian versions of several dishes including Moi Moi, Jollof Rice, and various soups without meat. Our vegetarian options are prepared separately to avoid cross-contamination."),
        ("How much does a plate of Rice and Stew cost?", "White Rice and Stew costs ₦1,200 for a regular serving and ₦2,000 for a large serving. Additional protein options start from ₦500."),
        ("Can I place an order in advance?", "Yes, you can place orders up to 7 days in advance. For large orders, we encourage pre-ordering to ensure timely preparation and delivery."),
        ("What's the cost of your Pepper Soup?", "Goat Meat Pepper Soup costs ₦2,500, Catfish Pepper Soup costs ₦3,000, and Chicken Pepper Soup costs ₦2,200. All servings come with a side of yam or plantain."),
        ("Do you accommodate special dietary requirements?", "Yes, we can accommodate certain dietary requirements with advance notice. Please inform us about any allergies or special dietary needs when placing your order."),
        ("How much is a wrap of Moi Moi?", "A regular wrap of Moi Moi costs ₦500, a premium wrap with eggs costs ₦700, and a special wrap with eggs and fish costs ₦1,000."),
        ("Do you have a minimum order for delivery?", "Yes, our minimum order for delivery is ₦3,000, excluding the delivery fee. For orders below this amount, you can pick up at our location or use a third-party delivery service."),
        ("What's the price of your Efo Riro with assorted meat?", "Efo Riro with assorted meat costs ₦2,200 for a regular portion and ₦3,300 for a large portion. This is served with a choice of swallow – Eba, Amala, or Pounded Yam."),
        ("Do you offer a loyalty program?", "Yes, we have a loyalty program! For every 10 orders above ₦2,000, you get a free dish of your choice up to the value of ₦2,500. Download our app or sign up in-store to join.")
    ]
    
    try:
        # Connect to the database
        conn = sqlite3.connect("chatbot.db")
        cursor = conn.cursor()
        
        # Find the tenant by API key
        cursor.execute("SELECT id, name FROM tenants WHERE api_key = ?", (api_key,))
        tenant = cursor.fetchone()
        
        if not tenant:
            print(f"No tenant found with API key: {api_key}")
            return
        
        tenant_id, tenant_name = tenant
        print(f"Found tenant: {tenant_name} (ID: {tenant_id})")
        
        # Ask if user wants to replace or add to existing FAQs
        cursor.execute("SELECT COUNT(*) FROM faqs WHERE tenant_id = ?", (tenant_id,))
        existing_count = cursor.fetchone()[0]
        
        if existing_count > 0:
            print(f"Tenant already has {existing_count} FAQs.")
            action = input("Do you want to (r)eplace existing FAQs or (a)dd to them? (r/a): ")
            
            if action.lower() == 'r':
                cursor.execute("DELETE FROM faqs WHERE tenant_id = ?", (tenant_id,))
                print(f"Deleted {existing_count} existing FAQs.")
        
        # Add the new FAQs
        for question, answer in nigerian_food_faqs:
            cursor.execute(
                "INSERT INTO faqs (tenant_id, question, answer) VALUES (?, ?, ?)",
                (tenant_id, question, answer)
            )
        
        conn.commit()
        
        # Confirm how many FAQs were added
        cursor.execute("SELECT COUNT(*) FROM faqs WHERE tenant_id = ?", (tenant_id,))
        new_count = cursor.fetchone()[0]
        
        print(f"Successfully added {len(nigerian_food_faqs)} Nigerian food vendor FAQs to tenant: {tenant_name}")
        print(f"Total FAQs for this tenant: {new_count}")
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        if conn:
            conn.rollback()
    except Exception as e:
        print(f"Error: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        api_key = sys.argv[1]
    else:
        api_key = "sk-420a63812b9d4458937df4e223f4edaa"
    
    add_nigerian_food_faqs(api_key)