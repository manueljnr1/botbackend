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
      box-shadow: 0 8px 25px rgba(0, 0, 0, 0.1);
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
      box-shadow: 0 12px 35px rgba(0, 0, 0, 0.15);
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
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3), 
              0 8px 30px rgba(0, 0, 0, 0.22),
              0 0 0 1px rgba(0, 0, 0, 0.05);
      border: none;
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
      font-weight: 500;
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
      display: flex; 
      flex-direction: column;
      overflow-y: auto; 
      position: relative;
    }

    
    .chatbot-header + .chatbot-body {
      padding: 20px; 
      gap: 16px; 
      background: linear-gradient(to bottom, #ffffff 0%, #fafbfc 100%);
    }

    .chatbot-welcome-view {
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 0;
      text-align: center;
      background: linear-gradient(to bottom, #000000 0%, #000000 40%, #ffffff 40%, #ffffff 100%);
      height: 100%;
      overflow-y: auto;
      overscroll-behavior: contain;
      position: relative;
    }

    .chatbot-welcome-view::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 40%;
      background-image: 
        linear-gradient(45deg, transparent 48%, var(--chatbot-secondary) 48%, var(--chatbot-secondary) 52%, transparent 52%),
        linear-gradient(-45deg, transparent 48%, var(--chatbot-secondary) 48%, var(--chatbot-secondary) 52%, transparent 52%);
      background-size: 40px 40px;
      background-position: 0 0, 20px 0;
      opacity: 0.08;
      pointer-events: none;
      z-index: 0;
    }

    .chatbot-welcome-content {
      padding: 40px 24px;
      width: 100%;
      display: flex;
      flex-direction: column;
      align-items: center;
      position: relative;
      z-index: 1;
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
      font-weight: 600;
      color: #ffffff;
      margin-bottom: 8px;
      line-height: 1.3;
    }

    .chatbot-welcome-subheading {
      font-size: 24px;
      font-weight: 600;
      color: #ffffff;
      margin-bottom: 24px;
      line-height: 1.3;
    }

    .chatbot-status-card {
      background: white;
      border: none;
      border-radius: 8px;
      padding: 16px;
      width: calc(100% - 16px); /* Changed */
      margin: 0 8px 16px 8px;
      display: flex;
      align-items: center;
      gap: 12px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1), 
                   0 -4px 12px rgba(0, 0, 0, 0.06);
    }


    .chatbot-quick-links-card {
      background: white;
      border: none;
      border-radius: 12px;
      padding: 16px;
      width: calc(100% - 16px); 
      margin: 0 8px 24px 8px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1), 
                  0 -4px 12px rgba(0, 0, 0, 0.06);
    }

    .chatbot-quick-links {
      width: 100%;
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
      font-weight: 500;
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
      gap: 8px;
      width: calc(100% - 16px); /* Changed */
      margin: 0 8px 24px 8px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1), 
                 0 -4px 12px rgba(0, 0, 0, 0.06);
    }

    .chatbot-action-btn {
      background: white;
      border: none;
      border-radius: 8px;
      padding: 16px 20px;
      font-size: 14px;
      font-weight: 400;
      color: #1f2937;
      color: #1f2937;
      cursor: pointer;
      transition: all 0.2s ease;
      display: flex;
      align-items: center;
      justify-content: space-between;
      text-align: left;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1), 
                   0 -4px 12px rgba(0, 0, 0, 0.06);
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



    .chatbot-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.4);
      z-index: 9999;
      backdrop-filter: blur(2px);
    }

    .chatbot-quick-links-title {
      font-size: 13px;
      font-weight: 500;
      color: #6b7280;
      margin-bottom: 12px;
      text-align: left;
    }

    .chatbot-quick-link {
      background: transparent;
      border: none;
      border-radius: 8px;
      padding: 14px 16px;
      font-size: 14px;
      color: #1f2937;
      cursor: pointer;
      transition: all 0.2s ease;
      display: flex;
      align-items: center;
      justify-content: space-between;
      text-align: left;
      margin-bottom: 8px;
      box-shadow: none;
      width: 100%;
    }

    .chatbot-quick-link:hover {
      background: #f9fafb;
      color: var(--chatbot-secondary);
    }

    .chatbot-quick-link:hover svg {
      color: var(--chatbot-secondary);
    }

    .chatbot-quick-link svg {
      width: 16px;
      height: 16px;
      color: #9ca3af;
    }



    .chatbot-footer {
      display: flex;
      border-top: none;
      background: white;
      padding: 8px 16px;
      /* This is the new, softer shadow */
      box-shadow: inset 0 5px 15px -5px rgba(0, 0, 0, 0.1);
      margin-top: auto;
    }

    .chatbot-footer-btn {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 4px;
      background: none;
      border: none;
      padding: 8px;
      cursor: pointer;
      color: #6b7280;
      font-size: 11px;
      transition: color 0.2s;
    }


    .chatbot-footer-btn.active {
      color: var(--chatbot-secondary);
    }

    .chatbot-footer-btn:hover {
      color: var(--chatbot-secondary);
    }

    .chatbot-footer-btn svg {
    transition: fill 0.2s ease-in-out, stroke 0.2s ease-in-out;
    }

    .chatbot-footer-btn:hover svg,
    .chatbot-footer-btn.active svg {
      fill: var(--chatbot-secondary); 
      stroke: white;
    }
   
    .chatbot-welcome-close-btn {
      position: fixed;
      top: 16px;
      right: 16px;
      background: rgba(255, 255, 255, 0.2);
      border: none;
      color: white;
      width: 32px;
      height: 32px;
      border-radius: 50%;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s ease;
      z-index: 10;
    }

    .chatbot-messages-list-view .chatbot-welcome-close-btn {
      color: #1f2937; /* The soft black color */
      background: rgba(0, 0, 0, 0.05); /* Optional: A very light grey background */
    }

    .chatbot-messages-list-view .chatbot-welcome-close-btn:hover {
        background: rgba(0, 0, 0, 0.1); /* Slightly darker on hover */
        transform: rotate(90deg); /* Keep the rotation effect */
    }

    .chatbot-welcome-close-btn:hover {
      background: rgba(255, 255, 255, 0.3);
      transform: rotate(90deg);
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
      font-weight: 600;
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



    .chatbot-new-chat-btn {
      position: absolute;
      bottom: 24px;
      left: 50%;
      transform: translateX(-50%);
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      background: var(--chatbot-secondary);
      color: #ffffff;
      border: none;
      border-radius: 25px; /* Pill shape */
      padding: 12px 20px;
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s ease;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    }

    .chatbot-new-chat-btn:hover {
      transform: translateX(-50%) translateY(-2px);
      box-shadow: 0 6px 16px rgba(0, 0, 0, 0.12);
    }

    .chatbot-new-chat-btn svg {
      width: 18px;
      height: 18px;
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
      font-weight: 400;
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





    .chatbot-faq-view {
      display: flex;
      flex-direction: column;
      flex: 1;
      background: #f9fafb; /* Light grey background for the whole view */
    }
    .chatbot-faq-header {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 10px 16px;
      border-bottom: 1px solid #e5e7eb;
      position: relative;
      background: white; /* Keep header white */
      flex-shrink: 0;
    }
    .chatbot-faq-back-btn {
      position: absolute;
      left: 16px;
      background: transparent;
      border: none;
      cursor: pointer;
      padding: 4px;
      color: #1f2937;
    }
    .chatbot-faq-header h2 {
      font-size: 16px; /* Smaller title for a refined look */
      font-weight: 500;
      color: #1f2937;
      margin: 0;
    }
    .chatbot-faq-list {
      flex: 1;
      overflow-y: auto;
      overscroll-behavior: contain;
      padding: 16px; /* More padding around the cards */
      display: flex;
      flex-direction: column;
      gap: 12px; /* Space between cards */
    }
    .chatbot-faq-item {
      background: white;
      border-radius: 12px; /* Rounded corners */
      border: 1px solid #e5e7eb;
      transition: all 0.2s ease-in-out;
      overflow: hidden; /* Crucial for the accordion animation */
    }
    .chatbot-faq-item:hover {
        border-color: #d1d5db;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05); /* Subtle hover shadow */
    }
    .chatbot-faq-question {
      background: transparent;
      border: none;
      width: 100%;
      text-align: left;
      padding: 16px; /* Consistent padding */
      font-size: 14px;
      font-weight: 500;
      color: #1f2937;
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .chatbot-faq-question svg {
      transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1); /* Smoother animation */
      flex-shrink: 0;
      margin-left: 12px;
      color: #9ca3af;
    }
    .chatbot-faq-item.active .chatbot-faq-question svg {
      transform: rotate(180deg);
      color: var(--chatbot-secondary); /* Use brand color when active */
    }
    .chatbot-faq-answer {
      max-height: 0;
      overflow: hidden;
      font-size: 14px; /* Larger answer text */
      color: #4b5563; /* Softer text color for readability */
      line-height: 1.6;
      padding: 0 16px;
      transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .chatbot-faq-item.active .chatbot-faq-answer {
      max-height: 500px; /* Generous height for content */
      padding-bottom: 20px;
    }


    .chatbot-game-view {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      flex: 1;
      background-color: #f0f2f5;
      color: #1f2937;
      text-align: center;
      padding: 20px;
      position: relative; /* Needed for the close button */
    }
    #lyra-tower-canvas {
      background-color: white;
      border-radius: 8px;
      box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
    }
    .chatbot-game-score {
      font-size: 24px;
      font-weight: 600;
      color: var(--chatbot-secondary);
      margin: 10px 0;
    }
    .chatbot-game-instructions {
      margin-top: 15px;
      font-size: 14px;
      color: #6b7280;
    }
    .chatbot-game-view .chatbot-welcome-close-btn {
      color: #1f2937;
      background: rgba(0, 0, 0, 0.05);
    }
    .chatbot-game-view .chatbot-welcome-close-btn:hover {
      background: rgba(0, 0, 0, 0.1);
    }


    .chatbot-messages-list-view {
      height: 100%;
      display: flex;
      flex-direction: column;
      background: white;
      position: relative; /* This is crucial for positioning the button */
    }
    .chatbot-messages-list-header {
      padding: 10px 20px;
      border-bottom: 1px solid #e5e7eb;
      display: flex;
      justify-content: center;
      align-items: center;
    }

    .chatbot-messages-list-header h2 {
      margin: 0;
      font-size: 20px;
      font-weight: 500;
      color: #1f2937;
    }

    .chatbot-messages-list {
      flex: 1;
      overflow-y: auto;
      overscroll-behavior: contain;
      padding: 12px;
    }

    .chatbot-conversation-item {
      display: flex;
      gap: 12px;
      padding: 12px;
      border-radius: 8px;
      border-bottom: 1px solid #f0f2f5;
      cursor: pointer;
      transition: background 0.2s;
    }

    .chatbot-conversation-item:hover {
      background: #f9fafb;
    }

    .chatbot-conversation-avatar {
      width: 40px;
      height: 40px;
      border-radius: 50%;
      background: var(--chatbot-secondary);
      color: white;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      font-weight: 500;
    }

    .chatbot-conversation-content {
      flex: 1;
      min-width: 0;
    }

    .chatbot-conversation-preview {
      font-size: 14px;
      color: #1f2937;
      margin-bottom: 4px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .chatbot-conversation-time {
      font-size: 12px;
      color: #6b7280;
    }


    chatbot-welcome-view {
      scrollbar-width: none;
      -ms-overflow-style: none; 
    }
    .chatbot-welcome-view::-webkit-scrollbar {
      display: none; 
    }

    .chatbot-header + .chatbot-body::-webkit-scrollbar-thumb {
      background-color: #e9e9e9;
      border-radius: 6px;
      border: 2px solid white; 
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

    .chatbot-widget {
      will-change: transform, opacity;
      transform: translateZ(0);
      backface-visibility: hidden;
    }

    .chatbot-body {
      will-change: scroll-position;
      transform: translateZ(0);
      -webkit-overflow-scrolling: touch;
      overscroll-behavior: contain;
    }

    .chatbot-message {
      will-change: transform, opacity;
      transform: translateZ(0);
    }

    .chatbot-quote {
      font-size: 13px; 
      // font-style: italic;
      font-weight: 600;
      color: #9ca3af;
      cursor: default;
      transition: all 0.4s ease;
      margin-top: auto; 
      padding-top: 15px;
      padding-bottom: 25px;
      user-select: none; /* <-- Add this line */
      -webkit-user-select: none;
    }

    .chatbot-quote:hover {
      color: transparent;
      background-image: linear-gradient(45deg, #ff00ff, #00ffff, #ffff00, #ff00ff);
      background-size: 400% 400%;
      -webkit-background-clip: text;
      background-clip: text;
      -webkit-text-fill-color: transparent;
      animation: radiant-text 3s ease infinite, sparkle-glow 1.5s ease-in-out infinite alternate;
    }

    @keyframes radiant-text {
      0% { background-position: 0% 50%; }
      50% { background-position: 100% 50%; }
      100% { background-position: 0% 50%; }
    }

    @keyframes sparkle-glow {
      from {
        text-shadow: 0 0 5px #fff, 0 0 10px #fff, 0 0 15px #00ffff;
      }
      to {
        text-shadow: 0 0 10px #fff, 0 0 20px #ff00ff, 0 0 30px #ffff00;
      }
    }

    @media (min-width: 769px) {
      .chatbot-widget.chatbot-bottom-right,
      .chatbot-widget.chatbot-bottom-left,
      .chatbot-open-btn.chatbot-bottom-right,
      .chatbot-open-btn.chatbot-bottom-left {
      }
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
        font-weight: 400;
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
        max-height: 100dvh;
        border-radius: 0;
        position: fixed;
        top: 0 !important;
        left: 0 !important;
        right: 0 !important;
        bottom: 0 !important;
        margin: 0;
        transform: translateZ(0);
      }

      .chatbot-body {
        position: fixed;
        top: 60px;
        bottom: 80px;
        left: 0;
        right: 0;
        padding: 16px;
        overflow-y: auto;
        transform: translateZ(0);
        display: flex; 
        flex-direction: column;
      }
      
      .chatbot-input-area {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        padding: 12px;
        background: white;
        z-index: 2;
        transform: translateZ(0);
        padding-bottom: max(12px, env(safe-area-inset-bottom));
      }
      
      .chatbot-header {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        padding: 16px;
        z-index: 2;
        transform: translateZ(0);
        padding-top: max(16px, env(safe-area-inset-top));
      }

      .chatbot-widget > .chatbot-body:first-child {
        position: fixed;
        top: 0;
        bottom: 56px; 
        left: 0;
        right: 0;
        width: 100%;
        overflow-y: auto;
        overscroll-behavior: contain;
      }

      .chatbot-input-area.disabled {
        min-height: 74px;
        display: flex;
        justify-content: center;
        align-items: center;
      }

      .closed-message {
        color: #4b5563;     
        font-weight: 400;   
        font-size: 14px;
      }

      .chatbot-body.is-game-view {
        bottom: 0;

      .chatbot-widget > .chatbot-body:first-child + .chatbot-footer {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        width: 100%;
        padding-bottom: env(safe-area-inset-bottom);
        box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.1);
      }

      .chatbot-input-wrapper * {
        font-size: 16px !important;
      }
    }
  `;
  document.head.appendChild(style);


  const loadBranding = async (config, tenantInfo) => {
    if (!config.baseUrl || !config.apiKey) return tenantInfo; // Return original if no config
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
          // Return the NEW, merged object
          return {
            ...tenantInfo,
            ...data,
            branding: { ...tenantInfo.branding, ...data.branding }
          };
        }
      }
    } catch (error) {
      console.warn('Failed to fetch branding', error);
    }
    return tenantInfo; // Return original on error
  };

  const updateBrandingCSS = (tenantInfo) => {
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

  window.LyraChatbot = {
    init: async function(config) {
      console.log('🚀 COMPLETE MODIFIED CHATBOT VERSION');
      try {
        const container = document.getElementById('lyra-chatbot-widget');
        if (!container) {
          console.error('Container element not found');
          return;
        }

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

        // tenantInfo = await loadBranding(config, tenantInfo);
        if (config.branding) {
          tenantInfo.branding = { ...tenantInfo.branding, ...config.branding };
        } else {
          tenantInfo = await loadBranding(config, tenantInfo);
        }
        updateBrandingCSS(tenantInfo);
        

        let isOpen = false;
        let isTyping = false;
        let messages = [];
        let conversationCache = {};
        let inputValue = '';
        let userId = config.userId || ('user_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9));

        if (config.userEmail || config.userName) {
          try {
            await fetch(`${config.baseUrl}/chatbot/capture/manual-user-data`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'X-API-Key': config.apiKey
              },
              body: JSON.stringify({
                session_id: userId,
                email: config.userEmail || null,
                name: config.userName || null,
                source: 'business_provided'
              })
            });
            console.log('✅ Manual user data captured:', config.userEmail, config.userName);
          } catch (error) {
            console.warn('Failed to capture manual user data:', error);
          }
        }
        
        let showWelcome = true;
        let isFaqViewOpen = false; // <-- Add this line
        let faqData = [];
        let currentView = 'welcome';
        let conversations = [];
        let conversationsPromise = null; 
        let isCurrentChatActive = true;
        let userInfo = null;
        let renderedMessageCount = 0;
        let currentPage = 1;
        let totalPages = 1;
        let isLoadingMore = false;
        
        let videoPlayer = {
          active: false,
          minimized: false,
          expanded: false,
          url: '',
          x: window.innerWidth - 450,
          y: 100
        };

        

        const loadMessages = async () => {
          if (!config.enableServerStorage || !config.baseUrl || !config.apiKey) {
            try {
              const stored = localStorage.getItem(`chatbot_messages_${userId}`);
              if (stored) {
                const loadedMessages = JSON.parse(stored);
                if (loadedMessages.length > 0) {
                  messages = loadedMessages;
              
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
                
              }
            }
          } catch (error) {
            console.warn('Failed to load server messages:', error);
          }
        };

        const prefetchConversations = () => {
          if (!conversationsPromise) {
            conversationsPromise = fetch(`${config.baseUrl}/chatbot/sessions/list/${userId}`, {
              headers: { 'X-API-Key': config.apiKey }
            })
            .then(res => {
              if (!res.ok) throw new Error('Failed to prefetch');
              return res.json();
            })
            .then(data => {
              conversations = data.conversations || [];
              return conversations;
            })
            .catch(err => {
              console.error("Prefetch failed:", err);
              conversationsPromise = null; // Allow retry on failure
              return [];
            });
          }
          return conversationsPromise;
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



        const loadConversation = async (sessionId, isActive) => {
          currentView = 'chat';
          showWelcome = false;
        
          if (conversationCache[sessionId]) {
              messages = conversationCache[sessionId].messages;
              isCurrentChatActive = conversationCache[sessionId].is_active;
              render();
              return;
          }
        
          messages = null;
          render();
        
          try {
              const response = await fetch(`${config.baseUrl}/chatbot/messages/history/${sessionId}?page=1&page_size=30`, {
                  headers: { 'X-API-Key': config.apiKey }
              });
              if (!response.ok) throw new Error('Failed to fetch history');
        
              const data = await response.json();
              messages = data.messages || [];
              isCurrentChatActive = data.is_active;
              
              conversationCache[sessionId] = {
                  messages,
                  is_active: isCurrentChatActive
              };
              
              render();
          } catch (error) {
              console.error("Error loading conversation:", error);
              messages = [{ role: 'assistant', content: 'Could not load this conversation.' }];
              render();
          }
        };
        

        const findOrCreateActiveChat = async () => {
          const conversationList = await prefetchConversations(); 
          const activeConversation = conversationList.find(conv => conv.is_active);
        
          if (activeConversation) {
            // Active conversation exists, load it directly.
            loadConversation(activeConversation.session_id, true);
          } else {
            // No active chat found, create a new one.
            currentView = 'chat';
            showWelcome = false;
            messages = [];
            isCurrentChatActive = true;
            render();
            
            setTimeout(() => {
                const input = container.querySelector('.chatbot-input');
                if (input) input.focus();
            }, 100);
          }
        };




        const loadUserInfo = async () => {
          if (!config.baseUrl || !config.apiKey) return null;
          
          try {
            const response = await fetch(`${config.baseUrl}/chatbot/user-info/${userId}`, {
              headers: {
                'Content-Type': 'application/json',
                'X-API-Key': config.apiKey
              }
            });
            
            if (response.ok) {
              return await response.json();
            }
          } catch (error) {
            console.warn('Failed to load user info:', error);
          }
          return null;
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
          if (!inputValue.trim() || isTyping) return;
        
          const userMessage = { role: 'user', content: inputValue.trim() };
          messages.push(userMessage);
          
          inputValue = '';
          isTyping = true;
          showWelcome = false;
          render();
        
          try {
            const response = await fetch(`${config.baseUrl}/chatbot/chat/smart`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'X-API-Key': config.apiKey },
              body: JSON.stringify({
                message: userMessage.content,
                user_identifier: userId,
                max_context: 200
              })
            });
        
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        
            const reader = response.body?.getReader();
            if (!reader) throw new Error('Response body is not readable');
        
            const decoder = new TextDecoder();
            let currentChunk = '';
            let botReply = '';
        
            messages.push({ role: 'assistant', content: '' }); // Add an empty placeholder for the bot message
        
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
        
              currentChunk += decoder.decode(value, { stream: true });
              // In a streaming response, we find the last complete JSON object
              const lastNewline = currentChunk.lastIndexOf('\n');
              if (lastNewline !== -1) {
                const jsonLines = currentChunk.substring(0, lastNewline).split('\n');
                currentChunk = currentChunk.substring(lastNewline + 1);
        
                for (const line of jsonLines) {
                  if (line.trim() === '') continue;
                  try {
                    const data = JSON.parse(line);
                    if (data.type === 'main_response') {
                      botReply = data.content;
                      messages[messages.length - 1].content = botReply; // Update the placeholder
                      render();
                    }
                  } catch (e) {
                    console.warn("Error parsing stream chunk:", e);
                  }
                }
              }
            }
            isTyping = false;
            render();
            saveMessages(); // <<< IMPORTANT: Save messages AFTER the bot has replied.
        
          } catch (error) {
            console.error('Chat error:', error);
            messages.pop(); // Remove the empty bot message placeholder on error
            messages.push({ role: 'assistant', content: 'Sorry, I ran into an error. Please try again.' });
            isTyping = false;
            render();
            saveMessages();
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
            currentView = 'welcome';
            showWelcome = true;
            isFaqViewOpen = false;
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
        
          const closeBtn = document.createElement('button');
          closeBtn.className = 'chatbot-welcome-close-btn';
          closeBtn.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;
          closeBtn.addEventListener('click', () => {
            isOpen = false;
            render();
          });
        
          const content = document.createElement('div');
          content.className = 'chatbot-welcome-content';
        
          const logo = document.createElement('div');
          logo.className = 'chatbot-welcome-logo';
          logo.appendChild(createCompanyLogo(80));

          logo.style.cursor = 'pointer'; 
          logo.addEventListener('click', () => {
            currentView = 'game';
            showWelcome = false;
            render();
          });
        
          const heading = document.createElement('div');
          heading.className = 'chatbot-welcome-heading';
          heading.textContent = userInfo?.name ? `Hi ${userInfo.name.split(' ')[0]},` : 'Need support?';
        
          if (!userInfo?.name) {
            loadUserInfo().then(info => {
              if (info?.name) {
                userInfo = info;
                heading.textContent = `Hi ${info.name.split(' ')[0]},`;
              }
            });
          }
        
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
              <div class="chatbot-status-time">Updated Oct 13, 03:43 UTC</div>
            </div>
          `;
        
          const actionButtons = document.createElement('div');
          actionButtons.className = 'chatbot-action-buttons';
        
          const sendMessageBtn = document.createElement('button');
          sendMessageBtn.className = 'chatbot-action-btn';
          sendMessageBtn.innerHTML = `
            <strong>Send us a message</strong>
            <svg viewBox="0 0 512 512">
              <path fill="currentColor" d="m476.59 227.05l-.16-.07L49.35 49.84A23.56 23.56 0 0 0 27.14 52A24.65 24.65 0 0 0 16 72.59v113.29a24 24 0 0 0 19.52 23.57l232.93 43.07a4 4 0 0 1 0 7.86L35.53 303.45A24 24 0 0 0 16 327v113.31A23.57 23.57 0 0 0 26.59 460a23.94 23.94 0 0 0 13.22 4a24.55 24.55 0 0 0 9.52-1.93L476.4 285.94l.19-.09a32 32 0 0 0 0-58.8Z"/>
            </svg>
          `;
        



          sendMessageBtn.addEventListener('click', findOrCreateActiveChat);

          const searchBtn = document.createElement('button');
          searchBtn.className = 'chatbot-action-btn';
          searchBtn.innerHTML = `
            Search for help
            <svg viewBox="0 0 512 512">
              <path fill="currentColor" d="M325.8 0C223 0 139.6 83.4 139.6 186.2c0 33.5 9 64.8 24.4 92L0 442.2l23.3 46.5L69.8 512l164-164c27.1 15.5 58.5 24.4 92 24.4C428.6 372.4 512 289 512 186.2S428.6 0 325.8 0zm0 314.2c-70.7 0-128-57.3-128-128s57.3-128 128-128s128 57.3 128 128s-57.3 128-128 128z"/>
            </svg>
          `;
          searchBtn.addEventListener('click', () => {
            console.log('Search functionality - coming soon');
          });
        
          actionButtons.appendChild(sendMessageBtn);
          actionButtons.appendChild(searchBtn);
        
          const quickLinksCard = document.createElement('div');
          quickLinksCard.className = 'chatbot-quick-links-card';
        
          const quickLinks = document.createElement('div');
          quickLinks.className = 'chatbot-quick-links';
        
          const quickLinksTitle = document.createElement('div');
          quickLinksTitle.className = 'chatbot-quick-links-title';
          quickLinksTitle.textContent = 'Quick help';
        
          const links = [
            { text: 'How to Get Support', action: () => console.log('Link clicked: How to Get Support') },
            { text: 'Getting Started Guide', action: () => console.log('Link clicked: Getting Started Guide') },
            { 
              text: 'Common Questions', 
              action: async () => {
                try {
                  const response = await fetch(`${config.baseUrl}/knowledge-base/faqs`, {
                    headers: { 'X-API-Key': config.apiKey }
                  });
                  if (!response.ok) throw new Error('Failed to fetch FAQs');
                  faqData = await response.json();
                  isFaqViewOpen = true;
                  render();
                } catch (error) {
                  console.error('Error fetching FAQs:', error);
                  faqData = []; // Ensure it's empty on error
                  isFaqViewOpen = true; // Still open the view to show "No FAQs found"
                  render();
                }
              } 
            }
          ];
    
          const linksContainer = document.createElement('div');
          links.forEach(linkInfo => {
            const link = document.createElement('button');
            link.className = 'chatbot-quick-link';
            link.innerHTML = `
            <span>${linkInfo.text}</span>
            <svg width="18" height="18" viewBox="0 0 24 24">
              <g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2">
                <path d="m15 17l5-5l-5-5"/>
                <path d="M4 18v-2a4 4 0 0 1 4-4h12"/>
              </g>
            </svg>
          `;
            link.addEventListener('click', linkInfo.action);
            linksContainer.appendChild(link);
          });
        
          quickLinks.appendChild(quickLinksTitle);
          quickLinks.appendChild(linksContainer);
          quickLinksCard.appendChild(quickLinks);
        
          content.appendChild(logo);
          content.appendChild(heading);
          content.appendChild(subheading);
          content.appendChild(statusCard);
          content.appendChild(actionButtons);
          content.appendChild(quickLinksCard);
        
          welcomeView.appendChild(closeBtn);
          welcomeView.appendChild(content);
        
          return welcomeView;
        };



        const createFaqView = () => {
          const faqView = document.createElement('div');
          faqView.className = 'chatbot-faq-view';

          // Header with Back Button
          const header = document.createElement('div');
          header.className = 'chatbot-faq-header';
          
          const backBtn = document.createElement('button');
          backBtn.className = 'chatbot-faq-back-btn';
          backBtn.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>`;
          backBtn.addEventListener('click', () => {
            isFaqViewOpen = false;
            render();
          });

          header.innerHTML = `<h2>Common Questions</h2>`;
          header.prepend(backBtn);
          
          // List of FAQs
          const list = document.createElement('div');
          list.className = 'chatbot-faq-list';

          if (faqData.length > 0) {
            faqData.forEach(faq => {
              const item = document.createElement('div');
              item.className = 'chatbot-faq-item';
              
              const question = document.createElement('button');
              question.className = 'chatbot-faq-question';
              question.innerHTML = `
                <span>${faq.question}</span>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"></polyline></svg>
              `;

              const answer = document.createElement('div');
              answer.className = 'chatbot-faq-answer';
              answer.innerHTML = `<p>${faq.answer.replace(/\n/g, '<br>')}</p>`;

              question.addEventListener('click', () => {
                item.classList.toggle('active');
              });

              item.appendChild(question);
              item.appendChild(answer);
              list.appendChild(item);
            });
          } else {
            list.innerHTML = `<p style="text-align:center; padding: 20px; color: #6b7280;">No FAQs found.</p>`;
          }

          faqView.appendChild(header);
          faqView.appendChild(list);
          return faqView;
        };


        let towerGameInstance = null;
        
        const createGameView = () => {
          const gameView = document.createElement('div');
          gameView.className = 'chatbot-game-view';

          // Add the Close Button
          const closeBtn = document.createElement('button');
          closeBtn.className = 'chatbot-welcome-close-btn'; 
          closeBtn.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;
          closeBtn.addEventListener('click', () => {
            isOpen = false;
            render();
          });

          gameView.innerHTML = `
            <h2>Lyra Tower</h2>
            <div id="game-score" class="chatbot-game-score">0</div>
            <canvas id="lyra-tower-canvas" width="300" height="400"></canvas>
            <div id="game-instructions" class="chatbot-game-instructions">Click to start!</div>
          `;
          
          gameView.prepend(closeBtn); // Add the close button to the top

          setTimeout(() => {
            const canvas = gameView.querySelector('#lyra-tower-canvas');
            if (canvas) {
              towerGameInstance = LyraTowerGame(canvas);
              gameView.addEventListener('click', () => {
                if (towerGameInstance) towerGameInstance.onTap();
              });
            }
          }, 100);

          const quote = document.createElement('div');
          quote.className = 'chatbot-quote';
          quote.innerHTML = `<em>"The time is always right to do what is right"</em>`;
          gameView.appendChild(quote);

          return gameView;

          return gameView;
        };

        const LyraTowerGame = (canvas) => {
          const ctx = canvas.getContext('2d');
          let score, blocks, gameState, animationFrameId;

          const reset = () => {
            if (animationFrameId) cancelAnimationFrame(animationFrameId);
            
            score = 0;
            gameState = 'waiting';
            blocks = [{ x: 0, y: canvas.height - 20, width: canvas.width, height: 20 }];
            
            document.getElementById('game-score').textContent = '0';
            document.getElementById('game-instructions').textContent = 'Click to start!';
            
            loop();
          };

          const addBlock = (x, width) => {
            const newY = blocks[blocks.length - 1].y - 20;
            blocks.push({ x, y: newY, width, height: 20, speed: (2 + score / 5) * (Math.random() > 0.5 ? 1 : -1) });
          };

          const onTap = () => {
            if (gameState === 'waiting') {
              gameState = 'playing';
              document.getElementById('game-instructions').textContent = 'Click to drop the block!';
              addBlock(Math.random() * (canvas.width - 100), 100);
            } else if (gameState === 'playing') {
              const currentBlock = blocks[blocks.length - 1];
              const topBlock = blocks[blocks.length - 2];
              const overlap = Math.max(0, Math.min(currentBlock.x + currentBlock.width, topBlock.x + topBlock.width) - Math.max(currentBlock.x, topBlock.x));

              if (overlap > 0) {
                currentBlock.width = overlap;
                currentBlock.x = Math.max(currentBlock.x, topBlock.x);
                score++;
                document.getElementById('game-score').textContent = score;
                addBlock(currentBlock.x, currentBlock.width);
              } else {
                gameState = 'gameOver';
                document.getElementById('game-instructions').textContent = `Game Over! Score: ${score}. Click to play again.`;
              }
            } else if (gameState === 'gameOver') {
              reset();
            }
          };

          const loop = () => {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            if (gameState === 'playing') {
              const currentBlock = blocks[blocks.length - 1];
              currentBlock.x += currentBlock.speed;
              if (currentBlock.x < 0 || currentBlock.x + currentBlock.width > canvas.width) {
                currentBlock.speed *= -1;
              }
            }
            blocks.forEach((block, i) => {
              const hue = 190 + (i * 10);
              ctx.fillStyle = `hsl(${hue}, 80%, 60%)`;
              ctx.fillRect(block.x, block.y, block.width, block.height);
            });
            animationFrameId = requestAnimationFrame(loop);
          };

          reset();
          return { onTap };
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

          if (messages === null) {
            const loadingState = document.createElement('div');
            loadingState.style.cssText = 'text-align:center;padding:80px 20px;color:#6b7280;';
            loadingState.innerHTML = '<p>Loading chat...</p>';
            messagesContainer.appendChild(loadingState);
            return messagesContainer;
          }
          
          messagesContainer.appendChild(createBrandSection());
        
          messages.forEach((message, index) => {
            const messageEl = document.createElement('div');
            const isNewMessage = index >= renderedMessageCount;
            
            // Only add animation class for NEW messages
            messageEl.className = `chatbot-message ${message.role === 'assistant' ? 'assistant' : 'user'}`;
            
            if (isNewMessage) {
              messageEl.classList.add('chatbot-message-animate');
              messageEl.style.animationDelay = `${(index - renderedMessageCount) * 0.1}s`;
            } else {
              // Force no animation for existing messages
              messageEl.style.opacity = '1';
              messageEl.style.transform = 'translateY(0)';
            }
        
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

          renderedMessageCount = messages.length;
          return messagesContainer;
          
        };

        const createInputArea = () => {
          const inputArea = document.createElement('div');
          inputArea.className = `chatbot-input-area ${!isCurrentChatActive ? 'disabled' : ''}`;
        
          if (!isCurrentChatActive) {
            const closedMessage = document.createElement('div');
            closedMessage.className = 'closed-message';
            closedMessage.textContent = 'This conversation has ended.';
            inputArea.appendChild(closedMessage);
            return inputArea;
          }
        
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
            <svg width="20" height="20" viewBox="0 0 512 512" fill="currentColor" class="chatbot-send-icon">
              <path d="m476.59 227.05l-.16-.07L49.35 49.84A23.56 23.56 0 0 0 27.14 52A24.65 24.65 0 0 0 16 72.59v113.29a24 24 0 0 0 19.52 23.57l232.93 43.07a4 4 0 0 1 0 7.86L35.53 303.45A24 24 0 0 0 16 327v113.31A23.57 23.57 0 0 0 26.59 460a23.94 23.94 0 0 0 13.22 4a24.55 24.55 0 0 0 9.52-1.93L476.4 285.94l.19-.09a32 32 0 0 0 0-58.8Z"/>
            </svg>
          `;
          
          sendBtn.addEventListener('click', sendMessage);
        
          inputWrapper.appendChild(input);
          inputWrapper.appendChild(sendBtn);
          inputArea.appendChild(inputWrapper);
        
          return inputArea;
        };
        



        const createFooter = () => {
          const footer = document.createElement('div');
          footer.className = 'chatbot-footer';
        
          const homeBtn = document.createElement('button');
          homeBtn.className = `chatbot-footer-btn ${currentView === 'welcome' ? 'active' : ''}`;
          // Correct Solid Home Icon
          homeBtn.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5">
              <path fill="none" stroke="currentColor" d="m2 8l9.732-4.866a.6.6 0 0 1 .536 0L22 8m-2 3v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-8"/>
            </svg>
            <span>Home</span>
          `;
          homeBtn.addEventListener('click', () => {
            currentView = 'welcome';
            showWelcome = true;
            render();
          });
        
          const messagesBtn = document.createElement('button');
          messagesBtn.className = `chatbot-footer-btn ${currentView === 'messages' ? 'active' : ''}`;
          // Correct Solid Messages Icon
          messagesBtn.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 24 24" stroke-width="1.5" stroke-linecap="round">
              <g fill="none" stroke="currentColor">
                <path d="M22 12c0 4.714 0 7.071-1.465 8.535C19.072 22 16.714 22 12 22s-7.071 0-8.536-1.465C2 19.072 2 16.714 2 12s0-7.071 1.464-8.536C4.93 2 7.286 2 12 2"/>
                <path stroke-linejoin="round" d="m16.155 3.434l2.357 2.043c1.623 1.406 2.434 2.11 2.434 3.023c0 .913-.811 1.616-2.434 3.023l-2.357 2.043c-.714.618-1.07.927-1.363.794c-.292-.134-.292-.606-.292-1.55v-1.524c-3 0-6.25 1.393-7.5 3.714c0-7.429 4.444-9.286 7.5-9.286V4.19c0-.944 0-1.416.292-1.55c.293-.133.65.176 1.363.794Z"/>
              </g>
            </svg>
            <span>Messages</span>
          `;
        
          // Logic to fetch conversations when the messages tab is clicked
          messagesBtn.addEventListener('click', async () => {
            currentView = 'messages';
            showWelcome = false;
            render(); // Render immediately, data will populate when promise resolves
            
            // Use the pre-fetched data
            await prefetchConversations();
            render(); // Re-render once data is available
          });
        
          footer.appendChild(homeBtn);
          footer.appendChild(messagesBtn);
          return footer;
        };
        


        const createMessagesList = () => {
          const listContainer = document.createElement('div');
          listContainer.className = 'chatbot-messages-list';

          if (conversations === null) {
            const loadingState = document.createElement('div');
            loadingState.style.cssText = 'text-align:center;padding:40px 20px;color:#6b7280;';
            loadingState.innerHTML = '<p>Loading conversations...</p>';
            listContainer.appendChild(loadingState);
            return listContainer;
          }

          if (conversations.length === 0) {
            const emptyState = document.createElement('div');
            emptyState.style.cssText = 'text-align:center;padding:40px 20px;color:#6b7280;';
            emptyState.innerHTML = '<p>No past conversations found.</p>';
            listContainer.appendChild(emptyState);
            return listContainer;
          }

          conversations.forEach((conv) => {
            const item = document.createElement('div');
            item.className = `chatbot-conversation-item ${!conv.is_active ? 'closed' : ''}`;
            item.dataset.sessionId = conv.session_id;
            
            // ... (code for avatar, content, preview, time remains the same)
            const avatar = document.createElement('div');
            avatar.className = 'chatbot-conversation-avatar';
            avatar.textContent = tenantInfo.branding.logo_text || 'AI';

            const content = document.createElement('div');
            content.className = 'chatbot-conversation-content';
            
            const preview = document.createElement('div');
            preview.className = 'chatbot-conversation-preview';
            preview.textContent = conv.last_message_preview;
            
            const time = document.createElement('div');
            time.className = 'chatbot-conversation-time';
            const date = new Date(conv.updated_at);
            time.textContent = date.toLocaleString('en-US', { month: 'short', day: 'numeric' });

            content.appendChild(preview);
            content.appendChild(time);
            item.appendChild(avatar);
            item.appendChild(content);

            
            item.addEventListener('click', () => loadConversation(conv.session_id));

            listContainer.appendChild(item);
          });

          return listContainer;
        };



        const createMessagesListView = () => {
          const view = document.createElement('div');
          view.className = 'chatbot-messages-list-view';

          const closeBtn = document.createElement('button');
          closeBtn.className = 'chatbot-welcome-close-btn'; 
          closeBtn.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;
          closeBtn.addEventListener('click', () => {
            isOpen = false;
            render();
          });
          view.appendChild(closeBtn);

          const header = document.createElement('div');
          header.className = 'chatbot-messages-list-header';
          header.innerHTML = `<h2>Messages</h2>`;
          
          
          const messagesListContainer = createMessagesList();

          const newChatBtn = document.createElement('button');
          newChatBtn.className = 'chatbot-new-chat-btn';
          newChatBtn.innerHTML = `
            <svg width="18" height="18" viewBox="0 0 512 512" fill="currentColor">
              <path d="m476.59 227.05l-.16-.07L49.35 49.84A23.56 23.56 0 0 0 27.14 52A24.65 24.65 0 0 0 16 72.59v113.29a24 24 0 0 0 19.52 23.57l232.93 43.07a4 4 0 0 1 0 7.86L35.53 303.45A24 24 0 0 0 16 327v113.31A23.57 23.57 0 0 0 26.59 460a23.94 23.94 0 0 0 13.22 4a24.55 24.55 0 0 0 9.52-1.93L476.4 285.94l.19-.09a32 32 0 0 0 0-58.8Z"/>
            </svg>
            <span>Chat with us</span>
          `;

          
          newChatBtn.addEventListener('click', findOrCreateActiveChat);

          messagesListContainer.appendChild(newChatBtn);
          view.appendChild(header);
          view.appendChild(messagesListContainer);

          return view;
        };
        

        const createWidget = () => {
          const widget = document.createElement('div');
          widget.className = `chatbot-widget ${getPositionClass()} ${isOpen ? 'chatbot-widget-open' : ''}`;
          widget.style.display = isOpen ? 'flex' : 'none';
        
          const body = document.createElement('div');
          body.className = 'chatbot-body';
          
          if (currentView === 'game') {
            body.classList.add('is-game-view');
            body.style.padding = '0';
            body.appendChild(createGameView());
            widget.appendChild(body); // Note: No footer is added here
          } else if (showWelcome) {
            body.style.padding = '0';
            if (isFaqViewOpen) {
              body.appendChild(createFaqView());
            } else {
              body.appendChild(createWelcomeView());
            }
            widget.appendChild(body);
            widget.appendChild(createFooter());
          } else if (currentView === 'messages') {
            body.style.padding = '0';
            body.appendChild(createMessagesListView());
            widget.appendChild(body);
            widget.appendChild(createFooter());
          } else {
            currentView = 'chat';
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
              
              if (chatBody) {
                // Scroll to bottom only if it's the first page load
                if (currentPage === 1) {
                  chatBody.scrollTop = chatBody.scrollHeight;
                }

                // Add scroll listener for loading more messages
                chatBody.addEventListener('scroll', async () => {
                  if (chatBody.scrollTop === 0 && !isLoadingMore && currentPage < totalPages) {
                    isLoadingMore = true;
                    const nextPage = currentPage + 1;
                    const currentSessionId = messages[0]?.sessionId || document.querySelector('.chatbot-conversation-item.active')?.dataset.sessionId; // A way to get current session

                    // Keep track of scroll height to prevent jarring jumps
                    const prevScrollHeight = chatBody.scrollHeight;

                    try {
                      const response = await fetch(`${config.baseUrl}/chatbot/messages/history/${currentSessionId}?page=${nextPage}&page_size=30`, {
                         headers: { 'X-API-Key': config.apiKey }
                      });
                      const data = await response.json();
                      
                      messages = [...data.messages, ...messages]; // Prepend older messages
                      currentPage = data.pagination.page;
                      render();

                      // Restore scroll position after re-render
                      setTimeout(() => {
                        const newScrollHeight = chatBody.scrollHeight;
                        chatBody.scrollTop = newScrollHeight - prevScrollHeight;
                        isLoadingMore = false;
                      }, 50);

                    } catch (error) {
                      console.error("Failed to load more messages", error);
                      isLoadingMore = false;
                    }
                  }
                });
              }
            }, 100);
          }
        };
        prefetchConversations();

      

        render();

      } catch (error) {
        console.error('Chatbot initialization failed:', error);
      }
    }
  };
})();