// Step 1: Install the necessary CodeMirror 6 packages
// You can run these commands in your project directory
// npm install @codemirror/view @codemirror/state @codemirror/language @codemirror/commands @codemirror/lang-python @codemirror/theme-one-dark @codemirror/basic-setup

// Step 2: Create a file called code-viewer.js in your static/js directory

import { EditorState } from '@codemirror/state';
import { EditorView, lineNumbers, highlightActiveLineGutter, highlightSpecialChars, 
         drawSelection, dropCursor, rectangularSelection, crosshairCursor, 
         highlightActiveLine, keymap } from '@codemirror/view';
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands';
import { indentOnInput, syntaxHighlighting, defaultHighlightStyle, bracketMatching, 
         foldGutter, foldKeymap } from '@codemirror/language';
import { python } from '@codemirror/lang-python';
import { oneDark } from '@codemirror/theme-one-dark';
import { Decoration } from "@codemirror/view";
import { RangeSetBuilder } from "@codemirror/state";

/**
 * Build a DecorationSet that highlights the requested line ranges.
 *
 * @param {Array<{start: number, end: number, type: string}>} ranges
 * @param {EditorState} state   – pass the editor state so we can convert
 *                                line numbers to document positions
 * @returns {DecorationSet}
 */
function buildHighlightDecorations(ranges, state) {
  if (!ranges || ranges.length === 0) return Decoration.none;

  const builder = new RangeSetBuilder();

  for (const range of ranges) {
    const fromLine = state.doc.line(range.start);
    const toLine   = state.doc.line(range.end);

    builder.add(
      fromLine.from,
      toLine.to,
      Decoration.line({ class: `cm-${range.type}` })
    );
  }

  return builder.finish();
}

// Function to create and set up the CodeMirror editor
function createCodeEditor(container, code, lineStart = 1, highlightRanges = []) {
  // Create the initial editor state
  const state = EditorState.create({
    doc: code,
    extensions: [
      // Basic editor setup
      lineNumbers(),
      highlightActiveLineGutter(),
      highlightSpecialChars(),
      history(),
      drawSelection(),
      dropCursor(),
      EditorState.allowMultipleSelections.of(true),
      indentOnInput(),
      syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
      bracketMatching(),
      rectangularSelection(),
      crosshairCursor(),
      highlightActiveLine(),
      
      // Python language support
      python(),
      
      // Code folding
      foldGutter({
        // Using the default fold markers
        openText: "▾",
        closedText: "▸",
      }),
      
      // Keymaps for keyboard shortcuts
      keymap.of([
        ...defaultKeymap,
        ...historyKeymap,
        ...foldKeymap
      ]),
      
      // Dark theme (optional, remove if you prefer light theme)
      oneDark,
      
      // Set read-only mode if needed
      // EditorState.readOnly.of(true),
      
      // Custom highlighting for function, component, or segment ranges
    //   EditorView.decorations.of(createHighlightDecorations(highlightRanges, lineStart)),
      EditorView.decorations.compute(
        [],                           // re‑compute only when doc changes
        state => buildHighlightDecorations(highlightRanges, state)
      )
    ]
  });

  // Create the editor view
  const view = new EditorView({
    state,
    parent: container
  });
  
  return view;
}

// Function to create decorations for highlighting specific ranges
function createHighlightDecorations(ranges, lineStart) {
  if (!ranges || ranges.length === 0) return [];
  
  const decorations = [];
  
  ranges.forEach(range => {
    const start = range.start - lineStart;
    const end = range.end - lineStart;
    const highlightClass = range.type || 'highlight-default';
    
    if (start >= 0 && end >= start) {
      decorations.push({
        from: positionForLine(start),
        to: positionForLine(end + 1),
        class: `cm-${highlightClass}`
      });
    }
  });
  
  return decorations;
}

// Helper to get position for a line number
function positionForLine(line) {
  // This is a simplified version - you might need to adjust this for your specific use case
  return line;
}

