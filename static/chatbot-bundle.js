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
    .chatbot-widget * { box-sizing: border-box; }
    
    /* Floating background animation */
    @keyframes chatbot-float {
      0%, 100% { transform: translateY(0px); opacity: 0.2; }
      50% { transform: translateY(-20px); opacity: 0.8; }
    }
    
    .chatbot-float-1 { animation: chatbot-float 3s ease-in-out infinite; animation-delay: 0s; }
    .chatbot-float-2 { animation: chatbot-float 3s ease-in-out infinite; animation-delay: 0.5s; }
    .chatbot-float-3 { animation: chatbot-float 3s ease-in-out infinite; animation-delay: 1s; }
    .chatbot-float-4 { animation: chatbot-float 3s ease-in-out infinite; animation-delay: 1.5s; }
    .chatbot-float-5 { animation: chatbot-float 3s ease-in-out infinite; animation-delay: 2s; }
    .chatbot-float-6 { animation: chatbot-float 3s ease-in-out infinite; animation-delay: 2.5s; }
    
    /* Typing animation */
    @keyframes chatbot-pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }
    
    .chatbot-typing-dot {
      width: 6px; 
      height: 6px; 
      background: #8b5cf6; 
      border-radius: 50%; 
      animation: chatbot-pulse 1.4s ease-in-out infinite both;
    }
    .chatbot-typing-dot:nth-child(1) { animation-delay: -0.32s; }
    .chatbot-typing-dot:nth-child(2) { animation-delay: -0.16s; }
    .chatbot-typing-dot:nth-child(3) { animation-delay: 0s; }
    
    /* Scrollbar styling */
    .chatbot-scroll::-webkit-scrollbar { width: 4px; }
    .chatbot-scroll::-webkit-scrollbar-track { background: rgba(255,255,255,0.1); }
    .chatbot-scroll::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.3); border-radius: 2px; }
    
    /* Button animations */
    @keyframes chatbot-pulse-ring {
      0% { transform: scale(0.33); }
      80%, 100% { opacity: 0; }
    }
    
    .chatbot-pulse-ring {
      position: absolute;
      border: 3px solid #8b5cf6;
      border-radius: 50%;
      width: 100%;
      height: 100%;
      animation: chatbot-pulse-ring 1.25s cubic-bezier(0.215, 0.61, 0.355, 1) infinite;
    }
    
    .chatbot-pulse-ring-2 {
      position: absolute;
      border: 3px solid #3b82f6;
      border-radius: 50%;
      width: 100%;
      height: 100%;
      animation: chatbot-pulse-ring 1.25s cubic-bezier(0.215, 0.61, 0.355, 1) infinite;
      animation-delay: 0.4s;
    }
    
    /* Message animations */
    @keyframes chatbot-fadeInUp {
      from {
        opacity: 0;
        transform: translateY(10px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }
    
    .chatbot-message-animate {
      animation: chatbot-fadeInUp 0.3s ease-out;
    }
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
        let userId = config.userId || ('user_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9));

        // Create floating background elements
        const floatingBg = document.createElement('div');
        floatingBg.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:40;';
        
        for (let i = 1; i <= 6; i++) {
          const dot = document.createElement('div');
          dot.className = `chatbot-float-${i}`;
          dot.style.cssText = `position:absolute;width:4px;height:4px;background:rgba(139,92,246,0.2);border-radius:50%;top:${20 + i * 15}%;left:${20 + i * 12}%;`;
          floatingBg.appendChild(dot);
        }

        // Chat button
        const button = document.createElement('button');
        button.style.cssText = `
          position:fixed;bottom:16px;right:16px;width:56px;height:56px;border-radius:50%;
          background:linear-gradient(45deg, ${config.brandColor || '#8b5cf6'}, #3b82f6);border:none;
          box-shadow:0 20px 25px -5px rgba(0,0,0,0.1), 0 10px 10px -5px rgba(0,0,0,0.04);
          cursor:pointer;z-index:1000;transition:all 0.3s ease;
          display:flex;align-items:center;justify-content:center;position:relative;
        `;
        
        button.innerHTML = `
          <div class="chatbot-pulse-ring"></div>
          <div class="chatbot-pulse-ring-2"></div>
          <svg width="24" height="24" viewBox="0 0 32 32" fill="white">
            <path d="M0 0 C0.94101562 -0.01675781 1.88203125 -0.03351562 2.8515625 -0.05078125 C5.375 0.3125 5.375 0.3125 7.1875 1.4921875 C8.81620937 3.98882752 8.77412297 5.78689539 8.75 8.75 C8.75773437 9.69746094 8.76546875 10.64492187 8.7734375 11.62109375 C8.31447132 14.72136532 7.5434107 16.07791714 5.375 18.3125 C2.35333856 19.31972048 0.39774409 19.38591677 -2.75 19.3125 C-4.37456329 19.27482897 -6.00066762 19.26592416 -7.625 19.3125 C-7.955 19.6425 -8.285 19.9725 -8.625 20.3125 C-10.62458364 20.35330783 -12.62545254 20.35504356 -14.625 20.3125 C-13.965 18.9925 -13.305 17.6725 -12.625 16.3125 C-13.12 15.961875 -13.615 15.61125 -14.125 15.25 C-15.625 13.3125 -15.625 13.3125 -16.125 9.875 C-15.625 6.3125 -15.625 6.3125 -13.4375 4 C-8.9125767 1.28504602 -5.30278687 0.02191234 0 0 Z" transform="translate(15.625,1.6875)"/>
          </svg>
        `;

        button.addEventListener('mouseenter', () => {
          button.style.transform = 'scale(1.1)';
          button.style.boxShadow = `0 0 20px ${config.brandColor || '#8b5cf6'}66`;
        });
        
        button.addEventListener('mouseleave', () => {
          button.style.transform = 'scale(1)';
          button.style.boxShadow = '0 20px 25px -5px rgba(0,0,0,0.1), 0 10px 10px -5px rgba(0,0,0,0.04)';
        });

        // Chat window
        const chatWindow = document.createElement('div');
        chatWindow.className = 'chatbot-widget';
        
        const updateChatWindow = () => {
          const isMobile = window.innerWidth < 640;
          const baseStyle = `
            position:fixed;z-index:50;display:${isOpen ? 'flex' : 'none'};flex-direction:column;
            background:rgba(255,255,255,0.05);backdrop-filter:blur(20px);
            border:1px solid rgba(255,255,255,0.1);
            box-shadow:0 25px 50px -12px rgba(0,0,0,0.25);
            transition:all 0.3s cubic-bezier(0.4,0,0.2,1);overflow:hidden;
          `;
          
          if (isMobile) {
            chatWindow.style.cssText = baseStyle + 'top:0;right:0;bottom:0;left:0;width:100%;height:100vh;border-radius:0;';
          } else {
            chatWindow.style.cssText = baseStyle + `
              bottom:16px;right:16px;width:${isExpanded ? '560px' : '384px'};
              height:${isExpanded ? '90vh' : '560px'};max-height:90vh;border-radius:16px;
            `;
          }
          
          if (isExpanded) {
            chatWindow.classList.add('chatbot-widget-expanded');
          } else {
            chatWindow.classList.remove('chatbot-widget-expanded');
          }
        };
        
        updateChatWindow();
        window.addEventListener('resize', updateChatWindow);

        // Header
        const header = document.createElement('div');
        header.className = 'chatbot-header';
        header.style.cssText = `
          display:flex;align-items:center;justify-content:space-between;
          padding:16px;background:rgba(255,255,255,0.05);backdrop-filter:blur(10px);
        `;

        const headerLeft = document.createElement('div');
        headerLeft.className = 'chatbot-header-left';
        headerLeft.style.cssText = 'display:flex;align-items:center;gap:12px;';
        
        const logoContainer = document.createElement('div');
        logoContainer.className = 'chatbot-logo-container';
        logoContainer.style.cssText = 'position:relative;display:flex;align-items:center;justify-content:center;';
        
        const logoImg = document.createElement('div');
        logoImg.style.cssText = `
          width:32px;height:32px;background:rgba(255,255,255,0.9);border-radius:50%;
          display:flex;align-items:center;justify-content:center;
        `;
        logoImg.innerHTML = `
          <svg width="20" height="20" viewBox="0 0 24 24" fill="${config.brandColor || '#8b5cf6'}">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
          </svg>
        `;
        
        const onlineIndicator = document.createElement('div');
        onlineIndicator.className = 'chatbot-online-indicator';
        onlineIndicator.style.cssText = `
          position:absolute;bottom:-2px;right:-2px;width:12px;height:12px;
          background:#10b981;border:2px solid white;border-radius:50%;
        `;
        
        logoContainer.appendChild(logoImg);
        logoContainer.appendChild(onlineIndicator);

        const headerInfo = document.createElement('div');
        headerInfo.className = 'chatbot-header-info';
        headerInfo.style.cssText = 'display:flex;flex-direction:column;';
        
        const title = document.createElement('h3');
        title.className = 'chatbot-title';
        title.textContent = 'Support Chat';
        title.style.cssText = 'margin:0;font-size:16px;font-weight:600;color:white;line-height:1.2;';
        
        const status = document.createElement('span');
        status.className = 'chatbot-status';
        status.textContent = 'Online';
        status.style.cssText = 'font-size:12px;color:#10b981;';

        headerInfo.appendChild(title);
        headerInfo.appendChild(status);
        headerLeft.appendChild(logoContainer);
        headerLeft.appendChild(headerInfo);

        const headerActions = document.createElement('div');
        headerActions.className = 'chatbot-header-actions';
        headerActions.style.cssText = 'display:flex;align-items:center;gap:8px;';

        const expandBtn = document.createElement('button');
        expandBtn.className = 'chatbot-expand-btn';
        expandBtn.style.cssText = `
          width:32px;height:32px;background:none;border:none;color:white;cursor:pointer;
          display:flex;align-items:center;justify-content:center;border-radius:6px;
          transition:background 0.2s;
        `;
        
        const updateExpandBtn = () => {
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
        updateExpandBtn();
        
        expandBtn.addEventListener('mouseenter', () => {
          expandBtn.style.background = 'rgba(255,255,255,0.1)';
        });
        expandBtn.addEventListener('mouseleave', () => {
          expandBtn.style.background = 'none';
        });
        expandBtn.addEventListener('click', () => {
          isExpanded = !isExpanded;
          updateChatWindow();
          updateExpandBtn();
        });

        const closeBtn = document.createElement('button');
        closeBtn.className = 'chatbot-close-btn';
        closeBtn.style.cssText = expandBtn.style.cssText;
        closeBtn.innerHTML = `
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        `;
        closeBtn.addEventListener('mouseenter', () => {
          closeBtn.style.background = 'rgba(255,255,255,0.1)';
        });
        closeBtn.addEventListener('mouseleave', () => {
          closeBtn.style.background = 'none';
        });
        closeBtn.addEventListener('click', () => {
          isOpen = false;
          button.style.display = 'flex';
          updateChatWindow();
        });

        headerActions.appendChild(expandBtn);
        headerActions.appendChild(closeBtn);
        header.appendChild(headerLeft);
        header.appendChild(headerActions);

        // Main content area
        const content = document.createElement('div');
        content.style.cssText = 'display:flex;flex-direction:column;flex:1;min-height:0;';

        // Messages area
        const chatBody = document.createElement('div');
        chatBody.className = 'chatbot-body chatbot-scroll';
        chatBody.style.cssText = `
          flex:1;min-height:0;display:flex;flex-direction:column;
          padding:24px;overflow-y:auto;
        `;

        // Brand section
        const brandSection = document.createElement('div');
        brandSection.className = 'chatbot-brand-section';
        brandSection.style.cssText = `
          display:flex;flex-direction:column;align-items:center;gap:16px;
          margin-bottom:24px;
        `;

        const brandLogoWrapper = document.createElement('div');
        brandLogoWrapper.className = 'chatbot-brand-logo-wrapper';
        brandLogoWrapper.style.cssText = 'position:relative;display:flex;align-items:center;justify-content:center;';

        const brandGlow = document.createElement('div');
        brandGlow.className = 'chatbot-brand-glow';
        brandGlow.style.cssText = `
          position:absolute;width:60px;height:60px;
          background:radial-gradient(circle, ${config.brandColor || '#8b5cf6'}40, transparent);
          border-radius:50%;animation:chatbot-pulse 2s infinite;
        `;

        const brandLogo = document.createElement('div');
        brandLogo.style.cssText = `
          width:48px;height:48px;background:rgba(255,255,255,0.9);border-radius:50%;
          display:flex;align-items:center;justify-content:center;z-index:1;position:relative;
        `;
        brandLogo.innerHTML = `
          <svg width="32" height="32" viewBox="0 0 24 24" fill="${config.brandColor || '#8b5cf6'}">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
          </svg>
        `;

        brandLogoWrapper.appendChild(brandGlow);
        brandLogoWrapper.appendChild(brandLogo);

        const brandName = document.createElement('h4');
        brandName.className = 'chatbot-brand-name';
        brandName.textContent = 'Support Chat';
        brandName.style.cssText = 'margin:0;font-size:24px;font-weight:600;color:white;';

        const brandSubtitle = document.createElement('span');
        brandSubtitle.className = 'chatbot-brand-subtitle';
        brandSubtitle.textContent = 'Powered by AI';
        brandSubtitle.style.cssText = 'font-size:12px;color:rgba(255,255,255,0.6);';

        brandSection.appendChild(brandLogoWrapper);
        brandSection.appendChild(brandName);
        brandSection.appendChild(brandSubtitle);

        // Messages container
        const messagesContainer = document.createElement('div');
        messagesContainer.style.cssText = 'display:flex;flex-direction:column;gap:16px;';

        chatBody.appendChild(brandSection);
        chatBody.appendChild(messagesContainer);

        // Input area
        const inputArea = document.createElement('div');
        inputArea.className = 'chatbot-input-area';
        inputArea.style.cssText = `
          border-top:1px solid rgba(255,255,255,0.1);padding:16px;
          background:rgba(0,0,0,0.1);backdrop-filter:blur(10px);
        `;

        const inputWrapper = document.createElement('div');
        inputWrapper.className = 'chatbot-input-wrapper';
        inputWrapper.style.cssText = 'display:flex;align-items:center;gap:12px;';

        const input = document.createElement('input');
        input.className = 'chatbot-input';
        input.type = 'text';
        input.placeholder = 'Type your message...';
        input.style.cssText = `
          flex:1;height:48px;padding:0 16px;
          border:1px solid rgba(255,255,255,0.2);border-radius:24px;
          background:rgba(255,255,255,0.05);color:white;outline:none;
          font-size:14px;transition:all 0.2s;
        `;

        input.addEventListener('focus', () => {
          input.style.borderColor = config.brandColor || '#8b5cf6';
          input.style.boxShadow = `0 0 0 3px ${config.brandColor || '#8b5cf6'}33`;
        });
        input.addEventListener('blur', () => {
          input.style.borderColor = 'rgba(255,255,255,0.2)';
          input.style.boxShadow = 'none';
        });

        const sendBtn = document.createElement('button');
        sendBtn.className = 'chatbot-send-btn';
        sendBtn.style.cssText = `
          width:48px;height:48px;background:linear-gradient(45deg, ${config.brandColor || '#8b5cf6'}, #3b82f6);
          color:white;border:none;border-radius:50%;cursor:pointer;
          display:flex;align-items:center;justify-content:center;
          box-shadow:0 4px 12px rgba(0,0,0,0.15);transition:all 0.2s;
        `;
        sendBtn.innerHTML = `
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="22" y1="2" x2="11" y2="13"></line>
            <polygon points="22,2 15,22 11,13 2,9 22,2"></polygon>
          </svg>
        `;

        sendBtn.addEventListener('mouseenter', () => {
          sendBtn.style.transform = 'scale(1.05)';
          sendBtn.style.boxShadow = `0 0 20px ${config.brandColor || '#8b5cf6'}66`;
        });
        sendBtn.addEventListener('mouseleave', () => {
          sendBtn.style.transform = 'scale(1)';
          sendBtn.style.boxShadow = '0 4px 12px rgba(0,0,0,0.15)';
        });

        inputWrapper.appendChild(input);
        inputWrapper.appendChild(sendBtn);
        inputArea.appendChild(inputWrapper);

        content.appendChild(chatBody);
        content.appendChild(inputArea);
        chatWindow.appendChild(header);
        chatWindow.appendChild(content);

        // Render messages
        const renderMessages = () => {
          messagesContainer.innerHTML = '';
          
          messages.forEach((msg, index) => {
            const msgElement = document.createElement('div');
            msgElement.className = `chatbot-message ${msg.role} chatbot-message-animate`;
            
            if (msg.role === 'assistant') {
              msgElement.style.cssText = 'display:flex;align-items:flex-start;gap:12px;';
              
              const avatar = document.createElement('div');
              avatar.className = 'chatbot-avatar';
              avatar.style.cssText = 'flex-shrink:0;';
              
              const avatarContainer = document.createElement('div');
              avatarContainer.className = 'chatbot-logo-container chatbot-avatar-bounce';
              avatarContainer.style.cssText = `
                width:32px;height:32px;background:rgba(255,255,255,0.9);border-radius:50%;
                display:flex;align-items:center;justify-content:center;
              `;
              avatarContainer.innerHTML = `
                <svg width="18" height="18" viewBox="0 0 24 24" fill="${config.brandColor || '#8b5cf6'}">
                  <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
                </svg>
              `;
              
              avatar.appendChild(avatarContainer);
              
              const bubble = document.createElement('div');
              bubble.className = 'chatbot-bubble assistant chatbot-bubble-enhanced';
              bubble.style.cssText = `
                position:relative;max-width:85%;padding:12px 16px;
                background:rgba(0,0,0,0.4);color:white;border-radius:18px 18px 18px 6px;
                border:1px solid rgba(255,255,255,0.1);font-size:14px;line-height:1.5;
                box-shadow:0 4px 12px rgba(0,0,0,0.15);
              `;
              bubble.innerHTML = msg.content;
              
              msgElement.appendChild(avatar);
              msgElement.appendChild(bubble);
            } else {
              msgElement.style.cssText = 'display:flex;justify-content:flex-end;';
              
              const bubble = document.createElement('div');
              bubble.className = 'chatbot-bubble user chatbot-bubble-enhanced';
              bubble.style.cssText = `
                position:relative;max-width:85%;padding:12px 16px;
                background:linear-gradient(135deg, ${config.brandColor || '#8b5cf6'}, #3b82f6);
                color:white;border-radius:18px 18px 6px 18px;font-size:14px;line-height:1.5;
                box-shadow:0 4px 12px rgba(0,0,0,0.15);
              `;
              bubble.textContent = msg.content;
              
              msgElement.appendChild(bubble);
            }
            
            messagesContainer.appendChild(msgElement);
          });

          // Add typing indicator if needed
          if (isTyping) {
            const typingElement = document.createElement('div');
            typingElement.className = 'chatbot-message assistant chatbot-message-animate';
            typingElement.style.cssText = 'display:flex;align-items:flex-start;gap:12px;';
            
            const avatar = document.createElement('div');
            avatar.className = 'chatbot-avatar';
            avatar.style.cssText = 'flex-shrink:0;';
            
            const avatarContainer = document.createElement('div');
            avatarContainer.className = 'chatbot-logo-container';
            avatarContainer.style.cssText = `
              width:32px;height:32px;background:rgba(255,255,255,0.9);border-radius:50%;
              display:flex;align-items:center;justify-content:center;
            `;
            avatarContainer.innerHTML = `
              <svg width="18" height="18" viewBox="0 0 24 24" fill="${config.brandColor || '#8b5cf6'}">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
              </svg>
            `;
            
            avatar.appendChild(avatarContainer);
            
            const typingBubble = document.createElement('div');
            typingBubble.className = 'chatbot-bubble typing-bubble';
            typingBubble.style.cssText = `
              padding:16px 20px;background:rgba(0,0,0,0.4);color:white;
              border-radius:18px 18px 18px 6px;border:1px solid rgba(255,255,255,0.1);
              box-shadow:0 4px 12px rgba(0,0,0,0.15);
            `;
            
            const typingAnimation = document.createElement('div');
            typingAnimation.className = 'chatbot-typing';
            typingAnimation.style.cssText = 'display:flex;align-items:center;gap:4px;';
            
            for (let i = 0; i < 3; i++) {
              const dot = document.createElement('div');
              dot.className = 'chatbot-typing-dot';
              typingAnimation.appendChild(dot);
            }
            
            typingBubble.appendChild(typingAnimation);
            typingElement.appendChild(avatar);
            typingElement.appendChild(typingBubble);
            messagesContainer.appendChild(typingElement);
          }

          // Auto scroll to bottom
          setTimeout(() => {
            chatBody.scrollTop = chatBody.scrollHeight;
          }, 100);
        };

        // Send message function
        const sendMessage = async (text) => {
          if (!text.trim() || isTyping) return;
          
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
                user_identifier: userId,
                max_context: 200
              })
            });

            if (!response.ok) {
              throw new Error('Network response was not ok');
            }

            const responseText = await response.text();
            const lines = responseText.trim().split('\n');
            let botMessage = '';
            let sessionId = null;
            let emailCaptured = false;
            let feedbackTriggered = false;
            let answeredBy = null;
            let contextAnalysis = null;
            let followups = [];
            let hasMainResponse = false;

            for (const line of lines) {
              if (line.trim()) {
                try {
                  const data = JSON.parse(line);
                  if (data.type === 'main_response') {
                    botMessage = data.content;
                    sessionId = data.session_id;
                    emailCaptured = data.email_captured;
                    feedbackTriggered = data.feedback_triggered;
                    answeredBy = data.answered_by;
                    contextAnalysis = data.context_analysis;
                    hasMainResponse = true;
                  } else if (data.type === 'metadata') {
                    userId = data.user_id;
                  } else if (data.type === 'followup') {
                    followups.push({
                      content: data.content,
                      index: data.index,
                      is_last: data.is_last
                    });
                  }
                } catch (parseError) {
                  console.error('Parse error for line:', line, parseError);
                }
              }
            }

            messages.push({ 
              role: 'assistant', 
              content: hasMainResponse ? botMessage : 'I apologize, but I was unable to process your request. Please try again.' 
            });
          } catch (error) {
            console.error('Error sending message:', error);
            messages.push({ 
              role: 'assistant', 
              content: 'Sorry, I encountered an error. Please try again.' 
            });
          } finally {
            isTyping = false;
            input.disabled = false;
            sendBtn.disabled = false;
            renderMessages();
            input.focus();
          }
        };

        // Event listeners
        button.addEventListener('click', () => {
          isOpen = true;
          button.style.display = 'none';
          updateChatWindow();
          renderMessages();
          setTimeout(() => input.focus(), 100);
        });

        sendBtn.addEventListener('click', () => sendMessage(input.value));
        
        input.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage(input.value);
          }
        });

        // Add to DOM
        const widget = document.createElement('div');
        widget.className = 'chatbot-widget';
        widget.appendChild(floatingBg);
        widget.appendChild(button);
        widget.appendChild(chatWindow);
        container.appendChild(widget);

        // Initial render
        renderMessages();

      } catch (error) {
        console.error('Widget initialization error:', error);
      }
    }
  };
})();



