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
  segmentNode.dataset.functionId = segment.target_function.id;

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
    currentFilePath = segment.target_function.file_path;

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
