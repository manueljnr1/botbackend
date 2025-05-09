# Multi-Tenant AI Customer Support Chatbot

A sophisticated AI-powered customer support chatbot system that allows different businesses to have their own isolated chatbot with custom knowledge bases and FAQ data.

## Features

- **Multi-Tenant Architecture**: Each business has its own isolated chatbot
- **GPT-4 Integration**: Powered by OpenAI's GPT-4 for intelligent responses
- **Knowledge Base Management**: Upload documents (PDF, DOC, DOCX, TXT, CSV, XLSX)
- **FAQ Management**: Upload FAQ spreadsheets or add individual Q&A pairs
- **Multiple Integration Channels**: Slack, WhatsApp, and webhook integrations
- **Vector Embedding**: Efficient semantic search with FAISS vector database

## Quick Start

### Prerequisites

- Python 3.11+
- OpenAI API Key
- PostgreSQL (optional, SQLite works for development)

### Installation

1. Clone this repository:
   ```
   git clone <repository-url>
   cd multi-tenant-chatbot
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Run the setup script:
   ```
   python setup.py
   ```

4. Edit the `.env` file with your OpenAI API key and other settings:
   ```
   OPENAI_API_KEY=your-key-here
   ```

5. Start the application:
   ```
   uvicorn app.main:app --reload
   ```

The API will be available at `http://localhost:8000`

## Project Structure

```
multi_tenant_chatbot/
├── app/                    # Main application package
│   ├── auth/               # Authentication models
│   ├── tenants/            # Tenant management models
│   ├── knowledge_base/     # Document processing
│   ├── chatbot/            # Chatbot engine
│   ├── integrations/       # Platform integrations
│   ├── database.py         # Database connection setup
│   ├── config.py           # Configuration settings
│   └── main.py             # Application entry point
├── uploads/                # Uploaded document storage
├── vector_db/              # Vector embeddings storage
├── temp/                   # Temporary file storage
├── requirements.txt        # Python dependencies
├── setup.py                # Setup script
└── .env                    # Environment variables
```

## API Endpoints

The API includes the following endpoints:

- **Authentication**: `/auth/token`
- **Tenant Management**: `/tenants/`
- **Knowledge Base**: `/knowledge-base/`
- **Chatbot**: `/chatbot/chat`
- **Integrations**:
  - Slack: `/integrations/slack/events`
  - WhatsApp: `/integrations/whatsapp/webhook`
  - Webhook: `/integrations/webhook/chat`

## Using the Chatbot

1. Create a tenant with an API key
2. Upload knowledge base documents and FAQs
3. Send messages to the chatbot API:

```python
import requests

response = requests.post(
    "http://localhost:8000/chatbot/chat",
    headers={"X-API-Key": "your-tenant-api-key"},
    json={
        "message": "Hello, I need help with my order",
        "user_identifier": "customer123"
    }
)

print(response.json())
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| DATABASE_URL | Database connection string | sqlite:///./chatbot.db |
| JWT_SECRET_KEY | Secret key for JWT tokens | your-secret-key |
| OPENAI_API_KEY | OpenAI API key | None |
| VECTOR_DB_PATH | Path to vector database | ./vector_db |
| SLACK_SIGNING_SECRET | Slack signing secret | None |
| SLACK_BOT_TOKEN | Slack bot token | None |
| TWILIO_ACCOUNT_SID | Twilio account SID | None |
| TWILIO_AUTH_TOKEN | Twilio auth token | None |

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.