# Copy to config.js for local development or GitHub Pages deployment.
window.MTA_CONFIG = {
  API_BASE_URL: "http://localhost:8000",
  // Optional when MTA_READ_API_KEY is set on the API:
  // API_READ_KEY: "your-read-key",
  // When MTA_DASHBOARD_PASSWORD is set, sign in via the dashboard login screen
  // (Bearer token stored in localStorage) instead of using API_READ_KEY.
};