// @ts-nocheck
$(document).ready(function () {
  const chatButton = document.querySelector('#chat-button');
  const chatHeader = document.querySelector('.chat-header');
  const chatMessages = document.querySelector('.chat-messages');
  const chatInputForm = document.querySelector('#chat-input-form');
  const chatInput = document.querySelector('.chat-input');
  const clearChatBtn = document.querySelector('.clear-chat-button');

  // Load messages from local storage or initialize empty array
  const messages = JSON.parse(localStorage.getItem('messages')) || [];
  let sessionId = getRandomSessionId();

  localStorage.setItem('sessionId', JSON.stringify(sessionId));

  // Create chat message element using DOM methods instead of innerHTML
  const createChatMessageElement = (message) => {
    // Get the message template
    const template = document.getElementById('chat-message-template');
    const messageElement = document.importNode(template.content.firstElementChild, true);
    
    // Set message type class
    messageElement.classList.add(message.sender === 'user' ? 'blue-bg' : 'gray-bg');
    
    // Set sender text
    const senderElement = messageElement.querySelector('.message-sender');
    senderElement.textContent = message.sender === 'user' ? 'You' : 'AI Assistant';
    
    // Set message text with safe handling of newlines and links
    const textElement = messageElement.querySelector('.message-text');
    setFormattedText(textElement, message.text);
    
    // Set timestamp
    const timestampElement = messageElement.querySelector('.message-timestamp');
    timestampElement.textContent = message.timestamp;
    
    return messageElement;
  };

  // Helper function to safely set formatted text content
  function setFormattedText(element, text) {
    // Clear any existing content
    while (element.firstChild) {
      element.removeChild(element.firstChild);
    }
    
    // Split text by newlines
    const lines = text.split('\n');
    
    // Process each line
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      
      // Process URLs in the line
      const segments = line.split(/(https?:\/\/[^\s]+)/g);
      
      for (const segment of segments) {
        if (segment.match(/^https?:\/\//)) {
          // This is a URL, create a link
          const link = document.createElement('a');
          link.href = segment;
          link.textContent = segment;
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
          element.appendChild(link);
        } else if (segment) {
          // This is regular text
          element.appendChild(document.createTextNode(segment));
        }
      }
      
      // Add line break if not the last line
      if (i < lines.length - 1) {
        element.appendChild(document.createElement('br'));
      }
    }
  }

  // Generate random session ID
  function getRandomSessionId(min = 1000000000, max = 9999999999) {
    return Math.floor(Math.random() * (max - min) + min);
  }

  // Load saved messages when page loads
  window.onload = () => {
    messages.forEach((message) => {
      const messageElement = createChatMessageElement(message);
      chatMessages.appendChild(messageElement);
    });
    
    // Scroll to bottom of messages
    chatMessages.scrollTop = chatMessages.scrollHeight;
  };

  let messageSender = 'user';

  // Function to update message sender and UI state
  const updateMessageSender = (name) => {
    messageSender = name;
    
    if (name === 'ai') {
      // Update header without innerHTML
      while (chatHeader.firstChild) {
        chatHeader.removeChild(chatHeader.firstChild);
      }
      
      const icon = document.createElement('i');
      icon.className = 'fas fa-robot';
      chatHeader.appendChild(icon);
      chatHeader.appendChild(document.createTextNode(' AI Assistant is typing...'));
      
      // Disable input during AI response
      chatInput.disabled = true;
      chatButton.disabled = true;
    } else {
      chatHeader.textContent = 'Ask questions about your documents';
      
      // Enable input when it's user's turn
      chatInput.disabled = false;
      chatButton.disabled = false;
      chatInput.focus(); // Auto-focus the input field
    }
  };

  // Function to create loading message element
  function createLoadingMessage(id) {
    const template = document.getElementById('loading-message-template');
    const loadingElement = document.importNode(template.content.firstElementChild, true);
    loadingElement.id = id;
    return loadingElement;
  }

  // Function to handle AI chat
  function chatWithAI(message) {
    let apiendpointchat = $("#apiendpointchat").text();
    let chunksize = $("#chunk-size").val();
    
    // Show loading indicator in chat
    const loadingMsgId = 'loading-' + Date.now();
    const loadingElement = createLoadingMessage(loadingMsgId);
    chatMessages.appendChild(loadingElement);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    post({ 
      "inputTranscript": message,
      "sessionId": JSON.parse(localStorage.getItem('sessionId')),
      "config": chunksize
    }, apiendpointchat)
    .then(function (data) {
      // Remove loading indicator
      const loadingMsg = document.getElementById(loadingMsgId);
      if (loadingMsg) {
        loadingMsg.remove();
      }
      
      let timestamp = new Date().toLocaleString('en-US', { hour: 'numeric', minute: 'numeric', hour12: true });
      let aiMessage = {
        sender: 'ai',
        text: data,
        timestamp,
      };
      
      // Save message to storage
      messages.push(aiMessage);
      localStorage.setItem('messages', JSON.stringify(messages));
      
      // Create and append message element
      const messageElement = createChatMessageElement(aiMessage);
      chatMessages.appendChild(messageElement);
      chatMessages.scrollTop = chatMessages.scrollHeight;
      
      // Return to user mode
      updateMessageSender('user');
      
      // Show success notification
      showNotification('<i class="fas fa-check"></i> Response received', 'success');
    })
    .catch(function (err) {
      // Remove loading indicator
      const loadingMsg = document.getElementById(loadingMsgId);
      if (loadingMsg) {
        loadingMsg.remove();
      }
      
      console.error(err);
      
      // Add error message to chat
      let timestamp = new Date().toLocaleString('en-US', { hour: 'numeric', minute: 'numeric', hour12: true });
      let errorMessage = {
        sender: 'ai',
        text: "Sorry, there was an error processing your request. Please try again.",
        timestamp,
      };
      
      // Create and append error message
      const errorElement = createChatMessageElement(errorMessage);
      chatMessages.appendChild(errorElement);
      chatMessages.scrollTop = chatMessages.scrollHeight;
      
      // Return to user mode
      updateMessageSender('user');
      
      // Show error notification
      showNotification('<i class="fas fa-exclamation-triangle"></i> Error processing request', 'error');
    });
  }

  // Send message handler
  const sendMessage = (e) => {
    e.preventDefault();
    
    // Don't send empty messages
    if (!chatInput.value.trim()) return;
    
    const timestamp = new Date().toLocaleString('en-US', { hour: 'numeric', minute: 'numeric', hour12: true });
    const message = {
      sender: messageSender,
      text: chatInput.value,
      timestamp,
    };
    
    // Save user message
    messages.push(message);
    localStorage.setItem('messages', JSON.stringify(messages));
    
    // Create and append message element
    const messageElement = createChatMessageElement(message);
    chatMessages.appendChild(messageElement);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    // Clear input field
    const userMessage = chatInput.value;
    chatInputForm.reset();
    
    // Switch to AI mode and send the message
    updateMessageSender('ai');
    chatWithAI(userMessage);
  };

  // Clear chat handler
  const clearChat = () => {
    // Clear local storage
    localStorage.removeItem('messages');
    
    // Generate new session ID
    let sessionId = getRandomSessionId();
    localStorage.setItem('sessionId', JSON.stringify(sessionId));
    
    // Clear UI - safely remove all child elements
    while (chatMessages.firstChild) {
      chatMessages.removeChild(chatMessages.firstChild);
    }
    
    updateMessageSender('user');
    
    // Show notification
    showNotification('<i class="fas fa-trash"></i> Chat cleared', 'info');
  };

  // Event listeners
  chatInputForm.addEventListener('submit', sendMessage);
  clearChatBtn.addEventListener('click', clearChat);
});
