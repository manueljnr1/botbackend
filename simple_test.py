# simple_email_test.py
import sys
import os

# Add project root to path
sys.path.insert(0, '/Users/mac/Downloads/chatbot')

print("Testing email service...")
print("=" * 50)

# Import the email service
try:
    from app.core.email_service import email_service
    print("✅ Email service imported successfully")
except Exception as e:
    print(f"❌ Failed to import email service: {e}")
    exit(1)

# Check configuration
print("\nConfiguration status:")
print(f"Is configured: {email_service.is_configured}")

if not email_service.is_configured:
    print("\n❌ Email service not configured properly")
    print("\nTo fix this:")
    print("1. Create a .env file in your project root (/Users/mac/Downloads/chatbot/.env)")
    print("2. Add these variables:")
    print("   SENDGRID_API_KEY=SG.your-sendgrid-api-key")
    print("   DEFAULT_SENDER_EMAIL=your-verified-email@gmail.com")
    print("   DEFAULT_SENDER_NAME=Your App Name")
    print("\n3. Set up SendGrid:")
    print("   - Go to sendgrid.com")
    print("   - Create free account")
    print("   - Verify your sender email")
    print("   - Create API key with Mail Send permission")
    exit(1)

# Test sending email
print("\n" + "=" * 50)
test_email = input("Enter your email for testing: ").strip()

if not test_email:
    print("No email provided, exiting...")
    exit(1)

print(f"\nSending test email to: {test_email}")

success = email_service.send_email(
    to_email=test_email,
    subject="🎉 Test Email from Your Chatbot App",
    html_content="""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background-color: #28a745; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0;">
            <h2>✅ Success!</h2>
        </div>
        <div style="background-color: #f8f9fa; padding: 20px; border: 1px solid #dee2e6; border-radius: 0 0 5px 5px;">
            <p><strong>Congratulations!</strong> Your email service is working correctly.</p>
            <p>This means your password reset emails will work properly.</p>
            <h3>What's working:</h3>
            <ul>
                <li>✅ SendGrid API connection</li>
                <li>✅ Email sending capability</li>
                <li>✅ Environment variable loading</li>
            </ul>
            <p><strong>Next step:</strong> Test your forgot password endpoint!</p>
        </div>
    </body>
    </html>
    """
)

if success:
    print("\n🎉 SUCCESS! Email sent successfully!")
    print("📧 Check your inbox (and spam folder)")
    print("✅ Your password reset system is ready to use!")
else:
    print("\n❌ Failed to send email")
    print("Check the error messages above")