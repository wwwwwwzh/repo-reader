// Add handler for the toggle button
document
  .getElementById('show-interactive-tree')
  .addEventListener('click', function () {
    // Create and show the interactive tree panel
    setupInteractiveTree();

    // Add class to body to indicate tree panel is visible
    document.body.classList.add('tree-panel-visible');

    // Hide the button
    this.style.display = 'none';
  });

// Initialize the interactive tree when the page is loaded
document.addEventListener('DOMContentLoaded', () => {
  // Connect function selection in the normal tree view with the interactive tree
  connectRegularTreeToInteractiveTree();
  
  // Add global function to window to allow other scripts to interact with the tree
  window.interactiveTree = {
    highlight: highlightNode,
    select: selectFunction,
    update: updateVisualization,
    expandAll: expandAllNodes,
    collapseAll: collapseAllNodes,
  };
});

// Connect interactions between regular tree view and interactive visualization
function connectRegularTreeToInteractiveTree() {
  const observer = new MutationObserver(function (mutations) {
    mutations.forEach(function (mutation) {
      if (
        mutation.type === 'attributes' &&
        mutation.attributeName === 'class'
      ) {
        const node = mutation.target;
        if (
          node.classList.contains('active-node') &&
          node.parentNode.dataset.id
        ) {
          // A node was selected in the regular tree view
          const functionId = node.parentNode.dataset.id;

          // If interactive tree is initialized and visible, highlight the node there
          if (
            window.interactiveTree &&
            !document.querySelector('.floating-tree-panel.collapsed')
          ) {
            window.interactiveTree.highlight(functionId);
          }
        }
      }
    });
  });

  // Observe all tree-nav changes
  const treeNav = document.querySelector('.tree-nav');
  if (treeNav) {
    observer.observe(treeNav, {
      attributes: true,
      subtree: true,
    });
  }

  // Connect function links in QA panel responses
  document.addEventListener('click', function (e) {
    if (
      e.target.classList.contains('function-link') &&
      e.target.dataset.functionId
    ) {
      const functionId = e.target.dataset.functionId;

      // If interactive tree is initialized and visible, highlight the node there
      if (
        window.interactiveTree &&
        !document.querySelector('.floating-tree-panel.collapsed')
      ) {
        window.interactiveTree.select(functionId);
      }
    }
  });
}

// Interactive Function Tree Visualization
// This script creates a floating, interactive tree visualization of function call relationships
function setupInteractiveTree() {
  // Create the floating panel for the tree visualization
  createFloatingPanel();

  // Set up the event handlers
  initializeEventHandlers();

  // If repository hash is available, load the entry functions
  const repoHash = document.querySelector('.repo-info')?.dataset?.repoHash;
  if (repoHash) {
    // Initial load of entry functions as roots
    loadEntryFunctionsAsRoots(repoHash);
  }
}

function createFloatingPanel() {
  // Check if panel already exists
  if (document.getElementById('interactive-tree-panel')) {
    return;
  }

  // Create the floating panel
  const panel = document.createElement('div');
  panel.id = 'interactive-tree-panel';
  panel.className = 'floating-tree-panel';

  // Add panel header with title and controls
  panel.innerHTML = `
      <div class="tree-header">
        <h3>Function Call Tree</h3>
        <div class="tree-header-controls">
          <button id="tree-expand-all" title="Expand All Nodes">⊞</button>
          <button id="tree-collapse-all" title="Collapse All Nodes">⊟</button>
          <button id="tree-toggle" class="tree-toggle-btn">_</button>
        </div>
      </div>
      <div class="tree-container">
        <div id="tree-loader" class="tree-loader">Loading function data...</div>
        <div id="interactive-tree-viz"></div>
      </div>
      <div class="tree-controls">
        <select id="tree-layout-select">
          <option value="tree">Tree Layout</option>
          <option value="radial">Radial Layout</option>
        </select>
        <div class="tree-depth-control">
          <label for="tree-expansion-depth">Expansion Depth:</label>
          <input type="range" id="tree-expansion-depth" min="1" max="10" value="2">
          <span id="depth-value">2</span>
        </div>
      </div>
    `;

  document.body.appendChild(panel);

  // Make the panel draggable
  makeDraggable(panel, panel.querySelector('.tree-header'));
}

