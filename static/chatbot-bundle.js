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
  // Inject CSS styles
  const style = document.createElement('style');
  style.textContent = `
    .lyra-widget * { box-sizing: border-box; }
    .lyra-float-1 { animation: lyra-float 3s ease-in-out infinite; animation-delay: 0s; }
    .lyra-float-2 { animation: lyra-float 3s ease-in-out infinite; animation-delay: 0.5s; }
    .lyra-float-3 { animation: lyra-float 3s ease-in-out infinite; animation-delay: 1s; }
    .lyra-float-4 { animation: lyra-float 3s ease-in-out infinite; animation-delay: 1.5s; }
    .lyra-float-5 { animation: lyra-float 3s ease-in-out infinite; animation-delay: 2s; }
    .lyra-float-6 { animation: lyra-float 3s ease-in-out infinite; animation-delay: 2.5s; }
    @keyframes lyra-float {
      0%, 100% { transform: translateY(0px); opacity: 0.2; }
      50% { transform: translateY(-20px); opacity: 0.8; }
    }
    @keyframes lyra-pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }
    .lyra-typing-dot {
      width: 6px; height: 6px; background: #a855f7; border-radius: 50%; 
      animation: lyra-pulse 1.4s ease-in-out infinite both;
    }
    .lyra-typing-dot:nth-child(1) { animation-delay: -0.32s; }
    .lyra-typing-dot:nth-child(2) { animation-delay: -0.16s; }
    .lyra-typing-dot:nth-child(3) { animation-delay: 0s; }
    .lyra-scroll::-webkit-scrollbar { width: 4px; }
    .lyra-scroll::-webkit-scrollbar-track { background: rgba(255,255,255,0.1); }
    .lyra-scroll::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.3); border-radius: 2px; }
  `;
  document.head.appendChild(style);

  window.LyraChatbot = {
    init: function(config) {
      try {
        const container = document.getElementById('lyra-chatbot-widget');
        if (!container) return;

        let isOpen = false;
        let isExpanded = false;
        let isTyping = false;
        let messages = [{ role: 'assistant', content: 'Hello! How can I help you today?' }];

        // Create floating background elements
        const floatingBg = document.createElement('div');
        floatingBg.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:40;';
        
        for (let i = 1; i <= 6; i++) {
          const dot = document.createElement('div');
          dot.className = `lyra-float-${i}`;
          dot.style.cssText = `position:absolute;width:4px;height:4px;background:rgba(139,92,246,0.2);border-radius:50%;top:${20 + i * 15}%;left:${20 + i * 12}%;`;
          floatingBg.appendChild(dot);
        }

        // Chat button with custom SVG icon
        const button = document.createElement('button');
        button.style.cssText = `
          position:fixed;bottom:16px;right:16px;width:56px;height:56px;border-radius:50%;
          background:linear-gradient(45deg, #8b5cf6, #3b82f6);border:none;
          box-shadow:0 20px 25px -5px rgba(0,0,0,0.1), 0 10px 10px -5px rgba(0,0,0,0.04);
          cursor:pointer;z-index:1000;transition:all 0.3s ease;
          display:flex;align-items:center;justify-content:center;
        `;
        button.innerHTML = `
          <svg width="24" height="24" viewBox="0 0 32 32" fill="white">
            <path d="M0 0 C0.94101562 -0.01675781 1.88203125 -0.03351562 2.8515625 -0.05078125 C5.375 0.3125 5.375 0.3125 7.1875 1.4921875 C8.81620937 3.98882752 8.77412297 5.78689539 8.75 8.75 C8.75773437 9.69746094 8.76546875 10.64492187 8.7734375 11.62109375 C8.31447132 14.72136532 7.5434107 16.07791714 5.375 18.3125 C2.35333856 19.31972048 0.39774409 19.38591677 -2.75 19.3125 C-4.37456329 19.27482897 -6.00066762 19.26592416 -7.625 19.3125 C-7.955 19.6425 -8.285 19.9725 -8.625 20.3125 C-10.62458364 20.35330783 -12.62545254 20.35504356 -14.625 20.3125 C-13.965 18.9925 -13.305 17.6725 -12.625 16.3125 C-13.12 15.961875 -13.615 15.61125 -14.125 15.25 C-15.625 13.3125 -15.625 13.3125 -16.125 9.875 C-15.625 6.3125 -15.625 6.3125 -13.4375 4 C-8.9125767 1.28504602 -5.30278687 0.02191234 0 0 Z" transform="translate(15.625,1.6875)"/>
          </svg>
        `;

        button.onmouseenter = () => {
          button.style.transform = 'scale(1.1)';
          button.style.boxShadow = '0 0 15px rgba(139,92,246,0.6)';
        };
        button.onmouseleave = () => {
          button.style.transform = 'scale(1)';
          button.style.boxShadow = '0 20px 25px -5px rgba(0,0,0,0.1), 0 10px 10px -5px rgba(0,0,0,0.04)';
        };

        // Chat window
        const chatWindow = document.createElement('div');
        const updateChatWindow = () => {
          const isMobile = window.innerWidth < 640;
          const baseStyle = `
            position:fixed;z-index:50;display:${isOpen ? 'flex' : 'none'};flex-direction:column;
            background:rgba(255,255,255,0.1);backdrop-filter:blur(16px);
            border:1px solid rgba(255,255,255,0.2);box-shadow:0 25px 50px -12px rgba(0,0,0,0.25);
            transition:all 0.3s cubic-bezier(0.4,0,0.2,1);overflow:hidden;
          `;
          
          if (isMobile) {
            chatWindow.style.cssText = baseStyle + `
              top:0;right:0;bottom:0;left:0;width:100%;height:100vh;border-radius:0;
            `;
          } else {
            chatWindow.style.cssText = baseStyle + `
              bottom:16px;right:16px;width:${isExpanded ? '560px' : '384px'};
              height:${isExpanded ? '90vh' : '560px'};max-height:90vh;border-radius:16px;
            `;
          }
        };
        updateChatWindow();
        window.addEventListener('resize', updateChatWindow);

        // Header
        const header = document.createElement('div');
        header.style.cssText = `
          display:flex;align-items:center;justify-content:space-between;
          padding:16px;background:rgba(255,255,255,0.05);
        `;

        const headerLeft = document.createElement('div');
        headerLeft.style.cssText = 'display:flex;align-items:center;gap:8px;';
        
        const avatar = document.createElement('div');
        avatar.style.cssText = `
          width:50px;height:50px;background:rgba(255,255,255,0.2);border-radius:50%;
          display:flex;align-items:center;justify-content:center;
        `;
        avatar.innerHTML = `
          <svg width="40" height="40" viewBox="0 0 24 24" fill="white">
            <path d="M12 2C13.1 2 14 2.9 14 4C14 5.1 13.1 6 12 6C10.9 6 10 5.1 10 4C10 2.9 10.9 2 12 2ZM21 9V7L15 1H5C3.9 1 3 1.9 3 3V19C3 20.1 3.9 21 5 21H19C20.1 21 21 20.1 21 19V9ZM19 19H5V3H14V8H19V19Z"/>
          </svg>
        `;

        const title = document.createElement('span');
        title.textContent = 'Support Chat';
        title.style.cssText = 'font-size:18px;font-weight:600;color:white;';

        headerLeft.appendChild(avatar);
        headerLeft.appendChild(title);

        const headerRight = document.createElement('div');
        headerRight.style.cssText = 'display:flex;align-items:center;gap:8px;';

        const expandBtn = document.createElement('button');
        expandBtn.style.cssText = `
          width:24px;height:24px;background:none;border:none;color:white;cursor:pointer;
          display:flex;align-items:center;justify-content:center;border-radius:4px;
          transition:background 0.2s;
        `;
        expandBtn.onmouseenter = () => expandBtn.style.background = 'rgba(255,255,255,0.2)';
        expandBtn.onmouseleave = () => expandBtn.style.background = 'none';
        expandBtn.onclick = () => {
          isExpanded = !isExpanded;
          updateChatWindow();
          expandBtn.innerHTML = isExpanded ? `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="4 14 10 14 10 20"></polyline>
              <polyline points="20 10 14 10 14 4"></polyline>
              <line x1="14" y1="10" x2="21" y2="3"></line>
              <line x1="3" y1="21" x2="10" y2="14"></line>
            </svg>
          ` : `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="15 3 21 3 21 9"></polyline>
              <polyline points="9 21 3 21 3 15"></polyline>
              <line x1="21" y1="3" x2="14" y2="10"></line>
              <line x1="3" y1="21" x2="10" y2="14"></line>
            </svg>
          `;
        };

        const closeBtn = document.createElement('button');
        closeBtn.style.cssText = expandBtn.style.cssText;
        closeBtn.innerHTML = `
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        `;
        closeBtn.onmouseenter = () => closeBtn.style.background = 'rgba(255,255,255,0.2)';
        closeBtn.onmouseleave = () => closeBtn.style.background = 'none';
        closeBtn.onclick = () => {
          isOpen = false;
          button.style.display = 'flex';
          updateChatWindow();
        };

        expandBtn.innerHTML = `
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="15 3 21 3 21 9"></polyline>
            <polyline points="9 21 3 21 3 15"></polyline>
            <line x1="21" y1="3" x2="14" y2="10"></line>
            <line x1="3" y1="21" x2="10" y2="14"></line>
          </svg>
        `;

        headerRight.appendChild(expandBtn);
        headerRight.appendChild(closeBtn);

        header.appendChild(headerLeft);
        header.appendChild(headerRight);

        // Main content area
        const content = document.createElement('div');
        content.style.cssText = 'display:flex;flex-direction:column;flex:1;min-height:0;';

        // Messages area with intro
        const messagesContainer = document.createElement('div');
        messagesContainer.style.cssText = `
          flex:1;min-height:0;display:flex;flex-direction:column;gap:24px;
          padding:24px;overflow-y:auto;
        `;
        messagesContainer.className = 'lyra-scroll';

        const intro = document.createElement('div');
        intro.style.cssText = 'display:flex;flex-direction:column;align-items:center;gap:16px;margin-bottom:16px;';

        const largeLogo = document.createElement('div');
        largeLogo.style.cssText = `
          width:70px;height:70px;background:rgba(255,255,255,0.8);border-radius:50%;
          display:flex;align-items:center;justify-content:center;
        `;
        largeLogo.innerHTML = `
          <svg width="70" height="70" viewBox="0 0 24 24" fill="#007bff">
            <path d="M12 2C13.1 2 14 2.9 14 4C14 5.1 13.1 6 12 6C10.9 6 10 5.1 10 4C10 2.9 10.9 2 12 2ZM21 9V7L15 1H5C3.9 1 3 1.9 3 3V19C3 20.1 3.9 21 5 21H19C20.1 21 21 20.1 21 19V9ZM19 19H5V3H14V8H19V19Z"/>
          </svg>
        `;

        const introText = document.createElement('div');
        introText.style.cssText = 'display:flex;flex-direction:column;gap:12px;text-align:center;color:white;';
        introText.innerHTML = `
          <h4 style="font-size:32px;font-weight:500;margin:0;">Support Chat</h4>
          <span style="font-size:12px;color:rgb(209,213,219);">Powered by AI</span>
        `;

        intro.appendChild(largeLogo);
        intro.appendChild(introText);

        const messagesDiv = document.createElement('div');
        messagesDiv.style.cssText = 'display:flex;flex-direction:column;gap:16px;';

        messagesContainer.appendChild(intro);
        messagesContainer.appendChild(messagesDiv);

        // Input area
        const inputArea = document.createElement('div');
        inputArea.style.cssText = `
          border-top:1px solid rgba(255,255,255,0.2);padding:16px;
          display:flex;align-items:center;gap:12px;color:white;
          background:rgba(0,0,0,0.1);
        `;

        const input = document.createElement('input');
        input.type = 'text';
        input.placeholder = 'Type your message...';
        input.style.cssText = `
          flex:1;height:48px;padding:0 12px;border:1px solid rgba(255,255,255,0.3);
          border-radius:8px;background:rgba(0,0,0,0.2);color:white;outline:none;
          font-size:14px;transition:all 0.2s;
        `;
        input.style.setProperty('::placeholder', 'color: rgb(156,163,175);');

        input.onfocus = () => {
          input.style.borderColor = '#8b5cf6';
          input.style.boxShadow = '0 0 0 3px rgba(139,92,246,0.2)';
        };
        input.onblur = () => {
          input.style.borderColor = 'rgba(255,255,255,0.3)';
          input.style.boxShadow = 'none';
        };

        const sendBtn = document.createElement('button');
        sendBtn.style.cssText = `
          width:48px;height:48px;background:linear-gradient(45deg, #8b5cf6, #3b82f6);
          color:white;border:none;border-radius:8px;cursor:pointer;
          display:flex;align-items:center;justify-content:center;
          box-shadow:0 10px 15px -3px rgba(0,0,0,0.1);transition:all 0.2s;
        `;
        sendBtn.innerHTML = `
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="22" y1="2" x2="11" y2="13"></line>
            <polygon points="22,2 15,22 11,13 2,9 22,2"></polygon>
          </svg>
        `;
        sendBtn.onmouseenter = () => {
          sendBtn.style.background = 'linear-gradient(45deg, #7c3aed, #2563eb)';
          sendBtn.style.boxShadow = '0 0 20px rgba(139,92,246,0.2)';
        };
        sendBtn.onmouseleave = () => {
          sendBtn.style.background = 'linear-gradient(45deg, #8b5cf6, #3b82f6)';
          sendBtn.style.boxShadow = '0 10px 15px -3px rgba(0,0,0,0.1)';
        };

        inputArea.appendChild(input);
        inputArea.appendChild(sendBtn);

        content.appendChild(messagesContainer);
        content.appendChild(inputArea);

        chatWindow.appendChild(header);
        chatWindow.appendChild(content);

        // Render messages
        const renderMessages = () => {
          messagesDiv.innerHTML = '';
          messages.forEach(msg => {
            const msgContainer = document.createElement('div');
            msgContainer.style.cssText = msg.role === 'assistant' 
              ? 'display:flex;align-items:flex-start;gap:12px;'
              : 'display:flex;justify-content:flex-end;';

            const bubble = document.createElement('div');
            if (msg.role === 'assistant') {
              bubble.style.cssText = `
                border-radius:12px;padding:12px;font-size:14px;max-width:90%;
                background:rgba(0,0,0,0.5);color:white;word-break:break-word;
                box-shadow:0 10px 15px -3px rgba(0,0,0,0.1);
                border:1px solid rgba(255,255,255,0.1);
                transform:scale(1);transition:transform 0.2s;line-height:1.6;
              `;
              bubble.innerHTML = msg.content;
            } else {
              bubble.style.cssText = `
                border-radius:12px;padding:12px;font-size:14px;max-width:90%;
                background:linear-gradient(135deg, #8b5cf6, #3b82f6);color:white;
                word-break:break-word;box-shadow:0 10px 15px -3px rgba(0,0,0,0.1);
                backdrop-filter:blur(4px);transform:scale(1);transition:transform 0.2s;line-height:1.6;
              `;
              bubble.textContent = msg.content;
            }

            bubble.onmouseenter = () => bubble.style.transform = 'scale(1.02)';
            bubble.onmouseleave = () => bubble.style.transform = 'scale(1)';

            msgContainer.appendChild(bubble);
            messagesDiv.appendChild(msgContainer);
          });

          if (isTyping) {
            const typingContainer = document.createElement('div');
            typingContainer.style.cssText = 'display:flex;align-items:flex-start;gap:12px;';
            
            const typingBubble = document.createElement('div');
            typingBubble.style.cssText = `
              background:rgba(0,0,0,0.5);border-radius:12px;padding:8px;max-width:80%;
              box-shadow:0 10px 15px -3px rgba(0,0,0,0.1);
              border:1px solid rgba(255,255,255,0.1);
            `;
            
            const dots = document.createElement('div');
            dots.style.cssText = 'display:flex;gap:8px;';
            for (let i = 0; i < 3; i++) {
              const dot = document.createElement('div');
              dot.className = 'lyra-typing-dot';
              dots.appendChild(dot);
            }
            
            typingBubble.appendChild(dots);
            typingContainer.appendChild(typingBubble);
            messagesDiv.appendChild(typingContainer);
          }

          messagesContainer.scrollTop = messagesContainer.scrollHeight;
        };

        // Send message function
        const sendMessage = async (text) => {
          if (!text.trim()) return;
          
          messages.push({ role: 'user', content: text });
          renderMessages();
          input.value = '';
          input.disabled = true;
          sendBtn.disabled = true;
          isTyping = true;
          renderMessages();

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

            const responseText = await response.text();
            const lines = responseText.trim().split('\n');
            let botMessage = '';

            for (const line of lines) {
              if (line.trim()) {
                try {
                  const obj = JSON.parse(line);
                  if (obj.type === 'main_response') {
                    botMessage = obj.content;
                    break;
                  }
                } catch (e) {
                  console.error('Parse error:', e);
                }
              }
            }

            messages.push({ 
              role: 'assistant', 
              content: botMessage || 'I apologize, but I was unable to process your request. Please try again.' 
            });
          } catch (error) {
            console.error('Error:', error);
            messages.push({ role: 'assistant', content: 'Sorry, I encountered an error. Please try again.' });
          } finally {
            isTyping = false;
            input.disabled = false;
            sendBtn.disabled = false;
            renderMessages();
            input.focus();
          }
        };

        // Event listeners
        button.onclick = () => {
          isOpen = true;
          button.style.display = 'none';
          updateChatWindow();
          renderMessages();
          setTimeout(() => input.focus(), 100);
        };

        sendBtn.onclick = () => sendMessage(input.value);
        input.onkeydown = (e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage(input.value);
          }
        };

        // Add to DOM
        const widget = document.createElement('div');
        widget.className = 'lyra-widget';
        widget.appendChild(floatingBg);
        widget.appendChild(button);
        widget.appendChild(chatWindow);
        container.appendChild(widget);

        renderMessages();

      } catch (error) {
        console.error('Widget initialization error:', error);
      }
    }
  };
})();