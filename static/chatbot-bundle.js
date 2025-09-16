(function() {
  function createChatWidget(config) {
    let isOpen = false;
    let messages = [{ role: 'assistant', content: 'Hello! How can I help you today?' }];
    
    const sendMessage = async (messageText) => {
      messages.push({ role: 'user', content: messageText });
      renderMessages();
      
      try {
        const response = await fetch(`${config.baseUrl}/chatbot/chat/smart`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-API-Key': config.apiKey
          },
          body: JSON.stringify({
            message: messageText,
            user_identifier: config.userId,
            max_context: 200
          })
        });
        
        const data = await response.json();
        messages.push({ role: 'assistant', content: data.response || 'Error occurred' });
        renderMessages();
      } catch (error) {
        messages.push({ role: 'assistant', content: 'Error occurred' });
        renderMessages();
      }
    };
    
    const renderMessages = () => {
      const messagesDiv = document.getElementById('chat-messages');
      if (!messagesDiv) return;
      
      messagesDiv.innerHTML = '';
      messages.forEach(msg => {
        const msgDiv = document.createElement('div');
        msgDiv.style.marginBottom = '10px';
        msgDiv.style.textAlign = msg.role === 'user' ? 'right' : 'left';
        
        const bubble = document.createElement('div');
        bubble.style.display = 'inline-block';
        bubble.style.padding = '8px 12px';
        bubble.style.borderRadius = '10px';
        bubble.style.backgroundColor = msg.role === 'user' ? '#007bff' : '#f1f1f1';
        bubble.style.color = msg.role === 'user' ? 'white' : 'black';
        bubble.textContent = msg.content;
        
        msgDiv.appendChild(bubble);
        messagesDiv.appendChild(msgDiv);
      });
    };
    
    const createWidget = () => {
      const container = document.getElementById('lyra-chatbot-widget');
      
      // Floating button
      const button = document.createElement('button');
      button.textContent = '💬';
      button.style.cssText = 'position:fixed;bottom:20px;right:20px;width:60px;height:60px;border-radius:50%;background:#007bff;border:none;color:white;font-size:24px;cursor:pointer;z-index:1000;';
      button.onclick = () => {
        isOpen = true;
        button.style.display = 'none';
        chatWindow.style.display = 'flex';
      };
      
      // Chat window
      const chatWindow = document.createElement('div');
      chatWindow.style.cssText = 'position:fixed;bottom:20px;right:20px;width:350px;height:500px;background:white;border:1px solid #ccc;border-radius:10px;display:none;flex-direction:column;z-index:1000;';
      
      // Header
      const header = document.createElement('div');
      header.style.cssText = 'padding:10px;border-bottom:1px solid #eee;display:flex;justify-content:space-between;';
      header.innerHTML = '<span>Chat Support</span><button onclick="this.parentElement.parentElement.style.display=\'none\';this.parentElement.parentElement.previousElementSibling.style.display=\'block\'">×</button>';
      
      // Messages area
      const messagesArea = document.createElement('div');
      messagesArea.id = 'chat-messages';
      messagesArea.style.cssText = 'flex:1;padding:10px;overflow-y:scroll;';
      
      // Input area
      const inputArea = document.createElement('div');
      inputArea.style.cssText = 'padding:10px;border-top:1px solid #eee;display:flex;';
      
      const input = document.createElement('input');
      input.type = 'text';
      input.style.cssText = 'flex:1;padding:8px;border:1px solid #ccc;border-radius:4px;';
      input.onkeypress = (e) => {
        if (e.key === 'Enter' && input.value.trim()) {
          sendMessage(input.value.trim());
          input.value = '';
        }
      };
      
      const sendBtn = document.createElement('button');
      sendBtn.textContent = 'Send';
      sendBtn.style.cssText = 'margin-left:10px;padding:8px 16px;background:#007bff;color:white;border:none;border-radius:4px;cursor:pointer;';
      sendBtn.onclick = () => {
        if (input.value.trim()) {
          sendMessage(input.value.trim());
          input.value = '';
        }
      };
      
      inputArea.appendChild(input);
      inputArea.appendChild(sendBtn);
      
      chatWindow.appendChild(header);
      chatWindow.appendChild(messagesArea);
      chatWindow.appendChild(inputArea);
      
      container.appendChild(button);
      container.appendChild(chatWindow);
      
      renderMessages();
    };
    
    createWidget();
  }
  
  window.LyraChatbot = {
    init: function(config) {
      createChatWidget(config);
    }
  };
})();