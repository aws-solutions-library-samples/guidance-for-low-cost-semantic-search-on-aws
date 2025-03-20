var json = $.getJSON("./config.json", function( data ) {
  // create a display none div element for each value
  $("#apiendpointupload").text(data.apiendpointupload);
  $("#apiendpointconfig").text(data.apiendpointconfig);
  $("#apiendpointchat").text(data.apiendpointchat);
  $("#apiendpointdocuments").text(data.apiendpointdocuments);
  $("#signinurl").text(data.signinurl);
  $('#cognito-client-id').text(data.cognitoclientid);
  $('#cognito-region').text(data.cognitoregion)
  return {
      "apiendpointupload": data["apiendpointupload"],
      "apiendpointconfig": data["apiendpointconfig"],
      "apiendpointchat": data["apiendpointchat"],
      "apiendpointdocuments": data["apiendpointdocuments"],
      "signinurl": data["signinurl"],
      "cognitoclientid": data["cognitoclientid"],
      "cognitoregion": data["cognitoregion"]}
});

function get(url, headers = {}) {
  if (JSON.stringify(headers) == "{}") {
      const token = getCognitoToken();
      if (token == null) {
          redirectToLogin();
      }
      headers = {"Authorization": "Bearer " + token};
  }
  return $.ajax({
      type: 'GET',
      url: url,
      headers: headers
  });
}
function post(data, url, headers = {}) {
  if (JSON.stringify(headers) == "{}") {
      const token = getCognitoToken();
      if (token == null) {
          redirectToLogin();
      }
      headers = {"Authorization": "Bearer " + token};
  }
  return $.ajax({
      type: 'POST',
      data: JSON.stringify(data),
      dataType: 'json',
      url: url,
      headers: headers
  });
}
function put(url,data) {
  // make a request to the signed url
  return $.ajax({
      contentType: 'binary/octet-stream',
      url: url,
      type: 'PUT',
      data: data,
      processData: false
  });
}
// Delete that has the same behavvior as post
function del(url, data, headers = {}) {
  if (JSON.stringify(headers) == "{}") {
      const token = getCognitoToken();
      headers = {"Authorization": "Bearer " + token};
  }
  return $.ajax({
      type: 'DELETE',
      url: url,
      data: JSON.stringify(data),
      dataType: 'json',
      headers: headers
  });
}

  
function getTokens() {
  const cookies = document.cookie.split(';').reduce((cookiesObj, cookie) => {
      const [name, value] = cookie.trim().split('=');
      cookiesObj[name] = value;
      return cookiesObj;
  }, {});
  return {
      idToken: cookies['id_token'],
      refreshToken: cookies['refresh_token'],
      accessToken: cookies['access_token']
  };
}
function storeTokens(idToken, refreshToken, accessToken) {
  document.cookie = `id_token=${idToken}; Secure; SameSite=Strict; Path=/`;
  document.cookie = `refresh_token=${refreshToken}; Secure; SameSite=Strict; Path=/`;
  document.cookie = `access_token=${accessToken}; Secure; SameSite=Strict; Path=/`;
}
function clearTokens() {
  document.cookie = `id_token=; Secure; SameSite=Strict; Path=/`;
  document.cookie = `refresh_token=; Secure; SameSite=Strict; Path=/`;
  document.cookie = `access_token=; Secure; SameSite=Strict; Path=/`;
}

function storeTokensFromHash() {
  const hashParams = new URLSearchParams(window.location.hash.substring(1));
  const idToken = hashParams.get('id_token');
  const accessToken = hashParams.get('access_token');
  const refreshToken = hashParams.get('refresh_token');
  // store tokens
  storeTokens(idToken, refreshToken, accessToken);
}

