// build means it returns HTML
// display wraps upper and lower panel handling
// buildFullFunctionCodeView handles lower panel view


// Build HTML for function summary
function buildFunctionSummary(functionData) {
  let html = `
          <div class="function-details">
              <div class="file-path">
                ${functionData.full_name}
                ${
                  functionData.module_name
                    ? `, Module: ${functionData.module_name}`
                    : ''
                }
                <!--Lines: ${functionData.lineno} - ${
    functionData.end_lineno
  }-->
                ${functionData.is_entry ? '<strong> Entry Point </strong>' : ''}
              </div>
              
              ${
                functionData.class_name
                  ? `<div>Class: ${functionData.class_name}</div>`
                  : ''
              }
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

function buildSegmentSummary(segment) {
  // Build segment details
  let content = `
<div class="segment segment-${segment.type}">
    <div class="segment-body">
        <pre><code>${escapeHTML(segment.content)}</code></pre>
    </div>
`;

  // Add target info for call segments
  if (segment.type === 'call' && segment.target_function) {
    const target = segment.target_function;
    // console.log(target);
    content += `
    <div class="segment-target">
        <div><strong>Module path:</strong> ${target.full_name}</div>
        <div><strong>Description:</strong> ${target.short_description}</div>
        <div><strong>Details:</strong> ${target.long_description}</div>
    </div>
`;
  }

  content += '</div>'; // Close segment div

  return content;
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
      scrollToHighlight();
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
      scrollToHighlight();
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
                          ${
                            segment.end_lineno
                              ? ` to ${segment.end_lineno}`
                              : ''
                          }
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

  // Update upper panel
  panelContent.innerHTML = buildSegmentSummary(segment);

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
    scrollToHighlight();
  }
}

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
                <button class="scroll-function-button" onclick="scrollToHighlight()">
                    Scroll to Function
                </button>
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
