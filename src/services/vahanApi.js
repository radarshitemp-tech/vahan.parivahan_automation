const API_BASE_URL = import.meta.env.Base_url || 'http://127.0.0.1:8003/api';

export const vahanApi = {
  // Check backend health
  async checkHealth() {
    try {
      const res = await fetch(`${API_BASE_URL}/health`);
      return await res.json();
    } catch (e) {
      return { status: 'offline', error: e.message };
    }
  },

  // Upload and validate batch
  async uploadBatch(fileOrBlob, filename = 'dataset.csv') {
    const formData = new FormData();
    formData.append('file', fileOrBlob, filename);

    const res = await fetch(`${API_BASE_URL}/vahan/batches`, {
      method: 'POST',
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Failed to upload batch to validation engine.');
    }

    return await res.json();
  },

  // Get batch status
  async getBatch(batchId) {
    const res = await fetch(`${API_BASE_URL}/vahan/batches/${batchId}`);
    if (!res.ok) {
      throw new Error(`Failed to fetch batch ${batchId}`);
    }
    return await res.json();
  },

  // Phase B: Launch visible Chrome & check authentication
  async inspectPortal() {
    const res = await fetch(`${API_BASE_URL}/vahan/portal/inspect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Failed to launch portal browser.');
    }

    return await res.json();
  },

  // Phase B: Confirm login & inspect form
  async confirmLoginAndInspect() {
    const res = await fetch(`${API_BASE_URL}/vahan/portal/confirm-login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Failed to inspect portal form.');
    }

    return await res.json();
  },

  // Phase C: Get or generate suggested field mapping
  async getFieldMapping(batchId) {
    const res = await fetch(`${API_BASE_URL}/vahan/batches/${batchId}/mapping`);
    if (!res.ok) {
      throw new Error('Failed to retrieve field mapping.');
    }
    return await res.json();
  },

  // Phase C: Save user-confirmed field mapping
  async saveFieldMapping(batchId, mappingConfig) {
    const res = await fetch(`${API_BASE_URL}/vahan/batches/${batchId}/mapping`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(mappingConfig),
    });

    if (!res.ok) {
      throw new Error('Failed to save field mapping.');
    }
    return await res.json();
  },

  // Phase D: Dry-run autofill single test record (without submitting)
  async executeDryRun(batchId, recordIndex = 0) {
    const res = await fetch(`${API_BASE_URL}/vahan/batches/${batchId}/dry-run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ record_index: recordIndex }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Dry-run execution failed.');
    }

    return await res.json();
  },

  // Phase E & F: Start processing (single or batch or selected subset)
  async startBatchProcessing(batchId, mode = 'batch', selectedRowNumbers = null, selectedRecordIds = null) {
    const payload = { mode };
    if (selectedRowNumbers && selectedRowNumbers.length > 0) {
      payload.selected_row_numbers = selectedRowNumbers;
    }
    if (selectedRecordIds && selectedRecordIds.length > 0) {
      payload.selected_record_ids = selectedRecordIds;
    }

    const res = await fetch(`${API_BASE_URL}/vahan/batches/${batchId}/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Failed to start batch processing.');
    }

    return await res.json();
  },

  // Resume paused batch after user completes manual re-authentication
  async resumeBatch(batchId) {
    const res = await fetch(`${API_BASE_URL}/vahan/batches/${batchId}/resume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Failed to resume batch processing.');
    }

    return await res.json();
  },

  // Stop processing
  async stopBatch(batchId) {
    const res = await fetch(`${API_BASE_URL}/vahan/batches/${batchId}/stop`, {
      method: 'POST',
    });

    if (!res.ok) {
      throw new Error('Failed to send stop signal to worker.');
    }

    return await res.json();
  },

  // Fetch structured execution audit logs
  async getExecutionLogs(batchId, params = {}) {
    const query = new URLSearchParams(params).toString();
    const url = `${API_BASE_URL}/vahan/batches/${batchId}/logs${query ? `?${query}` : ''}`;
    const res = await fetch(url);
    if (!res.ok) {
      return [];
    }
    return await res.json();
  },

  // Get execution report
  async getBatchReport(batchId) {
    const res = await fetch(`${API_BASE_URL}/vahan/batches/${batchId}/report`);
    if (!res.ok) {
      throw new Error('Failed to retrieve batch execution report.');
    }
    return await res.json();
  },

  // Fetch single root log file content (vahan_automation.log)
  async getUnifiedLogs(lines = 200) {
    try {
      const res = await fetch(`${API_BASE_URL}/vahan/logs/unified?lines=${lines}`);
      if (!res.ok) return { log_file: '', content: '' };
      return await res.json();
    } catch {
      return { log_file: '', content: '' };
    }
  },
};
