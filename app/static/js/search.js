
// Global variables specific to search
let pinnedFunctions = [];
let searchCache = {};
let lastSearchTime = 0;
const MIN_SEARCH_INTERVAL = 2000;

// Set up function search
function setupFunctionSearch() {
  const searchInput = document.getElementById('function-search');
  const searchButton = document.getElementById('search-button');
  const searchResults = document.getElementById('search-results');
  const searchContainer = document.querySelector('.search-container');

  // LLM API KEY SETTING
  const apiKeyLink = document.createElement('a');
  apiKeyLink.href = '#';
  apiKeyLink.textContent = 'Set Groq API Key';
  apiKeyLink.style.fontSize = '0.8em';
  apiKeyLink.style.marginTop = '5px';
  apiKeyLink.style.display = 'block';
  apiKeyLink.addEventListener('click', (e) => {
    e.preventDefault();
    const currentKey = localStorage.getItem('groqApiKey') || '';
    const newKey = prompt(
      'Enter your Groq API key for better search results:',
      currentKey
    );
    if (newKey !== null) {
      localStorage.setItem('groqApiKey', newKey);
      alert(
        'API key saved! ' +
          (newKey
            ? 'Semantic search is now enabled.'
            : 'Semantic search is now disabled.')
      );
    }
  });
  searchContainer.appendChild(apiKeyLink);

  // SEARCH
  // Function to perform the search
  async function performSearch() {
    const searchTerm = searchInput.value.trim();

    if (searchTerm.length < 2) {
      searchResults.style.display = 'none';
      return;
    }

    try {
      // Show loading state
      searchResults.innerHTML = '<div class="loading"></div>';
      searchResults.style.display = 'block';

      // Fetch matching functions
      const functions = await searchFunctions(repoHash, searchTerm);
      addToSearchHistory(searchTerm);

      // Display results
      if (functions.length === 0) {
        searchResults.innerHTML =
          '<div class="search-result-item">No functions found</div>';
      } else {
        searchResults.innerHTML = functions
          .map((func) => {
            return `
                          <div class="search-result-item" data-id="${func.id}" data-full-name="${func.full_name}" data-name="${func.name}">
                              <div class="function-name">${func.name}</div>
                              <div class="function-path">${func.full_name}</div>
                          </div>
                      `;
          })
          .join('');

        // Add click event listeners to results
        document.querySelectorAll('.search-result-item').forEach((item) => {
          item.addEventListener('click', () => {
            const functionId = item.dataset.id;
            const functionName = item.dataset.name;
            const fullName = item.dataset.fullName;

            // Add to custom functions list
            addToCustomFunctionsList(functionId, functionName, fullName);

            // Clear search input and results
            searchInput.value = '';
            searchResults.style.display = 'none';

            // Load function details
            loadFunctionDetails(repoHash, functionId);
          });
        });
      }
    } catch (error) {
      console.error('Error searching functions:', error);
      searchResults.innerHTML =
        '<div class="search-result-item">Error searching functions</div>';
    }
  }

  // Click search button
  searchButton.addEventListener('click', performSearch);
  // Also search on Enter key press
  searchInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
      performSearch();
    }
  });
  // Hide search results when clicking outside
  document.addEventListener('click', (e) => {
    if (
      !searchInput.contains(e.target) &&
      !searchButton.contains(e.target) &&
      !searchResults.contains(e.target)
    ) {
      searchResults.style.display = 'none';
    }
  });

  // MANAGE SEARCH HISTORY
  const historyKey = `searchHistory_${repoHash}`;
  let searchHistory = JSON.parse(localStorage.getItem(historyKey) || '[]');

  // Create search history dropdown
  const historyContainer = document.createElement('div');
  historyContainer.className = 'search-history-container';
  historyContainer.style.marginTop = '8px';

  // Function to update the history display
  function updateHistoryDisplay() {
    if (searchHistory.length === 0) {
      historyContainer.style.display = 'none';
      return;
    }

    historyContainer.style.display = 'block';
    historyContainer.innerHTML = `
              <div class="search-history-title">Recent Searches:</div>
              <div class="search-history-items"></div>
          `;

    const historyItems = historyContainer.querySelector(
      '.search-history-items'
    );

    searchHistory.forEach((term, index) => {
      const historyItem = document.createElement('div');
      historyItem.className = 'search-history-item';
      historyItem.innerHTML = `
                  <span class="history-term">${term}</span>
                  <button class="history-delete" data-index="${index}">&times;</button>
              `;

      // Click on history item to re-run search
      historyItem
        .querySelector('.history-term')
        .addEventListener('click', () => {
          searchInput.value = term;
          performSearch();
        });

      // Delete history item
      historyItem
        .querySelector('.history-delete')
        .addEventListener('click', (e) => {
          e.stopPropagation();
          const itemIndex = parseInt(e.target.dataset.index);
          searchHistory.splice(itemIndex, 1);
          localStorage.setItem(historyKey, JSON.stringify(searchHistory));
          updateHistoryDisplay();
        });

      historyItems.appendChild(historyItem);
    });
  }

  // Function to add search term to history
  function addToSearchHistory(term) {
    if (term.length < 2) return;

    // Remove if already exists
    const index = searchHistory.indexOf(term);
    if (index !== -1) {
      searchHistory.splice(index, 1);
    }

    // Add to beginning
    searchHistory.unshift(term);

    // Limit to 5 items
    if (searchHistory.length > 5) {
      searchHistory.pop();
    }

    // Save to localStorage
    localStorage.setItem(historyKey, JSON.stringify(searchHistory));

    // Update display
    updateHistoryDisplay();
  }

  // Add history container to search container
  searchContainer.appendChild(historyContainer);

  // Initialize history display
  updateHistoryDisplay();
}

