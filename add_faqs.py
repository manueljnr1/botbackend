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