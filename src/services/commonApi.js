// src/services/commonApi.js
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_BASE_URL || 'http://127.0.0.1:8003/api';

export const commonApi = {
  // Check backend server health
  async checkHealth() {
    try {
      const res = await fetch(`${API_BASE_URL}/health`);
      return await res.json();
    } catch (e) {
      return { status: 'offline', error: e.message };
    }
  },

  // Get active modules list from backend registry
  async listModules() {
    try {
      const res = await fetch(`${API_BASE_URL}/modules`);
      if (!res.ok) return [];
      return await res.json();
    } catch {
      return [];
    }
  },

  // Get Chrome browser & authentication status
  async getSessionStatus() {
    try {
      const res = await fetch(`${API_BASE_URL}/session`);
      if (!res.ok) return { is_alive: false, is_authenticated: false, message: 'Offline' };
      return await res.json();
    } catch (e) {
      return { is_alive: false, is_authenticated: false, message: e.message };
    }
  },

  // Close active browser session gracefully
  async closeBrowser() {
    const res = await fetch(`${API_BASE_URL}/browser/close`, {
      method: 'POST',
    });
    return await res.json();
  },

  // Fetch unified root audit log file (vahan_automation.log)
  async getUnifiedLogs(lines = 250) {
    try {
      const res = await fetch(`${API_BASE_URL}/vahan/logs/unified?lines=${lines}`);
      if (!res.ok) return { log_file: '', content: '' };
      return await res.json();
    } catch {
      return { log_file: '', content: '' };
    }
  },

  // Fetch structured audit logs for the current active session
  async getSessionStructuredLogs(limit = 150) {
    try {
      const res = await fetch(`${API_BASE_URL}/vahan/logs/session-structured?limit=${limit}`);
      if (!res.ok) return [];
      return await res.json();
    } catch {
      return [];
    }
  },

  // Start a fresh session log (overwriting current log and archiving previous session to backup)
  async startNewLogSession(sessionId = null) {
    try {
      const res = await fetch(`${API_BASE_URL}/vahan/logs/new-session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      });
      return await res.json();
    } catch (e) {
      return { error: e.message };
    }
  },
};

