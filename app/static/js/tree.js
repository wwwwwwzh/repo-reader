// import dotenv from '../../../node_modules/dotenv';
// dotenv.config();
// const repos_dir = process.env.REPO_CACHE_DIR;
const repos_dir = '/home/webadmin/projects/code/repos';

let currentFunctionId = null;
let repoHash = null;
let pinnedFunctions = [];
const searchCache = {};
let lastSearchTime = 0;
const MIN_SEARCH_INTERVAL = 2000;
const treeNav = document.querySelector('.tree-nav');

treeNav.addEventListener('scroll', updateStickyPositions);
window.addEventListener('resize', updateStickyPositions); // optional but handy

document.addEventListener('DOMContentLoaded', () => {
  // Get repository hash from data attribute
  repoHash = document.querySelector('.repo-info').dataset.repoHash;

  // Initialize the page
  setupPanelToggling();
  loadFileStructure(repoHash);
  loadEntryFunctions(repoHash);
});

// Set up upper right panel toggling functionality
function setupPanelToggling() {
  const panelHeader = document.getElementById('panel-header');
  const panelToggle = document.getElementById('panel-toggle');
  const upperPanel = document.querySelector('.upper-panel');
  const lowerPanel = document.getElementById('lower-panel');

  panelHeader.addEventListener('click', () => {
    upperPanel.classList.toggle('collapsed');
    lowerPanel.classList.toggle('expanded');

    // Update the toggle icon
    panelToggle.textContent = upperPanel.classList.contains('collapsed')
      ? '▼'
      : '▲';
  });

  // Set up function search
  setupFunctionSearch();

  // Load pinned functions from localStorage if available
  loadPinnedFunctions();
}

//MARK: Search function
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
      const newKey = prompt('Enter your Groq API key for better search results:', currentKey);
      if (newKey !== null) {
          localStorage.setItem('groqApiKey', newKey);
          alert('API key saved! ' + (newKey ? 'Semantic search is now enabled.' : 'Semantic search is now disabled.'));
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

      if (prompt && functions.length > 0) {
        const shortFunctionIds = await queryGroqForFunctions(
          prompt,
          searchTerm,
          groqApiKey
        );

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
          model: 'llama3-8b-8192',
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

    // Extract short function IDs - expecting a comma-separated list
    const shortFunctionIds = content.split(',').map((id) => id.trim());

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

// Debounce function to limit API calls
function debounce(func, wait) {
  let timeout;
  return function (...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), wait);
  };
}
// MARK: File System
// Load repository file structure
async function loadFileStructure(repoHash) {
  try {
    // Show loading indicator
    const fileTreeElement = document.getElementById('file-tree');
    fileTreeElement.innerHTML =
      '<h3>File Structure</h3><div id="loading-file-tree" class="loading"></div>';

    // Fetch file structure from an API endpoint
    const response = await fetch(`/code/api/files/${repoHash}`);
    const files = await response.json();

    // Remove loading indicator
    document.getElementById('loading-file-tree').remove();

    // Build file tree
    const rootElement = document.createElement('div');
    rootElement.className = 'node-root';
    fileTreeElement.appendChild(rootElement);

    // Build file structure tree
    buildFileTree(files, rootElement);
  } catch (error) {
    console.error('Error loading file structure:', error);
    document.getElementById('file-tree').innerHTML =
      '<h3>File Structure</h3><p>Error loading file structure. Please try again later.</p>';
  }
}

function buildFileTree(files, parentElement) {
  console.warn(files);
  // Group files by directory
  const fileGroups = {};

  files.forEach((file) => {
    const path = file.path.split('/');
    const fileName = path.pop();
    const dirPath = path.join('/');

    if (!fileGroups[dirPath]) {
      fileGroups[dirPath] = [];
    }

    fileGroups[dirPath].push({
      name: fileName,
      path: file.path,
      is_dir: file.is_dir,
    });
  });

  // Create directory nodes recursively
  buildDirectoryNode('', fileGroups, parentElement);
}

function buildDirectoryNode(dirPath, fileGroups, parentElement) {
  const dirFiles = fileGroups[dirPath] || [];
  console.log(dirFiles);

  // Sort directories first, then files
  dirFiles.sort((a, b) => {
    if (a.is_dir && !b.is_dir) return -1;
    if (!a.is_dir && b.is_dir) return 1;
    return a.name.localeCompare(b.name);
  });

  dirFiles.forEach((file) => {
    const fileNode = document.createElement('div');
    fileNode.className = 'node';

    const nameElement = document.createElement('span');
    nameElement.textContent = file.name;

    if (file.is_dir) {
      nameElement.className = 'caret';

      const childrenElement = document.createElement('div');
      childrenElement.className = 'nested';

      nameElement.onclick = function () {
        toggleNode(this);

        // If expanding and there are no children, load the subdirectory
        const nested = this.parentElement.querySelector('.nested');
        if (
          nested &&
          nested.classList.contains('active') &&
          nested.children.length === 0
        ) {
          const subDirPath = dirPath ? `${dirPath}/${file.name}` : file.name;
          buildDirectoryNode(subDirPath, fileGroups, nested);
        }
      };

      fileNode.appendChild(nameElement);
      fileNode.appendChild(childrenElement);
    } else {
      // It's a file
      nameElement.className = 'file-node';
      nameElement.onclick = function () {
        loadFileContent(file.path);
      };

      fileNode.appendChild(nameElement);
    }

    parentElement.appendChild(fileNode);
  });
}