// Function to replace the tree.js buildFullFunctionCodeView function
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
    // Use the file_path to get the complete file content
    const filePath = functionData.file_path;
    const functionStart = functionData.lineno;
    const functionEnd = functionData.end_lineno;
    
    // Fetch the file content using an API endpoint
    let fileContent = '';
    
    try {
      const repoHash = document.querySelector('.repo-info').dataset.repoHash;
      const response = await fetch(`/code/api/file?path=${encodeURIComponent(filePath)}&repo_hash=${repoHash}`);
      
      if (response.ok) {
        fileContent = await response.text();
      } else {
        console.warn('Error fetching complete file, falling back to function-only view');
        // Fall back to function-only view using segments
        return fallbackToFunctionOnlyView(functionData, highlightComponent, highlightSegment);
      }
    } catch (fileError) {
      console.warn('Error reading file directly, falling back to function-only view:', fileError);
      return fallbackToFunctionOnlyView(functionData, highlightComponent, highlightSegment);
    }
    
    // Prepare highlight ranges for components and segments
    const highlightRanges = [];
    
    // Add function range
    highlightRanges.push({
      start: functionStart,
      end: functionEnd,
      type: 'function-highlight'
    });
    
    // Add component highlighting if applicable
    if (highlightComponent) {
      highlightRanges.push({
        start: highlightComponent.start_lineno,
        end: highlightComponent.end_lineno,
        type: 'component-highlight'
      });
    }
    
    // Add segment highlighting if applicable
    if (highlightSegment) {
      // Convert relative line numbers to absolute for highlighting
      const segmentStart = functionData.lineno + highlightSegment.lineno - 1;
      const segmentEnd = highlightSegment.end_lineno ? 
                          functionData.lineno + highlightSegment.end_lineno - 1 : 
                          segmentStart;
                          
      highlightRanges.push({
        start: segmentStart,
        end: segmentEnd,
        type: `segment-${highlightSegment.type}-highlight`
      });
    }
    
    // Generate a unique ID for the editor container
    const editorId = `code-editor-${Date.now()}`;
    
    // Add scroll indicator
    const scrollToFunction = `
      <div class="scroll-indicator">
        <button id="scroll-to-function-${editorId}">
          Scroll to Function (Line ${functionStart})
        </button>
      </div>
    `;
    
    // Return HTML structure with placeholder for the editor
    const html = `
      ${scrollToFunction}
      <div class="function-code-view">
        <div id="${editorId}" class="code-editor-container"></div>
      </div>
    `;
    
    // After the HTML is inserted into the DOM, initialize the CodeMirror editor
    setTimeout(() => {
      const container = document.getElementById(editorId);
      if (container) {
        const editor = createCodeEditor(container, fileContent, 1, highlightRanges);
        
        // Set up scroll to function button
        const scrollButton = document.getElementById(`scroll-to-function-${editorId}`);
        if (scrollButton) {
          scrollButton.addEventListener('click', () => {
            // Scroll to the function line
            editor.dispatch({
              effects: EditorView.scrollIntoView(functionStart - 1)
            });
          });
        }
      }
    }, 100);
    
    return html;
  } catch (error) {
    console.error('Error building function code view:', error);
    return `<p>Error displaying function code: ${error.message}</p>`;
  }
}

// Function to fall back to function-only view
function fallbackToFunctionOnlyView(functionData, highlightComponent, highlightSegment) {
  try {
    // Sort segments by line number to ensure correct order
    const sortedSegments = [...functionData.segments].sort((a, b) => a.lineno - b.lineno);
    
    // Create a string to hold all lines of the function
    let code = '';
    
    // Fill in content from segments
    for (const segment of sortedSegments) {
      code += segment.content + '\n';
    }
    
    // Prepare highlight ranges
    const highlightRanges = [];
    
    // Add component highlighting if applicable
    if (highlightComponent) {
      const relStart = highlightComponent.start_lineno - functionData.lineno + 1;
      const relEnd = highlightComponent.end_lineno - functionData.lineno + 1;
      
      highlightRanges.push({
        start: relStart,
        end: relEnd,
        type: 'component-highlight'
      });
    }
    
    // Add segment highlighting if applicable
    if (highlightSegment) {
      highlightRanges.push({
        start: highlightSegment.lineno,
        end: highlightSegment.end_lineno || highlightSegment.lineno,
        type: `segment-${highlightSegment.type}-highlight`
      });
    }
    
    // Generate a unique ID for the editor container
    const editorId = `code-editor-${Date.now()}`;
    
    // Return HTML structure with placeholder for the editor
    const html = `
      <div class="function-code-view">
        <div class="file-view-note">
          <p>Note: Showing only the function code. Unable to load the complete file.</p>
        </div>
        <div id="${editorId}" class="code-editor-container"></div>
      </div>
    `;
    
    // After the HTML is inserted into the DOM, initialize the CodeMirror editor
    setTimeout(() => {
      const container = document.getElementById(editorId);
      if (container) {
        createCodeEditor(container, code, 1, highlightRanges);
      }
    }, 100);
    
    return html;
  } catch (error) {
    console.error('Error building fallback function view:', error);
    return `<p>Error displaying function code: ${error.message}</p>`;
  }
}

export { createCodeEditor, buildFullFunctionCodeView, fallbackToFunctionOnlyView };