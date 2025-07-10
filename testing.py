import resend
import os

resend.api_key = os.getenv("RESEND_API_KEY")

try:
    result = resend.Emails.send({
        "from": "onboarding@resend.dev",
        "to": ["emmanuelibbk@gmail.com"],
        "subject": "Test",
        "html": "<h1>Test email</h1>"
    })
    print("✅ Success:", result)
except Exception as e:
    print("❌ Error:", e)