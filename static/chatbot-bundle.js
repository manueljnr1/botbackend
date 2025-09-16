// (function() {
//   function createChatWidget(config) {
//     let isOpen = false;
//     let messages = [{ role: 'assistant', content: 'Hello! How can I help you today?' }];
    
//     const sendMessage = async (messageText) => {
//       messages.push({ role: 'user', content: messageText });
//       renderMessages();
      
//       try {
//         const response = await fetch(`${config.baseUrl}/chatbot/chat/smart`, {
//           method: 'POST',
//           headers: {
//             'Content-Type': 'application/json',
//             'X-API-Key': config.apiKey
//           },
//           body: JSON.stringify({
//             message: messageText,
//             user_identifier: config.userId,
//             max_context: 200
//           })
//         });
        
//         const data = await response.json();
//         messages.push({ role: 'assistant', content: data.response || 'Error occurred' });
//         renderMessages();
//       } catch (error) {
//         messages.push({ role: 'assistant', content: 'Error occurred' });
//         renderMessages();
//       }
//     };
    
//     const renderMessages = () => {
//       const messagesDiv = document.getElementById('chat-messages');
//       if (!messagesDiv) return;
      
//       messagesDiv.innerHTML = '';
//       messages.forEach(msg => {
//         const msgDiv = document.createElement('div');
//         msgDiv.style.marginBottom = '10px';
//         msgDiv.style.textAlign = msg.role === 'user' ? 'right' : 'left';
        
//         const bubble = document.createElement('div');
//         bubble.style.display = 'inline-block';
//         bubble.style.padding = '8px 12px';
//         bubble.style.borderRadius = '10px';
//         bubble.style.backgroundColor = msg.role === 'user' ? '#007bff' : '#f1f1f1';
//         bubble.style.color = msg.role === 'user' ? 'white' : 'black';
//         bubble.textContent = msg.content;
        
//         msgDiv.appendChild(bubble);
//         messagesDiv.appendChild(msgDiv);
//       });
//     };
    
//     const createWidget = () => {
//       const container = document.getElementById('lyra-chatbot-widget');
//       if (!container) {
//           console.error("The target element #lyra-chatbot-widget was not found in the DOM.");
//           return;
//       }
      
//       // Floating button
//       const button = document.createElement('button');
//       button.textContent = '💬';
//       button.style.cssText = 'position:fixed;bottom:20px;right:20px;width:60px;height:60px;border-radius:50%;background:#007bff;border:none;color:white;font-size:24px;cursor:pointer;z-index:1000;';
//       button.onclick = () => {
//         isOpen = true;
//         button.style.display = 'none';
//         chatWindow.style.display = 'flex';
//       };
      
//       // Chat window
//       const chatWindow = document.createElement('div');
//       chatWindow.style.cssText = 'position:fixed;bottom:20px;right:20px;width:350px;height:500px;background:white;border:1px solid #ccc;border-radius:10px;display:none;flex-direction:column;z-index:1000;';
      
//       // Header
//       const header = document.createElement('div');
//       header.style.cssText = 'padding:10px;border-bottom:1px solid #eee;display:flex;justify-content:space-between;';
      
//       const headerTitle = document.createElement('span');
//       headerTitle.textContent = 'Chat Support';
      
//       const closeBtn = document.createElement('button');
//       closeBtn.innerHTML = '&times;'; // Use innerHTML for the '×' character
//       closeBtn.style.cssText = 'background:none;border:none;font-size:20px;cursor:pointer;';
//       closeBtn.onclick = () => {
//         chatWindow.style.display = 'none';
//         button.style.display = 'block';
//       };
      
//       header.appendChild(headerTitle);
//       header.appendChild(closeBtn);
      
//       // Messages area
//       const messagesArea = document.createElement('div');
//       messagesArea.id = 'chat-messages';
//       messagesArea.style.cssText = 'flex:1;padding:10px;overflow-y:scroll;';
      
//       // Input area
//       const inputArea = document.createElement('div');
//       inputArea.style.cssText = 'padding:10px;border-top:1px solid #eee;display:flex;';
      
//       const input = document.createElement('input');
//       input.type = 'text';
//       input.placeholder = 'Type a message...';
//       input.style.cssText = 'flex:1;padding:8px;border:1px solid #ccc;border-radius:4px;';
//       input.onkeypress = (e) => {
//         if (e.key === 'Enter' && input.value.trim()) {
//           sendMessage(input.value.trim());
//           input.value = '';
//         }
//       };
      
//       const sendBtn = document.createElement('button');
//       sendBtn.textContent = 'Send';
//       sendBtn.style.cssText = 'margin-left:10px;padding:8px 16px;background:#007bff;color:white;border:none;border-radius:4px;cursor:pointer;';
//       sendBtn.onclick = () => {
//         if (input.value.trim()) {
//           sendMessage(input.value.trim());
//           input.value = '';
//         }
//       };
      
//       inputArea.appendChild(input);
//       inputArea.appendChild(sendBtn);
      
//       chatWindow.appendChild(header);
//       chatWindow.appendChild(messagesArea);
//       chatWindow.appendChild(inputArea);
      
