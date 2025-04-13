document.addEventListener('DOMContentLoaded', () => {
    const repoHash = document.querySelector('.repo-info').dataset.repoHash;
    loadFunctions(repoHash);
});

async function loadFunctions(repoHash) {
    try {
        // Show loading indicator
        const treeContainer = document.getElementById('tree');
        treeContainer.innerHTML = '<div id="loading-tree" class="loading"></div>';
        
        // Fetch all entry functions for the repository
        const response = await fetch(`/code/api/functions/${repoHash}/entries`);
        const functions = await response.json();
        
        // Remove loading indicator
        document.getElementById('loading-tree')?.remove();
        
        if (functions.length === 0) {
            treeContainer.innerHTML = '<p>No functions found for this repository.</p>';
            return;
        }
        
        // Create a structured tree of functions
        const treeRoot = document.createElement('div');
        treeRoot.className = 'tree-root';
        
        // Group functions by module for better organization
        const moduleGroups = groupByModule(functions);
        
        // Build the tree
        for (const [moduleName, moduleFunctions] of Object.entries(moduleGroups)) {
            // Create module group
            const moduleNode = document.createElement('div');
            moduleNode.className = 'node node-root';
            
            // Create module header
            const moduleLabel = document.createElement('span');
            moduleLabel.className = 'caret';
            moduleLabel.textContent = moduleName || 'Main';
            moduleLabel.onclick = () => toggleNode(moduleLabel);
            
            // Create container for functions in this module
            const moduleChildren = document.createElement('div');
            moduleChildren.className = 'nested';
            
            // Add each function in this module
            moduleFunctions.forEach(func => {
                const funcNode = createFunctionNode(func, repoHash);
                moduleChildren.appendChild(funcNode);
            });
            
            // Assemble module node
            moduleNode.appendChild(moduleLabel);
            moduleNode.appendChild(moduleChildren);
            treeRoot.appendChild(moduleNode);
        }
        
        treeContainer.appendChild(treeRoot);
        
        // Expand the first module by default
        const firstModule = treeContainer.querySelector('.caret');
        if (firstModule) {
            toggleNode(firstModule);
        }
    } catch (error) {
        console.error('Error loading functions:', error);
        document.getElementById('tree').innerHTML = 
            '<p>Error loading function data. Please try again later.</p>';
    }
}

function groupByModule(functions) {
    const groups = {};
    
    functions.forEach(func => {
        const moduleName = func.module_name || 'Undefined';
        if (!groups[moduleName]) {
            groups[moduleName] = [];
        }
        groups[moduleName].push(func);
    });
    
    // Sort functions within each module by name
    for (const moduleName in groups) {
        groups[moduleName].sort((a, b) => a.name.localeCompare(b.name));
    }
    
    return groups;
}

function createFunctionNode(func, repoHash) {
    const funcNode = document.createElement('div');
    funcNode.className = 'node';
    funcNode.dataset.id = func.id;
    funcNode.dataset.type = 'function';
    
    const funcLabel = document.createElement('span');
    funcLabel.className = 'caret';
    funcLabel.textContent = func.name;
    funcLabel.onclick = function() {
        toggleNode(this);
        
        // Load function details if not already loaded
        const nestedContainer = funcNode.querySelector('.nested');
        if (nestedContainer && nestedContainer.children.length === 0) {
            loadFunctionSegments(repoHash, func.id, nestedContainer);
        }
        
        // Also display function details in the right panel
        displayFunctionDetails(repoHash, func.id);
    };
    
    // Create container for segments
    const segmentsContainer = document.createElement('div');
    segmentsContainer.className = 'nested';
    
    funcNode.appendChild(funcLabel);
    funcNode.appendChild(segmentsContainer);
    
    return funcNode;
}

function toggleNode(element) {
    element.classList.toggle('caret-down');
    const nested = element.parentElement.querySelector('.nested');
    if (nested) {
        nested.classList.toggle('active');
    }
}

