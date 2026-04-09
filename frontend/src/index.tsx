import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';

// Load runtime configuration from backend before rendering app
// This allows subpath deployment configuration (PUBLIC_URL, API_BASE_URL)
// to be injected at runtime rather than build time
async function initializeApp() {
  const fallbackApiBaseUrl = process.env.REACT_APP_API_URL || '/api';

  try {
    // Fetch frontend config from backend
    const configResponse = await fetch('/api/config', {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json'
      }
    });
    
    if (configResponse.ok) {
      const config = await configResponse.json();
      // Inject into window so other code can access it
      (window as any).__CONFIG__ = config;
      console.log('Frontend config loaded:', config);
    } else {
      console.warn('Failed to load frontend config, using defaults');
      (window as any).__CONFIG__ = {
        publicUrl: '/',
        apiBaseUrl: fallbackApiBaseUrl
      };
    }
  } catch (error) {
    console.error('Error loading frontend config:', error);
    // Fallback to defaults if config endpoint is unavailable
    (window as any).__CONFIG__ = {
      publicUrl: '/',
      apiBaseUrl: fallbackApiBaseUrl
    };
  }
  
  // Now render the React app
  const root = ReactDOM.createRoot(
    document.getElementById('root') as HTMLElement
  );
  root.render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
}

// Initialize the app
initializeApp();
