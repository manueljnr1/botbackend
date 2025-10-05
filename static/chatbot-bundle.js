(function() {
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

    .chatbot-widget {
      position: fixed;
      z-index: 10000;
      width: 100%;
      max-width: 420px;
      height: 75vh;
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

    .chatbot-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 16px;
      background: white;
      color: #1f2937;
      position: relative;
      border-bottom: 1px solid #e5e7eb;
    }

    .chatbot-header-left {
      display: flex;
      align-items: center;
      gap: 12px;
      z-index: 1;
    }

    .chatbot-back-btn {
      background: transparent;
      border: none;
      color: #1f2937;
      cursor: pointer;
      padding: 4px;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s ease;
    }

    .chatbot-back-btn:hover {
      transform: translateX(-2px);
    }

    .chatbot-logo-container {
      position: relative;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .chatbot-title {
      font-size: 1rem;
      font-weight: 600;
      color: #1f2937;
      margin: 0;
    }

    .chatbot-header-actions {
      display: flex;
      gap: 8px;
      align-items: center;
    }

    .chatbot-close-btn {
      background: transparent;
      padding: 4px;
      border: none;
      color: #1f2937;
      cursor: pointer;
      transition: all 0.2s ease;
      z-index: 1;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .chatbot-close-btn:hover {
      transform: rotate(90deg);
    }

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

    .chatbot-welcome-view {
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 0;
      text-align: center;
      background: linear-gradient(to bottom, var(--chatbot-secondary) 0%, var(--chatbot-secondary) 40%, #ffffff 40%, #ffffff 100%);
      height: 100%;
      overflow-y: auto;
    }

    .chatbot-welcome-content {
      padding: 40px 24px;
      width: 100%;
      display: flex;
      flex-direction: column;
      align-items: center;
    }

    .chatbot-welcome-logo {
      width: 80px;
      height: 80px;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 24px;
    }

    .chatbot-welcome-heading {
      font-size: 24px;
      font-weight: 700;
      color: #ffffff;
      margin-bottom: 8px;
      line-height: 1.3;
    }

    .chatbot-welcome-subheading {
      font-size: 24px;
      font-weight: 700;
      color: #ffffff;
      margin-bottom: 24px;
      line-height: 1.3;
    }

    .chatbot-status-card {
      background: white;
      border: 1px solid #e5e7eb;
      border-radius: 12px;
      padding: 16px;
      width: 100%;
      max-width: 360px;
      margin-bottom: 24px;
      display: flex;
      align-items: center;
      gap: 12px;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    }

    .chatbot-status-icon {
      width: 40px;
      height: 40px;
      background: #10b981;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }

    .chatbot-status-content {
      flex: 1;
      text-align: left;
    }

    .chatbot-status-title {
      font-size: 14px;
      font-weight: 600;
      color: #1f2937;
      margin-bottom: 2px;
    }

    .chatbot-status-time {
      font-size: 12px;
      color: #6b7280;
    }

    .chatbot-action-buttons {
      display: flex;
      flex-direction: column;
      gap: 12px;
      width: 100%;
      max-width: 360px;
      margin-bottom: 24px;
    }

    .chatbot-action-btn {
      background: white;
      border: 1px solid #e5e7eb;
      border-radius: 10px;
      padding: 14px 20px;
      font-size: 14px;
      font-weight: 500;
      color: #1f2937;
      cursor: pointer;
      transition: all 0.2s ease;
      display: flex;
      align-items: center;
      justify-content: space-between;
      text-align: left;
    }

    .chatbot-action-btn:hover {
      background: #f9fafb;
      border-color: var(--chatbot-secondary);
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    }

    .chatbot-action-btn svg {
      width: 18px;
      height: 18px;
      color: var(--chatbot-secondary);
    }

    .chatbot-quick-links {
      width: 100%;
      max-width: 360px;
    }

    .chatbot-quick-links-title {
      font-size: 13px;
      font-weight: 600;
      color: #6b7280;
      margin-bottom: 12px;
      text-align: left;
    }

    .chatbot-quick-link {
      background: white;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      padding: 12px 16px;
      font-size: 13px;
      color: #1f2937;
      cursor: pointer;
      transition: all 0.2s ease;
      display: flex;
      align-items: center;
      justify-content: space-between;
      text-align: left;
      margin-bottom: 8px;
    }

    .chatbot-quick-link:hover {
      background: #f9fafb;
      border-color: #d1d5db;
    }

    .chatbot-quick-link svg {
      width: 16px;
      height: 16px;
      color: #9ca3af;
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
      width: 80px;
      height: 80px;
      display: flex;
      align-items: center;
      justify-content: center;
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
      to { opacity: 1; transform: translateY(0); }
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

    @keyframes pulse-dot {
      0%, 80%, 100% { opacity: 0.3; transform: scale(1); }
      40% { opacity: 1; transform: scale(1.4); }
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

    .chatbot-video-player {
      position: fixed;
      width: 400px;
      height: 225px;
      background: #000;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3);
      z-index: 10001;
      transition: all 0.3s ease;
      display: none;
    }

    .chatbot-video-player.active {
      display: block;
    }

    .chatbot-video-player.expanded {
      width: 800px;
      height: 450px;
    }

    .chatbot-video-player.minimized {
      width: 300px;
      height: 60px;
    }

    .chatbot-video-player-header {
      background: rgba(0, 0, 0, 0.9);
      padding: 8px 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      cursor: move;
    }

    .chatbot-video-player-title {
      color: white;
      font-size: 13px;
      font-weight: 500;
      flex: 1;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .chatbot-video-player-controls {
      display: flex;
      gap: 4px;
    }

    .chatbot-video-player-btn {
      background: rgba(255, 255, 255, 0.1);
      border: none;
      color: white;
      width: 24px;
      height: 24px;
      border-radius: 4px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.2s;
    }

    .chatbot-video-player-btn:hover {
      background: rgba(255, 255, 255, 0.2);
    }

    .chatbot-video-player-content {
      width: 100%;
      height: calc(100% - 40px);
      background: #000;
    }

    .chatbot-video-player.minimized .chatbot-video-player-content {
      display: none;
    }

    .chatbot-video-player iframe {
      width: 100%;
      height: 100%;
      border: none;
    }

    .chatbot-message a {
      color: var(--chatbot-secondary);
      text-decoration: underline;
      cursor: pointer;
    }

    .chatbot-message a:hover {
      text-decoration: none;
    }

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
      .chatbot-video-player {
        width: 90vw !important;
        height: calc(90vw * 0.5625) !important;
        left: 5vw !important;
        top: 50% !important;
        transform: translateY(-50%) !important;
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
      console.log('🚀 COMPLETE MODIFIED CHATBOT VERSION');
      try {
        const container = document.getElementById('lyra-chatbot-widget');
        if (!container) {
          console.error('Container element not found');
          return;
        }

        let isOpen = false;
        let isTyping = false;
        let messages = [];
        let inputValue = '';
        let userId = config.userId || ('user_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9));
        let showWelcome = true;
        
        let videoPlayer = {
          active: false,
          minimized: false,
          expanded: false,
          url: '',
          x: window.innerWidth - 450,
          y: 100
        };

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

        const loadMessages = async () => {
          if (!config.enableServerStorage || !config.baseUrl || !config.apiKey) {
            try {
              const stored = localStorage.getItem(`chatbot_messages_${userId}`);
              if (stored) {
                const loadedMessages = JSON.parse(stored);
                if (loadedMessages.length > 0) {
                  messages = loadedMessages;
                  showWelcome = false;
                }
              }
            } catch (error) {
              console.warn('Failed to load local messages:', error);
            }
            return;
          }
        
          try {
            const response = await fetch(`${config.baseUrl}/chatbot/messages/${userId}`, {
              headers: {
                'Content-Type': 'application/json',
                'X-API-Key': config.apiKey
              }
            });
            
            if (response.ok) {
              const data = await response.json();
              if (data.messages && data.messages.length > 0) {
                messages = data.messages;
                showWelcome = false;
              }
            }
          } catch (error) {
            console.warn('Failed to load server messages:', error);
          }
        };
        
        const saveMessages = async () => {
          if (!config.enableServerStorage || !config.baseUrl || !config.apiKey) {
            try {
              localStorage.setItem(`chatbot_messages_${userId}`, JSON.stringify(messages));
            } catch (error) {
              console.warn('Failed to save local messages:', error);
            }
            return;
          }
        
          try {
            await fetch(`${config.baseUrl}/chatbot/messages/${userId}`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'X-API-Key': config.apiKey
              },
              body: JSON.stringify({ messages })
            });
          } catch (error) {
            console.warn('Failed to save server messages:', error);
          }
        };

        const extractVideoId = (url) => {
          let match = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\s]+)/);
          if (match) return { type: 'youtube', id: match[1] };
          
          match = url.match(/vimeo\.com\/(\d+)/);
          if (match) return { type: 'vimeo', id: match[1] };
          
          return null;
        };

        const openVideoPlayer = (url) => {
          const video = extractVideoId(url);
          if (!video) return;

          videoPlayer.active = true;
          videoPlayer.minimized = false;
          videoPlayer.url = video.type === 'youtube' 
            ? `https://www.youtube.com/embed/${video.id}?autoplay=1`
            : `https://player.vimeo.com/video/${video.id}?autoplay=1`;
          
          render();
        };

        const linkifyMessage = (content) => {
          const urlRegex = /(https?:\/\/[^\s]+)/g;
          return content.replace(urlRegex, (url) => {
            const video = extractVideoId(url);
            if (video) {
              return `<a href="#" data-video-url="${url}">${url}</a>`;
            }
            return `<a href="${url}" target="_blank">${url}</a>`;
          });
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
        await loadMessages();

        const capitalizeWords = (str) => {
          return str.replace(/\b\w/g, (c) => c.toUpperCase());
        };

        const createCompanyLogo = (size = 32, useWidgetIcon = false) => {
          if (useWidgetIcon) {
            return createTextLogo(size);
          }
          
          const logoImage = tenantInfo.branding?.logo_image;
          if (logoImage) {
            const img = document.createElement('img');
            img.src = logoImage;
            img.alt = 'Company Logo';
            img.style.cssText = `width:${size}px;height:${size}px;border-radius:50%;object-fit:cover;display:block;`;
            return img;
          }
          return createTextLogo(size);
        };

        const createTextLogo = (size) => {
          const container = document.createElement('div');
          container.style.cssText = `width:${size}px;height:${size}px;display:flex;align-items:center;justify-content:center;`;
          
          const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
          const svgSize = Math.max(24, size * 0.9);
          svg.setAttribute('width', svgSize);
          svg.setAttribute('height', svgSize);
          svg.setAttribute('viewBox', '0 0 24 24');
          svg.setAttribute('fill', 'white');
          
          const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
          path.setAttribute('d', 'M12,2c-4.97056,0 -9,4.02944 -9,9c0,4.97056 4.02944,9 9,9v2.5c0,0.381 0.41219,0.62459 0.74219,0.43359c1.93936,-1.12274 7.06688,-4.82624 8.07227,-10.12305c0.00536,-0.02992 0.01057,-0.05987 0.01563,-0.08984c0.04363,-0.24189 0.0857,-0.48402 0.11133,-0.73242c0.03765,-0.3281 0.05721,-0.65803 0.05859,-0.98828c0,-4.97056 -4.02944,-9 -9,-9z');
          
          svg.appendChild(path);
          container.appendChild(svg);
          return container;
        };

        const createVideoPlayer = () => {
          if (!videoPlayer.active) return null;

          const player = document.createElement('div');
          player.className = `chatbot-video-player active ${videoPlayer.expanded ? 'expanded' : ''} ${videoPlayer.minimized ? 'minimized' : ''}`;
          player.style.left = videoPlayer.x + 'px';
          player.style.top = videoPlayer.y + 'px';

          const header = document.createElement('div');
          header.className = 'chatbot-video-player-header';

          const title = document.createElement('div');
          title.className = 'chatbot-video-player-title';
          title.textContent = 'Video Player';

          const controls = document.createElement('div');
          controls.className = 'chatbot-video-player-controls';

          const minimizeBtn = document.createElement('button');
          minimizeBtn.className = 'chatbot-video-player-btn';
          minimizeBtn.innerHTML = videoPlayer.minimized ? '▢' : '—';
          minimizeBtn.addEventListener('click', () => {
            videoPlayer.minimized = !videoPlayer.minimized;
            render();
          });

          const expandBtn = document.createElement('button');
          expandBtn.className = 'chatbot-video-player-btn';
          expandBtn.innerHTML = videoPlayer.expanded ? '◱' : '⛶';
          expandBtn.addEventListener('click', () => {
            videoPlayer.expanded = !videoPlayer.expanded;
            render();
          });

          const closeBtn = document.createElement('button');
          closeBtn.className = 'chatbot-video-player-btn';
          closeBtn.innerHTML = '✕';
          closeBtn.addEventListener('click', () => {
            videoPlayer.active = false;
            render();
          });

          controls.appendChild(minimizeBtn);
          controls.appendChild(expandBtn);
          controls.appendChild(closeBtn);

          header.appendChild(title);
          header.appendChild(controls);

          const content = document.createElement('div');
          content.className = 'chatbot-video-player-content';
          
          const iframe = document.createElement('iframe');
          iframe.src = videoPlayer.url;
          iframe.allow = 'autoplay; fullscreen';
          iframe.allowFullscreen = true;
          
          content.appendChild(iframe);
          player.appendChild(header);
          player.appendChild(content);

          let isDragging = false;
          let offsetX, offsetY;

          header.addEventListener('mousedown', (e) => {
            isDragging = true;
            offsetX = e.clientX - videoPlayer.x;
            offsetY = e.clientY - videoPlayer.y;
          });

          document.addEventListener('mousemove', (e) => {
            if (isDragging) {
              videoPlayer.x = e.clientX - offsetX;
              videoPlayer.y = e.clientY - offsetY;
              player.style.left = videoPlayer.x + 'px';
              player.style.top = videoPlayer.y + 'px';
            }
          });

          document.addEventListener('mouseup', () => {
            isDragging = false;
          });

          return player;
        };

        const sendMessage = async () => {
          if (!inputValue.trim()) return;

          const newMessage = { role: 'user', content: inputValue.trim() };
          messages.push(newMessage);
          saveMessages();
          inputValue = '';
          isTyping = true;
          showWelcome = false;
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
                        saveMessages();
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
                      saveMessages();
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
            saveMessages();
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

          openButton.appendChild(createCompanyLogo(24, true));
          
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

          const backBtn = document.createElement('button');
          backBtn.className = 'chatbot-back-btn';
          backBtn.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>`;
          backBtn.addEventListener('click', () => {
            showWelcome = true;
            render();
          });

          const logoContainer = document.createElement('div');
          logoContainer.className = 'chatbot-logo-container';
          logoContainer.appendChild(createCompanyLogo(32));

          const title = document.createElement('span');
          title.className = 'chatbot-title';
          title.textContent = capitalizeWords(tenantInfo.business_name);

          headerLeft.appendChild(backBtn);
          headerLeft.appendChild(logoContainer);
          headerLeft.appendChild(title);

          const headerActions = document.createElement('div');
          headerActions.className = 'chatbot-header-actions';

          const closeBtn = document.createElement('button');
          closeBtn.className = 'chatbot-close-btn';
          closeBtn.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;
          closeBtn.addEventListener('click', () => {
            isOpen = false;
            render();
          });

          headerActions.appendChild(closeBtn);
          header.appendChild(headerLeft);
          header.appendChild(headerActions);

          return header;
        };

        const createWelcomeView = () => {
          const welcomeView = document.createElement('div');
          welcomeView.className = 'chatbot-welcome-view';

          const content = document.createElement('div');
          content.className = 'chatbot-welcome-content';

          const logo = document.createElement('div');
          logo.className = 'chatbot-welcome-logo';
          logo.appendChild(createCompanyLogo(80));

          const heading = document.createElement('div');
          heading.className = 'chatbot-welcome-heading';
          heading.textContent = 'Need support?';

          const subheading = document.createElement('div');
          subheading.className = 'chatbot-welcome-subheading';
          subheading.textContent = 'How can we help?';

          const statusCard = document.createElement('div');
          statusCard.className = 'chatbot-status-card';
          statusCard.innerHTML = `
            <div class="chatbot-status-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
            </div>
            <div class="chatbot-status-content">
              <div class="chatbot-status-title">Status: All Systems Operational</div>
              <div class="chatbot-status-time">Updated Oct 5, 08:55 UTC</div>
            </div>
          `;

          const actionButtons = document.createElement('div');
          actionButtons.className = 'chatbot-action-buttons';

          const sendMessageBtn = document.createElement('button');
          sendMessageBtn.className = 'chatbot-action-btn';
          sendMessageBtn.innerHTML = `
            Send us a message
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M5 12h14M12 5l7 7-7 7"/>
            </svg>
          `;
          sendMessageBtn.addEventListener('click', () => {
            showWelcome = false;
            render();
            setTimeout(() => {
              const input = container.querySelector('.chatbot-input');
              if (input) input.focus();
            }, 100);
          });

          const searchBtn = document.createElement('button');
          searchBtn.className = 'chatbot-action-btn';
          searchBtn.innerHTML = `
            Search for help
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8"></circle>
              <path d="m21 21-4.35-4.35"/>
            </svg>
          `;
          searchBtn.addEventListener('click', () => {
            console.log('Search functionality - coming soon');
          });

          actionButtons.appendChild(sendMessageBtn);
          actionButtons.appendChild(searchBtn);

          const quickLinks = document.createElement('div');
          quickLinks.className = 'chatbot-quick-links';

          const quickLinksTitle = document.createElement('div');
          quickLinksTitle.className = 'chatbot-quick-links-title';
          quickLinksTitle.textContent = 'Quick help';

          const links = [
            'How to Get Support',
            'Getting Started Guide',
            'Common Questions'
          ];

          const linksContainer = document.createElement('div');
          links.forEach(linkText => {
            const link = document.createElement('button');
            link.className = 'chatbot-quick-link';
            link.innerHTML = `
              ${linkText}
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="9 18 15 12 9 6"></polyline>
              </svg>
            `;
            link.addEventListener('click', () => {
              console.log('Quick link clicked:', linkText);
            });
            linksContainer.appendChild(link);
          });

          quickLinks.appendChild(quickLinksTitle);
          quickLinks.appendChild(linksContainer);

          content.appendChild(logo);
          content.appendChild(heading);
          content.appendChild(subheading);
          content.appendChild(statusCard);
          content.appendChild(actionButtons);
          content.appendChild(quickLinks);

          welcomeView.appendChild(content);

          return welcomeView;
        };

        const createBrandSection = () => {
          const brandSection = document.createElement('div');
          brandSection.className = 'chatbot-brand-section';

          const brandLogoWrapper = document.createElement('div');
          brandLogoWrapper.className = 'chatbot-brand-logo-wrapper';
          brandLogoWrapper.appendChild(createCompanyLogo(80));

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
              bubble.innerHTML = linkifyMessage(formatBotMessage(message.content));
            } else {
              bubble.innerHTML = linkifyMessage(message.content.split('\n').map(line => line).join('<br>'));
            }

            bubble.querySelectorAll('a[data-video-url]').forEach(link => {
              link.addEventListener('click', (e) => {
                e.preventDefault();
                openVideoPlayer(link.getAttribute('data-video-url'));
              });
            });

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
            sendBtn.disabled = !inputValue.trim();
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
          widget.className = `chatbot-widget ${getPositionClass()} ${isOpen ? 'chatbot-widget-open' : ''}`;
          widget.style.display = isOpen ? 'flex' : 'none';

          const body = document.createElement('div');
          body.className = 'chatbot-body';
          
          if (showWelcome) {
            const welcomeView = createWelcomeView();
            body.appendChild(welcomeView);
            widget.appendChild(body);
          } else {
            const header = createHeader();
            widget.appendChild(header);
            
            const messagesView = createMessages();
            body.appendChild(messagesView);
            widget.appendChild(body);
            
            const inputArea = createInputArea();
            widget.appendChild(inputArea);
          }

          return widget;
        };

        const render = () => {
          container.innerHTML = '';
        
          if (!isOpen) {
            container.appendChild(createParticles());
            container.appendChild(createOpenButton());
          } else {
            container.appendChild(createWidget());
            
            const existingPlayer = document.querySelector('.chatbot-video-player');
            if (existingPlayer) existingPlayer.remove();
            
            const player = createVideoPlayer();
            if (player) {
              document.body.appendChild(player);
            }
            
            setTimeout(() => {
              const input = container.querySelector('.chatbot-input');
              const chatBody = container.querySelector('.chatbot-body');
              if (input && !showWelcome) input.focus();
              if (chatBody) chatBody.scrollTop = chatBody.scrollHeight;
            }, 100);
          }
        };

        render();

      } catch (error) {
        console.error('Chatbot initialization failed:', error);
      }
    }
  };
})();