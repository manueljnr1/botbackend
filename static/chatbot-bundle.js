(function() {
    // Standalone React chatbot widget
    const React = window.React;
    const ReactDOM = window.ReactDOM;
    
    function ChatWidget({ config }) {
      const [isOpen, setIsOpen] = React.useState(false);
      const [message, setMessage] = React.useState('');
      const [messages, setMessages] = React.useState([
        { role: 'assistant', content: 'Hello! How can I help you today?' }
      ]);
      
      const sendMessage = async () => {
        if (!message.trim()) return;
        
        setMessages(prev => [...prev, { role: 'user', content: message }]);
        setMessage('');
        
        try {
          const response = await fetch(`${config.baseUrl}/chatbot/chat/smart`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-API-Key': config.apiKey
            },
            body: JSON.stringify({
              message: message,
              user_identifier: config.userId,
              max_context: 200
            })
          });
          
          const data = await response.json();
          setMessages(prev => [...prev, { role: 'assistant', content: data.response }]);
        } catch (error) {
          setMessages(prev => [...prev, { role: 'assistant', content: 'Error occurred' }]);
        }
      };
      
      return React.createElement('div', null,
        !isOpen && React.createElement('button', {
          onClick: () => setIsOpen(true),
          style: {
            position: 'fixed',
            bottom: '20px',
            right: '20px',
            width: '60px',
            height: '60px',
            borderRadius: '50%',
            backgroundColor: '#007bff',
            border: 'none',
            color: 'white',
            fontSize: '24px',
            cursor: 'pointer',
            zIndex: 1000
          }
        }, '💬'),
        
        isOpen && React.createElement('div', {
          style: {
            position: 'fixed',
            bottom: '20px',
            right: '20px',
            width: '350px',
            height: '500px',
            backgroundColor: 'white',
            border: '1px solid #ccc',
            borderRadius: '10px',
            display: 'flex',
            flexDirection: 'column',
            zIndex: 1000
          }
        },
          React.createElement('div', {
            style: { padding: '10px', borderBottom: '1px solid #eee', display: 'flex', justifyContent: 'space-between' }
          },
            React.createElement('span', null, 'Chat Support'),
            React.createElement('button', { onClick: () => setIsOpen(false) }, '×')
          ),
          
          React.createElement('div', {
            style: { flex: 1, padding: '10px', overflowY: 'scroll' }
          },
            messages.map((msg, i) => 
              React.createElement('div', {
                key: i,
                style: {
                  marginBottom: '10px',
                  textAlign: msg.role === 'user' ? 'right' : 'left'
                }
              },
                React.createElement('div', {
                  style: {
                    display: 'inline-block',
                    padding: '8px 12px',
                    borderRadius: '10px',
                    backgroundColor: msg.role === 'user' ? '#007bff' : '#f1f1f1',
                    color: msg.role === 'user' ? 'white' : 'black'
                  }
                }, msg.content)
              )
            )
          ),
          
          React.createElement('div', {
            style: { padding: '10px', borderTop: '1px solid #eee', display: 'flex' }
          },
            React.createElement('input', {
              type: 'text',
              value: message,
              onChange: (e) => setMessage(e.target.value),
              style: { flex: 1, padding: '8px', border: '1px solid #ccc', borderRadius: '4px' },
              onKeyPress: (e) => e.key === 'Enter' && sendMessage()
            }),
            React.createElement('button', {
              onClick: sendMessage,
              style: { marginLeft: '10px', padding: '8px 16px', backgroundColor: '#007bff', color: 'white', border: 'none', borderRadius: '4px' }
            }, 'Send')
          )
        )
      );
    }
    
    window.LyraChatbot = {
      init: function(config) {
        // Load React if not available
        if (!window.React) {
          const reactScript = document.createElement('script');
          reactScript.src = 'https://unpkg.com/react@18/umd/react.production.min.js';
          document.head.appendChild(reactScript);
          
          const reactDOMScript = document.createElement('script');
          reactDOMScript.src = 'https://unpkg.com/react-dom@18/umd/react-dom.production.min.js';
          document.head.appendChild(reactDOMScript);
          
          reactDOMScript.onload = () => {
            const container = document.getElementById('lyra-chatbot-widget');
            ReactDOM.render(React.createElement(ChatWidget, { config }), container);
          };
        } else {
          const container = document.getElementById('lyra-chatbot-widget');
          ReactDOM.render(React.createElement(ChatWidget, { config }), container);
        }
      }
    };
  })();