function initializeEventHandlers() {
  // Ensure the panel exists
  const panel = document.getElementById('interactive-tree-panel');
  if (!panel) return;

  // Toggle panel expansion/collapse
  const toggleBtn = document.getElementById('tree-toggle');
  toggleBtn.addEventListener('click', () => {
    panel.classList.toggle('collapsed');
    toggleBtn.textContent = panel.classList.contains('collapsed') ? '□' : '_';

    // If expanding, update the visualization to fit
    if (!panel.classList.contains('collapsed')) {
      updateVisualization();
    }
  });

  // Layout selector
  const layoutSelect = document.getElementById('tree-layout-select');
  layoutSelect.addEventListener('change', () => {
    updateVisualization();
  });

  // Depth slider
  const depthSlider = document.getElementById('tree-expansion-depth');
  const depthValue = document.getElementById('depth-value');
  depthSlider.addEventListener('input', () => {
    depthValue.textContent = depthSlider.value;
  });
  depthSlider.addEventListener('change', () => {
    // When slider value is confirmed, update the default expansion depth
    window.treeDefaultExpansionDepth = parseInt(depthSlider.value);
  });

  // Expand all button
  document.getElementById('tree-expand-all').addEventListener('click', () => {
    expandAllNodes();
  });

  // Collapse all button
  document.getElementById('tree-collapse-all').addEventListener('click', () => {
    collapseAllNodes();
  });
}

// Update tree visualization based on current data and layout
function updateVisualization() {
  if (!window.treeData || !window.treeData.nodes.length) return;

  const container = document.getElementById('interactive-tree-viz');
  const layoutType = document.getElementById('tree-layout-select').value;

  // Clear previous visualization
  container.innerHTML = '';

  // Set dimensions
  const containerRect = container.getBoundingClientRect();
  const width = containerRect.width || 600;
  const height = containerRect.height || 400;

  // Create the hierarchical data structure for visualization
  const root = createHierarchy();

  // Render based on selected layout type
  if (layoutType === 'tree') {
    renderTreeLayout(container, root, width, height);
  } else if (layoutType === 'radial') {
    renderRadialLayout(container, root, width, height);
  }
}

// Create hierarchical data for tree layouts
function createHierarchy() {
  const entryNodes = window.treeData.nodes.filter((n) => n.isEntry);
  
  // Create root node
  const root = {
    id: 'root',
    name: 'Root',
    children: [],
  };

  // Add entry nodes as children of root
  for (const entryNode of entryNodes) {
    root.children.push(buildHierarchyNode(entryNode.id, new Set()));
  }

  return d3.hierarchy(root);
}

// Build hierarchical tree recursively
function buildHierarchyNode(nodeId, visitedNodes) {
  if (visitedNodes.has(nodeId)) {
    // Circular reference - create a placeholder node
    const node = window.treeData.nodes.find((n) => n.id === nodeId);
    return {
      id: nodeId + '_circular',
      name: node.name + ' (circular)',
      fullName: node.fullName,
      shortDescription: node.shortDescription,
      longDescription: node.longDescription,
      isCircular: true,
      _originalId: nodeId,
    };
  }

  visitedNodes.add(nodeId);

  const node = window.treeData.nodes.find((n) => n.id === nodeId);
  if (!node) return null;

  const hierarchyNode = {
    id: nodeId,
    name: node.name,
    fullName: node.fullName,
    shortDescription: node.shortDescription,
    longDescription: node.longDescription,
    expanded: node.expanded,
    isEntry: node.isEntry,
    children: [],
  };

  if (node.expanded) {
    // Get child node IDs
    const childIds = window.treeData.links
      .filter((l) => l.source === nodeId)
      .map((l) => l.target);

    // Recursively build children
    for (const childId of childIds) {
      const childNode = buildHierarchyNode(
        childId,
        new Set([...visitedNodes])
      );
      if (childNode) {
        hierarchyNode.children.push(childNode);
      }
    }
  }

  return hierarchyNode;
}

