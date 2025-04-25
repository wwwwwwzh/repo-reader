// import { setupFunctionSearch, addToCustomFunctionsList, loadPinnedFunctions } from './search.js';
// import dotenv from '../../../node_modules/dotenv';
// dotenv.config();
// const repos_dir = process.env.REPO_CACHE_DIR;
const repos_dir = '/home/webadmin/projects/code/repos';

let currentFunctionId = null;
let currentFilePath = null;

let repoHash = null;

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
  setUpScrollButton();
  setupQAPanel();
  initializeListeners();
});

window.scrollToHighlight = scrollToHighlight;

function setUpScrollButton() {
  const codeView = document.querySelector('.lower-panel');

  function isInViewport(el) {
    const { top, bottom } = el.getBoundingClientRect();
    return bottom > 0 && top < window.innerHeight;
  }

  codeView.addEventListener('scroll', () => {
    const functionElement = document.querySelector('.function-highlight');
    const scrollButton = document.querySelector('.scroll-function-button');

    if (!functionElement || !scrollButton) return;

    // Show the button only when the highlight is completely out of view
    scrollButton.style.display = isInViewport(functionElement)
      ? 'none'
      : 'block';
  });
}

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
  // console.warn(files);
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
  // console.log(dirFiles);

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
// Update the loadFileContent function to store the file path when a file is loaded
async function loadFileContent(filePath) {
  try {
    // Store the current file path globally
    currentFilePath = filePath;

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

// MARK: Fetch Content
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

// MARK: Code Interaction
// Track if we've already added listeners to prevent duplication
let listenersInitialized = false;

function initializeListeners() {
  addCodeLineListeners();

  // Add a mutation observer to detect when the lower panel content changes
  const lowerPanel = document.getElementById('lower-panel');

  // Configure the observer to be less aggressive
  const observer = new MutationObserver(function (mutations) {
    // Only add listeners if a significant change has occurred
    const significantChange = mutations.some(
      (mutation) =>
        mutation.type === 'childList' &&
        mutation.addedNodes.length > 0 &&
        Array.from(mutation.addedNodes).some(
          (node) => node.classList && node.classList.contains('code-container')
        )
    );

    if (significantChange) {
      // Reset flag to allow re-initialization when new code is loaded
      listenersInitialized = false;
      addCodeLineListeners();
    }
  });

  observer.observe(lowerPanel, {
    childList: true,
    subtree: true,
  });
}

// Function to add click listeners to code lines
function addCodeLineListeners() {
  // Prevent adding listeners multiple times
  if (listenersInitialized) return;
  listenersInitialized = true;

  // Get the lower panel (where the code is displayed)
  const lowerPanel = document.getElementById('lower-panel');

  // Remove any existing listeners (just to be safe)
  lowerPanel.removeEventListener('click', handleCodeLineClick);

  // Add a delegated event listener to the lower panel
  lowerPanel.addEventListener('click', handleCodeLineClick);

  console.log('Code line listeners added.');
}

// Handler function for code line clicks
// Update the handleCodeLineClick function to use the stored file path
function handleCodeLineClick(event) {
  // Find the clicked code line
  const codeLine = event.target.closest('.code-line');
  if (!codeLine) return; // Exit if click wasn't on a code line

  // Get the line number
  const lineNumber = parseInt(
    codeLine.querySelector('.line-number').textContent
  );
  if (isNaN(lineNumber)) return; // Exit if line number is not valid

  // Get repository hash
  const repoHash = document.querySelector('.repo-info').dataset.repoHash;

  // Use the global file path variable, or try to extract it if not available
  let filePath = currentFilePath;

  if (!filePath) {
    // Try to get file path from the function details panel if we're looking at a function
    const filePathElement = document.querySelector('.panel-content .file-path');
    if (filePathElement) {
      filePath = filePathElement.textContent.trim();
    }

    // If still not found, try to get it from the panel title
    if (!filePath) {
      const panelTitle = document.querySelector('.panel-title').textContent;
      if (panelTitle.startsWith('File:')) {
        filePath = panelTitle.replace('File:', '').trim();
      }
    }
  }

  if (!filePath) {
    console.warn("No file path found - can't locate function");
    showTemporaryNotification("Can't determine current file path", 'error');
    return;
  }

  // If we're viewing a function, check if the click is inside that function
  if (currentFunctionId) {
    // Fetch data about the current function to compare line numbers
    fetch(`/code/api/functions/${repoHash}/${currentFunctionId}`)
      .then((response) => response.json())
      .then((functionData) => {
        const functionStartLine = functionData.lineno;
        const functionEndLine = functionData.end_lineno;

        // Check if the clicked line is within the current function's range
        if (lineNumber >= functionStartLine && lineNumber <= functionEndLine) {
          // Use existing behavior to highlight the component
          findAndHighlightComponent(currentFunctionId, lineNumber);
        } else {
          // Line is outside the current function, find the function at this line
          findFunctionAtLine(repoHash, filePath, lineNumber);
        }
      })
      .catch((error) => {
        console.error('Error fetching function data:', error);
        // If we can't determine, try to find a function at the clicked line
        findFunctionAtLine(repoHash, filePath, lineNumber);
      });
  } else {
    // No function is currently loaded, try to find a function at this line
    findFunctionAtLine(repoHash, filePath, lineNumber);
  }
}

async function loadFunctionDetails(repoHash, functionId, is_same_file = false) {
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

    // Store the file path for this function
    currentFilePath = functionData.file_path;

    // Update panel title
    panelTitle.textContent = `Function: ${functionData.name}`;

    // Update upper panel with function summary
    panelContent.innerHTML = buildFunctionSummary(functionData);

    // Update lower panel with complete function code
    const codeView = await buildFullFunctionCodeView(functionData);
    // TODO: if same file, don't use the full buildFullFunctionCodeView, just load the upper pannel and highlight compoennts of the function
    lowerPanel.innerHTML = `
      <h3>Complete Function Code</h3>
      ${codeView}
    `;

    const parentNode = document.querySelector(`.node[data-id="${functionId}"]`);

    if (!is_same_file && parentNode && parentNode.dataset.type === 'function') {
      scrollToHighlight();
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

// Track if we're currently processing a click to prevent multiple highlights
let isProcessingClick = false;

// Find and highlight the component containing the clicked line
async function findAndHighlightComponent(functionId, lineNumber) {
  // Prevent concurrent processing
  if (isProcessingClick) return;
  isProcessingClick = true;

  try {
    // Get repository hash
    const repoHash = document.querySelector('.repo-info').dataset.repoHash;

    // Calculate absolute line number
    const absoluteLineNumber = lineNumber;

    // Fetch components for this function
    const componentsResponse = await fetch(
      `/code/api/functions/${repoHash}/${functionId}/components`
    );
    const components = await componentsResponse.json();

    // Find the component that contains this line
    const containingComponent = components.find(
      (comp) =>
        absoluteLineNumber >= comp.start_lineno &&
        absoluteLineNumber <= comp.end_lineno
    );

    if (!containingComponent) {
      console.log(
        'No component found for line',
        lineNumber,
        'absolute line',
        absoluteLineNumber
      );
      isProcessingClick = false;
      return;
    }

    // Find and highlight the component node in the tree
    highlightComponentNodeInTree(functionId, containingComponent.id);
  } catch (error) {
    console.error('Error finding component for line:', error);
  } finally {
    // Reset processing flag after a delay to prevent rapid clicks
    setTimeout(() => {
      isProcessingClick = false;
    }, 500);
  }
}

// Highlight the component node in the tree
function highlightComponentNodeInTree(functionId, componentId) {
  // First check if the function node is expanded
  const functionNode =
    document.querySelector(`.node[data-id="${functionId}"]`) ||
    document.querySelector(`.node[data-function-id="${functionId}"]`);

  if (!functionNode) {
    console.log('Function node not found:', functionId);
    return;
  }

  const functionCaret = functionNode.querySelector('.caret');
  const functionNested = functionNode.querySelector('.nested');

  if (
    functionCaret &&
    functionNested &&
    !functionNested.classList.contains('active')
  ) {
    // Expand the function node first
    functionCaret.click();
  }

  // Now find the component node
  const componentNode = document.querySelector(
    `.node[data-id="${componentId}"]`
  );
  if (!componentNode) {
    console.log('Component node not found:', componentId);
    return;
  }

  // Find the component caret and click it
  const componentCaret = componentNode.querySelector('.caret');
  if (componentCaret) {
    // Clear other active nodes
    clearActiveNodes();

    // Add active class to this caret
    componentCaret.classList.add('active-node');

    // Scroll the component into view
    componentCaret.scrollIntoView({ behavior: 'smooth', block: 'center' });

    // Optionally, trigger the click event to show component details
    componentCaret.click();
  }
}