async function loadFileContent(filePath) {
  try {
    // Show loading indicators
    const upperPanel = document.querySelector('.upper-panel');
    const lowerPanel = document.getElementById('lower-panel');
    const panelContent = upperPanel.querySelector('.panel-content');
    const panelTitle = upperPanel.querySelector('.panel-title');

    panelContent.innerHTML = '<div class="loading"></div>';
    lowerPanel.innerHTML = '<div class="loading"></div>';
    panelTitle.textContent = 'Loading File...';

    // Ensure panel is expanded
    upperPanel.classList.remove('collapsed');
    lowerPanel.classList.remove('expanded');
    upperPanel.querySelector('.panel-toggle').textContent = '▲';

    // Get repository hash
    const repoHash = document.querySelector('.repo-info').dataset.repoHash;

    // Construct complete file path for the repository
    const completeFilePath = `${repos_dir}/${repoHash}/${filePath}`;

    // Fetch file content using the complete path
    const response = await fetch(
      `/code/api/file?path=${encodeURIComponent(
        completeFilePath
      )}&repo_hash=${repoHash}`
    );

    if (!response.ok) {
      throw new Error(`Failed to load file: ${response.statusText}`);
    }

    const fileContent = await response.text();

    // Update panel title
    panelTitle.textContent = `File: ${filePath.split('/').pop()}`;

    // Update upper panel with file info
    panelContent.innerHTML = `
            <div class="function-details">
                <div class="file-path">${filePath}</div>
            </div>
        `;

    // Update lower panel with file content
    const fileLines = fileContent.split('\n');
    let codeHTML = '<div class="code-container">';

    fileLines.forEach((line, index) => {
      codeHTML += `
                <div class="code-line">
                    <span class="line-number">${index + 1}</span>
                    <span class="line-content"><code class="language-python">${escapeHTML(
                      line
                    )}</code></span>
                </div>
            `;
    });

    codeHTML += '</div>';

    lowerPanel.innerHTML = `
            <h3>File Content</h3>
            ${codeHTML}
        `;

    // Reset current function ID since we're viewing a full file
    currentFunctionId = null;

    setTimeout(() => {
      Prism.highlightAll();
    }, 100);
  } catch (error) {
    console.error('Error loading file content:', error);
    document.getElementById(
      'lower-panel'
    ).innerHTML = `<p>Error loading file content: ${error.message}</p>`;
  }
}

// MARK: Workflow System
// Load entry point functions for the repository
async function loadEntryFunctions(repoHash) {
  try {
    // Show loading indicator
    const treeElement = document.getElementById('tree');
    treeElement.innerHTML = '<div id="loading-tree" class="loading"></div>';

    // Fetch entry functions
    const response = await fetch(`/code/api/functions/${repoHash}/entries`);
    const functions = await response.json();

    // Remove loading indicator
    treeElement.innerHTML = '';

    if (functions.length === 0) {
      treeElement.innerHTML = '<p>No entry functions found.</p>';
      return;
    }

    // Build the tree root
    const rootElement = document.createElement('div');
    rootElement.className = 'node-root';
    treeElement.appendChild(rootElement);

    // Add each entry function to the tree
    functions.forEach((func) => {
      addFunctionNodeToTree(func, rootElement, repoHash);
    });
  } catch (error) {
    console.error('Error loading entry functions:', error);
    document.getElementById('tree').innerHTML =
      '<p>Error loading function tree. Please try again later.</p>';
  }
}

// Add a function node to the tree
function addFunctionNodeToTree(func, parentElement, repoHash) {
  const funcNode = document.createElement('div');
  funcNode.className = 'node';
  funcNode.dataset.id = func.id;
  funcNode.dataset.type = 'function';

  const nameElement = document.createElement('span');
  nameElement.className = 'caret node-function';
  nameElement.textContent = func.name;

  // Handle click on function name
  nameElement.onclick = function () {
    clearActiveNodes();
    this.classList.add('active-node');

    toggleNode(this);
    loadFunctionDetails(repoHash, func.id);

    // If expanding and there are no children, load components
    const nested = this.parentElement.querySelector('.nested');
    if (
      nested &&
      nested.classList.contains('active') &&
      nested.children.length === 0
    ) {
      loadFunctionComponents(repoHash, func.id, nested);
    }
  };

  const childrenElement = document.createElement('div');
  childrenElement.className = 'nested';

  funcNode.appendChild(nameElement);
  funcNode.appendChild(childrenElement);
  parentElement.appendChild(funcNode);
}

// Toggle expansion of a tree node
// Updated toggleNode function with proper style reset
function toggleNode(element) {
  element.classList.toggle('caret-down');
  const nested = element.parentElement.querySelector('.nested');

  if (nested) {
    nested.classList.toggle('active');

    // Handle sticky headers when this is a function, component or call segment
    const parentNode = element.parentElement;
    const nodeType = parentNode.dataset.type;

    if (
      nodeType === 'function' ||
      nodeType === 'component' ||
      (nodeType === 'segment' && parentNode.dataset.segmentType === 'call')
    ) {
      if (nested.classList.contains('active')) {
        // Add sticky class to the caret element itself
        element.classList.add('sticky-caret');

        // Update sticky positions for all carets
        updateStickyPositions();
      } else {
        // Remove sticky class from this caret
        element.classList.remove('sticky-caret');

        // Important: Reset the styles when removing sticky
        element.style.top = '';
        element.style.zIndex = '';

        // Reset styles for all child sticky carets in this nested section
        const childCarets = nested.querySelectorAll('.sticky-caret');
        childCarets.forEach((childCaret) => {
          childCaret.classList.remove('sticky-caret');
          childCaret.style.top = '';
          childCaret.style.zIndex = '';
        });

        // Update sticky positions again
        updateStickyPositions();
      }
    }
  }
}