// Render horizontal tree layout
function renderTreeLayout(container, root, width, height) {
  // Create SVG
  const svg = d3
    .create('svg')
    .attr('width', width)
    .attr('height', height)
    .attr('viewBox', [0, 0, width, height])
    .attr('style', 'max-width: 100%; height: auto; font: 10px sans-serif;');

  // Add a group for zoom/pan
  const g = svg.append('g');

  // Create zoom behavior
  const zoom = d3
    .zoom()
    .scaleExtent([0.1, 8])
    .on('zoom', (event) => {
      g.attr('transform', event.transform);
    });

  // Apply zoom to SVG
  svg.call(zoom);

  // Create tree layout
  const treeLayout = d3
    .tree()
    .size([height - 40, width - 160])
    .nodeSize([40, 160]);

  // Apply layout
  const treeData = treeLayout(root);

  // Create marker for arrow
  svg.append('defs').append('marker')
    .attr('id', 'arrowhead')
    .attr('refX', 6)
    .attr('refY', 3)
    .attr('markerWidth', 10)
    .attr('markerHeight', 6)
    .attr('orient', 'auto')
    .append('path')
    .attr('d', 'M0,0 L0,6 L6,3 z')
    .attr('fill', '#999');

  // Draw links
  g.append('g')
    .attr('fill', 'none')
    .attr('stroke', '#999')
    .attr('stroke-opacity', 0.4)
    .attr('stroke-width', 1.5)
    .selectAll('path')
    .data(treeData.links())
    .join('path')
    .attr('marker-end', 'url(#arrowhead)')
    .attr('d', d3.linkHorizontal()
      .x((d) => d.y)
      .y((d) => d.x)
    );

  // Draw nodes
  const node = g
    .append('g')
    .selectAll('g')
    .data(treeData.descendants())
    .join('g')
    .attr('transform', (d) => `translate(${d.y},${d.x})`)
    .attr('class', (d) => {
      const classes = ['tree-node'];
      if (d.data.isEntry) classes.push('entry-point');
      if (d.data.expanded) classes.push('expanded');
      if (d.data.isCircular) classes.push('circular');
      return classes.join(' ');
    })
    .attr('data-id', (d) => d.data.id)
    .on('click', (event, d) => {
      if (d.data.id !== 'root' && !d.data.isCircular) {
        // Toggle node expansion
        toggleInteractiveTreeNode(d.data.id);
        
        // Highlight this node and its subnodes
        highlightNodeAndSubnodes(d.data.id);
        
        // Load function details in the code panel
        const repoHash = document.querySelector('.repo-info').dataset.repoHash;
        loadFunctionDetails(repoHash, d.data.id);
        
        // Also add to custom functions list for easy access later
        if (d.data.name && d.data.fullName) {
          addToCustomFunctionsList(d.data.id, d.data.name, d.data.fullName);
        }
      }
    });

  // Add circles to nodes
  node
    .append('circle')
    .attr('r', 5)
    .attr('fill', (d) =>
      d.data.isEntry ? '#bbdefb' : d.data.expanded ? '#e3f2fd' : '#fff'
    )
    .attr('stroke', (d) => (d.data.isEntry ? '#0d47a1' : '#1976d2'))
    .attr('stroke-width', (d) => (d.data.isEntry ? 2 : 1.5));

  // Add function name above node (except for root and entry points)
  node
    .filter(d => d.data.id !== 'root' && !d.data.isEntry)
    .append('text')
    .attr('dy', '-0.5em')
    .attr('x', (d) => (d.children ? -8 : 8))
    .attr('text-anchor', (d) => (d.children ? 'end' : 'start'))
    .attr('class', 'node-label-name')
    .text((d) => d.data.name)
    .clone(true)
    .lower()
    .attr('stroke', 'white')
    .attr('stroke-width', 3);

  // Add module path below node for all nodes except root
  node
    .filter(d => d.data.id !== 'root')
    .append('text')
    .attr('dy', '1.2em')
    .attr('x', (d) => (d.children ? -8 : 8))
    .attr('text-anchor', (d) => (d.children ? 'end' : 'start'))
    .attr('class', 'node-label-path')
    .attr('font-size', '8px')
    .text((d) => d.data.fullName || '')
    .clone(true)
    .lower()
    .attr('stroke', 'white')
    .attr('stroke-width', 3);

  // Add tooltips with descriptions
  node
    .append('title')
    .text((d) => {
      if (d.data.id === 'root') return '';
      
      let tooltip = d.data.fullName || '';
      
      if (d.data.shortDescription) {
        tooltip += '\n\nDescription: ' + d.data.shortDescription;
      }
      
      if (d.data.longDescription) {
        tooltip += '\n\nDetails: ' + d.data.longDescription;
      }
      
      return tooltip;
    });

  // Center the tree
  centerTreeVisualization(g, treeData, width, height);

  // Append the SVG to the container
  container.appendChild(svg.node());
}

