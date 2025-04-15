// Global variables for state management
let currentFunctionId = null;
let repoHash = null;
const treeNav = document.querySelector('.tree-nav');

treeNav.addEventListener('scroll', updateStickyPositions);
window.addEventListener('resize', updateStickyPositions); // optional but handy

document.addEventListener('DOMContentLoaded', () => {
    // Get repository hash from data attribute
    repoHash = document.querySelector('.repo-info').dataset.repoHash;
    
    // Initialize the page
    setupPanelToggling();
    loadEntryFunctions(repoHash);
});

// Set up panel toggling functionality
function setupPanelToggling() {
    const panelHeader = document.getElementById('panel-header');
    const panelToggle = document.getElementById('panel-toggle');
    const upperPanel = document.querySelector('.upper-panel');
    const lowerPanel = document.getElementById('lower-panel');
    
    panelHeader.addEventListener('click', () => {
        upperPanel.classList.toggle('collapsed');
        lowerPanel.classList.toggle('expanded');
        
        // Update the toggle icon
        panelToggle.textContent = upperPanel.classList.contains('collapsed') ? '▼' : '▲';
    });
}

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
        functions.forEach(func => {
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
    nameElement.onclick = function() {
        clearActiveNodes();
        this.classList.add('active-node');
        
        toggleNode(this);
        loadFunctionDetails(repoHash, func.id);
        
        // If expanding and there are no children, load components
        const nested = this.parentElement.querySelector('.nested');
        if (nested && nested.classList.contains('active') && nested.children.length === 0) {
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
        
        if (nodeType === 'function' || 
            nodeType === 'component' || 
            (nodeType === 'segment' && parentNode.dataset.segmentType === 'call')) {
            
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
                childCarets.forEach(childCaret => {
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
    stickyCarets.forEach(caret => {
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
        console.log(`Caret "${caret.textContent.trim()}" set to top: ${topPosition}px, z-index: ${100 - level}`);
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
            fetchFunctionDetails(repoHash, functionId)
        ]);
        
        // Clear loading indicator
        parentElement.innerHTML = '';
        
        if (components.length === 0) {
            // If no components found, display segments directly
            parentElement.innerHTML = '<div class="node">No components found. Showing segments directly:</div>';
            
            // Add segments directly
            if (functionData.segments && functionData.segments.length > 0) {
                loadSegmentsIntoNode(functionData.segments, parentElement, repoHash, functionId);
            } else {
                parentElement.innerHTML += '<div class="node">No segments found</div>';
            }
            return;
        }
        
        // Organize segments by component
        const { componentSegments, unassignedSegments } = organizeSegmentsByComponent(functionData.segments);
        
        // Add each component
        components.forEach(component => {
            addComponentNode(component, componentSegments, parentElement, repoHash, functionId);
        });
        
        // Add unassigned segments node if there are any
        if (unassignedSegments.length > 0) {
            addUnassignedSegmentsNode(unassignedSegments, parentElement, repoHash, functionId);
        }
    } catch (error) {
        console.error('Error loading components:', error);
        parentElement.innerHTML = '<div class="node">Error loading function components</div>';
    }
}

// Fetch function components
async function fetchComponents(repoHash, functionId) {
    const response = await fetch(`/code/api/functions/${repoHash}/${functionId}/components`);
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
        segments.forEach(segment => {
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
function addComponentNode(component, componentSegments, parentElement, repoHash, functionId) {
    const componentNode = document.createElement('div');
    componentNode.className = 'node';
    componentNode.dataset.id = component.id;
    componentNode.dataset.type = 'component';
    componentNode.dataset.functionId = functionId;
    
    const nameElement = document.createElement('span');
    nameElement.className = 'caret node-component';
    // Use short description as the title
    nameElement.textContent = component.short_description || component.name || `Component ${component.index + 1}`;
    
    const segmentsContainer = document.createElement('div');
    segmentsContainer.className = 'nested';
    
    // Get segments for this component
    const segments = componentSegments[component.id] || [];
    
    // Handle click on component name
    nameElement.onclick = function() {
        clearActiveNodes();
        this.classList.add('active-node');
        
        toggleNode(this);
        
        // Display component details
        displayComponentDetails(component, segments, functionId);
        
        // Load segments if expanding
        if (segmentsContainer.classList.contains('active') && segmentsContainer.children.length === 0) {
            if (segments.length > 0) {
                loadSegmentsIntoNode(segments, segmentsContainer, repoHash, functionId);
            } else {
                segmentsContainer.innerHTML = '<div class="node">No segments in this component</div>';
            }
        }
    };
    
    componentNode.appendChild(nameElement);
    componentNode.appendChild(segmentsContainer);
    parentElement.appendChild(componentNode);
}

// Add unassigned segments node
function addUnassignedSegmentsNode(unassignedSegments, parentElement, repoHash, functionId) {
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
    unassignedLabel.onclick = function() {
        clearActiveNodes();
        this.classList.add('active-node');
        
        toggleNode(this);
        
        // Display unassigned segments details
        displayUnassignedSegmentsDetails(unassignedSegments, functionId);
        
        // Load segments if expanding
        if (unassignedContainer.classList.contains('active') && unassignedContainer.children.length === 0) {
            loadSegmentsIntoNode(unassignedSegments, unassignedContainer, repoHash, functionId);
        }
    };
    
    unassignedNode.appendChild(unassignedLabel);
    unassignedNode.appendChild(unassignedContainer);
    parentElement.appendChild(unassignedNode);
}

// Load segments into a node
function loadSegmentsIntoNode(segments, parentElement, repoHash, parentFunctionId) {
    segments.forEach(segment => {
        if (segment.type === 'call' && segment.target_function) {
            addCallSegmentNode(segment, parentElement, repoHash, parentFunctionId);
        } else {
            addNormalSegmentNode(segment, parentElement, parentFunctionId);
        }
    });
}

// Add a call segment node
function addCallSegmentNode(segment, parentElement, repoHash, parentFunctionId) {
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
    segmentLabel.onclick = function() {
        clearActiveNodes();
        this.classList.add('active-node');
        
        toggleNode(this);
        
        // Display segment details
        displaySegmentDetails(segment, segment.target_function.id);
        
        // Load target function components if expanding
        if (targetContainer.classList.contains('active') && targetContainer.children.length === 0) {
            loadFunctionComponents(repoHash, segment.target_function.id, targetContainer);
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
    const contentPreview = segment.content.split("\n")[0].substring(0, 30);
    segmentLabel.textContent = `${segment.type.charAt(0).toUpperCase() + segment.type.slice(1)}: ${contentPreview}... (Line ${segment.lineno})`;
    
    // Handle click on segment
    segmentLabel.onclick = function() {
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
    document.querySelectorAll('.active-node').forEach(node => {
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
    } catch (error) {
        console.error('Error loading function details:', error);
        const panelContent = document.querySelector('.panel-content');
        panelContent.innerHTML = '<p>Error loading function details. Please try again later.</p>';
        document.getElementById('lower-panel').innerHTML = '<p>Error loading function code.</p>';
    }
}

// Build HTML for function summary
function buildFunctionSummaryHTML(functionData) {
    let html = `
        <div class="function-details">
            <div class="file-path">${functionData.full_name}</div>
            <div>Lines: ${functionData.lineno} - ${functionData.end_lineno}</div>
            ${functionData.is_entry ? '<div><strong>Entry Point</strong></div>' : ''}
            ${functionData.class_name ? `<div>Class: ${functionData.class_name}</div>` : ''}
            <div>Module: ${functionData.module_name}</div>
        </div>
    `;
    
    // Add descriptions if available
    if (functionData.short_description || functionData.input_output_description || functionData.long_description) {
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
    panelTitle.textContent = `Component: ${component.short_description || component.name || `Component ${component.index + 1}`}`;
    
    // Ensure panel is expanded
    upperPanel.classList.remove('collapsed');
    lowerPanel.classList.remove('expanded');
    upperPanel.querySelector('.panel-toggle').textContent = '▲';
    
    // Build component summary
    let content = `
        <div class="component">
            <p><strong>Lines:</strong> ${component.start_lineno} - ${component.end_lineno}</p>
            ${component.long_description ? `<p><strong>Detailed Description:</strong> ${component.long_description}</p>` : ''}
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
        
        unassignedSegments.forEach(segment => {
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
            <div><strong>Lines:</strong> ${segment.lineno}${segment.end_lineno ? ` - ${segment.end_lineno}` : ''}</div>
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
    if ((segmentType === 'call' && segment.target_function && targetFunctionId !== currentFunctionId) || 
        targetFunctionId !== currentFunctionId) {
        
        // Update current function ID
        currentFunctionId = targetFunctionId;
        
        // Show loading
        lowerPanel.innerHTML = '<div class="loading"></div>';
        
        try {
            // Fetch function details
            const functionData = await fetchFunctionDetails(repoHash, targetFunctionId);
            
            // Special handling for call segments to show target function
            if (segmentType === 'call' && segment.target_function) {
                const codeView = await buildFullFunctionCodeView(functionData);
                lowerPanel.innerHTML = `
                    <h3>Target Function: ${functionData.name}</h3>
                    ${codeView}
                `;
            } else {
                // Normal handling for other segment types
                const codeView = await buildFullFunctionCodeView(functionData, null, segment);
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
            const functionData = await fetchFunctionDetails(repoHash, targetFunctionId);
            const codeView = await buildFullFunctionCodeView(functionData, null, segment);
            lowerPanel.innerHTML = `
                <h3>Complete Function Code</h3>
                ${codeView}
            `;
        } catch (error) {
            console.error('Error updating segment highlighting:', error);
        }
    }
}

// Helper function to build a complete function code view with highlighting
// Helper function to build a complete function code view with highlighting
async function buildFullFunctionCodeView(functionData, highlightComponent = null, highlightSegment = null) {
    // If functionData is null but we have a current function ID, fetch the function data
    if (!functionData && currentFunctionId) {
        try {
            const repoHash = document.querySelector('.repo-info').dataset.repoHash;
            const response = await fetch(`/code/api/functions/${repoHash}/${currentFunctionId}`);
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
        // Use the file_path and line numbers to get the complete function code
        const filePath = functionData.file_path;
        const startLine = functionData.lineno;
        const endLine = functionData.end_lineno;
        
        // Fetch the file content using an API endpoint
        let fileLines = [];
        let useSegmentsFallback = true;
        
        // Try to get file content from repository if we have required info
        if (filePath && startLine && endLine) {
            try {
                const repoHash = document.querySelector('.repo-info').dataset.repoHash;
                const response = await fetch(`/code/api/file?path=${encodeURIComponent(filePath)}&repo_hash=${repoHash}&line_start=${startLine}&line_end=${endLine}`);
                
                if (response.ok) {
                    const fileContent = await response.text();
                    fileLines = fileContent.split('\n');
                    useSegmentsFallback = false;
                } else {
                    console.warn('Error fetching file content, fallback to segments');
                }
            } catch (fileError) {
                console.warn('Error reading file directly, falling back to segments:', fileError);
                // Continue with segments fallback
            }
        }
        
        // Fallback: reconstruct from segments
        if (useSegmentsFallback) {
            // Sort segments by line number to ensure correct order
            const sortedSegments = [...functionData.segments].sort((a, b) => a.lineno - b.lineno);
            
            // Create an array to hold all lines of the function
            const totalLines = endLine - startLine + 1;
            fileLines = Array(totalLines).fill('');
            
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
        }
        
        // Prepare the code with syntax highlighting for segments
        let codeLines = [];
        
        // Get components for the function
        let components = [];
        try {
            const repoHash = document.querySelector('.repo-info').dataset.repoHash;
            const compResponse = await fetch(`/code/api/functions/${repoHash}/${functionData.id}/components`);
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
            'rgba(187, 222, 251, 0.15)',  // Light blue (very faint)
            'rgba(200, 230, 201, 0.15)',  // Light green (very faint)
            'rgba(255, 236, 179, 0.15)'   // Light amber (very faint)
        ];
        
        const segmentColors = {
            'code': 'rgba(255, 253, 231, 0.2)',    // Light yellow (faint)
            'call': 'rgba(255, 232, 230, 0.2)',    // Light red (faint)
            'comment': 'rgba(245, 245, 245, 0.2)'  // Light gray (faint)
        };
        
        const highlightedComponentColor = 'rgba(187, 222, 251, 0.5)';  // Blue (stronger)
        
        const highlightedSegmentColors = {
            'code': 'rgba(255, 253, 231, 0.7)',    // Yellow (stronger)
            'call': 'rgba(255, 232, 230, 0.7)',    // Red (stronger)
            'comment': 'rgba(245, 245, 245, 0.7)'  // Gray (stronger)
        };
        
        // Function to determine if a line belongs to a component
        function lineInComponent(absLine, component) {
            return absLine >= component.start_lineno && absLine <= component.end_lineno;
        }
        
        // Function to determine if a line belongs to a segment
        function lineInSegment(relLine, segment) {
            return relLine >= segment.lineno && 
                   (segment.end_lineno ? relLine <= segment.end_lineno : relLine === segment.lineno);
        }
        
        // Function to get the component index for coloring
        function getComponentIndex(component, components) {
            const index = components.findIndex(c => c.id === component.id);
            return index >= 0 ? index % componentColors.length : -1;
        }
        
        // Build code lines with appropriate highlighting
        for (let i = 0; i < fileLines.length; i++) {
            const relLine = i + 1;  // Relative line number (1-based)
            const absLine = functionData.lineno + i;  // Absolute line number
            const lineContent = fileLines[i] || '';
            
            // Find the component that contains this line
            const containingComponent = components.find(comp => lineInComponent(absLine, comp));
            
            // Find the segment that contains this line
            const segment = functionData.segments.find(seg => lineInSegment(relLine, seg));
            
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
            if (highlightComponent && containingComponent && highlightComponent.id === containingComponent.id) {
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
                <div class="code-line ${strongHighlight ? 'strong-highlight' : ''}" 
                     style="background-color: ${backgroundColor}; ${borderLeft ? 'border-left: ' + borderLeft + ';' : ''}">
                    <span class="line-number">${relLine}</span>
                    <span class="line-content">${escapeHTML(lineContent)}</span>
                </div>
            `);
        }
        
        // Return the complete code view
        return `
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

function escapeHTML(str) {
    if (!str) return '';
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
        
      