async function loadFunctionSegments(repoHash, functionId, container) {
    try {
        // Show loading
        container.innerHTML = '<div class="loading"></div>';
        
        // Fetch function details
        const response = await fetch(`/code/api/functions/${repoHash}/${functionId}`);
        const func = await response.json();
        
        // Remove loading
        container.innerHTML = '';
        
        if (!func.segments || func.segments.length === 0) {
            container.innerHTML = '<div class="node"><span>No segments available</span></div>';
            return;
        }
        
        // Add segments to container
        func.segments.forEach((segment, index) => {
            const segmentNode = document.createElement('div');
            segmentNode.className = 'node';
            segmentNode.dataset.type = 'segment';
            segmentNode.dataset.segmentType = segment.type;
            segmentNode.dataset.segmentId = `${functionId}_segment_${index}`;
            
            const segmentLabel = document.createElement('span');
            
            // Format the label based on segment type
            if (segment.type === 'call' && segment.target_function) {
                segmentLabel.className = 'caret';
                segmentLabel.innerHTML = `<span class="segment-type">CALL:</span> ${segment.target_function.name}()`;
                
                // Create nested container for target function
                const targetContainer = document.createElement('div');
                targetContainer.className = 'nested';
                
                // Setup click handler
                segmentLabel.onclick = function() {
                    toggleNode(this);
                    
                    // If empty, load the target function's segments
                    if (targetContainer.children.length === 0) {
                        loadFunctionSegments(repoHash, segment.target_function.id, targetContainer);
                    }
                    
                    // Display the call segment details
                    displaySegmentDetails(segment);
                };
                
                segmentNode.appendChild(segmentLabel);
                segmentNode.appendChild(targetContainer);
            } else {
                // For code or comment segments
                const previewText = segment.content.split('\n')[0].substring(0, 30) + 
                                   (segment.content.length > 30 ? '...' : '');
                
                segmentLabel.innerHTML = `<span class="segment-type">${segment.type.toUpperCase()}:</span> ${previewText}`;
                
                // Setup click handler for non-call segments
                segmentLabel.onclick = function() {
                    displaySegmentDetails(segment);
                };
                
                segmentNode.appendChild(segmentLabel);
            }
            
            container.appendChild(segmentNode);
        });
    } catch (error) {
        console.error('Error loading function segments:', error);
        container.innerHTML = '<div class="node"><span>Error loading segments</span></div>';
    }
}

function displaySegmentDetails(segment) {
    // Highlight selected segment in the tree
    const activeNodes = document.querySelectorAll('.active-node');
    activeNodes.forEach(node => node.classList.remove('active-node'));
    
    // Build the preview content
    const codePreview = document.getElementById('code-preview');
    
    let content = `
        <div class="segment-details segment-${segment.type}">
            <h3>${segment.type.toUpperCase()} Segment</h3>
            <p>Lines: ${segment.lineno}${segment.end_lineno ? ` - ${segment.end_lineno}` : ''}</p>
            <pre><code>${escapeHTML(segment.content)}</code></pre>
    `;
    
    // For call segments, add target function info
    if (segment.type === 'call' && segment.target_function) {
        const target = segment.target_function;
        content += `
            <div class="target-function-info">
                <h4>Calls Function:</h4>
                <p><strong>${target.name}</strong> (${target.full_name})</p>
                <p>File: ${target.file_path}</p>
                <p>Lines: ${target.lineno} - ${target.end_lineno}</p>
            </div>
        `;
    }
    
    content += '</div>';
    codePreview.innerHTML = content;
}

async function displayFunctionDetails(repoHash, functionId) {
    try {
        // Highlight the selected function
        const activeNodes = document.querySelectorAll('.active-node');
        activeNodes.forEach(node => node.classList.remove('active-node'));
        
        const selectedNode = document.querySelector(`[data-id="${functionId}"] > span`);
        if (selectedNode) {
            selectedNode.classList.add('active-node');
        }
        
        // Show loading
        const codePreview = document.getElementById('code-preview');
        codePreview.innerHTML = '<div class="loading"></div>';
        
        // Fetch function details
        const response = await fetch(`/code/api/functions/${repoHash}/${functionId}`);
        const func = await response.json();
        
        // Build content
        let content = `
            <div class="function-details">
                <h2>${func.name}</h2>
                <p class="file-path">${func.full_name}</p>
                <p>File: ${func.file_path}</p>
                <p>Lines: ${func.lineno} - ${func.end_lineno}</p>
                ${func.is_entry ? '<p><strong>Entry Point</strong></p>' : ''}
                ${func.class_name ? `<p>Class: ${func.class_name}</p>` : ''}
                <p>Module: ${func.module_name}</p>
            </div>
            
            <p>Select a segment from the tree to view its details.</p>
        `;
        
        codePreview.innerHTML = content;
    } catch (error) {
        console.error('Error loading function details:', error);
        document.getElementById('code-preview').innerHTML = 
            '<p>Error loading function details. Please try again.</p>';
    }
}

// Helper function to escape HTML
function escapeHTML(str) {
    if (!str) return '';
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}