function updateStickyPositions() {
  // Find all sticky carets
  const stickyCarets = document.querySelectorAll('.sticky-caret');

  // Process each sticky caret
  stickyCarets.forEach((caret) => {
    // Calculate nesting level by counting parent .nested elements
    let level = 0;
    let current = caret;
    let parent = current.parentElement;

    while (parent) {
      if (parent.classList.contains('nested')) {
        level++;
      }
      parent = parent.parentElement;
    }

    // Set the top position (25px per level to account for the header height)
    const topPosition = level * 25;

    // IMPORTANT: Make sure to use +'px' for the top value
    caret.style.top = topPosition + 'px';

    // Set z-index inversely proportional to level (higher = lower z-index)
    caret.style.zIndex = (100 - level).toString();

    // Optional: Add this to console to verify values are being set
    console.log(
      `Caret "${caret.textContent.trim()}" set to top: ${topPosition}px, z-index: ${
        100 - level
      }`
    );
  });
}

// Load function components
async function loadFunctionComponents(repoHash, functionId, parentElement) {
  try {
    // Show loading indicator
    parentElement.innerHTML = '<div class="loading"></div>';

    // Fetch components and function details
    const [components, functionData] = await Promise.all([
      fetchComponents(repoHash, functionId),
      fetchFunctionDetails(repoHash, functionId),
    ]);

    // Clear loading indicator
    parentElement.innerHTML = '';

    if (components.length === 0) {
      // If no components found, display segments directly
      parentElement.innerHTML =
        '<div class="node">No components found. Showing segments directly:</div>';

      // Add segments directly
      if (functionData.segments && functionData.segments.length > 0) {
        loadSegmentsIntoNode(
          functionData.segments,
          parentElement,
          repoHash,
          functionId
        );
      } else {
        parentElement.innerHTML += '<div class="node">No segments found</div>';
      }
      return;
    }

    // Organize segments by component
    const { componentSegments, unassignedSegments } =
      organizeSegmentsByComponent(functionData.segments);

    // Add each component
    components.forEach((component) => {
      addComponentNode(
        component,
        componentSegments,
        parentElement,
        repoHash,
        functionId
      );
    });

    // Add unassigned segments node if there are any
    if (unassignedSegments.length > 0) {
      addUnassignedSegmentsNode(
        unassignedSegments,
        parentElement,
        repoHash,
        functionId
      );
    }
  } catch (error) {
    console.error('Error loading components:', error);
    parentElement.innerHTML =
      '<div class="node">Error loading function components</div>';
  }
}

// Fetch function components
async function fetchComponents(repoHash, functionId) {
  const response = await fetch(
    `/code/api/functions/${repoHash}/${functionId}/components`
  );
  return await response.json();
}

// Fetch function details
async function fetchFunctionDetails(repoHash, functionId) {
  const response = await fetch(`/code/api/functions/${repoHash}/${functionId}`);
  return await response.json();
}

// Organize segments by component ID
function organizeSegmentsByComponent(segments) {
  const componentSegments = {};
  const unassignedSegments = [];

  if (segments) {
    segments.forEach((segment) => {
      if (segment.func_component_id) {
        if (!componentSegments[segment.func_component_id]) {
          componentSegments[segment.func_component_id] = [];
        }
        componentSegments[segment.func_component_id].push(segment);
      } else {
        unassignedSegments.push(segment);
      }
    });
  }

  return { componentSegments, unassignedSegments };
}

// Add a component node to the tree
function addComponentNode(
  component,
  componentSegments,
  parentElement,
  repoHash,
  functionId
) {
  const componentNode = document.createElement('div');
  componentNode.className = 'node';
  componentNode.dataset.id = component.id;
  componentNode.dataset.type = 'component';
  componentNode.dataset.functionId = functionId;

  const nameElement = document.createElement('span');
  nameElement.className = 'caret node-component';
  // Use short description as the title
  nameElement.textContent =
    component.short_description ||
    component.name ||
    `Component ${component.index + 1}`;

  const segmentsContainer = document.createElement('div');
  segmentsContainer.className = 'nested';

  // Get segments for this component
  const segments = componentSegments[component.id] || [];

  // Handle click on component name
  nameElement.onclick = function () {
    clearActiveNodes();
    this.classList.add('active-node');

    toggleNode(this);

    // Display component details
    displayComponentDetails(component, segments, functionId);

    // Load segments if expanding
    if (
      segmentsContainer.classList.contains('active') &&
      segmentsContainer.children.length === 0
    ) {
      if (segments.length > 0) {
        loadSegmentsIntoNode(segments, segmentsContainer, repoHash, functionId);
      } else {
        segmentsContainer.innerHTML =
          '<div class="node">No segments in this component</div>';
      }
    }
  };

  componentNode.appendChild(nameElement);
  componentNode.appendChild(segmentsContainer);
  parentElement.appendChild(componentNode);
}