function refreshAuthToken(refreshToken) {
  const clientId = $('#cognito-client-id').text();
  
  try {
      const headers = {
          'X-Amz-Target': 'AWSCognitoIdentityProviderService.InitiateAuth',
          'Content-Type': 'application/x-amz-json-1.1'
      }
      const data = {
          AuthFlow: 'REFRESH_TOKEN_AUTH',
          ClientId: clientId,
          AuthParameters: {
              REFRESH_TOKEN: refreshToken
          }
      }
      const cognitoEndpoint = `https://cognito-idp.${$('#cognito-region').text()}.amazonaws.com/`;
      const response = post(data, cognitoEndpoint, headers);

      if (response.AuthenticationResult) {
          const { IdToken, AccessToken } = response.AuthenticationResult;
          storeTokens(IdToken, refreshToken, AccessToken);
          // Note: A new refresh token is not provided during refresh
          return IdToken;
      }
  } catch (error) {
      console.error('Error refreshing token:', error);
      throw error;
  }
}
function isTokenExpired(token) {
  try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      const expirationTime = payload.exp * 1000; // Convert to milliseconds
      return Date.now() >= expirationTime;
  } catch (error) {
      console.error('Error parsing token:', error);
      return true;
  }
}
function redirectToLogin() {
  const signinUrl = $("#signinurl").text();
  if (signinUrl) {
      window.location.href = signinUrl;
  } else {
      console.error('Sign-in URL not found');
  }
}
function getCognitoToken() {
  // First check if there's a token in cookie
  const storedToken = getTokens().idToken;
  if (storedToken) {
      // Check if token is expired
      if (isTokenExpired(storedToken)) {
          // If token is expired, try to refresh it
          const refreshToken = getTokens().refreshToken;
          if (refreshToken && refreshToken !="null") {
              try {
                  const id_token = refreshAuthToken(refreshToken);
                  return id_token;
              } catch (error) {
                  clearTokens();
                  redirectToLogin();
                  return null;
              }
          } else {
              clearTokens();
              redirectToLogin();
              return null;
          }
      }
      return storedToken;
  }

  // If no token in cookies, check URL hash for new login
  if (window.location.hash) {
      const hashParams = new URLSearchParams(window.location.hash.substring(1));
      const idToken = hashParams.get('id_token');
      
      if (idToken) {
          // Store the tokens from the URL
          storeTokensFromHash();
          // Clear the hash from the URL
          window.history.replaceState(null, null, window.location.pathname);
          return idToken;
      }
  }
  
  // No valid token found
  return null;
}

/**
* Notification utility class to handle notifications safely
*/
class NotificationUtils {
constructor() {
  this.container = this.createNotificationContainer();
}

/**
 * Creates notification container if it doesn't exist
 */
createNotificationContainer() {
  if (!document.getElementById('notification-container')) {
    const container = document.createElement('div');
    container.id = 'notification-container';
    document.body.appendChild(container);
  }
  return document.getElementById('notification-container');
}

/**
 * Helper function to safely set text content
 */
setTextContent(element, text) {
  // Clear any existing content
  while (element.firstChild) {
    element.removeChild(element.firstChild);
  }
  element.appendChild(document.createTextNode(text));
}

/**
 * Show a notification using DOM manipulation
 */
showNotification(message, type = 'info', duration = 3000, isModal = false) {
  // Clone notification template
  const template = document.getElementById('notification-template');
  const notification = document.importNode(template.content.firstElementChild, true);
  
  // Set notification type
  notification.classList.add(`notification-${type}`);
  if (isModal) {
    notification.classList.add('modal');
  } else {
    notification.classList.add('toast');
  }
  
  // Create backdrop for modal
  let backdrop = null;
  if (isModal) {
    backdrop = document.createElement('div');
    backdrop.className = 'notification-backdrop fade-in';
    document.body.appendChild(backdrop);
    
    // Prevent scrolling on body
    document.body.style.overflow = 'hidden';
  }
  
  // Set icon based on type
  const iconElement = notification.querySelector('.notification-icon');
  let iconClass = '';
  
  switch (type) {
    case 'success':
      iconClass = 'fas fa-check-circle';
      break;
    case 'error':
      iconClass = 'fas fa-exclamation-circle';
      break;
    case 'warning':
      iconClass = 'fas fa-exclamation-triangle';
      break;
    case 'info':
    default:
      iconClass = 'fas fa-info-circle';
      break;
  }
  
  // Create icon element safely
  const icon = document.createElement('i');
  icon.className = iconClass;
  iconElement.appendChild(icon);
  
  // Set message text safely
  const contentElement = notification.querySelector('.notification-content');
  
  // If message is HTML, parse and append safely
  if (typeof message === 'string' && message.includes('<')) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(message, 'text/html');
    while (doc.body.firstChild) {
      contentElement.appendChild(doc.body.firstChild);
    }
  } else {
    // Plain text
    this.setTextContent(contentElement, message);
  }
  
  // Add to container
  this.container.appendChild(notification);
  
  // Close button functionality
  const closeBtn = notification.querySelector('.notification-close');
  closeBtn.addEventListener('click', () => {
    this.closeNotification(notification, backdrop);
  });
  
  // Auto-close after duration (for toasts only)
  if (!isModal && duration > 0) {
    setTimeout(() => {
      this.closeNotification(notification, backdrop);
    }, duration);
  }
  