// Render radial tree layout
function renderRadialLayout(container, root, width, height) {
  // Create SVG
  const svg = d3
    .create('svg')
    .attr('width', width)
    .attr('height', height)
    .attr('viewBox', [0, 0, width, height])
    .attr('style', 'max-width: 100%; height: auto; font: 10px sans-serif;');

  // Add a group for zoom/pan
  const g = svg.append('g')
    .attr('transform', `translate(${width / 2},${height / 2})`);

  // Create zoom behavior
  const zoom = d3
    .zoom()
    .scaleExtent([0.1, 8])
    .on('zoom', (event) => {
      g.attr('transform', `translate(${width / 2 + event.transform.x},${height / 2 + event.transform.y}) scale(${event.transform.k})`);
    });

  // Apply zoom to SVG
  svg.call(zoom);

  // Compute the radial layout
  const radius = Math.min(width, height) / 2 - 50;
  const tree = d3
    .tree()
    .size([2 * Math.PI, radius])
    .separation((a, b) => (a.parent === b.parent ? 1 : 2) / a.depth);

  // Apply the layout
  const treeData = tree(root);

  // Create marker for arrow
  svg.append('defs').append('marker')
    .attr('id', 'radial-arrowhead')
    .attr('refX', 6)
    .attr('refY', 3)
    .attr('markerWidth', 10)
    .attr('markerHeight', 6)
    .attr('orient', 'auto')
    .append('path')
    .attr('d', 'M0,0 L0,6 L6,3 z')
    .attr('fill', '#999');

  // Draw links with arrow markers
  g.append('g')
    .attr('fill', 'none')
    .attr('stroke', '#999')
    .attr('stroke-opacity', 0.4)
    .attr('stroke-width', 1.5)
    .selectAll('path')
    .data(treeData.links())
    .join('path')
    .attr('marker-end', 'url(#radial-arrowhead)')
    .attr('d', d3.linkRadial()
      .angle(d => d.x)
      .radius(d => d.y)
    );

  // Helper function to calculate points on a circle
  function radialPoint(x, y) {
    return [(y = +y) * Math.cos((x -= Math.PI / 2)), y * Math.sin(x)];
  }

  // Draw nodes
  const node = g
    .append('g')
    .selectAll('g')
    .data(treeData.descendants())
    .join('g')
    .attr('transform', (d) => `translate(${radialPoint(d.x, d.y)})`)
    .attr('class', (d) => {
      const classes = ['tree-node'];
      if (d.data.isEntry) classes.push('entry-point');
      if (d.data.expanded) classes.push('expanded');
      if (d.data.isCircular) classes.push('circular');
      return classes.join(' ');
    })
    .attr('data-id', (d) => d.data.id)
    .on('click', (event, d) => {
      if (d.data.id !== 'root' && !d.data.isCircular) {
        // Toggle node expansion
        toggleInteractiveTreeNode(d.data.id);
        
        // Highlight this node and its subnodes
        highlightNodeAndSubnodes(d.data.id);
        
        // Load function details in the code panel
        const repoHash = document.querySelector('.repo-info').dataset.repoHash;
        loadFunctionDetails(repoHash, d.data.id);
        
        // Also add to custom functions list for easy access later
        if (d.data.name && d.data.fullName) {
          addToCustomFunctionsList(d.data.id, d.data.name, d.data.fullName);
        }
      }
    });

  // Add circles to nodes
  node
    .append('circle')
    .attr('r', 5)
    .attr('fill', (d) =>
      d.data.isEntry ? '#bbdefb' : d.data.expanded ? '#e3f2fd' : '#fff'
    )
    .attr('stroke', (d) => (d.data.isEntry ? '#0d47a1' : '#1976d2'))
    .attr('stroke-width', (d) => (d.data.isEntry ? 2 : 1.5));

  // Add function name above for non-root and non-entry nodes
  node
    .filter(d => d.data.id !== 'root' && !d.data.isEntry)
    .append('text')
    .attr('dy', '-0.5em')
    .attr('x', (d) => (d.x < Math.PI === !d.children ? 6 : -6))
    .attr('text-anchor', (d) => (d.x < Math.PI === !d.children ? 'start' : 'end'))
    .attr('transform', (d) => (d.x >= Math.PI ? 'rotate(180)' : null))
    .attr('class', 'node-label-name')
    .text((d) => d.data.name)
    .clone(true)
    .lower()
    .attr('stroke', 'white')
    .attr('stroke-width', 3);

  // Add module path below node
  node
    .filter(d => d.data.id !== 'root')
    .append('text')
    .attr('dy', '1.2em')
    .attr('x', (d) => (d.x < Math.PI === !d.children ? 6 : -6))
    .attr('text-anchor', (d) => (d.x < Math.PI === !d.children ? 'start' : 'end'))
    .attr('transform', (d) => (d.x >= Math.PI ? 'rotate(180)' : null))
    .attr('class', 'node-label-path')
    .attr('font-size', '8px')
    .text((d) => {
      // Show full path for all nodes
      return d.data.fullName || '';
    })
    .clone(true)
    .lower()
    .attr('stroke', 'white')
    .attr('stroke-width', 3);

  // Add tooltips with descriptions
  node
    .append('title')
    .text((d) => {
      if (d.data.id === 'root') return '';
      
      let tooltip = d.data.fullName || '';
      
      if (d.data.shortDescription) {
        tooltip += '\n\nDescription: ' + d.data.shortDescription;
      }
      
      if (d.data.longDescription) {
        tooltip += '\n\nDetails: ' + d.data.longDescription;
      }
      
      return tooltip;
    });

  // Append the SVG to the container
  container.appendChild(svg.node());
}