// Add unassigned segments node
function addUnassignedSegmentsNode(
  unassignedSegments,
  parentElement,
  repoHash,
  functionId
) {
  const unassignedNode = document.createElement('div');
  unassignedNode.className = 'node';
  unassignedNode.dataset.type = 'unassigned';
  unassignedNode.dataset.functionId = functionId;

  const unassignedLabel = document.createElement('span');
  unassignedLabel.className = 'caret';
  unassignedLabel.textContent = 'Unassigned Segments';

  const unassignedContainer = document.createElement('div');
  unassignedContainer.className = 'nested';

  // Handle click on unassigned segments label
  unassignedLabel.onclick = function () {
    clearActiveNodes();
    this.classList.add('active-node');

    toggleNode(this);

    // Display unassigned segments details
    displayUnassignedSegmentsDetails(unassignedSegments, functionId);

    // Load segments if expanding
    if (
      unassignedContainer.classList.contains('active') &&
      unassignedContainer.children.length === 0
    ) {
      loadSegmentsIntoNode(
        unassignedSegments,
        unassignedContainer,
        repoHash,
        functionId
      );
    }
  };

  unassignedNode.appendChild(unassignedLabel);
  unassignedNode.appendChild(unassignedContainer);
  parentElement.appendChild(unassignedNode);
}

// Load segments into a node
function loadSegmentsIntoNode(
  segments,
  parentElement,
  repoHash,
  parentFunctionId
) {
  segments.forEach((segment) => {
    if (segment.type === 'call' && segment.target_function) {
      addCallSegmentNode(segment, parentElement, repoHash, parentFunctionId);
    } else {
      addNormalSegmentNode(segment, parentElement, parentFunctionId);
    }
  });
}

// Add a call segment node
function addCallSegmentNode(
  segment,
  parentElement,
  repoHash,
  parentFunctionId
) {
  const segmentNode = document.createElement('div');
  segmentNode.className = 'node';
  segmentNode.dataset.type = 'segment';
  segmentNode.dataset.segmentType = 'call';
  segmentNode.dataset.functionId = parentFunctionId;

  const segmentLabel = document.createElement('span');
  segmentLabel.className = 'caret node-segment-call';
  segmentLabel.textContent = `Call: ${segment.target_function.name}() - Line ${segment.lineno}`;

  const targetContainer = document.createElement('div');
  targetContainer.className = 'nested';

  // Handle click on call segment
  segmentLabel.onclick = function () {
    clearActiveNodes();
    this.classList.add('active-node');

    toggleNode(this);

    // Display segment details
    displaySegmentDetails(segment, segment.target_function.id);

    // Load target function components if expanding
    if (
      targetContainer.classList.contains('active') &&
      targetContainer.children.length === 0
    ) {
      loadFunctionComponents(
        repoHash,
        segment.target_function.id,
        targetContainer
      );
    }
  };

  segmentNode.appendChild(segmentLabel);
  segmentNode.appendChild(targetContainer);
  parentElement.appendChild(segmentNode);
}

// Add a normal segment node (code or comment)
function addNormalSegmentNode(segment, parentElement, parentFunctionId) {
  const segmentNode = document.createElement('div');
  segmentNode.className = 'node';
  segmentNode.dataset.type = 'segment';
  segmentNode.dataset.segmentType = segment.type;
  segmentNode.dataset.functionId = parentFunctionId;

  const segmentLabel = document.createElement('span');
  segmentLabel.className = `node-segment-${segment.type}`;

  // Create a preview of the content
  const contentPreview = segment.content.split('\n')[0].substring(0, 30);
  segmentLabel.textContent = `${
    segment.type.charAt(0).toUpperCase() + segment.type.slice(1)
  }: ${contentPreview}... (Line ${segment.lineno})`;

  // Handle click on segment
  segmentLabel.onclick = function () {
    clearActiveNodes();
    this.classList.add('active-node');

    // Show segment details
    displaySegmentDetails(segment, parentFunctionId);
  };

  segmentNode.appendChild(segmentLabel);
  parentElement.appendChild(segmentNode);
}

// Clear active node highlighting
function clearActiveNodes() {
  document.querySelectorAll('.active-node').forEach((node) => {
    node.classList.remove('active-node');
  });
}

// Load function details
async function loadFunctionDetails(repoHash, functionId) {
  try {
    // Skip reloading if it's the same function
    if (currentFunctionId === functionId) {
      return;
    }

    // Update currently displayed function
    currentFunctionId = functionId;

    // Get panel elements
    const previewElement = document.getElementById('function-preview');
    const upperPanel = previewElement.querySelector('.upper-panel');
    const lowerPanel = document.getElementById('lower-panel');
    const panelContent = upperPanel.querySelector('.panel-content');
    const panelTitle = upperPanel.querySelector('.panel-title');

    // Show loading indicators
    panelContent.innerHTML = '<div class="loading"></div>';
    lowerPanel.innerHTML = '<div class="loading"></div>';
    panelTitle.textContent = 'Loading Function...';

    // Ensure panel is expanded
    upperPanel.classList.remove('collapsed');
    lowerPanel.classList.remove('expanded');
    upperPanel.querySelector('.panel-toggle').textContent = '▲';

    // Fetch function details
    const functionData = await fetchFunctionDetails(repoHash, functionId);

    // Update panel title
    panelTitle.textContent = `Function: ${functionData.name}`;

    // Update upper panel with function summary
    panelContent.innerHTML = buildFunctionSummaryHTML(functionData);

    // Update lower panel with complete function code
    const codeView = await buildFullFunctionCodeView(functionData);
    lowerPanel.innerHTML = `
            <h3>Complete Function Code</h3>
            ${codeView}
        `;

    const parentNode = document.querySelector(`.node[data-id="${functionId}"]`);

    if (parentNode && parentNode.dataset.type === 'function') {
      document
        .querySelector('.function-highlight')
        .scrollIntoView({ behavior: 'smooth' });
    }
  } catch (error) {
    console.error('Error loading function details:', error);
    const panelContent = document.querySelector('.panel-content');
    panelContent.innerHTML =
      '<p>Error loading function details. Please try again later.</p>';
    document.getElementById('lower-panel').innerHTML =
      '<p>Error loading function code.</p>';
  }
}