// Search functions with semantic capability
async function searchFunctions(repoHash, searchTerm) {
  try {
    // Check cache first
    const cacheKey = `${repoHash}:${searchTerm}`;
    if (searchCache[cacheKey]) {
      console.log('Using cached search results');
      return searchCache[cacheKey];
    }

    // Check if we have a Groq API key in local storage
    const groqApiKey = localStorage.getItem('groqApiKey');

    if (groqApiKey) {
      // Try semantic search first
      const { prompt, functions, shortIdMap } =
        await getAllFunctionsForSemanticSearch(repoHash);

      // Add check for prompt size here
      const isPromptTooLarge = prompt && prompt.length > 50000;

      if (prompt && functions.length > 0) {
        // If prompt is too large, use a simplified prompt with just function names
        let shortFunctionIds;

        if (isPromptTooLarge) {
          console.log(
            'Prompt exceeds size limit, using simplified version with just function names'
          );

          // Create a simplified prompt with just function names and IDs
          let simplifiedPrompt =
            'I have the following functions in my codebase. Each line contains: id | function_name\n\n';

          // Build the prompt using just the function names (not full paths or descriptions)
          Object.entries(shortIdMap).forEach(([shortId, fullId]) => {
            const func = functions.find((f) => f.id === fullId);
            if (func) {
              simplifiedPrompt += `${shortId} | ${func.full_name}\n`;
            }
          });

          // Use the simplified prompt instead
          shortFunctionIds = await queryGroqForFunctions(
            simplifiedPrompt,
            searchTerm,
            groqApiKey
          );
        } else {
          // Use the original prompt for smaller repositories
          shortFunctionIds = await queryGroqForFunctions(
            prompt,
            searchTerm,
            groqApiKey
          );
        }

        if (shortFunctionIds && shortFunctionIds.length > 0) {
          // Convert short IDs back to full IDs
          const fullFunctionIds = shortFunctionIds
            .filter((shortId) => shortIdMap[shortId])
            .map((shortId) => shortIdMap[shortId]);

          // Filter the functions based on the returned full IDs
          const relevantFunctions = functions.filter((func) =>
            fullFunctionIds.includes(func.id)
          );

          if (relevantFunctions.length > 0) {
            // Cache the results before returning
            searchCache[cacheKey] = relevantFunctions;
            return relevantFunctions;
          }
        }
      }
    }

    // Rest of the function remains unchanged...
    function simpleSearch(allFunctions, searchTerm) {
      return allFunctions.filter(
        (func) =>
          func.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
          func.full_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
          (func.short_description &&
            func.short_description
              .toLowerCase()
              .includes(searchTerm.toLowerCase()))
      );
    }

    // Fallback to regular search (same as before)
    const response = await fetch(`/code/api/functions/${repoHash}/all`);

    if (!response.ok) {
      console.error(
        `Error fetching functions from /code/api/functions/${repoHash}/all`
      );
      return [];
    }

    // If the API endpoint exists, use its response
    const allFunctions = await response.json();
    relevantFunctions = simpleSearch(allFunctions, searchTerm);
    searchCache[cacheKey] = relevantFunctions;
    return relevantFunctions;
  } catch (error) {
    console.error('Error fetching functions:', error);
    return [];
  }
}
// Get all functions and prepare for semantic search
async function getAllFunctionsForSemanticSearch(repoHash) {
  try {
    // Fetch all functions
    const response = await fetch(`/code/api/functions/${repoHash}/all`);
    if (!response.ok) {
      throw new Error('Failed to fetch functions');
    }

    const allFunctions = await response.json();

    // Map of short IDs to full IDs
    const shortIdMap = {};

    // Format the functions as a prompt for Groq
    let prompt =
      'I have the following functions in my codebase. Each line contains: id | function_name | full_name | short_description\n\n';

    allFunctions.forEach((func) => {
      // Extract short ID from the full ID
      const fullId = func.id;
      const shortId = fullId.split(':').pop();

      // Store mapping
      shortIdMap[shortId] = fullId;

      prompt += `${shortId} | ${func.name} | ${func.full_name} | ${
        func.short_description || 'No description'
      }\n`;
    });

    return {
      prompt,
      functions: allFunctions,
      shortIdMap,
    };
  } catch (error) {
    console.error('Error fetching functions for semantic search:', error);
    return { prompt: '', functions: [], shortIdMap: {} };
  }
}

