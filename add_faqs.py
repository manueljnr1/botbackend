# Create a simple script to add FAQs
import sqlite3

# Connect to your database
conn = sqlite3.connect("chatbot.db")
cursor = conn.cursor()

# Get your tenant ID
cursor.execute("SELECT id FROM tenants WHERE name = 'Test Tenant'")
tenant_id = cursor.fetchone()[0]

# Add some sample FAQs
sample_faqs = [
    ("What is your return policy?", "You can return any item within 30 days for a full refund."),
    ("How can I track my order?", "You can track your order by logging into your account and viewing your order history."),
    ("Do you offer international shipping?", "Yes, we ship to most countries worldwide. Shipping rates vary by location."),
    ("What payment methods do you accept?", "We accept Visa, Mastercard, American Express, PayPal, and Apple Pay."),
    ("How do I contact customer support?", "You can reach our customer support team at support@example.com or call us at 1-800-123-4567."),
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

# Clear existing FAQs
cursor.execute("DELETE FROM faqs WHERE tenant_id = ?", (tenant_id,))

# Add new FAQs
for question, answer in sample_faqs:
    cursor.execute(
        "INSERT INTO faqs (tenant_id, question, answer) VALUES (?, ?, ?)",
        (tenant_id, question, answer)
    )

conn.commit()
conn.close()

print("Added sample FAQs to the tenant")