// Center the tree visualization
function centerTreeVisualization(g, treeData, width, height) {
  // Calculate bounds of the tree
  const bounds = treeData.descendants().reduce(
    (bounds, node) => {
      return {
        minX: Math.min(bounds.minX, node.y),
        minY: Math.min(bounds.minY, node.x),
        maxX: Math.max(bounds.maxX, node.y),
        maxY: Math.max(bounds.maxY, node.x),
      };
    },
    { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity }
  );

  // Calculate translation to center the visualization
  const dx = width / 2 - (bounds.minX + bounds.maxX) / 2;
  const dy = height / 2 - (bounds.minY + bounds.maxY) / 2;
  
  g.attr('transform', `translate(${dx},${dy})`);
  
  // Store initial transform to handle first user interaction properly
  g.attr('data-initial-transform', `translate(${dx},${dy})`);
}

// Highlight a node and all its subnodes
// Highlight a node and all its sub-nodes (only inside the interactive SVG)
function highlightNodeAndSubnodes(nodeId) {
  const container = document.getElementById('interactive-tree-viz');
  if (!container) return;

  // 1) clear any old highlights in this panel
  container
    .querySelectorAll('.tree-node.highlight')
    .forEach(el => el.classList.remove('highlight'));

  // 2) do a DFS on treeData.links, but only within this panel
  const visited = new Set();
  function dfs(id) {
    if (visited.has(id)) return;
    visited.add(id);

    // highlight this node if it exists in the panel
    const nodeEl = container.querySelector(`.tree-node[data-id="${id}"]`);
    if (nodeEl) nodeEl.classList.add('highlight');

    // for each outgoing link in the current treeData
    window.treeData.links
      .filter(link => link.source === id)
      .forEach(link => dfs(link.target));
  }

  dfs(nodeId);
}


// Recursive function to highlight a subtree
function highlightSubtree(nodeId, visited) {
  if (visited.has(nodeId)) return;
  visited.add(nodeId);
  
  // Highlight this node
  const nodeElement = document.querySelector(`.tree-node[data-id="${nodeId}"]`);
  if (nodeElement) {
    nodeElement.classList.add('highlight');
  }
  
  // Find all outgoing links
  const outgoingLinks = window.treeData.links.filter(l => l.source === nodeId);
  
  // Recursively highlight subnodes
  for (const link of outgoingLinks) {
    highlightSubtree(link.target, visited);
  }
}

// Highlight a specific node in the visualization
function highlightNode(nodeId) {
  // Find the node element in the visualization
  const nodeElement = document.querySelector(`.tree-node[data-id="${nodeId}"]`);

  if (nodeElement) {
    // Remove highlight from any previously highlighted nodes
    document.querySelectorAll('.tree-node.highlight').forEach((node) => {
      node.classList.remove('highlight');
    });

    // Add highlight class to this node
    nodeElement.classList.add('highlight');

    // Scroll node into view
    nodeElement.scrollIntoView({
      behavior: 'smooth',
      block: 'center',
    });
  }
}