// Query Groq for semantic search
async function queryGroqForFunctions(prompt, query, apiKey) {
  const currentTime = Date.now();
  if (currentTime - lastSearchTime < MIN_SEARCH_INTERVAL) {
    console.log('Rate limiting Groq API call');
    throw new Error('Search rate limit exceeded');
  }
  lastSearchTime = currentTime;
  try {
    const finalPrompt = `${prompt}\n\nPlease find the top 5 most relevant functions for this query: "${query}"\nReturn only the function ids in a comma-separated list with no other text.`;

    const response = await fetch(
      'https://api.groq.com/openai/v1/chat/completions',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify({
          model: 'llama-3.1-8b-instant',
          messages: [
            {
              role: 'system',
              content:
                'You are a helpful assistant that finds relevant functions in a codebase.',
            },
            { role: 'user', content: finalPrompt },
          ],
          temperature: 0.2,
          max_tokens: 100,
        }),
      }
    );

    if (!response.ok) {
      throw new Error('Failed to query Groq API');
    }

    const data = await response.json();
    const content = data.choices[0].message.content;
    console.log(content);

    // Extract short function IDs - expecting a comma-separated list
    const shortFunctionIds = content.split(',').map((id) => {
      const trimmedId = id.trim();
      // Check if the ID is just a number, if so prefix it with func_
      return /^\d+$/.test(trimmedId) ? `func_${trimmedId}` : trimmedId;
    });

    console.log(shortFunctionIds);
    return shortFunctionIds;
  } catch (error) {
    console.error('Error querying Groq API:', error);
    return [];
  }
}

// Add function to custom functions list
function addToCustomFunctionsList(functionId, functionName, fullName) {
  const customFunctionsList = document.getElementById('custom-functions-list');

  // Remove empty state message if present
  const emptyState = customFunctionsList.querySelector('.empty-state');
  if (emptyState) {
    emptyState.remove();
  }

  // Check if function already exists in the list
  const existingFunction = document.querySelector(
    `.custom-function-item[data-id="${functionId}"]`
  );
  if (existingFunction) {
    // If exists, highlight it briefly
    existingFunction.style.backgroundColor = '#e0f7fa';
    setTimeout(() => {
      existingFunction.style.backgroundColor = '';
    }, 1000);
    return;
  }

  // Create function node container
  const functionNode = document.createElement('div');
  functionNode.className = 'node';
  functionNode.dataset.id = functionId;
  functionNode.dataset.type = 'function';

  // Create custom function item
  const customFunctionItem = document.createElement('div');
  customFunctionItem.className = 'custom-function-item';
  customFunctionItem.dataset.id = functionId;

  // Create pin button
  const isPinned = pinnedFunctions.includes(functionId);
  const pinButton = document.createElement('span');
  pinButton.className = `pin-button ${isPinned ? 'pinned' : ''}`;
  pinButton.title = isPinned ? 'Unpin function' : 'Pin function';

  // Create remove button
  const removeButton = document.createElement('button');
  removeButton.className = 'remove-btn';
  removeButton.innerHTML = '&times;';
  removeButton.title = 'Remove from list';

  // Create function name element (without caret)
  const nameElement = document.createElement('span');
  nameElement.className = 'custom-function-name';
  nameElement.textContent = functionName;

  // Create full name element
  const fullNameElement = document.createElement('div');
  fullNameElement.className = 'file-path';
  fullNameElement.textContent = fullName;

  // Handle click on function name
  nameElement.onclick = function () {
    clearActiveNodes();

    // Load function details
    loadFunctionDetails(repoHash, functionId);

    // Find the expandable node and expand it
    const expandableNode = functionNode.querySelector('.caret');
    if (expandableNode) {
      expandableNode.classList.add('active-node');

      toggleNode(expandableNode);

      // If expanding and there are no children, load components
      const nested = expandableNode.parentElement.querySelector('.nested');
      if (
        nested &&
        nested.classList.contains('active') &&
        nested.children.length === 0
      ) {
        loadFunctionComponents(repoHash, functionId, nested);
      }
    }
  };

  // Handle pin button click
  pinButton.addEventListener('click', (e) => {
    e.stopPropagation();
    togglePinFunction(functionId, pinButton);
  });

  // Handle remove button click
  removeButton.addEventListener('click', (e) => {
    e.stopPropagation();
    customFunctionItem.remove();

    // If function was pinned, remove from pinned list
    const pinnedIndex = pinnedFunctions.indexOf(functionId);
    if (pinnedIndex !== -1) {
      pinnedFunctions.splice(pinnedIndex, 1);
      savePinnedFunctions();
    }

    // If list is empty, show empty state
    if (customFunctionsList.children.length === 0) {
      customFunctionsList.innerHTML =
        '<div class="empty-state">Search for functions to add them here</div>';
    }
  });

  // Create nested container for components
  const childrenElement = document.createElement('div');
  childrenElement.className = 'nested';

  // Add caret for expanding/collapsing components
  const caretElement = document.createElement('span');
  caretElement.className = 'caret node-function';
  caretElement.textContent = 'Components';
  caretElement.onclick = function () {
    clearActiveNodes();
    this.classList.add('active-node');

    toggleNode(this);

    // If expanding and there are no children, load components
    if (
      childrenElement.classList.contains('active') &&
      childrenElement.children.length === 0
    ) {
      loadFunctionComponents(repoHash, functionId, childrenElement);
    }
  };

  // Assemble the function node
  functionNode.appendChild(caretElement);
  functionNode.appendChild(childrenElement);

  // Assemble the custom function item
  customFunctionItem.appendChild(pinButton);
  customFunctionItem.appendChild(nameElement);
  customFunctionItem.appendChild(fullNameElement);
  customFunctionItem.appendChild(removeButton);
  customFunctionItem.appendChild(functionNode);

  // Add to the list
  customFunctionsList.appendChild(customFunctionItem);
}