// Build HTML for function summary
function buildFunctionSummaryHTML(functionData) {
  let html = `
        <div class="function-details">
            <div class="file-path">${functionData.full_name}</div>
            <div>Lines: ${functionData.lineno} - ${
    functionData.end_lineno
  }</div>
            ${
              functionData.is_entry
                ? '<div><strong>Entry Point</strong></div>'
                : ''
            }
            ${
              functionData.class_name
                ? `<div>Class: ${functionData.class_name}</div>`
                : ''
            }
            <div>Module: ${functionData.module_name}</div>
        </div>
    `;

  // Add descriptions if available
  if (
    functionData.short_description ||
    functionData.input_output_description ||
    functionData.long_description
  ) {
    html += '<div class="function-descriptions">';

    if (functionData.short_description) {
      html += `<p><strong>Short Description:</strong> ${functionData.short_description}</p>`;
    }

    if (functionData.input_output_description) {
      html += `<p><strong>Input/Output:</strong> ${functionData.input_output_description}</p>`;
    }

    if (functionData.long_description) {
      html += `<p><strong>Detailed Description:</strong> ${functionData.long_description}</p>`;
    }

    html += '</div>';
  }

  return html;
}

// Display component details
async function displayComponentDetails(component, segments, functionId) {
  const upperPanel = document.querySelector('.upper-panel');
  const lowerPanel = document.getElementById('lower-panel');
  const panelContent = upperPanel.querySelector('.panel-content');
  const panelTitle = upperPanel.querySelector('.panel-title');

  // Update panel title
  panelTitle.textContent = `Component: ${
    component.short_description ||
    component.name ||
    `Component ${component.index + 1}`
  }`;

  // Ensure panel is expanded
  upperPanel.classList.remove('collapsed');
  lowerPanel.classList.remove('expanded');
  upperPanel.querySelector('.panel-toggle').textContent = '▲';

  // Build component summary
  let content = `
        <div class="component">
            <p><strong>Lines:</strong> ${component.start_lineno} - ${
    component.end_lineno
  }</p>
            ${
              component.long_description
                ? `<p><strong>Detailed Description:</strong> ${component.long_description}</p>`
                : ''
            }
        </div>
    `;

  // Update upper panel
  panelContent.innerHTML = content;

  // Update lower panel if the function has changed
  if (currentFunctionId !== functionId) {
    currentFunctionId = functionId;
    lowerPanel.innerHTML = '<div class="loading"></div>';

    try {
      // Fetch function details
      const functionData = await fetchFunctionDetails(repoHash, functionId);

      // Update lower panel with highlighted component
      const codeView = await buildFullFunctionCodeView(functionData, component);
      lowerPanel.innerHTML = `
                <h3>Complete Function Code</h3>
                ${codeView}
            `;
    } catch (error) {
      console.error('Error loading function code for component:', error);
      lowerPanel.innerHTML = '<p>Error loading function code.</p>';
    }
  } else {
    // Same function, just update highlighting
    try {
      const functionData = await fetchFunctionDetails(repoHash, functionId);
      const codeView = await buildFullFunctionCodeView(functionData, component);
      lowerPanel.innerHTML = `
                <h3>Complete Function Code</h3>
                ${codeView}
            `;
    } catch (error) {
      console.error('Error updating component highlighting:', error);
    }
  }
}

// Display unassigned segments details
function displayUnassignedSegmentsDetails(unassignedSegments, functionId) {
  const upperPanel = document.querySelector('.upper-panel');
  const panelContent = upperPanel.querySelector('.panel-content');
  const panelTitle = upperPanel.querySelector('.panel-title');

  // Update panel title
  panelTitle.textContent = 'Unassigned Segments';

  // Ensure panel is expanded
  upperPanel.classList.remove('collapsed');
  document.getElementById('lower-panel').classList.remove('expanded');
  upperPanel.querySelector('.panel-toggle').textContent = '▲';

  // Build unassigned segments summary
  let content = `
        <div class="unassigned-segments-info">
            <p>These segments are not associated with any specific component.</p>
        </div>
    `;

  // Add segments summary
  if (unassignedSegments && unassignedSegments.length > 0) {
    content += '<div class="segments-summary">';

    unassignedSegments.forEach((segment) => {
      content += `
                <div class="segment-summary segment-${segment.type}">
                    <div class="segment-header">
                        ${segment.type.toUpperCase()} - Line ${segment.lineno}
                        ${segment.end_lineno ? ` to ${segment.end_lineno}` : ''}
                    </div>
                    <div class="segment-preview">
                        ${escapeHTML(segment.content.split('\n')[0])}...
                    </div>
                </div>
            `;
    });

    content += '</div>';
  } else {
    content += '<p>No unassigned segments found.</p>';
  }

  // Update upper panel
  panelContent.innerHTML = content;
}

