// src/services/deleteApi.js
const API_BASE_URL = `${import.meta.env.VITE_BASE_URL}/api` || 'http://127.0.0.1:8003/api';

export const deleteApi = {
  // Get delete module readiness & session status
  async getStatus() {
    try {
      const res = await fetch(`${API_BASE_URL}/modules/delete/status`);
      if (!res.ok) return { is_ready: false, message: 'Status endpoint error' };
      return await res.json();
    } catch (e) {
      return { is_ready: false, message: e.message };
    }
  },

  // Explicitly navigate browser to Unlock VLTD portal URL
  async navigateToPortal() {
    const res = await fetch(`${API_BASE_URL}/modules/delete/navigate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) throw new Error(`Navigation failed: ${res.statusText}`);
    return await res.json();
  },

  // Step 1: Fetch available vehicle registration numbers from portal dropdown (select#reg_input / label#reg_label)
  async getRegistrations() {
    const res = await fetch(`${API_BASE_URL}/modules/delete/registrations`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Failed to fetch available registrations from portal.');
    }
    return await res.json();
  },

  // Step 1 & 2: Select a vehicle registration number from dropdown and verify Release section
  async selectRegistration(registrationNumber) {
    const res = await fetch(`${API_BASE_URL}/modules/delete/select`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ registration_number: registrationNumber }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Failed to select registration number.');
    }
    return await res.json();
  },

  // Step 3: Click the first 'Unlock VLTD' button (field id: 'j_idt112') to open reason modal
  async openReasonModal() {
    const res = await fetch(`${API_BASE_URL}/modules/delete/open-modal`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Failed to open unlock reason modal.');
    }
    return await res.json();
  },

  // Step 4: Populate reason (field: 'Inputreject') and click final unlock button (field: 'j_idt122')
  async confirmUnlock(registrationNumber, reason) {
    const res = await fetch(`${API_BASE_URL}/modules/delete/confirm-unlock`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        registration_number: registrationNumber,
        reason: reason || 'Untag VLTD / Fitment Removal',
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Unlock submission failed.');
    }
    return await res.json();
  },

  // Batch untag/unlock for a list of vehicle registrations
  async batchUnlock(registrations, defaultReason = 'Untag VLTD / Fitment Removal') {
    const res = await fetch(`${API_BASE_URL}/modules/delete/batch-unlock`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        registrations,
        default_reason: defaultReason,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Batch unlock failed.');
    }
    return await res.json();
  },
};