// Toggle pin status for a function
function togglePinFunction(functionId, pinButton) {
  const isPinned = pinnedFunctions.includes(functionId);

  if (isPinned) {
    // Unpin function
    const index = pinnedFunctions.indexOf(functionId);
    if (index !== -1) {
      pinnedFunctions.splice(index, 1);
    }
    pinButton.title = 'Pin function';
    pinButton.classList.remove('pinned');
  } else {
    // Pin function
    pinnedFunctions.push(functionId);
    pinButton.title = 'Unpin function';
    pinButton.classList.add('pinned');
  }

  // Save to localStorage
  savePinnedFunctions();

  // Re-sort the list to put pinned functions at the top
  sortCustomFunctionsList();
}

// Save pinned functions to localStorage
function savePinnedFunctions() {
  try {
    localStorage.setItem(
      `pinnedFunctions_${repoHash}`,
      JSON.stringify(pinnedFunctions)
    );
  } catch (error) {
    console.warn('Failed to save pinned functions to localStorage:', error);
  }
}

// Load pinned functions from localStorage
function loadPinnedFunctions() {
  try {
    const savedPinned = localStorage.getItem(`pinnedFunctions_${repoHash}`);
    if (savedPinned) {
      pinnedFunctions = JSON.parse(savedPinned);

      // Load each pinned function
      pinnedFunctions.forEach(async (functionId) => {
        try {
          const response = await fetch(
            `/code/api/functions/${repoHash}/${functionId}`
          );
          if (response.ok) {
            const functionData = await response.json();
            addToCustomFunctionsList(
              functionId,
              functionData.name,
              functionData.file_path
            );
          }
        } catch (error) {
          console.warn(`Failed to load pinned function ${functionId}:`, error);
        }
      });
    }
  } catch (error) {
    console.warn('Failed to load pinned functions from localStorage:', error);
  }
}

// Sort custom functions list (pinned functions at top)
function sortCustomFunctionsList() {
  const customFunctionsList = document.getElementById('custom-functions-list');
  const functionItems = Array.from(
    customFunctionsList.querySelectorAll('.custom-function-item')
  );

  // Sort: pinned first, then alphabetically by name
  functionItems.sort((a, b) => {
    const aIsPinned = pinnedFunctions.includes(a.dataset.id);
    const bIsPinned = pinnedFunctions.includes(b.dataset.id);

    if (aIsPinned && !bIsPinned) return -1;
    if (!aIsPinned && bIsPinned) return 1;

    const aName = a.querySelector('.node-function').textContent;
    const bName = b.querySelector('.node-function').textContent;
    return aName.localeCompare(bName);
  });

  // Remove all items and re-add in sorted order
  functionItems.forEach((item) => item.remove());
  functionItems.forEach((item) => customFunctionsList.appendChild(item));
}

// export { setupFunctionSearch, addToCustomFunctionsList, loadPinnedFunctions };
