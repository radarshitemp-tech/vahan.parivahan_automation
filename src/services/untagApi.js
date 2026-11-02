// src/services/replaceApi.js
const API_BASE_URL = `${import.meta.env.VITE_BASE_URL}/api` || 'http://127.0.0.1:8003/api';

export const replaceApi = {
  // Get module status and active portal session
  async getStatus() {
    const res = await fetch(`${API_BASE_URL}/modules/untag/status`);
    if (!res.ok) throw new Error(`Status check failed: ${res.statusText}`);
    return await res.json();
  },

  // Get supported replacement options
  async getOptions() {
    const res = await fetch(`${API_BASE_URL}/modules/untag/options`);
    if (!res.ok) throw new Error(`Failed to load options: ${res.statusText}`);
    return await res.json();
  },

  // Navigate active browser to the replacement portal URL
  async navigateToPortal() {
    const res = await fetch(`${API_BASE_URL}/modules/untag/navigate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) throw new Error(`Navigation failed: ${res.statusText}`);
    return await res.json();
  },

  // Select option in select_optn (S, D, or I) on portal and trigger PrimeFaces AJAX
  async selectOption(optionKey) {
    const res = await fetch(`${API_BASE_URL}/modules/untag/select-option`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ option_key: optionKey }),
    });
    if (!res.ok) throw new Error(`Option selection failed: ${res.statusText}`);
    return await res.json();
  },

  // Inspect revealed fitment fields on portal
  async inspectFields() {
    const res = await fetch(`${API_BASE_URL}/modules/untag/inspect`);
    if (!res.ok) throw new Error(`Field inspection failed: ${res.statusText}`);
    return await res.json();
  },

  // Execute single replacement record
  async executeSingle(data) {
    const res = await fetch(`${API_BASE_URL}/modules/untag/execute-single`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error(`Single execution failed: ${res.statusText}`);
    return await res.json();
  },

  // Execute batch replacement
  async executeBatch(optionKey, records) {
    const res = await fetch(`${API_BASE_URL}/modules/untag/batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ option_key: optionKey, records }),
    });
    if (!res.ok) throw new Error(`Batch execution failed: ${res.statusText}`);
    return await res.json();
  },
};
