
function scrollToHighlight() {
  if (isProcessingClick) {
    return; // code line click simulates tree-nav click without scroll since the element has to be within view already
  }
  (
    document.querySelector('.strong-highlight') ||
    document.querySelector('.function-highlight')
  )?.scrollIntoView({ behavior: 'smooth' });
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

function escapeRegExp(string) {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// function applyPrismHighlighting() {
//   // Force Prism to re-highlight all code elements
//   if (typeof Prism !== 'undefined') {
//     Prism.highlightAll();
//   }
// }

function findFunctionAtLine(repoHash, filePath, lineNumber) {
  // Show a small loading indicator
  const notification = document.createElement('div');
  notification.className = 'search-notification';
  notification.innerHTML = 'Finding function...';
  notification.style.position = 'fixed';
  notification.style.top = '10px';
  notification.style.right = '10px';
  notification.style.padding = '8px 12px';
  notification.style.background = 'rgba(0, 0, 0, 0.7)';
  notification.style.color = 'white';
  notification.style.borderRadius = '4px';
  notification.style.zIndex = '9999';
  document.body.appendChild(notification);

  // Use our new API endpoint to get functions in this file
  fetch(
    `/code/api/functions/${repoHash}/file?path=${encodeURIComponent(filePath)}`
  )
    .then((response) => response.json())
    .then((functionsInFile) => {
      // Find the function that contains this line
      const matchingFunction = functionsInFile.find(
        (func) => lineNumber >= func.lineno && lineNumber <= func.end_lineno
      );

      // Remove the notification
      document.body.removeChild(notification);

      if (matchingFunction) {
        // Add to custom functions list
        addToCustomFunctionsList(
          matchingFunction.id,
          matchingFunction.name,
          matchingFunction.full_name || matchingFunction.file_path
        );

        // Load function details
        loadFunctionDetails(repoHash, matchingFunction.id);

        // Show a success notification
        showTemporaryNotification(
          `Found function: ${matchingFunction.name}`,
          'success'
        );

        console.log(
          `Found function at line ${lineNumber}: ${matchingFunction.name}`
        );
      } else {
        console.log(`No function found at line ${lineNumber}`);
        // Show a notification to the user
        showTemporaryNotification('No function found at this line', 'warning');
      }
    })
    .catch((error) => {
      console.error('Error finding function at line:', error);

      // Fallback to using the all functions endpoint if the file endpoint fails
      fetch(`/code/api/functions/${repoHash}/all`)
        .then((response) => response.json())
        .then((allFunctions) => {
          // Find functions in this file
          const functionsInFile = allFunctions.filter((func) => {
            const funcPath = func.file_path;
            return (
              funcPath === filePath ||
              funcPath.endsWith(filePath) ||
              filePath.endsWith(funcPath) ||
              funcPath.includes(filePath) ||
              filePath.includes(funcPath)
            );
          });

          // Find the function that contains this line
          const matchingFunction = functionsInFile.find(
            (func) => lineNumber >= func.lineno && lineNumber <= func.end_lineno
          );

          if (matchingFunction) {
            // Add to custom functions list
            addToCustomFunctionsList(
              matchingFunction.id,
              matchingFunction.name,
              matchingFunction.full_name || matchingFunction.file_path
            );

            // Load function details
            loadFunctionDetails(
              repoHash,
              matchingFunction.id,
              filePath == currentFilePath
            );

            showTemporaryNotification(
              `Found function: ${matchingFunction.name}`,
              'success'
            );
          } else {
            showTemporaryNotification(
              'No function found at this line',
              'warning'
            );
          }
        })
        .catch((err) => {
          console.error('Fallback search failed:', err);
          showTemporaryNotification('Error finding function', 'error');
        })
        .finally(() => {
          if (notification.parentNode) {
            document.body.removeChild(notification);
          }
        });
    });
}
// Add this helper function to show temporary notifications
function showTemporaryNotification(message, type = 'info') {
  // Create notification element
  const notification = document.createElement('div');
  notification.className = 'notification';
  notification.innerHTML = message;
  notification.style.position = 'fixed';
  notification.style.top = '10px';
  notification.style.right = '10px';
  notification.style.padding = '8px 12px';
  notification.style.borderRadius = '4px';
  notification.style.zIndex = '9999';
  notification.style.maxWidth = '300px';
  notification.style.boxShadow = '0 2px 10px rgba(0,0,0,0.2)';

  // Set style based on notification type
  switch (type) {
    case 'success':
      notification.style.background = '#4caf50';
      notification.style.color = 'white';
      break;
    case 'warning':
      notification.style.background = '#ff9800';
      notification.style.color = 'white';
      break;
    case 'error':
      notification.style.background = '#f44336';
      notification.style.color = 'white';
      break;
    default: // info
      notification.style.background = '#2196f3';
      notification.style.color = 'white';
  }

  // Add to document
  document.body.appendChild(notification);

  // Remove after 3 seconds
  setTimeout(() => {
    notification.style.opacity = '0';
    notification.style.transition = 'opacity 0.5s';
    setTimeout(() => {
      if (notification.parentNode) {
        document.body.removeChild(notification);
      }
    }, 500);
  }, 3000);
}

function addFunctionLinkHandlers() {
  document.querySelectorAll('.function-link').forEach(link => {
    link.addEventListener('click', (e) => {
      const functionId = e.target.dataset.functionId;
      if (functionId) {
        // Get repository hash
        const repoHash = document.querySelector('.repo-info').dataset.repoHash;
        
        // Load function details when clicked
        loadFunctionDetails(repoHash, functionId);
        
        // Add to custom functions list
        const functionName = e.target.textContent;
        addToCustomFunctionsList(functionId, functionName, functionName);
      }
    });
  });
}