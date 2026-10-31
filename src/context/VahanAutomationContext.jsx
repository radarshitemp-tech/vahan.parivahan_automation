import React, { createContext, useContext, useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { vahanApi } from '../services/vahanApi';

const VahanAutomationContext = createContext(null);

const STORAGE_KEY = 'vahan_automation_session_v1';

// Helper to safely load persisted session state
const loadInitialState = () => {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      return {
        vahanBatch: parsed.vahanBatch || null,
        workflowState: parsed.workflowState || 'IDLE',
        portalInventory: parsed.portalInventory || null,
        fieldMapping: parsed.fieldMapping || null,
        dryRunResult: parsed.dryRunResult || null,
        executionLogs: parsed.executionLogs || [],
        selectedRowNumbers: Array.isArray(parsed.selectedRowNumbers) ? parsed.selectedRowNumbers : [],
      };
    }
  } catch (err) {
    console.warn('Could not restore VAHAN session from storage:', err);
  }
  return {
    vahanBatch: null,
    workflowState: 'IDLE',
    portalInventory: null,
    fieldMapping: null,
    dryRunResult: null,
    executionLogs: [],
    selectedRowNumbers: [],
  };
};

export const VahanAutomationProvider = ({ children }) => {
  const initial = loadInitialState();

  // Core Automation States
  const [vahanBatch, setVahanBatch] = useState(initial.vahanBatch);
  const [workflowState, setWorkflowState] = useState(initial.workflowState);
  const [portalInventory, setPortalInventory] = useState(initial.portalInventory);
  const [fieldMapping, setFieldMapping] = useState(initial.fieldMapping);
  const [dryRunResult, setDryRunResult] = useState(initial.dryRunResult);
  const [executionLogs, setExecutionLogs] = useState(initial.executionLogs);
  const [selectedRowNumbers, setSelectedRowNumbers] = useState(initial.selectedRowNumbers);

  // Operational / Loading Indicators
  const [isBackendHealthy, setIsBackendHealthy] = useState(false);
  const [isPortalActionLoading, setIsPortalActionLoading] = useState(false);
  const [isDryRunning, setIsDryRunning] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [isResuming, setIsResuming] = useState(false);

  // References for Timers & Lifecycle management
  const pollTimerRef = useRef(null);
  const healthTimerRef = useRef(null);
  const isMountedRef = useRef(true);

  // Persist critical state to sessionStorage whenever updated
  useEffect(() => {
    try {
      const dataToSave = {
        vahanBatch,
        workflowState,
        portalInventory,
        fieldMapping,
        dryRunResult,
        executionLogs,
        selectedRowNumbers,
      };
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(dataToSave));
    } catch (err) {
      console.warn('Failed to save VAHAN session to storage:', err);
    }
  }, [vahanBatch, workflowState, portalInventory, fieldMapping, dryRunResult, executionLogs, selectedRowNumbers]);

  // Monitor Backend Health
  const checkHealth = useCallback(async () => {
    try {
      const res = await vahanApi.checkHealth();
      if (isMountedRef.current) {
        setIsBackendHealthy(res.status === 'ok');
      }
    } catch {
      if (isMountedRef.current) {
        setIsBackendHealthy(false);
      }
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    checkHealth();
    healthTimerRef.current = setInterval(checkHealth, 15000);

    return () => {
      isMountedRef.current = false;
      if (healthTimerRef.current) clearInterval(healthTimerRef.current);
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, [checkHealth]);

  // Synchronize active batch from server if available on mount or state change
  const refreshActiveBatch = useCallback(async (batchId) => {
    if (!batchId) return;
    try {
      const updated = await vahanApi.getBatch(batchId);
      if (isMountedRef.current) {
        setVahanBatch(updated);
        setWorkflowState(updated.state);
        if (updated.mapping) {
          setFieldMapping(updated.mapping);
        }
        if (updated.dry_run_result) {
          setDryRunResult(updated.dry_run_result);
        }
        if (updated.logs) {
          setExecutionLogs(updated.logs);
        }
      }
    } catch (err) {
      console.warn(`Could not sync batch ${batchId}:`, err);
    }
  }, []);

  // Poll server while workflowState is PROCESSING
  useEffect(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }

    if (workflowState === 'PROCESSING' && vahanBatch?.batch_id) {
      pollTimerRef.current = setInterval(async () => {
        try {
          const updated = await vahanApi.getBatch(vahanBatch.batch_id);
          if (!isMountedRef.current) return;
          setVahanBatch(updated);
          setWorkflowState(updated.state);
          if (updated.state !== 'PROCESSING') {
            setIsStopping(false);
          }
          if (updated.logs) {
            setExecutionLogs(updated.logs);
          }
        } catch (pollErr) {
          console.warn('Polling notice:', pollErr);
        }
      }, 1000);
    }

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [workflowState, vahanBatch?.batch_id]);

  // Phase A: Upload & Validate CSV Batch
  const uploadAndValidateBatch = useCallback(async (fileOrBlob, fileName = 'dataset.csv') => {
    setWorkflowState('VALIDATING');
    setDryRunResult(null);
    try {
      const batchResponse = await vahanApi.uploadBatch(fileOrBlob, fileName);
      if (isMountedRef.current) {
        setVahanBatch(batchResponse);
        if (batchResponse.mapping) {
          setFieldMapping(batchResponse.mapping);
        }
        setWorkflowState(batchResponse.state);
        setSelectedRowNumbers([]);
      }
      return batchResponse;
    } catch (err) {
      if (isMountedRef.current) {
        setWorkflowState('COMPLETED_WITH_ERRORS');
      }
      throw err;
    }
  }, []);

  // Phase B: Launch Visible Chrome for Authentication
  const launchPortalBrowser = useCallback(async () => {
    setIsPortalActionLoading(true);
    setWorkflowState('WAITING_FOR_AUTHENTICATION');
    try {
      const inventory = await vahanApi.inspectPortal();
      if (isMountedRef.current) {
        setPortalInventory(inventory);
      }
      return inventory;
    } catch (err) {
      if (isMountedRef.current) {
        setWorkflowState((prev) => (vahanBatch?.state ? vahanBatch.state : 'READY_FOR_REVIEW'));
      }
      throw err;
    } finally {
      if (isMountedRef.current) {
        setIsPortalActionLoading(false);
      }
    }
  }, [vahanBatch?.state]);

  // Phase B: Confirm Login & Inspect Form Fields
  const confirmLoginAndInspectForm = useCallback(async () => {
    setIsPortalActionLoading(true);
    setWorkflowState('INSPECTING_FORM');
    try {
      const inventory = await vahanApi.confirmLoginAndInspect();
      if (isMountedRef.current) {
        setPortalInventory(inventory);
      }

      if (inventory.is_authenticated && inventory.is_sld_form_available) {
        if (isMountedRef.current) {
          setWorkflowState('READY_TO_PROCESS');
        }
        if (vahanBatch?.batch_id) {
          const mapping = await vahanApi.getFieldMapping(vahanBatch.batch_id);
          if (isMountedRef.current) {
            setFieldMapping((prev) => {
              // Safeguard: never overwrite complete mapping with an incomplete one
              if (prev && prev.is_complete && (!mapping || !mapping.is_complete)) {
                return prev;
              }
              return mapping;
            });
          }
        }
      } else {
        if (isMountedRef.current) {
          setWorkflowState('WAITING_FOR_AUTHENTICATION');
        }
      }
      return inventory;
    } catch (err) {
      if (isMountedRef.current) {
        setWorkflowState('WAITING_FOR_AUTHENTICATION');
      }
      throw err;
    } finally {
      if (isMountedRef.current) {
        setIsPortalActionLoading(false);
      }
    }
  }, [vahanBatch?.batch_id]);

  // Phase C: Fetch Field Mapping
  const fetchFieldMapping = useCallback(async (batchId = vahanBatch?.batch_id) => {
    if (!batchId) return null;
    const mapping = await vahanApi.getFieldMapping(batchId);
    if (isMountedRef.current) {
      setFieldMapping(mapping);
    }
    return mapping;
  }, [vahanBatch?.batch_id]);

  // Phase C: Save Field Mapping
  const saveFieldMapping = useCallback(async (customMapping) => {
    if (!vahanBatch?.batch_id) return null;
    const target = customMapping || fieldMapping;
    if (!target) return null;
    const updated = await vahanApi.saveFieldMapping(vahanBatch.batch_id, target);
    if (isMountedRef.current) {
      setFieldMapping(updated);
      setVahanBatch((prev) => (prev ? { ...prev, mapping: updated } : prev));
    }
    return updated;
  }, [vahanBatch?.batch_id, fieldMapping]);

  // Phase C: Quick-Apply Standard VAHAN Defaults
  const applyVahanPresets = useCallback(async () => {
    if (!fieldMapping || !vahanBatch?.batch_id) return null;

    const presets = {
      'Vehicle State': { target_field_id: 'stateCd', target_field_name: 'stateCd', target_field_label: 'Vehicle State', element_tag: 'select', is_required: true },
      'RTO': { target_field_id: 'offCd', target_field_name: 'offCd', target_field_label: 'RTO / Registering Authority', element_tag: 'select', is_required: true },
      'Registration Type': { target_field_id: 'reg_type', target_field_name: 'reg_type', target_field_label: 'Registration Type', element_tag: 'select', is_required: true },
      'Vehicle Chassis No': { target_field_id: 'temp_reg_no', target_field_name: 'temp_reg_no', target_field_label: 'Vehicle Chassis No', element_tag: 'input', is_required: true },
      'Vehicle Engine No (LAST 5 DIGITS)': { target_field_id: 'temp_eng_no', target_field_name: 'temp_eng_no', target_field_label: 'Vehicle Engine No (LAST 5 DIGITS)', element_tag: 'input', is_required: true },
      'VLTD Maker': { target_field_id: 'kit_maker', target_field_name: 'kit_maker', target_field_label: 'VLTD Maker', element_tag: 'select', is_required: true },
      'VLTD Model': { target_field_id: 'kit_alloted_model', target_field_name: 'kit_alloted_model', target_field_label: 'VLTD Model', element_tag: 'select', is_required: true },
      'VLTD serial Number': { target_field_id: 'sr_No_Panel', target_field_name: 'sr_No_Panel', target_field_label: 'VLTD Serial Number', element_tag: 'input', is_required: true },
      'Provider': { target_field_id: 'tf_scrPro', target_field_name: 'tf_scrPro', target_field_label: 'Service Provider', element_tag: 'select', is_required: true },
      'IMEI Number': { target_field_id: 'tf_imei', target_field_name: 'tf_imei', target_field_label: 'IMEI Number', element_tag: 'input', is_required: true },
      'ICC ID': { target_field_id: 'tf_iccID', target_field_name: 'tf_iccID', target_field_label: 'ICC ID', element_tag: 'input', is_required: true },
    };

    const aliasMap = {
      'vltd maker': 'VLTD Maker',
      'maker': 'VLTD Maker',
      'vltd model': 'VLTD Model',
      'model': 'VLTD Model',
      'vltd serial number': 'VLTD serial Number',
      'serial number': 'VLTD serial Number',
      'provider': 'Provider',
      'imei number': 'IMEI Number',
      'imei': 'IMEI Number',
      'icc id': 'ICC ID',
      'registration type': 'Registration Type',
      'vehicle chassis no': 'Vehicle Chassis No',
      'vehicle chasis no': 'Vehicle Chassis No',
      'chasis no': 'Vehicle Chassis No',
      'vehicle engine no (last 5 digits)': 'Vehicle Engine No (LAST 5 DIGITS)',
      'vehicle engine no.': 'Vehicle Engine No (LAST 5 DIGITS)',
      'vehicle engine no': 'Vehicle Engine No (LAST 5 DIGITS)',
      'engine no': 'Vehicle Engine No (LAST 5 DIGITS)',
      'vehicle state': 'Vehicle State',
      'state': 'Vehicle State',
      'rto': 'RTO',
    };

    const updatedMappings = { ...fieldMapping.mappings };
    Object.keys(updatedMappings).forEach((colKey) => {
      const cleanKey = colKey.toLowerCase().replace(/[\.\:\-_]+$/, '').trim();
      const targetCanonical = presets[colKey] ? colKey : (aliasMap[cleanKey] || null);
      if (targetCanonical && presets[targetCanonical]) {
        updatedMappings[colKey] = {
          ...updatedMappings[colKey],
          ...presets[targetCanonical],
        };
      }
    });

    Object.keys(presets).forEach((col) => {
      if (updatedMappings[col]) {
        updatedMappings[col] = {
          ...updatedMappings[col],
          ...presets[col],
        };
      }
    });

    const completeMapping = {
      ...fieldMapping,
      mappings: updatedMappings,
      missing_required_fields: [],
      is_complete: true,
    };

    if (isMountedRef.current) {
      setFieldMapping(completeMapping);
    }

    try {
      const saved = await vahanApi.saveFieldMapping(vahanBatch.batch_id, completeMapping);
      if (isMountedRef.current) {
        setFieldMapping(saved);
        setVahanBatch((prev) => (prev ? { ...prev, mapping: saved } : prev));
      }
      return saved;
    } catch {
      return completeMapping;
    }
  }, [fieldMapping, vahanBatch?.batch_id]);

  // Phase D: Execute Dry-Run Autofill
  const executeDryRunAutofill = useCallback(async (recordIndex = 0) => {
    if (!vahanBatch?.batch_id) return null;
    setIsDryRunning(true);
    try {
      if (fieldMapping) {
        await vahanApi.saveFieldMapping(vahanBatch.batch_id, fieldMapping);
      }
      const result = await vahanApi.executeDryRun(vahanBatch.batch_id, recordIndex);
      if (isMountedRef.current) {
        setDryRunResult(result);
        if (result.success) {
          setWorkflowState('READY_TO_PROCESS');
        }
      }
      return result;
    } finally {
      if (isMountedRef.current) {
        setIsDryRunning(false);
      }
    }
  }, [vahanBatch?.batch_id, fieldMapping]);

  // Phase E: Single Record Processing
  const startSingleRecordProcessing = useCallback(async () => {
    if (!vahanBatch?.batch_id) return null;
    if (fieldMapping) {
      await vahanApi.saveFieldMapping(vahanBatch.batch_id, fieldMapping);
    }
    setWorkflowState('PROCESSING');
    const updated = await vahanApi.startBatchProcessing(vahanBatch.batch_id, 'single');
    if (isMountedRef.current) {
      setVahanBatch(updated);
    }
    return updated;
  }, [vahanBatch?.batch_id, fieldMapping]);

  // Phase F: Sequential Batch Processing (Full or Selected Rows)
  const startBatchProcessing = useCallback(async (onlySelected = false) => {
    if (!vahanBatch?.batch_id) return null;
    if (fieldMapping) {
      await vahanApi.saveFieldMapping(vahanBatch.batch_id, fieldMapping);
    }
    setWorkflowState('PROCESSING');
    const rowsToProcess = onlySelected && selectedRowNumbers.length > 0 ? selectedRowNumbers : null;
    const updated = await vahanApi.startBatchProcessing(vahanBatch.batch_id, 'batch', rowsToProcess);
    if (isMountedRef.current) {
      setVahanBatch(updated);
    }
    return updated;
  }, [vahanBatch?.batch_id, fieldMapping, selectedRowNumbers]);

  // Resume processing after manual authentication
  const resumeBatchProcessing = useCallback(async () => {
    if (!vahanBatch?.batch_id) return null;
    setIsResuming(true);
    setWorkflowState('PROCESSING');
    try {
      const updated = await vahanApi.resumeBatch(vahanBatch.batch_id);
      if (isMountedRef.current) {
        setVahanBatch(updated);
      }
      return updated;
    } catch (err) {
      if (isMountedRef.current) {
        setWorkflowState('PAUSED_AUTH_REQUIRED');
      }
      throw err;
    } finally {
      if (isMountedRef.current) {
        setIsResuming(false);
      }
    }
  }, [vahanBatch?.batch_id]);

  // Controlled Stop
  const requestStopProcessing = useCallback(async () => {
    if (!vahanBatch?.batch_id) return null;
    setIsStopping(true);
    try {
      const res = await vahanApi.stopBatch(vahanBatch.batch_id);
      return res;
    } finally {
      // Keep isStopping true until state leaves PROCESSING
    }
  }, [vahanBatch?.batch_id]);

  // Fetch Execution Audit Logs
  const fetchExecutionLogs = useCallback(async (level = 'ALL') => {
    if (!vahanBatch?.batch_id) return [];
    try {
      const params = level !== 'ALL' ? { level } : {};
      const logs = await vahanApi.getExecutionLogs(vahanBatch.batch_id, params);
      if (isMountedRef.current) {
        setExecutionLogs(logs);
      }
      return logs;
    } catch (err) {
      console.warn('Failed to load logs:', err);
      return [];
    }
  }, [vahanBatch?.batch_id]);

  // Row Selection Management
  const toggleRowSelection = useCallback((rowNumber) => {
    setSelectedRowNumbers((prev) => {
      const exists = prev.includes(rowNumber);
      return exists ? prev.filter((r) => r !== rowNumber) : [...prev, rowNumber];
    });
  }, []);

  const selectAllRows = useCallback((rowNumbers) => {
    setSelectedRowNumbers(Array.from(new Set(rowNumbers)));
  }, []);

  const clearRowSelection = useCallback(() => {
    setSelectedRowNumbers([]);
  }, []);

  // Root Log File Inspection
  const fetchUnifiedLogs = useCallback(async (lines = 200) => {
    return await vahanApi.getUnifiedLogs(lines);
  }, []);

  // Complete Reset
  const resetAutomationState = useCallback(() => {
    setVahanBatch(null);
    setWorkflowState('IDLE');
    setPortalInventory(null);
    setFieldMapping(null);
    setDryRunResult(null);
    setExecutionLogs([]);
    setSelectedRowNumbers([]);
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {}
  }, []);

  // Memoized Summary Metrics
  const summaryMetrics = useMemo(() => {
    if (!vahanBatch) {
      return {
        totalRecords: 0,
        validRecords: 0,
        invalidRecords: 0,
        processedRecords: 0,
        successfulRecords: 0,
        failedRecords: 0,
        percentComplete: 0,
      };
    }
    const s = vahanBatch.summary || {};
    const total = s.total_records_count || vahanBatch.records?.length || 0;
    const completed = s.successful_records_count || 0;
    const failed = s.failed_records_count || 0;
    const processed = completed + failed;
    const percent = total > 0 ? Math.round((processed / total) * 100) : 0;
    return {
      totalRecords: total,
      validRecords: s.valid_records_count || 0,
      invalidRecords: s.invalid_records_count || 0,
      processedRecords: processed,
      successfulRecords: completed,
      failedRecords: failed,
      percentComplete: percent,
    };
  }, [vahanBatch]);

  const value = useMemo(() => ({
    // State
    vahanBatch,
    setVahanBatch,
    workflowState,
    setWorkflowState,
    portalInventory,
    setPortalInventory,
    fieldMapping,
    setFieldMapping,
    dryRunResult,
    setDryRunResult,
    executionLogs,
    selectedRowNumbers,
    isBackendHealthy,
    isPortalActionLoading,
    isDryRunning,
    isStopping,
    isResuming,
    summaryMetrics,

    // Actions (Stable useCallback hooks)
    uploadAndValidateBatch,
    launchPortalBrowser,
    confirmLoginAndInspectForm,
    fetchFieldMapping,
    saveFieldMapping,
    applyVahanPresets,
    executeDryRunAutofill,
    startSingleRecordProcessing,
    startBatchProcessing,
    resumeBatchProcessing,
    requestStopProcessing,
    fetchExecutionLogs,
    refreshActiveBatch,
    toggleRowSelection,
    selectAllRows,
    clearRowSelection,
    resetAutomationState,
    fetchUnifiedLogs,
  }), [
    vahanBatch,
    workflowState,
    portalInventory,
    fieldMapping,
    dryRunResult,
    executionLogs,
    selectedRowNumbers,
    isBackendHealthy,
    isPortalActionLoading,
    isDryRunning,
    isStopping,
    isResuming,
    summaryMetrics,
    uploadAndValidateBatch,
    launchPortalBrowser,
    confirmLoginAndInspectForm,
    fetchFieldMapping,
    saveFieldMapping,
    applyVahanPresets,
    executeDryRunAutofill,
    startSingleRecordProcessing,
    startBatchProcessing,
    resumeBatchProcessing,
    requestStopProcessing,
    fetchExecutionLogs,
    refreshActiveBatch,
    toggleRowSelection,
    selectAllRows,
    clearRowSelection,
    resetAutomationState,
    fetchUnifiedLogs,
  ]);

  return (
    <VahanAutomationContext.Provider value={value}>
      {children}
    </VahanAutomationContext.Provider>
  );
};

export const useVahanAutomation = () => {
  const context = useContext(VahanAutomationContext);
  if (!context) {
    throw new Error('useVahanAutomation must be used within a VahanAutomationProvider');
  }
  return context;
};