// Function to select a function in the tree and show its details
function selectFunction(functionId) {
  // Highlight the node in the tree
  highlightNode(functionId);

  // Get repository hash
  const repoHash = document.querySelector('.repo-info').dataset.repoHash;
  
  // Show function details in the main panel (reuse existing function)
  loadFunctionDetails(repoHash, functionId);

  // Make sure the node is in view
  expandToNode(functionId);
  
  // Find the node data to add to custom functions list
  const node = window.treeData?.nodes.find(n => n.id === functionId);
  if (node) {
    // Add to custom functions list for easy access
    addToCustomFunctionsList(node.id, node.name, node.fullName);
  } else {
    // If node not found in our data, fetch it from API
    fetch(`/code/api/functions/${repoHash}/${functionId}`)
      .then(response => response.json())
      .then(data => {
        if (data && data.name && data.full_name) {
          addToCustomFunctionsList(data.id, data.name, data.full_name);
        }
      })
      .catch(error => console.error('Error fetching function details:', error));
  }
}

// Expand tree to show a specific node
async function expandToNode(nodeId) {
  const node = window.treeData.nodes.find((n) => n.id === nodeId);
  if (!node) return;

  // If node is already visible, just highlight it
  const nodeElement = document.querySelector(`.tree-node[data-id="${nodeId}"]`);
  if (nodeElement) {
    highlightNode(nodeId);
    return;
  }

  // Find path to the node from entry points
  const path = findPathToNode(nodeId);
  if (!path.length) return;

  // Expand all nodes along the path
  const repoHash = document.querySelector('.repo-info').dataset.repoHash;
  const loader = document.getElementById('tree-loader');
  loader.style.display = 'block';

  for (const pathNodeId of path) {
    const pathNode = window.treeData.nodes.find((n) => n.id === pathNodeId);
    if (pathNode && !pathNode.expanded) {
      pathNode.expanded = true;

      if (!pathNode.childrenLoaded) {
        await loadFunctionCallees(repoHash, pathNode, 1);
      }
    }
  }

  loader.style.display = 'none';

  // Update visualization and highlight node
  updateVisualization();

  // Add a delay to allow the DOM to update
  setTimeout(() => {
    highlightNode(nodeId);
  }, 100);
}

// Find a path from an entry point to a specific node
function findPathToNode(nodeId) {
  const visitedNodes = new Set();

  function dfs(currentId, path = []) {
    // Prevent infinite recursion
    if (visitedNodes.has(currentId)) return null;
    visitedNodes.add(currentId);

    // If this is the target node, return the path
    if (currentId === nodeId) return [...path, currentId];

    // Get links where this node is the source
    const outgoingLinks = window.treeData.links.filter(
      (l) => l.source === currentId
    );

    // Check each child
    for (const link of outgoingLinks) {
      const targetId = link.target;
      const result = dfs(targetId, [...path, currentId]);
      if (result) return result;
    }

    return null;
  }

  // Try to find a path from each entry point
  const entryNodes = window.treeData.nodes.filter((n) => n.isEntry);

  for (const entryNode of entryNodes) {
    const path = dfs(entryNode.id);
    if (path) return path;
  }

  return [];
}

// Expand all nodes
async function expandAllNodes() {
  const repoHash = document.querySelector('.repo-info').dataset.repoHash;
  const loader = document.getElementById('tree-loader');
  loader.style.display = 'block';

  // Mark all nodes as expanded
  for (const node of window.treeData.nodes) {
    node.expanded = true;

    // Load children if not already loaded
    if (!node.childrenLoaded) {
      await loadFunctionCallees(repoHash, node, 1);
    }
  }

  loader.style.display = 'none';
  updateVisualization();
}

// Collapse all nodes
function collapseAllNodes() {
  // Mark all non-entry nodes as collapsed
  for (const node of window.treeData.nodes) {
    if (!node.isEntry) {
      node.expanded = false;
    }
  }

  updateVisualization();
}

// Collapse all nodes
function collapseAllNodes() {
  // Mark all non-entry nodes as collapsed
  for (const node of window.treeData.nodes) {
    if (!node.isEntry) {
      node.expanded = false;
    }
  }

  updateVisualization();
}