// Display segment details
async function displaySegmentDetails(segment, targetFunctionId) {
  const upperPanel = document.querySelector('.upper-panel');
  const lowerPanel = document.getElementById('lower-panel');
  const panelContent = upperPanel.querySelector('.panel-content');
  const panelTitle = upperPanel.querySelector('.panel-title');

  const segmentType = segment.type;

  // Update panel title
  panelTitle.textContent = `${segmentType.toUpperCase()} Segment`;

  // Ensure panel is expanded
  upperPanel.classList.remove('collapsed');
  lowerPanel.classList.remove('expanded');
  upperPanel.querySelector('.panel-toggle').textContent = '▲';

  // Build segment details
  let content = `
        <div class="segment segment-${segmentType}">
            <div><strong>Lines:</strong> ${segment.lineno}${
    segment.end_lineno ? ` - ${segment.end_lineno}` : ''
  }</div>
            <div class="segment-body">
                <pre><code>${escapeHTML(segment.content)}</code></pre>
            </div>
    `;

  // Add target info for call segments
  if (segmentType === 'call' && segment.target_function) {
    const target = segment.target_function;
    content += `
            <div class="segment-target">
                <div><strong>Name:</strong> ${target.name} (${target.full_name})</div>
                <div><strong>Lines:</strong> ${target.lineno} - ${target.end_lineno}</div>
            </div>
        `;
  }

  content += '</div>'; // Close segment div

  // Update upper panel
  panelContent.innerHTML = content;

  // Update lower panel based on segment type
  if (
    (segmentType === 'call' &&
      segment.target_function &&
      targetFunctionId !== currentFunctionId) ||
    targetFunctionId !== currentFunctionId
  ) {
    // Update current function ID
    currentFunctionId = targetFunctionId;

    // Show loading
    lowerPanel.innerHTML = '<div class="loading"></div>';

    try {
      // Fetch function details
      const functionData = await fetchFunctionDetails(
        repoHash,
        targetFunctionId
      );

      // Special handling for call segments to show target function
      if (segmentType === 'call' && segment.target_function) {
        const codeView = await buildFullFunctionCodeView(functionData);
        lowerPanel.innerHTML = `
                    <h3>Target Function: ${functionData.name}</h3>
                    ${codeView}
                `;
      } else {
        // Normal handling for other segment types
        const codeView = await buildFullFunctionCodeView(
          functionData,
          null,
          segment
        );
        lowerPanel.innerHTML = `
                    <h3>Complete Function Code</h3>
                    ${codeView}
                `;
      }
    } catch (error) {
      console.error('Error loading function for segment:', error);
      lowerPanel.innerHTML = '<p>Error loading function code.</p>';
    }
  } else {
    // Same function, just update highlighting
    try {
      const functionData = await fetchFunctionDetails(
        repoHash,
        targetFunctionId
      );
      const codeView = await buildFullFunctionCodeView(
        functionData,
        null,
        segment
      );
      lowerPanel.innerHTML = `
                <h3>Complete Function Code</h3>
                ${codeView}
            `;
    } catch (error) {
      console.error('Error updating segment highlighting:', error);
    }
  }

  if (segment.type === 'call') {
    document
      .querySelector('.function-highlight')
      .scrollIntoView({ behavior: 'smooth' });
  }
}

