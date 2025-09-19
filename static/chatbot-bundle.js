(function() {
  // Inject CSS styles
  const style = document.createElement('style');
  style.textContent = `
    :root {
      --chatbot-secondary: #007bff;
      --chatbot-text: #222222;
      --chatbot-border: #888c91;
      --chatbot-radius: 20px;
      --chatbot-font: 'Inter', sans-serif;
      --chatbot-shadow: 0 8px 30px rgba(0, 0, 0, 0.12);
    }

    /* Enhanced floating particles background */
    .chatbot-particles {
      position: fixed;
      inset: 0;
      pointer-events: none;
      z-index: 9999;
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

    /* Enhanced Floating Action Button */
    .chatbot-open-btn {
      position: fixed;
      width: 56px;
      height: 56px;
      background: var(--chatbot-secondary);
      color: #ffffff;
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

    /* Pulse rings */
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
      0% {
        width: 56px;
        height: 56px;
        opacity: 1;
      }
      100% {
        width: 80px;
        height: 80px;
        opacity: 0;
      }
    }

    /* Enhanced Widget Container */
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

    /* Position Classes */
    .chatbot-bottom-right { bottom: 24px; right: 24px; }
    .chatbot-bottom-left { bottom: 24px; left: 24px; }
    .chatbot-top-right { top: 24px; right: 24px; }
    .chatbot-top-left { top: 24px; left: 24px; }

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
      content: '';
      width: 4px;
      height: 4px;
      background-color: var(--chatbot-secondary);
      border-radius: 50%;
      position: absolute;
      left: 4px;
      top: 0.6em;
      transform: translateY(-50%);
    }

    /* Enhanced Header */
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
      content: '';
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

    .chatbot-title {
      font-size: 1.125rem;
      font-weight: 600;
      color: white;
      margin: 0;
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

    .chatbot-widget-expanded {
      height: 90vh !important;
      max-width: 600px;
      transition: all 0.3s ease-in-out;
    }

    /* Enhanced Chat Body */
    .chatbot-body {
      flex: 1;
      overflow-y: auto;
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 16px;
      background: linear-gradient(to bottom, #ffffff 0%, #fafbfc 100%);
      position: relative;
    }

    .chatbot-body::before {
      content: '';
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

    /* Enhanced Brand Section */
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

    /* Enhanced Messages */
    .chatbot-message {
      display: flex;
      gap: 12px;
      align-items: flex-start;
      opacity: 0;
      transform: translateY(20px);
      margin-bottom: 16px;
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

    .chatbot-bubble {
      padding: 12px 16px;
      border-radius: 18px;
      max-width: calc(100% - 60px);
      word-break: break-word;
      font-size: 13px;
      line-height: 1.5;
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
      background: #ffffff;
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

    /* Enhanced Input Area */
    .chatbot-input-area {
      border-top: 1px solid #dee2e6;
      padding: 16px;
      background: white;
      position: relative;
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

    /* Enhanced Typing Animation */
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
      background: var(--chatbot-secondary);
      opacity: 0.5;
      animation: pulse-dot 1.4s infinite;
    }

    .chatbot-typing .dot:nth-child(2) {
      animation-delay: 0.2s;
    }

    .chatbot-typing .dot:nth-child(3) {
      animation-delay: 0.4s;
    }

    /* Mobile Responsive */
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
    init: async function(config) {
      try {
        const container = document.getElementById('lyra-chatbot-widget');
        if (!container) {
          console.error('Container element not found');
          return;
        }

        let isOpen = false;
        let isExpanded = false;
        let isTyping = false;
        let messages = [{ role: 'assistant', content: 'Hello! How can I help you today?' }];
        let inputValue = '';
        let userId = config.userId || ('user_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9));
        
        let tenantInfo = {
          business_name: config.businessName || 'Your Support Bot',
          chatbot_widget_icon: config.widgetIcon || '',
          branding: {
            logo_text: config.logoText || 'SB',
            logo_image: config.logoImage || '',
            primary_color: config.primaryColor || '#007bff',
            secondary_color: config.secondaryColor || '#007bff',
            text_color: config.textColor || '#222222',
            user_bubble_color: config.userBubbleColor || '#007bff',
            border_color: config.borderColor || '#e0e0e0',
            border_radius: config.borderRadius || '12px',
            widget_position: config.position || 'bottom-right',
            font_family: config.fontFamily || 'Inter, sans-serif',
            custom_css: config.customCss || ''
          }
        };

        const formatBotMessage = (content) => {
          let formatted = content.trim()
            .replace(/^[•·]\s*(.*$)/gm, (_, text) => `<li>${text.trim()}</li>`)
            .replace(/^\d+\.\s*(.*$)/gm, (_, text) => `<li>${text.trim()}</li>`)
            .replace(/\n\n+/g, '|||PARAGRAPH|||')
            .replace(/\n/g, '<br>')
            .replace(/\|\|\|PARAGRAPH\|\|\|/g, '</p><p>');

          formatted = formatted.replace(
            /(?:<li>.*?<\/li>(?:\s*<br>?\s*<li>.*?<\/li>)*)/g,
            (match) => `<ul>${match.replace(/<br>?\s*/g, '')}</ul>`
          );

          if (!formatted.includes('<p>') && !formatted.includes('<ul>')) {
            formatted = `<p>${formatted}</p>`;
          }

          return formatted;
        };

        const loadBranding = async () => {
          if (!config.baseUrl || !config.apiKey) return;
          
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
                tenantInfo = {
                  ...tenantInfo,
                  ...data,
                  branding: { ...tenantInfo.branding, ...data.branding }
                };
              }
            }
          } catch (error) {
            console.warn('Failed to fetch branding', error);
          }
        };

        const updateBrandingCSS = () => {
          const root = document.documentElement;
          const { branding } = tenantInfo;
          root.style.setProperty('--chatbot-secondary', branding.user_bubble_color);
          root.style.setProperty('--chatbot-shadow', '0 8px 30px rgba(0,0,0,0.12)');

          if (branding.custom_css) {
            let styleEl = document.getElementById('chatbot-custom-styles');
            if (!styleEl) {
              styleEl = document.createElement('style');
              styleEl.id = 'chatbot-custom-styles';
              document.head.appendChild(styleEl);
            }
            styleEl.textContent = branding.custom_css;
          }
        };

        await loadBranding();
        updateBrandingCSS();

        const capitalizeWords = (str) => {
          return str.replace(/\b\w/g, (c) => c.toUpperCase());
        };

        const createLogo = (size = 32) => {
          const { branding } = tenantInfo;
          if (branding.logo_image) {
            const img = document.createElement('img');
            img.src = branding.logo_image;
            img.alt = 'Logo';
            img.style.cssText = `width:${size}px;height:${size}px;border-radius:50%;object-fit:cover;display:block;`;
            return img;
          }
          return createTextLogo(size);
        };

        // const createCompanyLogo = (size = 32) => {
        //   const { chatbot_widget_icon } = tenantInfo;
        //   if (chatbot_widget_icon) {
        //     const img = document.createElement('img');
        //     img.src = chatbot_widget_icon;
        //     img.alt = 'Logo';
        //     img.style.cssText = `width:${size}px;height:${size}px;border-radius:50%;object-fit:cover;display:block;`;
        //     return img;
        //   }
        //   return createTextLogo(size);
        // };

        const createCompanyLogo = (size = 32) => {
          return createTextLogo(size);
        };

        const createTextLogo = (size) => {
          const { branding } = tenantInfo;
          const text = branding.logo_text || capitalizeWords(tenantInfo.business_name.substring(0, 2)).toUpperCase();
          const fontSize = Math.max(12, size * 0.3);
          
          const span = document.createElement('span');
          span.style.cssText = `
            width:${size}px;height:${size}px;display:flex;align-items:center;justify-content:center;
            background:var(--chatbot-secondary);color:white;border-radius:50%;
            font-size:${fontSize}px;font-family:var(--chatbot-font);font-weight:600;
            text-align:center;text-transform:capitalize;line-height:1;
          `;
          span.textContent = text;
          return span;
        };

        const sendMessage = async () => {
          if (!inputValue.trim()) return;

          const newMessage = { role: 'user', content: inputValue.trim() };
          messages.push(newMessage);
          inputValue = '';
          isTyping = true;
          render();

          if (!config.baseUrl || !config.apiKey) {
            setTimeout(() => {
              messages.push({ role: 'assistant', content: 'Demo mode: Please configure your API settings.' });
              isTyping = false;
              render();
            }, 1000);
            return;
          }

          try {
            const response = await fetch(`${config.baseUrl}/chatbot/chat/smart`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'X-API-Key': config.apiKey
              },
              body: JSON.stringify({
                message: newMessage.content,
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
            let currentMessage = '';

            while (true) {
              const { done, value } = await reader.read();
              if (done) break;

              const chunk = decoder.decode(value, { stream: true });
              const lines = (currentMessage + chunk).split('\n');
              currentMessage = lines.pop() || '';

              for (const line of lines) {
                if (!line.trim()) continue;

                try {
                  const data = JSON.parse(line);

                  switch (data.type) {
                    case 'main_response':
                      let formattedContent = data.content;
                      if (typeof formattedContent === 'string') {
                        formattedContent = formattedContent
                          .split('\n')
                          .map((line) => line.trim())
                          .filter((line) => line.length > 0)
                          .join('\n');
                      }

                      const lastMessage = messages[messages.length - 1];
                      if (lastMessage?.role === 'assistant' && lastMessage.content === '') {
                        messages[messages.length - 1] = { ...lastMessage, content: formattedContent };
                      } else {
                        messages.push({ role: 'assistant', content: formattedContent });
                      }
                      render();
                      break;

                    case 'complete':
                      isTyping = false;
                      render();
                      break;

                    case 'error':
                      console.error('Chat error:', data.error);
                      messages.push({
                        role: 'assistant',
                        content: 'Error responding, please try again.'
                      });
                      isTyping = false;
                      render();
                      break;
                  }
                } catch (error) {
                  console.error('Failed to parse JSON:', error, 'Line:', line);
                }
              }
            }

            isTyping = false;
            render();
          } catch (error) {
            console.error('Chat error:', error);
            messages.push({
              role: 'assistant',
              content: 'Error responding, please try again.'
            });
            isTyping = false;
            render();
          }
        };

        const getPositionClass = () => {
          return `chatbot-${tenantInfo.branding.widget_position}`;
        };

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

        const createOpenButton = () => {
          const openButton = document.createElement('button');
          openButton.className = `chatbot-open-btn ${getPositionClass()}`;
          openButton.style.display = isOpen ? 'none' : 'flex';

          openButton.appendChild(createCompanyLogo(24));
          
          const ring1 = document.createElement('div');
          ring1.className = 'chatbot-pulse-ring';
          const ring2 = document.createElement('div');
          ring2.className = 'chatbot-pulse-ring-2';
          
          openButton.appendChild(ring1);
          openButton.appendChild(ring2);

          openButton.addEventListener('click', () => {
            isOpen = true;
            render();
          });

          return openButton;
        };

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
          title.textContent = capitalizeWords(tenantInfo.business_name);

          headerInfo.appendChild(title);
          headerLeft.appendChild(logoContainer);
          headerLeft.appendChild(headerInfo);

          const headerActions = document.createElement('div');
          headerActions.className = 'chatbot-header-actions';

          const expandBtn = document.createElement('button');
          expandBtn.className = 'chatbot-expand-btn';
          expandBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h6v6M14 10l6.1-6.1M9 21H3v-6M10 14l-6.1 6.1"/></svg>`;
          expandBtn.addEventListener('click', () => {
            isExpanded = !isExpanded;
            render();
          });

          const closeBtn = document.createElement('button');
          closeBtn.className = 'chatbot-close-btn';
          closeBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;
          closeBtn.addEventListener('click', () => {
            isOpen = false;
            render();
          });

          headerActions.appendChild(expandBtn);
          headerActions.appendChild(closeBtn);
          header.appendChild(headerLeft);
          header.appendChild(headerActions);

          return header;
        };

        const createBrandSection = () => {
          const brandSection = document.createElement('div');
          brandSection.className = 'chatbot-brand-section';

          const brandLogoWrapper = document.createElement('div');
          brandLogoWrapper.className = 'chatbot-brand-logo-wrapper';
          brandLogoWrapper.appendChild(createLogo(56));

          const brandGlow = document.createElement('div');
          brandGlow.className = 'chatbot-brand-glow';
          brandLogoWrapper.appendChild(brandGlow);

          const brandName = document.createElement('div');
          brandName.className = 'chatbot-brand-name';
          brandName.textContent = capitalizeWords(tenantInfo.business_name);

          const brandSubtitle = document.createElement('div');
          brandSubtitle.className = 'chatbot-brand-subtitle';
          brandSubtitle.textContent = "We're here to help! Ask us anything.";

          brandSection.appendChild(brandLogoWrapper);
          brandSection.appendChild(brandName);
          brandSection.appendChild(brandSubtitle);

          return brandSection;
        };

        const createMessages = () => {
          const messagesContainer = document.createElement('div');
          
          messagesContainer.appendChild(createBrandSection());

          messages.forEach((message, index) => {
            const messageEl = document.createElement('div');
            messageEl.className = `chatbot-message ${message.role === 'assistant' ? 'assistant' : 'user'} chatbot-message-animate`;
            messageEl.style.animationDelay = `${index * 0.1}s`;

            const bubble = document.createElement('div');
            bubble.className = `chatbot-bubble ${message.role} chatbot-bubble-enhanced`;

            if (message.role === 'assistant') {
              bubble.innerHTML = formatBotMessage(message.content);
            } else {
              bubble.innerHTML = message.content.split('\n').map(line => line).join('<br>');
            }

            const tail = document.createElement('div');
            tail.className = 'chatbot-bubble-tail';
            bubble.appendChild(tail);

            messageEl.appendChild(bubble);
            messagesContainer.appendChild(messageEl);
          });

          if (isTyping) {
            const typingMessage = document.createElement('div');
            typingMessage.className = 'chatbot-message assistant chatbot-message-animate';
            
            const typingBubble = document.createElement('div');
            typingBubble.className = 'chatbot-bubble assistant typing-bubble chatbot-bubble-enhanced';
            
            const typingIndicator = document.createElement('div');
            typingIndicator.className = 'chatbot-typing';
            typingIndicator.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
            
            const tail = document.createElement('div');
            tail.className = 'chatbot-bubble-tail';
            
            typingBubble.appendChild(typingIndicator);
            typingBubble.appendChild(tail);
            typingMessage.appendChild(typingBubble);
            messagesContainer.appendChild(typingMessage);
          }

          return messagesContainer;
        };

        const createInputArea = () => {
          const inputArea = document.createElement('div');
          inputArea.className = 'chatbot-input-area';

          const inputWrapper = document.createElement('div');
          inputWrapper.className = 'chatbot-input-wrapper';

          const input = document.createElement('input');
          input.className = 'chatbot-input';
          input.type = 'text';
          input.value = inputValue;
          input.placeholder = 'Type your message...';
          
          input.addEventListener('input', (e) => {
            inputValue = e.target.value;
          });
          
          input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              sendMessage();
            }
          });

          const sendBtn = document.createElement('button');
          sendBtn.className = 'chatbot-send-btn';
          sendBtn.disabled = !inputValue.trim();
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

          return inputArea;
        };

        const createWidget = () => {
          const widget = document.createElement('div');
          widget.className = `chatbot-widget ${getPositionClass()} ${isOpen ? 'chatbot-widget-open' : ''} ${isExpanded ? 'chatbot-widget-expanded' : ''}`;
          widget.style.display = isOpen ? 'flex' : 'none';

          const header = createHeader();
          const body = document.createElement('div');
          body.className = 'chatbot-body';
          
          const messages = createMessages();
          body.appendChild(messages);
          
          const inputArea = createInputArea();

          widget.appendChild(header);
          widget.appendChild(body);
          widget.appendChild(inputArea);

          return widget;
        };

        const render = () => {
          container.innerHTML = '';

          if (!isOpen) {
            container.appendChild(createParticles());
            container.appendChild(createOpenButton());
          } else {
            container.appendChild(createWidget());
            // Auto-focus input when opened
            setTimeout(() => {
              const input = container.querySelector('.chatbot-input');
              if (input) input.focus();
            }, 100);
          }
        };

        // Initial render
        render();

      } catch (error) {
        console.error('Chatbot initialization failed:', error);
      }
    }
  };
})();