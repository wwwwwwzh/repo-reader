
function setupQAPanel() {
  const qaPanel = document.getElementById('qa-panel');
  const qaToggle = document.getElementById('qa-toggle');
  const qaInput = document.getElementById('qa-input');
  const qaSubmit = document.getElementById('qa-submit');
  const qaMessages = document.getElementById('qa-messages');
  const chatHeader = document.querySelector('.chat-header');

  // Initial state - expanded
  qaPanel.classList.remove('collapsed');

  // Load previous messages from localStorage
  loadQAMessages();

  // Toggle QA panel
  qaToggle.addEventListener('click', () => {
    qaPanel.classList.toggle('collapsed');

    // Update toggle button text
    qaToggle.textContent = qaPanel.classList.contains('collapsed') ? '□' : '_';

    // Scroll to bottom of messages when expanding
    if (!qaPanel.classList.contains('collapsed')) {
      setTimeout(() => qaInput.focus(), 300);
      scrollToBottomOfMessages();
    }
  });

  // Handle submission of questions
  qaSubmit.addEventListener('click', () => {
    submitQuestion();
  });

  // Submit on Enter key
  qaInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
      submitQuestion();
    }
  });

  // Make the chat panel draggable
  makeDraggable(qaPanel, chatHeader);
}

function submitQuestion() {
  const qaInput = document.getElementById('qa-input');
  const question = qaInput.value.trim();

  // Validate input
  if (!question) return;

  // Clear input
  qaInput.value = '';

  // Add user message
  addMessage('user', question);

  // Add loading message
  const loadingMessageId = addLoadingMessage();

  // Get repository hash
  const repoHash = document.querySelector('.repo-info').dataset.repoHash;

  // Disable submit button
  document.getElementById('qa-submit').disabled = true;

  // Query the API
  fetch(`/code/api/qa/${repoHash}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      query: question,
      k: 5, // Number of functions to retrieve
    }),
  })
    .then((response) => response.json())
    .then((data) => {
      // Remove loading message
      removeLoadingMessage(loadingMessageId);

      // Add system response
      if (data.error) {
        addMessage('system', `Error: ${data.error}`);
      } else {
        // Add the response with formatting for code and functions
        addMessage('system', formatQAResponse(data.answer, data.functions));
      }
    })
    .catch((error) => {
      // Remove loading message
      removeLoadingMessage(loadingMessageId);

      // Add error message
      addMessage('system', `Failed to get a response: ${error.message}`);
    })
    .finally(() => {
      // Re-enable submit button
      document.getElementById('qa-submit').disabled = false;
    });
}

function addMessage(type, content) {
  const qaMessages = document.getElementById('qa-messages');
  const messageElement = document.createElement('div');
  messageElement.className = `chat-message ${type}`;

  const messageContent = document.createElement('div');
  messageContent.className = 'message-content';
  messageContent.innerHTML = formatMessageContent(content);

  const messageTime = document.createElement('div');
  messageTime.className = 'message-time';
  messageTime.textContent = getFormattedTime();

  messageElement.appendChild(messageContent);
  messageElement.appendChild(messageTime);

  // Add to the end of the messages
  qaMessages.appendChild(messageElement);

  // Scroll to the new message
  scrollToBottomOfMessages();

  // Save messages to localStorage
  saveQAMessages();

  // Add click handlers for function links
  addFunctionLinkHandlers();
}

function addLoadingMessage() {
  const qaMessages = document.getElementById('qa-messages');
  const messageId = 'loading-message-' + Date.now();

  const messageElement = document.createElement('div');
  messageElement.className = 'chat-message system loading';
  messageElement.id = messageId;

  const messageContent = document.createElement('div');
  messageContent.className = 'message-content';
  messageContent.innerHTML = 'Thinking<span class="loading-dots"></span>';

  messageElement.appendChild(messageContent);

  // Add to the end of the messages
  qaMessages.appendChild(messageElement);

  // Scroll to the new message
  scrollToBottomOfMessages();

  return messageId;
}

function removeLoadingMessage(messageId) {
  const loadingMessage = document.getElementById(messageId);
  if (loadingMessage) {
    loadingMessage.remove();
  }
}

function formatMessageContent(content) {
  // Format code blocks ```code```
  let formatted = content.replace(
    /```([\s\S]*?)```/g,
    '<pre><code>$1</code></pre>'
  );

  // Format inline code `code`
  formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Replace newlines with <br>
  formatted = formatted.replace(/\n/g, '<br>');

  return formatted;
}

function formatQAResponse(answer, functions) {
  let formatted = answer;

  // Add clickable links for function references
  if (functions && functions.length > 0) {
    functions.forEach((func, index) => {
      // Create regex to find references to this function
      const funcName = func.name;
      const fullName = func.full_name;

      // Replace function references with clickable links
      const funcRegex = new RegExp(
        `(${escapeRegExp(funcName)}|${escapeRegExp(fullName)})`,
        'g'
      );
      formatted = formatted.replace(
        funcRegex,
        `<a class="function-link" data-function-id="${func.id}">$1</a>`
      );
    });
  }

  return formatted;
}

function getFormattedTime() {
  const now = new Date();
  return now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function saveQAMessages() {
  const qaMessages = document.getElementById('qa-messages');
  const repoHash = document.querySelector('.repo-info').dataset.repoHash;

  // Save only the most recent 50 messages
  const messages = [];
  const messageElements = qaMessages.querySelectorAll(
    '.chat-message:not(.loading)'
  );

  // Get messages in order
  for (let i = 0; i < Math.min(messageElements.length, 50); i++) {
    const element = messageElements[i];
    const type = element.classList.contains('user') ? 'user' : 'system';
    const content = element.querySelector('.message-content').innerHTML;
    const time = element.querySelector('.message-time').textContent;

    messages.push({ type, content, time });
  }

  // Save to localStorage
  try {
    localStorage.setItem(`qa-messages-${repoHash}`, JSON.stringify(messages));
  } catch (e) {
    console.warn('Failed to save messages to localStorage', e);
  }
}

function loadQAMessages() {
  const qaMessages = document.getElementById('qa-messages');
  const repoHash = document.querySelector('.repo-info').dataset.repoHash;

  try {
    const savedMessages = localStorage.getItem(`qa-messages-${repoHash}`);
    if (savedMessages) {
      const messages = JSON.parse(savedMessages);

      // Clear existing messages
      qaMessages.innerHTML = '';

      // Add messages in order
      for (let i = 0; i < messages.length; i++) {
        const message = messages[i];

        const messageElement = document.createElement('div');
        messageElement.className = `chat-message ${message.type}`;

        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        messageContent.innerHTML = message.content;

        const messageTime = document.createElement('div');
        messageTime.className = 'message-time';
        messageTime.textContent = message.time;

        messageElement.appendChild(messageContent);
        messageElement.appendChild(messageTime);

        qaMessages.appendChild(messageElement);
      }

      // Add function link handlers
      addFunctionLinkHandlers();

      // Scroll to bottom
      scrollToBottomOfMessages();
    }
  } catch (e) {
    console.warn('Failed to load messages from localStorage', e);
  }
}

function scrollToBottomOfMessages() {
  const qaMessages = document.getElementById('qa-messages');
  qaMessages.scrollTop = qaMessages.scrollHeight;
}

function makeDraggable(element, handle) {
  let pos1 = 0,
    pos2 = 0,
    pos3 = 0,
    pos4 = 0;

  if (handle) {
    // If handle is specified, make only the handle element draggable
    handle.onmousedown = dragMouseDown;
  } else {
    // Otherwise, make the whole element draggable
    element.onmousedown = dragMouseDown;
  }

  function dragMouseDown(e) {
    e = e || window.event;
    e.preventDefault();
    // Get the mouse cursor position at startup
    pos3 = e.clientX;
    pos4 = e.clientY;
    document.onmouseup = closeDragElement;
    // Call a function whenever the cursor moves
    document.onmousemove = elementDrag;

    // Add dragging class
    element.classList.add('dragging');
  }

  function elementDrag(e) {
    e = e || window.event;
    e.preventDefault();
    // Calculate the new cursor position
    pos1 = pos3 - e.clientX;
    pos2 = pos4 - e.clientY;
    pos3 = e.clientX;
    pos4 = e.clientY;
    // Set the element's new position
    element.style.top = element.offsetTop - pos2 + 'px';
    element.style.left = element.offsetLeft - pos1 + 'px';
    element.style.bottom = 'auto'; // Override the bottom position
    element.style.right = 'auto'; // Override the right position
  }

  function closeDragElement() {
    // Stop moving when mouse button is released
    document.onmouseup = null;
    document.onmousemove = null;

    // Remove dragging class
    element.classList.remove('dragging');

    // Ensure the panel stays visible
    const rect = element.getBoundingClientRect();

    if (rect.top < 0) {
      element.style.top = '10px';
    }

    if (rect.left < 0) {
      element.style.left = '10px';
    }

    if (rect.right > window.innerWidth) {
      element.style.left = window.innerWidth - rect.width - 10 + 'px';
    }

    if (rect.bottom > window.innerHeight) {
      element.style.top = window.innerHeight - rect.height - 10 + 'px';
    }
  }
}