// Helper function to build a complete function code view with highlighting
// Helper function to build a complete function code view with highlighting
async function buildFullFunctionCodeView(
  functionData,
  highlightComponent = null,
  highlightSegment = null
) {
  // If functionData is null but we have a current function ID, fetch the function data
  if (!functionData && currentFunctionId) {
    try {
      const repoHash = document.querySelector('.repo-info').dataset.repoHash;
      const response = await fetch(
        `/code/api/functions/${repoHash}/${currentFunctionId}`
      );
      functionData = await response.json();
    } catch (error) {
      console.error('Error fetching current function data:', error);
      return '<p>Error loading function code.</p>';
    }
  }

  // If we still don't have function data, return an error message
  if (!functionData) {
    return '<p>No function data available.</p>';
  }

  try {
    // Use the file_path to get the complete file content
    const filePath = functionData.file_path;
    const functionStart = functionData.lineno;
    const functionEnd = functionData.end_lineno;

    // Fetch the file content using an API endpoint
    let fileLines = [];

    try {
      const repoHash = document.querySelector('.repo-info').dataset.repoHash;
      const response = await fetch(
        `/code/api/file?path=${encodeURIComponent(
          filePath
        )}&repo_hash=${repoHash}`
      );

      if (response.ok) {
        const fileContent = await response.text();
        fileLines = fileContent.split('\n');
      } else {
        console.warn(
          'Error fetching complete file, falling back to function-only view'
        );
        // Fall back to function-only view using segments
        return fallbackToFunctionOnlyView(
          functionData,
          highlightComponent,
          highlightSegment
        );
      }
    } catch (fileError) {
      console.warn(
        'Error reading file directly, falling back to function-only view:',
        fileError
      );
      return fallbackToFunctionOnlyView(
        functionData,
        highlightComponent,
        highlightSegment
      );
    }

    // Get components for the function
    let components = [];
    try {
      const repoHash = document.querySelector('.repo-info').dataset.repoHash;
      const compResponse = await fetch(
        `/code/api/functions/${repoHash}/${functionData.id}/components`
      );
      if (compResponse.ok) {
        components = await compResponse.json();
      }
    } catch (error) {
      console.warn('Error fetching components:', error);
    }

    // Sort components by start line
    components.sort((a, b) => a.start_lineno - b.start_lineno);

    // Use different background colors for different elements
    const componentColors = [
      'rgba(255, 217, 0, 0.4)', // Light blue (very faint)
      'rgba(242, 255, 0, 0.25)', // Light green (very faint)
    ];

    const segmentColors = {
      code: 'rgba(255, 253, 231, 0.2)', // Light yellow (faint)
      call: 'rgba(255, 232, 230, 0.2)', // Light red (faint)
      comment: 'rgba(245, 245, 245, 0.2)', // Light gray (faint)
    };

    const highlightedComponentColor = 'rgba(187, 222, 251, 0.7)'; // Blue (stronger)

    const highlightedSegmentColors = {
      code: 'rgba(255, 253, 231, 0.7)', // Yellow (stronger)
      call: 'rgba(255, 232, 230, 0.7)', // Red (stronger)
      comment: 'rgba(245, 245, 245, 0.7)', // Gray (stronger)
    };

    // Function to determine if a line belongs to a component
    function lineInComponent(absLine, component) {
      return (
        absLine >= component.start_lineno && absLine <= component.end_lineno
      );
    }

    // Function to determine if a line belongs to a segment
    function lineInSegment(relLine, segment) {
      const segmentRelLine = segment.lineno;
      const segmentRelEnd = segment.end_lineno || segment.lineno;
      return relLine >= segmentRelLine && relLine <= segmentRelEnd;
    }

    // Function to get the component index for coloring
    function getComponentIndex(component, components) {
      const index = components.findIndex((c) => c.id === component.id);
      return index >= 0 ? index % componentColors.length : -1;
    }

    // Build code lines with appropriate highlighting
    let codeLines = [];

    for (let i = 0; i < fileLines.length; i++) {
      const lineNumber = i + 1; // 1-based line number
      const lineContent = fileLines[i] || '';

      // Determine if this line is part of the selected function
      const isInFunction =
        lineNumber >= functionStart && lineNumber <= functionEnd;

      // If we're inside the function, apply specific highlighting
      let backgroundColor = isInFunction
        ? 'rgba(187, 222, 251, 0.15)'
        : 'transparent';
      let borderLeft = isInFunction ? '1px solid #bbdefb' : '';
      let strongHighlight = false;

      if (isInFunction) {
        const relLine = lineNumber - functionStart + 1; // Relative line within the function

        // Find the component that contains this line
        const containingComponent = components.find((comp) =>
          lineInComponent(lineNumber, comp)
        );

        // Find the segment that contains this line
        const segment = functionData.segments.find((seg) =>
          lineInSegment(relLine, seg)
        );

        // Base component highlighting (always show component regions with faint colors)
        if (containingComponent) {
          const colorIndex = getComponentIndex(containingComponent, components);
          backgroundColor = componentColors[colorIndex >= 0 ? colorIndex : 0];
        }

        // Enhanced component highlighting when a specific component is selected
        if (
          highlightComponent &&
          containingComponent &&
          highlightComponent.id === containingComponent.id
        ) {
          backgroundColor = highlightedComponentColor;
          borderLeft = '3px solid #1976d2';
          strongHighlight = true;
        }

        // Segment highlighting (overrides component highlighting)
        if (segment) {
          // Apply stronger highlight if this segment is specifically selected
          if (highlightSegment && segment.id === highlightSegment.id) {
            backgroundColor = highlightedSegmentColors[segment.type];
            borderLeft = '3px solid #f57c00';
            strongHighlight = true;
          }
          // Otherwise, if we're viewing a call segment and not on a component view,
          // just add a light highlight to all segments
          else if (!highlightComponent) {
            // Mix the segment color with existing background
            const segmentColor = segmentColors[segment.type];
            if (
              backgroundColor === 'transparent' ||
              backgroundColor === 'rgba(187, 222, 251, 0.15)'
            ) {
              backgroundColor = segmentColor;
            }
            // Otherwise, the component background will remain
          }
        }
      }

      // Generate the HTML for this line
      codeLines.push(`
                <div class="code-line ${
                  isInFunction ? 'function-highlight' : ''
                } ${strongHighlight ? 'strong-highlight' : ''}" 
                     style="background-color: ${backgroundColor}; ${
        borderLeft ? 'border-left: ' + borderLeft + ';' : ''
      }">
                    <span class="line-number">${lineNumber}</span>
                    <span class="line-content"><code class="language-python">${escapeHTML(
                      lineContent
                    )}</code></span>
                </div>
            `);
    }

    // Add a scroll indicator to jump to the function
    const scrollToFunction = `
            <div class="scroll-indicator">
                <button onclick="document.querySelector('.function-highlight').scrollIntoView({behavior: 'smooth'})">
                    Scroll to Function (Line ${functionStart})
                </button>
            </div>
        `;

    setTimeout(() => {
      Prism.highlightAll();
    }, 100);

    // Return the complete code view
    return `
            ${scrollToFunction}
            <div class="function-code-view">
                <div class="code-container">
                    ${codeLines.join('')}
                </div>
            </div>
        `;
  } catch (error) {
    console.error('Error building function code view:', error);
    return `<p>Error displaying function code: ${error.message}</p>`;
  }
}