//       container.appendChild(button);
//       container.appendChild(chatWindow);
      
//       renderMessages();
//     };
    
//     createWidget();
//   }
  
//   // Expose the init function to the global scope
//   window.LyraChatbot = {
//     init: function(config) {
//       // **MODIFICATION HERE**
//       // Wait for the document to be fully loaded before creating the widget
//       document.addEventListener('DOMContentLoaded', function() {
//         createChatWidget(config);
//       });
//     }
//   };
// })();


(function() {
  window.LyraChatbot = {
    init: function(config) {
      try {
        const container = document.getElementById('lyra-chatbot-widget');
        if (!container) return;
        
        let isOpen = false;
        let messages = [{ role: 'assistant', content: 'Hello! How can I help you today?' }];
        
        // Chat button
        const button = document.createElement('button');
        button.textContent = '💬';
        button.style.cssText = 'position:fixed;bottom:20px;right:20px;width:60px;height:60px;border-radius:50%;background:#007bff;border:none;color:white;font-size:24px;cursor:pointer;z-index:9999;';
        
        // Chat window
        const chatWindow = document.createElement('div');
        chatWindow.style.cssText = 'position:fixed;bottom:20px;right:20px;width:350px;height:500px;background:white;border:1px solid #ccc;border-radius:10px;display:none;flex-direction:column;z-index:9998;box-shadow:0 4px 12px rgba(0,0,0,0.15);';
        
        const header = document.createElement('div');
        header.style.cssText = 'padding:15px;background:#007bff;color:white;border-radius:10px 10px 0 0;display:flex;justify-content:space-between;align-items:center;';
        header.innerHTML = '<span style="font-weight:bold;">Chat Support</span><button onclick="this.closest(\'.chat-window\').style.display=\'none\';this.closest(\'.lyra-widget\').querySelector(\'.chat-button\').style.display=\'block\';" style="background:none;border:none;color:white;font-size:18px;cursor:pointer;">×</button>';
        
        const messagesDiv = document.createElement('div');
        messagesDiv.style.cssText = 'flex:1;padding:15px;overflow-y:auto;';
        messagesDiv.className = 'messages-area';
        
        const inputArea = document.createElement('div');
        inputArea.style.cssText = 'padding:15px;border-top:1px solid #eee;display:flex;gap:10px;';
        
        const input = document.createElement('input');
        input.type = 'text';
        input.placeholder = 'Type your message...';
        input.style.cssText = 'flex:1;padding:10px;border:1px solid #ddd;border-radius:5px;outline:none;';
        
        const sendBtn = document.createElement('button');
        sendBtn.textContent = 'Send';
        sendBtn.style.cssText = 'padding:10px 15px;background:#007bff;color:white;border:none;border-radius:5px;cursor:pointer;';
        
        chatWindow.appendChild(header);
        chatWindow.appendChild(messagesDiv);
        inputArea.appendChild(input);
        inputArea.appendChild(sendBtn);
        chatWindow.appendChild(inputArea);
        
        const widget = document.createElement('div');
        widget.className = 'lyra-widget';
        button.className = 'chat-button';
        chatWindow.className = 'chat-window';
        
        widget.appendChild(button);
        widget.appendChild(chatWindow);
        container.appendChild(widget);
        
        const renderMessages = () => {
          messagesDiv.innerHTML = '';
          messages.forEach(msg => {
            const msgDiv = document.createElement('div');
            msgDiv.style.marginBottom = '10px';
            msgDiv.style.textAlign = msg.role === 'user' ? 'right' : 'left';
            
            const bubble = document.createElement('div');
            bubble.style.cssText = `display:inline-block;padding:8px 12px;border-radius:15px;max-width:80%;word-wrap:break-word;${msg.role === 'user' ? 'background:#007bff;color:white;' : 'background:#f1f1f1;color:black;'}`;
            bubble.textContent = msg.content;
            
            msgDiv.appendChild(bubble);
            messagesDiv.appendChild(msgDiv);
          });
          messagesDiv.scrollTop = messagesDiv.scrollHeight;
        };
        
        const sendMessage = async (text) => {
          if (!text.trim()) return;
          
          messages.push({ role: 'user', content: text });
          renderMessages();
          input.value = '';
          
          try {
            const response = await fetch(`${config.baseUrl}/chatbot/chat/smart`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'X-API-Key': config.apiKey
              },
              body: JSON.stringify({
                message: text,
                user_identifier: config.userId,
                max_context: 200
              })
            });
            
            const data = await response.json();
            messages.push({ role: 'assistant', content: data.response || 'Sorry, I encountered an error.' });
            renderMessages();
          } catch (error) {
            messages.push({ role: 'assistant', content: 'Sorry, I encountered an error.' });
            renderMessages();
          }
        };
        
        button.onclick = () => {
          button.style.display = 'none';
          chatWindow.style.display = 'flex';
          renderMessages();
        };
        
        sendBtn.onclick = () => sendMessage(input.value);
        input.onkeypress = (e) => e.key === 'Enter' && sendMessage(input.value);
        
      } catch (error) {
        console.error('Widget error:', error);
      }
    }
  };
})();