// MARK: loading
// Load entry functions as roots of the tree
async function loadEntryFunctionsAsRoots(repoHash) {
  // Show loader
  const loader = document.getElementById('tree-loader');
  loader.style.display = 'block';

  try {
    // Fetch entry functions
    const response = await fetch(`/code/api/functions/${repoHash}/entries`);
    if (!response.ok) {
      throw new Error(`Failed to load entry functions: ${response.statusText}`);
    }

    const entryFunctions = await response.json();

    if (entryFunctions.length === 0) {
      document.getElementById('interactive-tree-viz').innerHTML =
        '<div class="tree-empty-state">No entry functions found for this repository.</div>';
      loader.style.display = 'none';
      return;
    }

    // Initialize the tree data structure
    window.treeData = {
      nodes: [],
      links: [],
    };

    // Default expansion depth
    window.treeDefaultExpansionDepth = parseInt(
      document.getElementById('tree-expansion-depth').value
    );

    // Add entry functions as root nodes
    for (const func of entryFunctions) {
      const node = {
        id: func.id,
        name: func.name,
        fullName: func.full_name,
        filePath: func.file_path,
        shortDescription: func.short_description,
        longDescription: func.long_description,
        isEntry: true,
        expanded: true,
        children: [],
        childrenLoaded: false,
      };

      window.treeData.nodes.push(node);

      // Load initial children
      await loadFunctionCallees(
        repoHash,
        node,
        window.treeDefaultExpansionDepth
      );
    }

    // Render the initial tree
    updateVisualization();
  } catch (error) {
    console.error('Error loading entry functions:', error);
    document.getElementById(
      'interactive-tree-viz'
    ).innerHTML = `<div class="tree-error">Error loading function data: ${error.message}</div>`;
  } finally {
    loader.style.display = 'none';
  }
}

// Load functions called by a given function
async function loadFunctionCallees(
  repoHash,
  parentNode,
  maxDepth = 1,
  currentDepth = 0
) {
  if (currentDepth >= maxDepth || parentNode.childrenLoaded) {
    return;
  }

  try {
    // Fetch functions called by this function
    const response = await fetch(
      `/code/api/functions/${repoHash}/${parentNode.id}/callees`
    );
    if (!response.ok) {
      throw new Error(`Failed to load callees: ${response.statusText}`);
    }

    const callees = await response.json();

    // Mark as loaded
    parentNode.childrenLoaded = true;

    // Process each callee
    for (const callee of callees) {
      // Check if node already exists in the tree
      let childNode = window.treeData.nodes.find((n) => n.id === callee.id);

      if (!childNode) {
        // Get additional function details like descriptions
        const detailsResponse = await fetch(
          `/code/api/functions/${repoHash}/${callee.id}`
        );
        let childDetails = {};

        if (detailsResponse.ok) {
          const details = await detailsResponse.json();
          childDetails = {
            shortDescription: details.short_description,
            longDescription: details.long_description,
          };
        }

        // Create new node
        childNode = {
          id: callee.id,
          name: callee.name,
          fullName: callee.full_name,
          filePath: callee.file_path,
          shortDescription: childDetails.shortDescription || '',
          longDescription: childDetails.longDescription || '',
          isEntry: false,
          expanded: currentDepth < maxDepth - 1,
          children: [],
          childrenLoaded: false,
        };

        // Add to global nodes list
        window.treeData.nodes.push(childNode);
      }

      // Add link to parent if it doesn't already exist
      const linkExists = window.treeData.links.some(
        (link) => link.source === parentNode.id && link.target === childNode.id
      );

      if (!linkExists) {
        window.treeData.links.push({
          source: parentNode.id,
          target: childNode.id,
        });

        // Add to parent's children array for tracking
        parentNode.children.push(childNode.id);
      }

      // Recursively load this node's children if expanded
      if (childNode.expanded && currentDepth < maxDepth - 1) {
        await loadFunctionCallees(
          repoHash,
          childNode,
          maxDepth,
          currentDepth + 1
        );
      }
    }
  } catch (error) {
    console.error(
      `Error loading callees for function ${parentNode.id}:`,
      error
    );
    parentNode.error = error.message;
  }
}

// Toggle node expansion
async function toggleInteractiveTreeNode(nodeId) {
  const node = window.treeData.nodes.find((n) => n.id === nodeId);
  if (!node) return;

  // Toggle expanded state
  node.expanded = !node.expanded;

  const repoHash = document.querySelector('.repo-info').dataset.repoHash;

  if (node.expanded && !node.childrenLoaded) {
    // Show loader
    const loader = document.getElementById('tree-loader');
    loader.style.display = 'block';

    // Load children
    await loadFunctionCallees(repoHash, node, window.treeDefaultExpansionDepth);

    // Hide loader
    loader.style.display = 'none';
  }

  // Update visualization
  updateVisualization();
}