// Fallback function for when we can't get the complete file
function fallbackToFunctionOnlyView(
  functionData,
  highlightComponent,
  highlightSegment
) {
  try {
    // Sort segments by line number to ensure correct order
    const sortedSegments = [...functionData.segments].sort(
      (a, b) => a.lineno - b.lineno
    );

    // Create an array to hold all lines of the function
    const totalLines = functionData.end_lineno - functionData.lineno + 1;
    const fileLines = Array(totalLines).fill('');

    // Fill in content from segments
    for (const segment of sortedSegments) {
      const segmentContent = segment.content.split('\n');
      const relStartLine = segment.lineno;

      for (let i = 0; i < segmentContent.length; i++) {
        const fileLineIndex = relStartLine - 1 + i;
        if (fileLineIndex >= 0 && fileLineIndex < totalLines) {
          fileLines[fileLineIndex] = segmentContent[i];
        }
      }
    }

    // Get components for the function
    let components = [];
    try {
      const repoHash = document.querySelector('.repo-info').dataset.repoHash;
      const compResponse = fetch(
        `/code/api/functions/${repoHash}/${functionData.id}/components`
      );
      components = compResponse.json();
    } catch (error) {
      console.warn('Error fetching components:', error);
    }

    // Sort components by start line
    components.sort((a, b) => a.start_lineno - b.start_lineno);

    // Define highlight colors (same as in the main function)
    const componentColors = [
      'rgba(187, 222, 251, 0.15)', // Light blue (very faint)
      'rgba(200, 230, 201, 0.15)', // Light green (very faint)
      'rgba(255, 236, 179, 0.15)', // Light amber (very faint)
    ];

    const segmentColors = {
      code: 'rgba(255, 253, 231, 0.2)', // Light yellow (faint)
      call: 'rgba(255, 232, 230, 0.2)', // Light red (faint)
      comment: 'rgba(245, 245, 245, 0.2)', // Light gray (faint)
    };

    const highlightedComponentColor = 'rgba(187, 222, 251, 0.5)'; // Blue (stronger)

    const highlightedSegmentColors = {
      code: 'rgba(255, 253, 231, 0.7)', // Yellow (stronger)
      call: 'rgba(255, 232, 230, 0.7)', // Red (stronger)
      comment: 'rgba(245, 245, 245, 0.7)', // Gray (stronger)
    };

    // Function to determine if a line belongs to a component
    function lineInComponent(absLine, component) {
      return (
        absLine >= component.start_lineno && absLine <= component.end_lineno
      );
    }

    // Function to determine if a line belongs to a segment
    function lineInSegment(relLine, segment) {
      return (
        relLine >= segment.lineno &&
        (segment.end_lineno
          ? relLine <= segment.end_lineno
          : relLine === segment.lineno)
      );
    }

    // Function to get the component index for coloring
    function getComponentIndex(component, components) {
      const index = components.findIndex((c) => c.id === component.id);
      return index >= 0 ? index % componentColors.length : -1;
    }

    // Build code lines with appropriate highlighting
    let codeLines = [];

    for (let i = 0; i < fileLines.length; i++) {
      const relLine = i + 1; // Relative line number (1-based)
      const absLine = functionData.lineno + i; // Absolute line number
      const lineContent = fileLines[i] || '';

      // Find the component that contains this line
      const containingComponent = components.find((comp) =>
        lineInComponent(absLine, comp)
      );

      // Find the segment that contains this line
      const segment = functionData.segments.find((seg) =>
        lineInSegment(relLine, seg)
      );

      // Determine the background color and highlighting
      let backgroundColor = 'transparent';
      let borderLeft = '';
      let strongHighlight = false;

      // Base component highlighting (always show component regions with faint colors)
      if (containingComponent) {
        const colorIndex = getComponentIndex(containingComponent, components);
        backgroundColor = componentColors[colorIndex >= 0 ? colorIndex : 0];
      }

      // Enhanced component highlighting when a specific component is selected
      if (
        highlightComponent &&
        containingComponent &&
        highlightComponent.id === containingComponent.id
      ) {
        backgroundColor = highlightedComponentColor;
        borderLeft = '3px solid #1976d2';
        strongHighlight = true;
      }

      // Segment highlighting (overrides component highlighting)
      if (segment) {
        // Apply stronger highlight if this segment is specifically selected
        if (highlightSegment && segment.id === highlightSegment.id) {
          backgroundColor = highlightedSegmentColors[segment.type];
          borderLeft = '3px solid #f57c00';
          strongHighlight = true;
        }
        // Otherwise, if we're viewing a call segment and not on a component view,
        // just add a light highlight to all segments
        else if (!highlightComponent) {
          // Mix the segment color with existing background
          const segmentColor = segmentColors[segment.type];
          if (backgroundColor === 'transparent') {
            backgroundColor = segmentColor;
          }
          // Otherwise, the component background will remain
        }
      }

      // Generate the HTML for this line
      codeLines.push(`
                <div class="code-line ${
                  strongHighlight ? 'strong-highlight' : ''
                }" 
                     style="background-color: ${backgroundColor}; ${
        borderLeft ? 'border-left: ' + borderLeft + ';' : ''
      }">
                    <span class="line-number">${relLine}</span>
                    span class="line-content"><code class="language-python">${escapeHTML(
                      lineContent
                    )}</code></span>
                </div>
            `);
    }

    // Return the function-only code view
    return `
            <div class="function-code-view">
                <div class="file-view-note">
                    <p>Note: Showing only the function code. Unable to load the complete file.</p>
                </div>
                <div class="code-container">
                    ${codeLines.join('')}
                </div>
            </div>
        `;
  } catch (error) {
    console.error('Error building fallback function view:', error);
    return `<p>Error displaying function code: ${error.message}</p>`;
  }
}

function applyPrismHighlighting() {
  // Force Prism to re-highlight all code elements
  if (typeof Prism !== 'undefined') {
    Prism.highlightAll();
  }
}

function escapeHTML(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