  // Close when clicking on backdrop
  if (backdrop) {
    backdrop.addEventListener('click', () => {
      this.closeNotification(notification, backdrop);
    });
  }
  
  return notification;
}

/**
 * Close notification
 */
closeNotification(notification, backdrop) {
  notification.classList.remove('fade-in');
  notification.classList.add('fade-out');
  
  if (backdrop) {
    backdrop.classList.remove('fade-in');
    backdrop.classList.add('fade-out');
    
    // Re-enable scrolling
    document.body.style.overflow = '';
  }
  
  setTimeout(() => {
    if (notification.parentNode) {
      notification.parentNode.removeChild(notification);
    }
    if (backdrop && backdrop.parentNode) {
      backdrop.parentNode.removeChild(backdrop);
    }
  }, 300);
}

/**
 * Show confirmation dialog
 */
showConfirmation(message, onConfirm, onCancel = null, confirmText = 'Confirm', cancelText = 'Cancel', type = 'warning') {
  // Clone confirmation template
  const template = document.getElementById('notification-confirmation-template');
  const notification = document.importNode(template.content.firstElementChild, true);
  
  // Create backdrop
  const backdrop = document.createElement('div');
  backdrop.className = 'notification-backdrop fade-in';
  document.body.appendChild(backdrop);
  
  // Prevent scrolling
  document.body.style.overflow = 'hidden';
  
  // Set icon based on type
  const iconElement = notification.querySelector('.notification-icon');
  let iconClass = '';
  
  switch (type) {
    case 'success':
      iconClass = 'fas fa-check-circle';
      break;
    case 'error':
      iconClass = 'fas fa-exclamation-circle';
      break;
    case 'warning':
      iconClass = 'fas fa-exclamation-triangle';
      break;
    case 'info':
    default:
      iconClass = 'fas fa-info-circle';
      break;
  }
  
  // Create icon element safely
  const icon = document.createElement('i');
  icon.className = iconClass;
  iconElement.appendChild(icon);
  
  // Set message content safely
  const contentElement = notification.querySelector('.notification-content');
  if (typeof message === 'string' && message.includes('<')) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(message, 'text/html');
    while (doc.body.firstChild) {
      contentElement.appendChild(doc.body.firstChild);
    }
  } else {
    this.setTextContent(contentElement, message);
  }
  
  // Set button text
  const confirmBtn = notification.querySelector('#confirm-btn');
  const cancelBtn = notification.querySelector('#cancel-btn');
  this.setTextContent(confirmBtn, confirmText);
  this.setTextContent(cancelBtn, cancelText);
  
  // Add to container
  this.container.appendChild(notification);
  
  // Button functionality
  confirmBtn.addEventListener('click', () => {
    this.closeNotification(notification, backdrop);
    if (onConfirm) onConfirm();
  });
  
  cancelBtn.addEventListener('click', () => {
    this.closeNotification(notification, backdrop);
    if (onCancel) onCancel();
  });
  
  return notification;
}

// Shorthand methods
showSuccessNotification(message, duration = 3000, isModal = false) {
  return this.showNotification(message, 'success', duration, isModal);
}

showErrorNotification(message, duration = 3000, isModal = false) {
  return this.showNotification(message, 'error', duration, isModal);
}

showWarningNotification(message, duration = 3000, isModal = false) {
  return this.showNotification(message, 'warning', duration, isModal);
}

showInfoNotification(message, duration = 3000, isModal = false) {
  return this.showNotification(message, 'info', duration, isModal);
}
}

// Global function references for backward compatibility
function showSuccessNotification(message, duration = 3000, isModal = false) {
const utils = new NotificationUtils();
return utils.showSuccessNotification(message, duration, isModal);
}

function showErrorNotification(message, duration = 3000, isModal = false) {
const utils = new NotificationUtils();
return utils.showErrorNotification(message, duration, isModal);
}

function showWarningNotification(message, duration = 3000, isModal = false) {
const utils = new NotificationUtils();
return utils.showWarningNotification(message, duration, isModal);
}

function showInfoNotification(message, duration = 3000, isModal = false) {
const utils = new NotificationUtils();
return utils.showInfoNotification(message, duration, isModal);
}

function closeNotification(notification) {
const utils = new NotificationUtils();
utils.closeNotification(notification);
}

function showConfirmation(message, onConfirm, onCancel = null, confirmText = 'Confirm', cancelText = 'Cancel', type = 'warning') {
const utils = new NotificationUtils();
return utils.showConfirmation(message, onConfirm, onCancel, confirmText, cancelText, type);
}
