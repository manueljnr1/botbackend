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
  // Inject all original CSS styles from the React build
  const style = document.createElement('style');
  style.textContent = `
    /* Original CSS from React build - preserving exact styling */
    :root {
      --chatbot-secondary: #007bff;
      --chatbot-text: #222222;
      --chatbot-border: #888c91;
      --chatbot-radius: 20px;
      --chatbot-font: 'Inter', sans-serif;
      --chatbot-shadow: 0 8px 30px rgba(0, 0, 0, 0.12);
    }

    /* Floating particles */
    .chatbot-particles {
      position: fixed;
      inset: 0;
      pointer-events: none;
      z-index: 40;
    }

    .particle {
      position: absolute;
      width: 4px;
      height: 4px;
      background: rgba(139, 92, 246, 0.2);
      border-radius: 50%;
    }

    .particle-1 { top: 20%; left: 20%; animation: particle-float 3s ease-in-out infinite; animation-delay: 0s; }
    .particle-2 { top: 35%; left: 32%; animation: particle-float 3s ease-in-out infinite; animation-delay: 0.5s; }
    .particle-3 { top: 50%; left: 44%; animation: particle-float 3s ease-in-out infinite; animation-delay: 1s; }
    .particle-4 { top: 65%; left: 56%; animation: particle-float 3s ease-in-out infinite; animation-delay: 1.5s; }
    .particle-5 { top: 80%; left: 68%; animation: particle-float 3s ease-in-out infinite; animation-delay: 2s; }
    .particle-6 { top: 95%; left: 80%; animation: particle-float 3s ease-in-out infinite; animation-delay: 2.5s; }

    @keyframes particle-float {
      0%, 100% { transform: translateY(0px); opacity: 0.2; }
      50% { transform: translateY(-20px); opacity: 0.8; }
    }

    /* Open button */
    .chatbot-open-btn {
      position: fixed;
      width: 56px;
      height: 56px;
      background: var(--chatbot-secondary);
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 8px 25px color-mix(in srgb, var(--chatbot-secondary) 30%, transparent);
      border: none;
      border-radius: 50%;
      cursor: pointer;
      font-family: var(--chatbot-font);
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      z-index: 10000;
      overflow: hidden;
    }

    .chatbot-open-btn:hover {
      transform: scale(1.1) translateY(-2px);
      box-shadow: 0 12px 35px color-mix(in srgb, var(--chatbot-secondary) 40%, transparent);
    }

    .chatbot-open-btn:active {
      transform: scale(0.95);
    }

    .chatbot-pulse-ring,
    .chatbot-pulse-ring-2 {
      position: absolute;
      border: 2px solid var(--chatbot-secondary);
      border-radius: 50%;
      animation: pulse-ring 2s cubic-bezier(0.455, 0.03, 0.515, 0.955) infinite;
    }

    .chatbot-pulse-ring-2 {
      animation-delay: 1s;
    }

    @keyframes pulse-ring {
      0% { width: 56px; height: 56px; opacity: 1; }
      100% { width: 80px; height: 80px; opacity: 0; }
    }

    /* Widget positioning */
    .chatbot-bottom-right { bottom: 24px; right: 24px; }
    .chatbot-bottom-left { bottom: 24px; left: 24px; }
    .chatbot-top-right { top: 24px; right: 24px; }
    .chatbot-top-left { top: 24px; left: 24px; }

    /* Main widget */
    .chatbot-widget {
      position: fixed;
      z-index: 10000;
      width: 100%;
      max-width: 500px;
      height: 70vh;
      background: linear-gradient(145deg, rgba(255, 255, 255, 0.9), rgba(255, 255, 255, 0.85));
      border-radius: var(--chatbot-radius);
      box-shadow: 0 4px 60px 20px rgba(0, 0, 0, 0.1), 0 2px 20px rgba(0, 0, 0, 0.1), 
                  0 0 0 1px rgba(0, 0, 0, 0.05), inset 0 0 0 1px rgba(255, 255, 255, 0.15), 
                  inset 0 0 20px rgba(255, 255, 255, 0.5);
      border: 1px solid rgba(209, 213, 219, 0.3);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
      font-family: var(--chatbot-font);
      backdrop-filter: blur(20px) saturate(180%);
      transform: scale(0.8) translateY(20px);
      opacity: 0;
      background-image: linear-gradient(145deg, rgba(255, 255, 255, 0.1) 0%, transparent 100%),
                        linear-gradient(to bottom, transparent, rgba(240, 240, 240, 0.2));
    }

    .chatbot-widget-open {
      transform: scale(1) translateY(0);
      opacity: 1;
    }

    .chatbot-widget-expanded {
      height: 90vh !important;
      max-width: 600px;
      transition: all 0.3s ease-in-out;
    }

    /* Header */
    .chatbot-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 16px;
      background: var(--chatbot-secondary);
      background: linear-gradient(135deg, var(--chatbot-secondary), color-mix(in srgb, var(--chatbot-secondary) 80%, #000));
      color: white;
      position: relative;
      overflow: hidden;
    }

    .chatbot-header::before {
      content: "";
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: linear-gradient(45deg, transparent 30%, rgba(255, 255, 255, 0.1) 50%, transparent 70%);
      animation: shimmer 3s ease-in-out infinite;
    }

    @keyframes shimmer {
      0% { transform: translateX(-100%); }
      100% { transform: translateX(100%); }
    }

    .chatbot-header-left {
      display: flex;
      align-items: center;
      z-index: 1;
    }

    .chatbot-logo-container {
      position: relative;
      margin-right: 12px;
      background: rgba(255, 255, 255, 0.2);
      border-radius: 50%;
      width: 40px;
      height: 40px;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .chatbot-online-indicator {
      position: absolute;
      bottom: 2px;
      right: 2px;
      width: 10px;
      height: 10px;
      background: #10b981;
      border: 2px solid white;
      border-radius: 50%;
      animation: pulse-online 2s ease-in-out infinite;
    }

    @keyframes pulse-online {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }

    .chatbot-header-info {
      display: flex;
      flex-direction: column;
    }

    .chatbot-title {
      font-size: 1.125rem;
      font-weight: 600;
      color: white;
      margin: 0;
    }

    .chatbot-status {
      font-size: 0.75rem;
      color: rgba(255, 255, 255, 0.8);
      margin-top: 2px;
    }

    .chatbot-header-actions {
      display: flex;
      gap: 8px;
      align-items: center;
    }

    .chatbot-close-btn,
    .chatbot-expand-btn {
      background: rgba(255, 255, 255, 0.2);
      padding: 8px;
      border-radius: 8px;
      border: none;
      color: white;
      cursor: pointer;
      transition: all 0.2s ease;
      z-index: 1;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .chatbot-close-btn:hover,
    .chatbot-expand-btn:hover {
      background: rgba(255, 255, 255, 0.3);
    }

    .chatbot-close-btn:hover {
      transform: rotate(90deg);
    }

    .chatbot-expand-btn:hover {
      transform: scale(1.1);
    }

    /* Body */
    .chatbot-body {
      flex: 1;
      overflow-y: auto;
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 16px;
      background: linear-gradient(to bottom, #fff 0%, #fafbfc 100%);
      position: relative;
    }

    .chatbot-body::before {
      content: "";
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 20px;
      background: linear-gradient(to bottom, rgba(255, 255, 255, 0.8), transparent);
      pointer-events: none;
      z-index: 1;
    }

    .chatbot-body::-webkit-scrollbar {
      width: 6px;
    }

    .chatbot-body::-webkit-scrollbar-track {
      background: transparent;
    }

    .chatbot-body::-webkit-scrollbar-thumb {
      background: linear-gradient(to bottom, var(--chatbot-secondary), color-mix(in srgb, var(--chatbot-secondary) 70%, transparent));
      border-radius: 3px;
    }

    /* Brand section */
    .chatbot-brand-section {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 20px 0;
      position: relative;
    }

    .chatbot-brand-logo-wrapper {
      position: relative;
      margin-bottom: 12px;
      background-color: var(--chatbot-secondary);
      border-radius: 50%;
      width: 80px;
      height: 80px;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .chatbot-brand-glow {
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      width: 80px;
      height: 80px;
      background: radial-gradient(circle, var(--chatbot-secondary) 0%, transparent 70%);
      opacity: 0.2;
      border-radius: 50%;
      animation: glow-pulse 3s ease-in-out infinite;
    }

    @keyframes glow-pulse {
      0%, 100% {
        transform: translate(-50%, -50%) scale(1);
        opacity: 0.2;
      }
      50% {
        transform: translate(-50%, -50%) scale(1.2);
        opacity: 0.1;
      }
    }

    .chatbot-brand-name {
      font-size: 1.25rem;
      font-weight: 700;
      color: var(--chatbot-text);
      margin-bottom: 4px;
      text-align: center;
      background: var(--chatbot-secondary);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }

    .chatbot-brand-subtitle {
      font-size: 0.875rem;
      color: #6b7280;
      text-align: center;
      opacity: 0.8;
    }

    /* Messages */
    .chatbot-message {
      display: flex;
      gap: 12px;
      align-items: flex-start;
      opacity: 0;
      transform: translateY(20px);
    }

    .chatbot-message-animate {
      animation: slideInMessage 0.5s cubic-bezier(0.4, 0, 0.2, 1) forwards;
    }

    @keyframes slideInMessage {
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    .chatbot-message.user {
      justify-content: flex-end;
    }

    .chatbot-message.assistant {
      justify-content: flex-start;
    }

    .chatbot-avatar {
      flex-shrink: 0;
      position: relative;
    }

    .chatbot-avatar-bounce {
      animation: avatarBounce 0.6s cubic-bezier(0.68, -0.55, 0.265, 1.55);
    }

    @keyframes avatarBounce {
      0% { transform: scale(0) rotate(180deg); }
      50% { transform: scale(1.2) rotate(90deg); }
      100% { transform: scale(1) rotate(0deg); }
    }

    .chatbot-bubble {
      padding: 12px 16px;
      border-radius: 18px;
      max-width: calc(100% - 60px);
      word-break: break-word;
      font-size: 13px;
      line-height: 1.7;
      position: relative;
      transition: all 0.2s ease;
    }

    .chatbot-bubble-enhanced {
      box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
    }

    .chatbot-bubble:hover {
      transform: translateY(-1px);
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.12);
    }

    .chatbot-bubble.user {
      background: linear-gradient(135deg, var(--chatbot-secondary), color-mix(in srgb, var(--chatbot-secondary) 80%, #000));
      color: white;
      margin-left: auto;
      border-bottom-right-radius: 6px;
    }

    .chatbot-bubble.assistant {
      background: #fff;
      color: #000;
      border: 1px solid #e5e7eb;
      border-bottom-left-radius: 6px;
    }

    .chatbot-bubble-tail {
      position: absolute;
      width: 0;
      height: 0;
    }

    .chatbot-bubble.user .chatbot-bubble-tail {
      bottom: 0;
      right: -6px;
      border-left: 6px solid var(--chatbot-secondary);
      border-bottom: 6px solid transparent;
    }

    .chatbot-bubble.assistant .chatbot-bubble-tail {
      bottom: 0;
      left: -7px;
      border-right: 6px solid white;
      border-bottom: 6px solid transparent;
    }

    .chatbot-bubble.typing-bubble {
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 48px;
      background: #dee2e6;
      background-size: 200% 100%;
      animation: shimmer-bg 2s ease-in-out infinite;
    }

    @keyframes shimmer-bg {
      0% { background-position: -200% 0; }
      100% { background-position: 200% 0; }
    }

    /* List styling */
    .chatbot-bubble ul {
      margin: 0.75em 0;
      padding-left: 0;
      list-style: none;
    }

    .chatbot-bubble li {
      margin: 0.25em 0;
      padding-left: 16px;
      position: relative;
    }

    .chatbot-bubble li::before {
      content: "";
      width: 4px;
      height: 4px;
      background-color: var(--chatbot-secondary);
      border-radius: 50%;
      position: absolute;
      left: 4px;
      top: 0.6em;
      transform: translateY(-50%);
    }

    /* Input area */
    .chatbot-input-area {
      border-top: 1px solid #dee2e6;
      padding: 16px;
      background: white;
      position: relative;
    }

    .chatbot-input-area::before {
      content: "";
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 1px;
      opacity: 0.3;
    }

    .chatbot-input-wrapper {
      display: flex;
      gap: 12px;
      align-items: center;
      background: #f9fafb;
      border-radius: 24px;
      padding: 4px;
      border: 2px solid #dee2e6;
      transition: all 0.3s ease;
    }

    .chatbot-input-wrapper:focus-within {
      border-color: var(--chatbot-secondary);
      background: white;
      box-shadow: 0 0 0 4px rgba(0, 123, 255, 0.1);
    }

    .chatbot-input {
      flex: 1;
      padding: 12px 16px;
      border: none;
      background: transparent;
      font-size: 14px;
      outline: none;
      color: #000;
      border-radius: 40px;
    }

    .chatbot-input::placeholder {
      color: #000;
    }

    .chatbot-send-btn {
      padding: 10px;
      background: linear-gradient(135deg, var(--chatbot-secondary), color-mix(in srgb, var(--chatbot-secondary) 80%, #000));
      color: white;
      border: none;
      border-radius: 50%;
      cursor: pointer;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      display: flex;
      align-items: center;
      justify-content: center;
      width: 40px;
      height: 40px;
      position: relative;
      overflow: hidden;
    }

    .chatbot-send-btn:hover:not(:disabled) {
      transform: scale(1.1) rotate(15deg);
      box-shadow: 0 4px 15px rgba(0, 123, 255, 0.3);
    }

    .chatbot-send-btn:active:not(:disabled) {
      transform: scale(0.95);
    }

    .chatbot-send-btn:disabled {
      background: #d1d5db;
      cursor: not-allowed;
      transform: none;
    }

    .chatbot-send-icon {
      transition: transform 0.2s ease;
    }

    .chatbot-send-btn:hover:not(:disabled) .chatbot-send-icon {
      transform: translateX(2px);
    }

    /* Typing animation */
    @keyframes pulse-dot {
      0%, 80%, 100% {
        opacity: 0.3;
        transform: scale(1);
      }
      40% {
        opacity: 1;
        transform: scale(1.4);
      }
    }

    .chatbot-typing {
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .chatbot-typing .dot {
      display: inline-block;
      width: 4px;
      height: 4px;
      border-radius: 50%;
      background: #000;
      opacity: 0.5;
      animation: pulse-dot 1.4s infinite;
    }

    .chatbot-typing .dot:nth-child(2) {
      animation-delay: 0.2s;
    }

    .chatbot-typing .dot:nth-child(3) {
      animation-delay: 0.4s;
    }

    /* Responsive design */
    @media (max-width: 768px) {
      .chatbot-widget {
        width: 70vw;
        height: 80vh;
        max-width: none;
      }
      .chatbot-open-btn {
        width: 50px;
        height: 50px;
      }
      .chatbot-bubble {
        max-width: calc(100% - 50px);
        font-size: 14px;
      }
      .particle {
        display: none;
      }
      .chatbot-input {
        font-size: 16px;
      }
    }

    @media (max-width: 480px) {
      .chatbot-widget {
        width: 100vw;
        height: 100dvh;
        max-height: -webkit-fill-available;
        border-radius: 0;
        position: fixed;
        top: 0 !important;
        left: 0 !important;
        right: 0 !important;
        bottom: 0 !important;
        margin: 0;
      }
      .chatbot-body {
        padding: 16px;
        height: calc(100dvh - 140px);
        overflow-y: auto;
      }
      .chatbot-expand-btn {
        display: none;
      }
      .chatbot-body {
        -webkit-overflow-scrolling: touch;
      }
      .chatbot-input-area {
        padding: 12px;
        position: sticky;
        bottom: 0;
        background: white;
        z-index: 2;
        padding-bottom: max(12px, env(safe-area-inset-bottom));
      }
      .chatbot-header {
        padding: 16px;
        position: sticky;
        top: 0;
        z-index: 2;
        padding-top: max(16px, env(safe-area-inset-top));
      }
      .chatbot-input-wrapper * {
        font-size: 16px !important;
      }
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
        let inputValue = '';
        let userId = config.userId || ('user_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9));
        let brandingData = {
          business_name: "Your Support Bot",
          chatbot_widget_icon: "",
          branding: {
            logo_text: "SB",
            logo_image: "",
            primary_color: "#007bff",
            secondary_color: "#007bff",
            text_color: "#222222",
            user_bubble_color: "#007bff",
            border_color: "#e0e0e0",
            border_radius: "12px",
            widget_position: config.position || "bottom-right",
            font_family: "Inter, sans-serif",
            custom_css: ""
          }
        };

        // Format message content exactly like React version
        const formatMessageContent = (content) => {
          let formatted = content.trim()
            .replace(/^[•·]\s*(.*$)/gm, (match, text) => `<li>${text.trim()}</li>`)
            .replace(/^\d+\.\s*(.*$)/gm, (match, text) => `<li>${text.trim()}</li>`)
            .replace(/\n\n+/g, "|||PARAGRAPH|||")
            .replace(/\n/g, "<br>")
            .replace(/\|\|\|PARAGRAPH\|\|\|/g, "</p><p>");

          formatted = formatted.replace(/(?:<li>.*?<\/li>(?:\s*<br>?\s*<li>.*?<\/li>)*)/g, 
            match => `<ul>${match.replace(/<br>?\s*/g, "")}</ul>`);

          if (!formatted.includes("<p>") && !formatted.includes("<ul>")) {
            formatted = `<p>${formatted}</p>`;
          }

          return formatted;
        };

        // Fetch branding data
        const fetchBranding = async () => {
          try {
            const response = await fetch(`${config.baseUrl}/chatbot/tenant-info`, {
              headers: {
                'Content-Type': 'application/json',
                'X-API-Key': config.apiKey
              }
            });
            if (response.ok) {
              const data = await response.json();
              if (data.branding) {
                brandingData = {
                  ...brandingData,
                  ...data,
                  branding: {
                    ...brandingData.branding,
                    ...data.branding
                  }
                };
                updateBrandingCSS();
              }
            }
          } catch (error) {
            console.warn('Failed to fetch branding', error);
          }
        };

        // Update CSS variables
        const updateBrandingCSS = () => {
          const root = document.documentElement;
          const { branding } = brandingData;
          
          root.style.setProperty('--chatbot-secondary', branding.user_bubble_color);
          root.style.setProperty('--chatbot-shadow', '0 8px 30px rgba(0,0,0,0.12)');

          if (branding.custom_css) {
            let customStyleEl = document.getElementById('chatbot-custom-styles');
            if (!customStyleEl) {
              customStyleEl = document.createElement('style');
              customStyleEl.id = 'chatbot-custom-styles';
              document.head.appendChild(customStyleEl);
            }
            customStyleEl.textContent = branding.custom_css;
          }
        };

        // Capitalize first letters
        const capitalizeWords = (str) => str.replace(/\b\w/g, l => l.toUpperCase());

        // Create logo element
        const createLogo = (size = 32) => {
          const { branding } = brandingData;
          if (branding.logo_image) {
            const img = document.createElement('img');
            img.src = branding.logo_image || '/placeholder.svg';
            img.alt = 'Logo';
            img.style.cssText = `width:${size}px;height:${size}px;border-radius:50%;object-fit:cover;display:block;`;
            return img;
          } else {
            return createTextLogo(size);
          }
        };

        // Create text logo with original SVG shape
        const createTextLogo = (size) => {
          const container = document.createElement('div');
          container.style.cssText = `
            width:${size}px;height:${size}px;display:flex;align-items:center;justify-content:center;
            border-radius:50%;
            box-shadow:0 2px 8px rgba(0,0,0,0.15), 0 1px 3px rgba(0,0,0,0.1);
          `;
          
          const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
          const svgSize = Math.max(28, size * 0.85); // Made bigger - was 0.7, now 0.85
          svg.setAttribute('width', svgSize);
          svg.setAttribute('height', svgSize);
          svg.setAttribute('viewBox', '0 0 32 32');
          svg.setAttribute('fill', 'white');
          svg.style.cssText = 'display:block;filter:drop-shadow(0 1px 2px rgba(0,0,0,0.2));';
          
          const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
          path.setAttribute('d', 'M0 0 C0.94101562 -0.01675781 1.88203125 -0.03351562 2.8515625 -0.05078125 C5.375 0.3125 5.375 0.3125 7.1875 1.4921875 C8.81620937 3.98882752 8.77412297 5.78689539 8.75 8.75 C8.75773437 9.69746094 8.76546875 10.64492187 8.7734375 11.62109375 C8.31447132 14.72136532 7.5434107 16.07791714 5.375 18.3125 C2.35333856 19.31972048 0.39774409 19.38591677 -2.75 19.3125 C-4.37456329 19.27482897 -6.00066762 19.26592416 -7.625 19.3125 C-7.955 19.6425 -8.285 19.9725 -8.625 20.3125 C-10.62458364 20.35330783 -12.62545254 20.35504356 -14.625 20.3125 C-13.965 18.9925 -13.305 17.6725 -12.625 16.3125 C-13.12 15.961875 -13.615 15.61125 -14.125 15.25 C-15.625 13.3125 -15.625 13.3125 -16.125 9.875 C-15.625 6.3125 -15.625 6.3125 -13.4375 4 C-8.9125767 1.28504602 -5.30278687 0.02191234 0 0 Z');
          path.setAttribute('transform', 'translate(15.625,1.6875)');
          
          svg.appendChild(path);
          container.appendChild(svg);
          
          return container;
        };

        // Create widget icon
        const createWidgetIcon = (size = 32) => {
          const { chatbot_widget_icon } = brandingData;
          if (chatbot_widget_icon) {
            const img = document.createElement('img');
            img.src = chatbot_widget_icon || '/placeholder.svg';
            img.alt = 'Logo';
            img.style.cssText = `width:${size}px;height:${size}px;border-radius:50%;object-fit:cover;display:block;`;
            return img;
          } else {
            return createTextLogo(size);
          }
        };

        // Send message function
        const sendMessage = async () => {
          if (!inputValue.trim()) return;

          const userMessage = { role: 'user', content: inputValue.trim() };
          messages.push(userMessage);
          renderMessages();
          inputValue = '';
          input.value = '';
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
                message: userMessage.content,
                user_identifier: userId,
                max_context: 200
              })
            });

            if (!response.ok) {
              throw new Error(`HTTP error! status: ${response.status}`);
            }

            const reader = response.body?.getReader();
            if (!reader) {
              throw new Error('Response body is not readable');
            }

            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
              const { done, value } = await reader.read();
              if (done) break;

              const chunk = decoder.decode(value, { stream: true });
              const lines = (buffer + chunk).split('\n');
              buffer = lines.pop() || '';

              for (const line of lines) {
                if (line.trim()) {
                  try {
                    const data = JSON.parse(line);
                    console.log('Parsed message data:', data);

                    switch (data.type) {
                      case 'main_response':
                        let content = data.content;
                        if (typeof content === 'string') {
                          content = content.split('\n').map(line => line.trim()).filter(line => line.length > 0).join('\n');
                        }
                        
                        const lastMessage = messages[messages.length - 1];
                        if (lastMessage?.role === 'assistant' && lastMessage.content === '') {
                          messages[messages.length - 1] = { ...lastMessage, content };
                        } else {
                          messages.push({ role: 'assistant', content });
                        }
                        break;

                      case 'followup':
                        if (data.content) {
                          console.log('Followup suggestion:', data.content);
                        }
                        break;

                      case 'complete':
                        isTyping = false;
                        break;

                      case 'error':
                        console.error('Chat error:', data.error);
                        messages.push({ role: 'assistant', content: 'Error responding, please try again.' });
                        isTyping = false;
                        break;

                      default:
                        console.warn('Unknown message type:', data.type);
                    }
                  } catch (parseError) {
                    console.error('Failed to parse JSON:', parseError, 'Line:', line);
                  }
                }
              }
            }

            isTyping = false;
          } catch (error) {
            console.error('Chat error:', error);
            messages.push({ role: 'assistant', content: 'Error responding, please try again.' });
            isTyping = false;
          } finally {
            renderMessages();
            input.focus();
          }
        };

        // Get position class
        const getPositionClass = () => `chatbot-${brandingData.branding.widget_position}`;

        // Create particles background
        const createParticles = () => {
          const particlesDiv = document.createElement('div');
          particlesDiv.className = 'chatbot-particles';
          
          for (let i = 1; i <= 6; i++) {
            const particle = document.createElement('div');
            particle.className = `particle particle-${i}`;
            particlesDiv.appendChild(particle);
          }
          
          return particlesDiv;
        };

        // Create open button
        const createOpenButton = () => {
          const button = document.createElement('button');
          button.className = `chatbot-open-btn ${getPositionClass()}`;
          button.style.display = isOpen ? 'none' : 'flex';
          
          const icon = createWidgetIcon(24);
          const ring1 = document.createElement('div');
          ring1.className = 'chatbot-pulse-ring';
          const ring2 = document.createElement('div');
          ring2.className = 'chatbot-pulse-ring-2';
          
          button.appendChild(icon);
          button.appendChild(ring1);
          button.appendChild(ring2);
          
          button.addEventListener('click', () => {
            isOpen = true;
            button.style.display = 'none';
            chatWidget.style.display = 'flex';
            setTimeout(() => {
              chatWidget.classList.add('chatbot-widget-open');
              renderMessages();
              input.focus();
            }, 10);
          });
          
          return button;
        };

        // Create header
        const createHeader = () => {
          const header = document.createElement('div');
          header.className = 'chatbot-header';
          
          const headerLeft = document.createElement('div');
          headerLeft.className = 'chatbot-header-left';
          
          const logoContainer = document.createElement('div');
          logoContainer.className = 'chatbot-logo-container';
          logoContainer.appendChild(createLogo(32));
          
          const headerInfo = document.createElement('div');
          headerInfo.className = 'chatbot-header-info';
          
          const title = document.createElement('span');
          title.className = 'chatbot-title';
          title.textContent = capitalizeWords(brandingData.business_name);
          
          headerInfo.appendChild(title);
          headerLeft.appendChild(logoContainer);
          headerLeft.appendChild(headerInfo);
          
          const headerActions = document.createElement('div');
          headerActions.className = 'chatbot-header-actions';
          
          const expandBtn = document.createElement('button');
          expandBtn.className = 'chatbot-expand-btn';
          expandBtn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M15 3h6v6M14 10l6.1-6.1M9 21H3v-6M10 14l-6.1 6.1"/>
            </svg>
          `;
          expandBtn.addEventListener('click', () => {
            isExpanded = !isExpanded;
            if (isExpanded) {
              chatWidget.classList.add('chatbot-widget-expanded');
              expandBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/>
                </svg>
              `;
            } else {
              chatWidget.classList.remove('chatbot-widget-expanded');
              expandBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M15 3h6v6M14 10l6.1-6.1M9 21H3v-6M10 14l-6.1 6.1"/>
                </svg>
              `;
            }
          });
          
          const closeBtn = document.createElement('button');
          closeBtn.className = 'chatbot-close-btn';
          closeBtn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          `;
          closeBtn.addEventListener('click', () => {
            isOpen = false;
            openButton.style.display = 'flex';
            chatWidget.style.display = 'none';
            chatWidget.classList.remove('chatbot-widget-open');
          });
          
          headerActions.appendChild(expandBtn);
          headerActions.appendChild(closeBtn);
          header.appendChild(headerLeft);
          header.appendChild(headerActions);
          
          return header;
        };

        // Create brand section
        const createBrandSection = () => {
          const brandSection = document.createElement('div');
          brandSection.className = 'chatbot-brand-section';
          
          const logoWrapper = document.createElement('div');
          logoWrapper.className = 'chatbot-brand-logo-wrapper';
          logoWrapper.appendChild(createLogo(56));
          
          const glow = document.createElement('div');
          glow.className = 'chatbot-brand-glow';
          logoWrapper.appendChild(glow);
          
          const brandName = document.createElement('div');
          brandName.className = 'chatbot-brand-name';
          brandName.textContent = capitalizeWords(brandingData.business_name);
          
          const brandSubtitle = document.createElement('div');
          brandSubtitle.className = 'chatbot-brand-subtitle';
          brandSubtitle.textContent = "We're here to help! Ask us anything.";
          
          brandSection.appendChild(logoWrapper);
          brandSection.appendChild(brandName);
          brandSection.appendChild(brandSubtitle);
          
          return brandSection;
        };

        // Create typing indicator
        const createTypingIndicator = () => {
          const typingDiv = document.createElement('div');
          typingDiv.className = 'chatbot-typing';
          
          for (let i = 0; i < 3; i++) {
            const dot = document.createElement('span');
            dot.className = 'dot';
            typingDiv.appendChild(dot);
          }
          
          return typingDiv;
        };

        // Render messages
        const renderMessages = () => {
          messagesContainer.innerHTML = '';
          
          messages.forEach((msg, index) => {
            const msgDiv = document.createElement('div');
            msgDiv.className = `chatbot-message ${msg.role} chatbot-message-animate`;
            msgDiv.style.animationDelay = `${index * 0.1}s`;
            
            const bubble = document.createElement('div');
            bubble.className = `chatbot-bubble ${msg.role} chatbot-bubble-enhanced`;
            
            if (msg.role === 'assistant') {
              bubble.innerHTML = formatMessageContent(msg.content);
            } else {
              // Handle user messages with line breaks
              const lines = msg.content.split('\n');
              lines.forEach((line, i) => {
                bubble.appendChild(document.createTextNode(line));
                if (i < lines.length - 1) {
                  bubble.appendChild(document.createElement('br'));
                }
              });
            }
            
            const tail = document.createElement('div');
            tail.className = 'chatbot-bubble-tail';
            bubble.appendChild(tail);
            
            msgDiv.appendChild(bubble);
            messagesContainer.appendChild(msgDiv);
          });

          // Add typing indicator
          if (isTyping) {
            const typingMsg = document.createElement('div');
            typingMsg.className = 'chatbot-message assistant chatbot-message-animate';
            
            const typingBubble = document.createElement('div');
            typingBubble.className = 'chatbot-bubble assistant typing-bubble chatbot-bubble-enhanced';
            typingBubble.appendChild(createTypingIndicator());
            
            const tail = document.createElement('div');
            tail.className = 'chatbot-bubble-tail';
            typingBubble.appendChild(tail);
            
            typingMsg.appendChild(typingBubble);
            messagesContainer.appendChild(typingMsg);
          }

          // Auto scroll
          setTimeout(() => {
            chatBody.scrollTop = chatBody.scrollHeight;
          }, 100);
        };

        // Create input area
        const createInputArea = () => {
          const inputArea = document.createElement('div');
          inputArea.className = 'chatbot-input-area';
          
          const inputWrapper = document.createElement('div');
          inputWrapper.className = 'chatbot-input-wrapper';
          
          const input = document.createElement('input');
          input.className = 'chatbot-input';
          input.type = 'text';
          input.placeholder = 'Type your message...';
          input.addEventListener('input', (e) => {
            inputValue = e.target.value;
          });
          input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              sendMessage();
            }
          });
          
          const sendBtn = document.createElement('button');
          sendBtn.className = 'chatbot-send-btn';
          sendBtn.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="chatbot-send-icon">
              <line x1="22" y1="2" x2="11" y2="13"></line>
              <polygon points="22,2 15,22 11,13 2,9 22,2"></polygon>
            </svg>
          `;
          sendBtn.addEventListener('click', sendMessage);
          
          inputWrapper.appendChild(input);
          inputWrapper.appendChild(sendBtn);
          inputArea.appendChild(inputWrapper);
          
          return { inputArea, input };
        };

        // Create main elements
        const particles = createParticles();
        const openButton = createOpenButton();
        
        const chatWidget = document.createElement('div');
        chatWidget.className = `chatbot-widget ${getPositionClass()}`;
        chatWidget.style.display = 'none';
        
        const header = createHeader();
        
        const chatBody = document.createElement('div');
        chatBody.className = 'chatbot-body';
        
        const brandSection = createBrandSection();
        const messagesContainer = document.createElement('div');
        
        chatBody.appendChild(brandSection);
        chatBody.appendChild(messagesContainer);
        
        const { inputArea, input } = createInputArea();
        
        chatWidget.appendChild(header);
        chatWidget.appendChild(chatBody);
        chatWidget.appendChild(inputArea);
        
        // Add to DOM
        const widget = document.createElement('div');
        widget.appendChild(particles);
        widget.appendChild(openButton);
        widget.appendChild(chatWidget);
        container.appendChild(widget);

        // Initialize
        fetchBranding();
        renderMessages();

      } catch (error) {
        console.error('Widget initialization error:', error);
      }
    }
  };
})();