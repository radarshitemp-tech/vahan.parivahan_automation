import { useState, useRef, useCallback, useMemo } from 'react';
import { useCsv } from '../context/CsvContext';
import { useVahanAutomation } from '../context/VahanAutomationContext';
import { vahanApi } from '../services/vahanApi';
import {
  Box,
  Typography,
  TextField,
  Button,
  Tabs,
  Tab,
  Alert,
  AlertTitle,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  TablePagination,
  Chip,
  IconButton,
  Tooltip,
  Snackbar,
  InputAdornment,
  LinearProgress,
  Collapse,
  Select,
  MenuItem,
  Menu,
  FormControl,
  Checkbox,
  Divider
} from '@mui/material';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import LinkIcon from '@mui/icons-material/Link';
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import SearchIcon from '@mui/icons-material/Search';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import ClearIcon from '@mui/icons-material/Clear';
import VisibilityIcon from '@mui/icons-material/Visibility';
import DownloadIcon from '@mui/icons-material/Download';
import OpenInBrowserIcon from '@mui/icons-material/OpenInBrowser';
import FactCheckIcon from '@mui/icons-material/FactCheck';
import StopCircleIcon from '@mui/icons-material/StopCircle';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import SaveIcon from '@mui/icons-material/Save';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import ModuleHeader from '../components/common/ModuleHeader';
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome';
import ReceiptLongIcon from '@mui/icons-material/ReceiptLong';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import MoreVertIcon from '@mui/icons-material/MoreVert';

export default function ExtractPage() {
  const {
    csvData,
    columns,
    fileName,
    sourceType,
    metadata,
    isLoading,
    error,
    setError,
    loadLocalFile,
    loadFromUrl,
    loadSampleData,
    clearData
  } = useCsv();

  // Ingestion Mode: 0 = Local File, 1 = Link / URL
  const [tabIndex, setTabIndex] = useState(0);

  // Local File state
  const [selectedLocalFile, setSelectedLocalFile] = useState(null);
  const fileInputRef = useRef(null);
  const [isDragOver, setIsDragOver] = useState(false);

  // Link state
  const [csvUrl, setCsvUrl] = useState('');

  // Dialog error state for redirect / invalid link error pop up
  const [errorDialogOpen, setErrorDialogOpen] = useState(false);
  const [errorDialogMessage, setErrorDialogMessage] = useState('');

  // Table pagination & filtering
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedRowDetail, setSelectedRowDetail] = useState(null);

  // Toast notification
  const [toastMessage, setToastMessage] = useState('');
  const [toastOpen, setToastOpen] = useState(false);

  // Consume persistent VAHAN automation context (memory/data preserved across re-renders and page navigation)
  const {
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
  } = useVahanAutomation();

  // Local UI modal states
  const [showErrorReview, setShowErrorReview] = useState(false);
  const [showInventoryReview, setShowInventoryReview] = useState(false);
  const [showMappingConfig, setShowMappingConfig] = useState(false);
  const [showExecutionReport, setShowExecutionReport] = useState(false);
  const [showLogsModal, setShowLogsModal] = useState(false);
  const [logFilterLevel, setLogFilterLevel] = useState('ALL');
  const [showUnifiedRootLog, setShowUnifiedRootLog] = useState(false);
  const [unifiedRootLogText, setUnifiedRootLogText] = useState('');
  const [unifiedRootLogPath, setUnifiedRootLogPath] = useState('');
  const [onDemandAnchorEl, setOnDemandAnchorEl] = useState(null);
  const handleOpenOnDemand = (event) => setOnDemandAnchorEl(event.currentTarget);
  const handleCloseOnDemand = () => setOnDemandAnchorEl(null);

  // Convert array of selected row numbers to Set for O(1) membership checks in table
  const selectedRows = useMemo(() => new Set(selectedRowNumbers), [selectedRowNumbers]);

  // Handle Local File Selection
  const handleFileChange = useCallback((e) => {
    const file = e.target.files && e.target.files[0];
    if (file) {
      setSelectedLocalFile(file);
      setError(null);
    }
  }, [setError]);

  // Drag and Drop handlers
  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setSelectedLocalFile(e.dataTransfer.files[0]);
      setError(null);
    }
  }, [setError]);

  // Core Extract Data Trigger (Client Preview + Python Backend Validation Integration)
  const handleExtractData = useCallback(async () => {
    setError(null);
    setWorkflowState('UPLOADING');
    setDryRunResult(null);

    let currentFileBlob = null;
    let currentFileName = 'dataset.csv';

    if (tabIndex === 0) {
      // Local File Mode
      if (!selectedLocalFile) {
        setError('Please select or drop a CSV file from your local device first.');
        setWorkflowState('IDLE');
        return;
      }
      currentFileBlob = selectedLocalFile;
      currentFileName = selectedLocalFile.name;

      try {
        await loadLocalFile(selectedLocalFile);
        setPage(0);
      } catch (err) {
        setErrorDialogMessage(err.message || 'Failed to extract local CSV data.');
        setErrorDialogOpen(true);
        setWorkflowState('IDLE');
        return;
      }
    } else {
      // Link / URL Mode
      if (!csvUrl || !csvUrl.trim()) {
        setError('Please enter a valid CSV link URL.');
        setWorkflowState('IDLE');
        return;
      }

      try {
        const urlRes = await loadFromUrl(csvUrl.trim());
        setPage(0);
        const textContent = urlRes?.rawText || '';
        currentFileBlob = new Blob([textContent], { type: 'text/csv' });
        currentFileName = urlRes?.fileName || 'remote-dataset.csv';
      } catch (err) {
        setErrorDialogMessage(err.message || 'The provided link does not redirect to a valid CSV file.');
        setErrorDialogOpen(true);
        setWorkflowState('IDLE');
        return;
      }
    }

    // Now validate through Python Backend (Phase A)
    try {
      setWorkflowState('VALIDATING');
      const batchResponse = await uploadAndValidateBatch(currentFileBlob, currentFileName);
      setToastMessage(`Validated batch ${batchResponse.batch_id.slice(0, 8)} (${batchResponse.summary.valid_records_count} valid, ${batchResponse.summary.invalid_records_count} invalid).`);
      setToastOpen(true);
    } catch (backendErr) {
      console.warn('Backend validation notice:', backendErr.message);
      setError(`Backend Schema Validation: ${backendErr.message}`);
    }
  }, [tabIndex, selectedLocalFile, csvUrl, loadLocalFile, loadFromUrl, uploadAndValidateBatch, setError, setWorkflowState, setDryRunResult]);

  // Phase B: Launch Visible Chrome Browser for Authentication
  const handleLaunchPortal = useCallback(async () => {
    try {
      await launchPortalBrowser();
      setToastMessage('Visible Chrome opened. Complete login in Chrome, then click "Confirm & Inspect Form".');
      setToastOpen(true);
    } catch (err) {
      setErrorDialogMessage(`Failed to launch VAHAN portal browser: ${err.message}`);
      setErrorDialogOpen(true);
    }
  }, [launchPortalBrowser]);

  // Confirm session Login (Checks session authentication + gives the field mapping and the discovered elements are hidden by default)
  const handleConfirmLoginAndInspect = useCallback(async () => {
    try {
      const inventory = await confirmLoginAndInspectForm();
      if (inventory.is_authenticated && inventory.is_sld_form_available) {
        setShowInventoryReview(false); // Discovered elements are hidden by default
        if (vahanBatch?.batch_id) {
          await fetchFieldMapping(vahanBatch.batch_id);
          setShowMappingConfig(true); // Gives the field mapping
        }
        setToastMessage(`Session authenticated! Discovered ${inventory.fields.length} form fields & field mapping loaded.`);
        setTimeout(() => {
          const el = document.getElementById('vahan-section-mapping');
          if (el) el.scrollIntoView({ behavior: 'smooth' });
        }, 150);
      } else {
        setErrorDialogMessage(inventory.message || 'Portal form not yet reached. Please complete login and navigate to SLD Fitting page.');
        setErrorDialogOpen(true);
      }
      setToastOpen(true);
    } catch (err) {
      setErrorDialogMessage(`Session authentication check failed: ${err.message}`);
      setErrorDialogOpen(true);
    }
  }, [confirmLoginAndInspectForm, vahanBatch?.batch_id, fetchFieldMapping]);

  // Phase C: Fetch / Configure Field Mapping
  const handleOpenMappingConfig = useCallback(async () => {
    if (!vahanBatch) return;
    try {
      await fetchFieldMapping(vahanBatch.batch_id);
      setShowMappingConfig(true);
      setTimeout(() => {
        const el = document.getElementById('vahan-section-mapping');
        if (el) el.scrollIntoView({ behavior: 'smooth' });
      }, 150);
    } catch (err) {
      setErrorDialogMessage(`Failed to load mapping: ${err.message}`);
      setErrorDialogOpen(true);
    }
  }, [vahanBatch, fetchFieldMapping]);

  // Phase C: Quick-Apply Standard VAHAN Portal Field Selectors
  const handleApplyVahanDefaults = useCallback(async () => {
    try {
      await applyVahanPresets();
      setToastMessage('Standard VAHAN VLTD field selectors loaded and saved successfully!');
      setToastOpen(true);
    } catch {
      setToastMessage('Standard VAHAN VLTD field selectors loaded! Click "Save Mapping" to verify.');
      setToastOpen(true);
    }
  }, [applyVahanPresets]);

  // Phase C: Save Field Mapping
  const handleSaveMapping = useCallback(async () => {
    if (!vahanBatch || !fieldMapping) return;
    try {
      const updated = await saveFieldMapping(fieldMapping);
      if (updated) {
        setToastMessage(updated.is_complete ? 'Field mapping verified and saved successfully!' : 'Mapping saved (Incomplete requirements flagged).');
        setToastOpen(true);
      }
    } catch (err) {
      setErrorDialogMessage(`Failed to save mapping: ${err.message}`);
      setErrorDialogOpen(true);
    }
  }, [vahanBatch, fieldMapping, saveFieldMapping]);

  // Phase D: Execute Dry-Run Autofill (Test Record 1 - No Submit)
  const handleExecuteDryRun = useCallback(async () => {
    if (!vahanBatch) return;
    try {
      const result = await executeDryRunAutofill(0);
      if (result) {
        if (result.success) {
          setToastMessage(`Dry-run succeeded! Record ${result.record_id} values matched DOM read-back.`);
        } else {
          setToastMessage(`Dry-run discrepancy detected for Record ${result.record_id}. Form was not submitted.`);
        }
        setToastOpen(true);
      }
    } catch (err) {
      setErrorDialogMessage(`Dry-run execution failed: ${err.message}`);
      setErrorDialogOpen(true);
    }
  }, [vahanBatch, executeDryRunAutofill]);

  // Phase E: Process Single Test Record
  const handleStartSingleRecord = useCallback(async () => {
    if (!vahanBatch) return;
    try {
      await startSingleRecordProcessing();
      setToastMessage('Started Phase E controlled test record submission.');
      setToastOpen(true);
    } catch (err) {
      setErrorDialogMessage(`Failed to start single test record: ${err.message}`);
      setErrorDialogOpen(true);
    }
  }, [vahanBatch, startSingleRecordProcessing]);

  // Phase F: Start Sequential Batch Processing (Full Batch or Selected Subset)
  const handleStartBatchProcessing = useCallback(async (onlySelected = false) => {
    if (!vahanBatch) return;
    try {
      await startBatchProcessing(onlySelected);
      setToastMessage(onlySelected ? `Started processing ${selectedRowNumbers.length} selected record(s).` : 'Started sequential batch entry.');
      setToastOpen(true);
    } catch (err) {
      setErrorDialogMessage(`Failed to start batch processing: ${err.message}`);
      setErrorDialogOpen(true);
    }
  }, [vahanBatch, startBatchProcessing, selectedRowNumbers.length]);

  // Resume processing after user completes manual re-authentication
  const handleResumeBatch = useCallback(async () => {
    if (!vahanBatch) return;
    try {
      await resumeBatchProcessing();
      setToastMessage('Resumed batch processing after re-authentication.');
      setToastOpen(true);
    } catch (err) {
      setErrorDialogMessage(`Failed to resume batch: ${err.message}`);
      setErrorDialogOpen(true);
    }
  }, [vahanBatch, resumeBatchProcessing]);

  // Open Structured Audit Logs Modal
  const handleRefreshUnifiedRootLog = useCallback(async () => {
    try {
      const data = await fetchUnifiedLogs(300);
      setUnifiedRootLogText(data.content || 'Root log file is currently empty.');
      setUnifiedRootLogPath(data.log_file || 'vahan_automation.log');
    } catch (err) {
      setUnifiedRootLogText(`Failed to load root log file: ${err.message}`);
    }
  }, [fetchUnifiedLogs]);

  // Open Structured Audit Logs Modal
  const handleOpenLogsModal = useCallback(async () => {
    try {
      if (vahanBatch) {
        await fetchExecutionLogs(logFilterLevel !== 'ALL' ? logFilterLevel : undefined);
      }
      await handleRefreshUnifiedRootLog();
      setShowLogsModal(true);
    } catch (err) {
      console.warn('Could not load logs:', err);
    }
  }, [vahanBatch, fetchExecutionLogs, logFilterLevel, handleRefreshUnifiedRootLog]);

  // Controlled Stop Request
  const handleStopProcessing = useCallback(async () => {
    if (!vahanBatch) return;
    try {
      await requestStopProcessing();
      setToastMessage('Stop request sent. Waiting for worker to cease between atomic operations...');
      setToastOpen(true);
    } catch (err) {
      setErrorDialogMessage(`Failed to send stop signal: ${err.message}`);
      setErrorDialogOpen(true);
    }
  }, [vahanBatch, requestStopProcessing]);

  // Download Execution Audit Report
  const handleDownloadReport = useCallback(() => {
    if (!vahanBatch) return;
    const reportData = {
      batch_id: vahanBatch.batch_id,
      file_name: vahanBatch.file_name,
      final_state: workflowState,
      summary: vahanBatch.summary,
      records: vahanBatch.records.map((r) => ({
        row_number: r.row_number,
        id: r.id,
        vltd_maker: r.vltd_maker,
        imei_number: r.imei_number,
        status: r.status,
        confirmation_ref: r.portal_confirmation_ref,
        execution_message: r.execution_message,
        executed_at: r.executed_at,
      })),
      errors: vahanBatch.errors,
      exported_at: new Date().toISOString(),
    };

    const blob = new Blob([JSON.stringify(reportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `vahan-execution-report-${vahanBatch.batch_id.slice(0, 8)}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }, [vahanBatch, workflowState]);

  // Search Filter with useMemo for performance
  const filteredData = useMemo(() => {
    if (!csvData || csvData.length === 0) return [];
    if (!searchQuery.trim()) return csvData;
    const query = searchQuery.toLowerCase();
    return csvData.filter((row) =>
      Object.values(row).some((val) =>
        val !== null && val !== undefined && String(val).toLowerCase().includes(query)
      )
    );
  }, [csvData, searchQuery]);

  const paginatedData = useMemo(() => {
    return filteredData.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);
  }, [filteredData, page, rowsPerPage]);

  // Copy JSON to clipboard
  const handleCopyJson = () => {
    navigator.clipboard.writeText(JSON.stringify(filteredData, null, 2));
    setToastMessage(`Copied ${filteredData.length} records as JSON to clipboard!`);
    setToastOpen(true);
    alert("Copied Json to your Clipboard")
  };

  // Export current view as CSV
  const handleExportCsv = () => {
    if (filteredData.length === 0) return;
    const headers = columns.join(',');
    const rows = filteredData.map((row) =>
      columns.map((col) => {
        const val = row[col];
        if (typeof val === 'string' && val.includes(',')) {
          return `"${val.replace(/"/g, '""')}"`;
        }
        return val ?? '';
      }).join(',')
    );
    const csvContent = [headers, ...rows].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `extracted-${fileName || 'data'}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setToastMessage('CSV download started!');
    setToastOpen(true);
  };

  // State Badge Color Helper
  const getStateColor = (st) => {
    switch (st) {
      case 'READY_TO_PROCESS':
      case 'COMPLETED':
        return '#10b981';
      case 'WAITING_FOR_AUTHENTICATION':
      case 'INSPECTING_FORM':
      case 'READY_FOR_REVIEW':
        return '#6366f1';
      case 'UPLOADING':
      case 'VALIDATING':
      case 'PROCESSING':
        return '#06b6d4';
      case 'STOPPED':
      case 'COMPLETED_WITH_ERRORS':
        return '#ef4444';
      default:
        return '#94a3b8';
    }
  };

  return (
    <div className="fade-in">
      {/* Central Module Navigation Header */}
      <ModuleHeader
        currentModuleId="add_vltd"
        title="Add / Fitment VLTD Module"
        badge="Fitment Details"
        description="Upload CSV data, inspect VAHAN retrofitment forms, configure field mappings, and execute bulk device fitment."
        color="#6366f1"
      />

      {/* Page Header */}
      <div className="extract-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <Typography variant="h4" sx={{ fontWeight: 800, color: '#fff', mb: 1 }}>
            VAHAN VLTD Ingestion & Automation Engine
          </Typography>
          <Typography variant="body1" sx={{ color: '#94a3b8' }}>
            Upload your CSV to validate VAHAN VLTD schemas, inspect the official portal form, configure field mapping, and execute controlled retrofitting entries.
          </Typography>
        </div>

        {/* Backend Connectivity Status Pill */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Chip
            icon={isBackendHealthy ? <CheckCircleIcon sx={{ fontSize: 16 }} /> : <WarningAmberIcon sx={{ fontSize: 16 }} />}
            label={isBackendHealthy ? 'Backend: Online' : 'Backend: Offline (Waiting)'}
            size="small"
            sx={{
              backgroundColor: isBackendHealthy ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)',
              color: isBackendHealthy ? '#34d399' : '#f87171',
              fontWeight: 600,
              border: `1px solid ${isBackendHealthy ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
            }}
          />
        </div>
      </div>

      {/* CSV Uploader Card (Preserved existing component & UI patterns) */}
      <div className="glass-panel" style={{ padding: '2rem', marginBottom: '2.5rem' }}>
        <Tabs
          value={tabIndex}
          onChange={(_, val) => {
            setTabIndex(val);
            setError(null);
          }}
          sx={{
            borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
            mb: 3,
            '& .MuiTab-root': {
              color: '#94a3b8',
              fontWeight: 600,
              textTransform: 'none',
              fontSize: '0.95rem',
              '&.Mui-selected': {
                color: '#818cf8',
              },
            },
            '& .MuiTabs-indicator': {
              backgroundColor: '#6366f1',
              height: 3,
              borderRadius: '3px 3px 0 0',
            },
          }}
        >
          <Tab icon={<CloudUploadIcon />} iconPosition="start" label="Upload Local CSV" />
          <Tab icon={<LinkIcon />} iconPosition="start" label="Input CSV Link (URL)" />
        </Tabs>

        {/* Tab 0: Local File Upload */}
        {tabIndex === 0 && (
          <Box>
            <input
              type="file"
              accept=".csv,text/csv"
              ref={fileInputRef}
              style={{ display: 'none' }}
              onChange={handleFileChange}
            />

            <div
              className={`dropzone-container ${isDragOver ? 'drag-over' : ''}`}
              onClick={() => fileInputRef.current && fileInputRef.current.click()}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <div className="dropzone-icon-circle">
                <CloudUploadIcon sx={{ fontSize: 36 }} />
              </div>

              {selectedLocalFile ? (
                <div>
                  <Typography variant="h6" sx={{ color: '#fff', fontWeight: 700, mb: 0.5 }}>
                    {selectedLocalFile.name}
                  </Typography>
                  <Typography variant="body2" sx={{ color: '#38bdf8' }}>
                    {(selectedLocalFile.size / 1024).toFixed(2)} KB • Click or drop another file to replace
                  </Typography>
                </div>
              ) : (
                <div>
                  <Typography variant="h6" sx={{ color: '#fff', fontWeight: 700, mb: 0.5 }}>
                    Drag & Drop your VAHAN VLTD CSV file here, or browse
                  </Typography>
                  <Typography variant="body2" sx={{ color: '#94a3b8' }}>
                    Columns: ID, VLTD Maker, VLTD Model, VLTD serial Number, Provider, IMEI Number, Registration Type.
                  </Typography>
                </div>
              )}
            </div>
          </Box>
        )}

        {/* Tab 1: CSV Link / URL */}
        {tabIndex === 1 && (
          <Box>
            <TextField
              fullWidth
              label="CSV Direct Link / URL"
              placeholder="https://example.com/data.csv or local sample endpoint"
              value={csvUrl}
              onChange={(e) => {
                setCsvUrl(e.target.value);
                setError(null);
              }}
              variant="outlined"
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <LinkIcon sx={{ color: '#818cf8' }} />
                  </InputAdornment>
                ),
                endAdornment: csvUrl && (
                  <InputAdornment position="end">
                    <IconButton size="small" onClick={() => setCsvUrl('')} sx={{ color: '#94a3b8' }}>
                      <ClearIcon fontSize="small" />
                    </IconButton>
                  </InputAdornment>
                ),
              }}
              sx={{
                mb: 2,
                '& .MuiOutlinedInput-root': {
                  color: '#fff',
                  backgroundColor: 'rgba(15, 23, 42, 0.6)',
                  borderRadius: '12px',
                  '& fieldset': {
                    borderColor: 'rgba(255, 255, 255, 0.15)',
                  },
                  '&:hover fieldset': {
                    borderColor: '#818cf8',
                  },
                  '&.Mui-focused fieldset': {
                    borderColor: '#6366f1',
                  },
                },
                '& .MuiInputLabel-root': {
                  color: '#94a3b8',
                  '&.Mui-focused': {
                    color: '#818cf8',
                  },
                },
              }}
            />

            {/* Quick Demo URLs to test both valid & invalid link behaviors */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 1 }}>
              <Typography variant="caption" sx={{ color: '#64748b', fontWeight: 600 }}>
                QUICK TEST LINKS:
              </Typography>
              <Chip
                label="VAHAN VLTD Sample (/sample-vahan-vltd.csv)"
                size="small"
                onClick={() => setCsvUrl('/sample-vahan-vltd.csv')}
                sx={{ backgroundColor: 'rgba(99, 102, 241, 0.15)', color: '#a5b4fc', cursor: 'pointer' }}
              />
              <Chip
                label="Invalid Schema Test (/invalid-sample-vahan.csv)"
                size="small"
                onClick={() => setCsvUrl('/invalid-sample-vahan.csv')}
                sx={{ backgroundColor: 'rgba(239, 68, 68, 0.15)', color: '#f87171', cursor: 'pointer' }}
              />
              <Chip
                label="Invalid Webpage Link (Tests Error Popup)"
                size="small"
                onClick={() => setCsvUrl('https://github.com/')}
                sx={{ backgroundColor: 'rgba(245, 158, 11, 0.15)', color: '#fde68a', cursor: 'pointer' }}
              />
            </Box>
          </Box>
        )}

        {/* Extraction Error Notice in Card */}
        {error && (
          <Alert
            severity="error"
            icon={<ErrorOutlineIcon />}
            sx={{
              mt: 2.5,
              backgroundColor: 'rgba(239, 68, 68, 0.12)',
              color: '#fca5a5',
              border: '1px solid rgba(239, 68, 68, 0.25)',
              borderRadius: '10px',
            }}
          >
            {error}
          </Alert>
        )}

        {/* PRIMARY "EXTRACT DATA" BUTTON */}
        <Box sx={{ mt: 3, display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
          <Button
            variant="contained"
            size="large"
            id="extract-data-btn"
            disabled={isLoading || workflowState === 'UPLOADING' || workflowState === 'VALIDATING' || workflowState === 'PROCESSING'}
            onClick={handleExtractData}
            startIcon={
              workflowState === 'UPLOADING' || workflowState === 'VALIDATING' ? (
                <CircularProgress size={22} color="inherit" />
              ) : (
                <FileDownloadIcon />
              )
            }
            sx={{
              background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
              color: '#fff',
              fontWeight: 700,
              fontSize: '1.05rem',
              padding: '0.85rem 2.2rem',
              borderRadius: '12px',
              textTransform: 'none',
              boxShadow: '0 8px 24px rgba(99, 102, 241, 0.45)',
              '&:hover': {
                background: 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
                boxShadow: '0 12px 30px rgba(99, 102, 241, 0.65)',
              },
            }}
          >
            {workflowState === 'UPLOADING' ? 'Uploading...' : workflowState === 'VALIDATING' ? 'Validating Schema...' : 'Extract & Validate CSV'}
          </Button>

          {csvData.length > 0 && (
            <Button
              variant="outlined"
              onClick={() => {
                clearData();
                setVahanBatch(null);
                setWorkflowState('IDLE');
                setPortalInventory(null);
                setFieldMapping(null);
                setDryRunResult(null);
              }}
              sx={{
                color: '#ef4444',
                borderColor: 'rgba(239, 68, 68, 0.35)',
                textTransform: 'none',
                borderRadius: '10px',
                '&:hover': {
                  borderColor: '#ef4444',
                  backgroundColor: 'rgba(239, 68, 68, 0.1)',
                },
              }}
            >
              Clear Current Data
            </Button>
          )}
        </Box>
      </div>

      {/* STEP 2: EXTRACTED DATA INSPECTOR (Directly below upload for immediate review) */}
      {csvData.length > 0 && (
        <div id="csv-data-inspector" className="glass-panel" style={{ padding: '1.75rem', marginBottom: '2rem' }}>
          {/* Metadata Header & Execution Actions */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 2, mb: 2 }}>
            <div>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5, flexWrap: 'wrap' }}>
                <Typography variant="h6" sx={{ fontWeight: 800, color: '#fff' }}>
                  Extracted Records: {fileName}
                </Typography>
                <Chip
                  label={`${metadata?.rowCount.toLocaleString()} Rows`}
                  size="small"
                  sx={{ backgroundColor: 'rgba(16, 185, 129, 0.2)', color: '#34d399', fontWeight: 700 }}
                />
                <Chip
                  label={`${columns.length} Columns`}
                  size="small"
                  sx={{ backgroundColor: 'rgba(99, 102, 241, 0.2)', color: '#a5b4fc', fontWeight: 700 }}
                />
              </Box>
              <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                Parsed in {metadata?.parseTimeMs}ms • Delimiter: "{metadata?.delimiter || ','}" • Source: {sourceType}
              </Typography>
            </div>

            {/* Actions */}
            <Box sx={{ display: 'flex', gap: 1.25, flexWrap: 'wrap', alignItems: 'center' }}>
              {vahanBatch && (
                <Button
                  variant="contained"
                  size="small"
                  onClick={() => {
                    const el = document.getElementById('vahan-controller');
                    if (el) el.scrollIntoView({ behavior: 'smooth' });
                  }}
                  sx={{
                    background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
                    color: '#fff',
                    textTransform: 'none',
                    fontWeight: 700,
                    borderRadius: '8px'
                  }}
                >
                  Go to VAHAN Actions ↓
                </Button>
              )}

              <Button
                variant="outlined"
                size="small"
                startIcon={<ContentCopyIcon />}
                onClick={handleCopyJson}
                sx={{
                  color: '#cbd5e1',
                  borderColor: 'rgba(255, 255, 255, 0.2)',
                  textTransform: 'none',
                  borderRadius: '8px',
                  '&:hover': { borderColor: '#fff' },
                }}
              >
                Copy JSON
              </Button>

              <Button
                variant="outlined"
                size="small"
                startIcon={<DownloadIcon />}
                onClick={handleExportCsv}
                sx={{
                  color: '#cbd5e1',
                  borderColor: 'rgba(255, 255, 255, 0.2)',
                  textTransform: 'none',
                  borderRadius: '8px',
                  '&:hover': { borderColor: '#fff' },
                }}
              >
                Export CSV
              </Button>
            </Box>
          </Box>

          {/* Search / Filter Bar */}
          <Box sx={{ mb: 2 }}>
            <TextField
              size="small"
              placeholder={`Search across ${csvData.length} records...`}
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setPage(0);
              }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon sx={{ color: '#94a3b8' }} />
                  </InputAdornment>
                ),
                endAdornment: searchQuery && (
                  <InputAdornment position="end">
                    <IconButton size="small" onClick={() => setSearchQuery('')} sx={{ color: '#94a3b8' }}>
                      <ClearIcon fontSize="small" />
                    </IconButton>
                  </InputAdornment>
                ),
              }}
              sx={{
                width: { xs: '100%', sm: 360 },
                '& .MuiOutlinedInput-root': {
                  color: '#fff',
                  backgroundColor: 'rgba(15, 23, 42, 0.5)',
                  borderRadius: '8px',
                  '& fieldset': { borderColor: 'rgba(255, 255, 255, 0.12)' },
                  '&:hover fieldset': { borderColor: '#818cf8' },
                },
              }}
            />
          </Box>

          {/* Row Selection Control Bar */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1.5, flexWrap: 'wrap' }}>
            <Typography variant="body2" sx={{ color: '#94a3b8', fontWeight: 600 }}>
              Record Selection:
            </Typography>
            <Chip
              label={`${selectedRows.size} of ${filteredData.length} records selected`}
              size="small"
              sx={{
                backgroundColor: selectedRows.size > 0 ? 'rgba(99, 102, 241, 0.25)' : 'rgba(255, 255, 255, 0.05)',
                color: selectedRows.size > 0 ? '#a5b4fc' : '#94a3b8',
                fontWeight: 700,
                border: selectedRows.size > 0 ? '1px solid rgba(99, 102, 241, 0.4)' : '1px solid rgba(255, 255, 255, 0.1)'
              }}
            />
            <Button
              size="small"
              variant="text"
              onClick={() => {
                const allRowNums = filteredData.map((_, i) => i + 2);
                selectAllRows(allRowNums);
              }}
              sx={{ textTransform: 'none', color: '#818cf8', fontWeight: 600, fontSize: '0.82rem' }}
            >
              Select All ({filteredData.length})
            </Button>
            {selectedRows.size > 0 && (
              <Button
                size="small"
                variant="text"
                onClick={clearRowSelection}
                sx={{ textTransform: 'none', color: '#f87171', fontWeight: 600, fontSize: '0.82rem' }}
              >
                Clear Selection
              </Button>
            )}
          </Box>

          {/* Data Table */}
          <div className="data-table-wrapper" style={{ maxHeight: '360px', overflowY: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: 44, textAlign: 'center' }}>
                    <Tooltip title="Select all on this page">
                      <Checkbox
                        size="small"
                        indeterminate={paginatedData.some((_, idx) => selectedRows.has(page * rowsPerPage + idx + 2)) && !paginatedData.every((_, idx) => selectedRows.has(page * rowsPerPage + idx + 2))}
                        checked={paginatedData.length > 0 && paginatedData.every((_, idx) => selectedRows.has(page * rowsPerPage + idx + 2))}
                        onChange={(e) => {
                          const pageRows = paginatedData.map((_, idx) => page * rowsPerPage + idx + 2);
                          if (e.target.checked) {
                            selectAllRows([...selectedRowNumbers, ...pageRows]);
                          } else {
                            selectAllRows(selectedRowNumbers.filter((r) => !pageRows.includes(r)));
                          }
                        }}
                        sx={{ color: '#818cf8', '&.Mui-checked': { color: '#6366f1' }, p: 0 }}
                      />
                    </Tooltip>
                  </th>
                  <th style={{ width: 50 }}>#</th>
                  {columns.map((col) => (
                    <th key={col}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span>{col}</span>
                        {metadata?.columnTypes?.[col] && (
                          <span
                            className={`tag-pill ${metadata.columnTypes[col] === 'number' ? 'tag-number' : 'tag-string'
                              }`}
                          >
                            {metadata.columnTypes[col] === 'number' ? 'NUM' : 'TXT'}
                          </span>
                        )}
                      </div>
                    </th>
                  ))}
                  <th style={{ textAlign: 'center', width: 70 }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {paginatedData.length > 0 ? (
                  paginatedData.map((row, idx) => {
                    const rowNumber = page * rowsPerPage + idx + 1;
                    const csvRowNumber = rowNumber + 1;
                    const isSelected = selectedRows.has(csvRowNumber);
                    return (
                      <tr key={idx} style={{ backgroundColor: isSelected ? 'rgba(99, 102, 241, 0.08)' : 'transparent' }}>
                        <td style={{ textAlign: 'center' }}>
                          <Checkbox
                            size="small"
                            checked={isSelected}
                            onChange={() => toggleRowSelection(csvRowNumber)}
                            sx={{ color: '#64748b', '&.Mui-checked': { color: '#818cf8' }, p: 0 }}
                          />
                        </td>
                        <td style={{ color: '#64748b', fontWeight: 600 }}>{rowNumber}</td>
                        {columns.map((col) => (
                          <td key={col}>
                            {row[col] !== null && row[col] !== undefined ? String(row[col]) : (
                              <span style={{ color: '#64748b', fontStyle: 'italic' }}>null</span>
                            )}
                          </td>
                        ))}
                        <td style={{ textAlign: 'center' }}>
                          <Tooltip title="Inspect Row Object">
                            <IconButton
                              size="small"
                              onClick={() => setSelectedRowDetail(row)}
                              sx={{ color: '#818cf8' }}
                            >
                              <VisibilityIcon fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan={columns.length + 2} style={{ textAlign: 'center', padding: '2rem', color: '#94a3b8' }}>
                      No matching records found for "{searchQuery}".
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Table Pagination */}
          <TablePagination
            component="div"
            count={filteredData.length}
            page={page}
            onPageChange={(_, newPage) => setPage(newPage)}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={(e) => {
              setRowsPerPage(parseInt(e.target.value, 10));
              setPage(0);
            }}
            rowsPerPageOptions={[5, 10, 25, 50]}
            sx={{
              color: '#94a3b8',
              borderTop: '1px solid rgba(255, 255, 255, 0.08)',
              mt: 1,
              '& .MuiTablePagination-selectIcon': { color: '#94a3b8' },
            }}
          />
        </div>
      )}

      {/* STEP 3: VAHAN AUTOMATION WORKFLOW CONTROLLER PANEL (Directly follows data inspector) */}
      {vahanBatch && (
        <div id="vahan-controller" className="glass-panel" style={{ padding: '2rem', marginBottom: '2.5rem', border: `1px solid ${getStateColor(workflowState)}` }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 2, mb: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
              <FactCheckIcon sx={{ color: getStateColor(workflowState), fontSize: 32 }} />
              <div>
                <Typography variant="h6" sx={{ fontWeight: 800, color: '#fff' }}>
                  VAHAN Automation Workflow Controller
                </Typography>
                <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                  Batch ID: <code>{vahanBatch.batch_id}</code> • File: {vahanBatch.file_name}
                </Typography>
              </div>
            </Box>

            {/* Current State Indicator */}
            <Chip
              label={`STATE: ${workflowState}`}
              sx={{
                backgroundColor: `${getStateColor(workflowState)}25`,
                color: getStateColor(workflowState),
                fontWeight: 800,
                fontSize: '0.88rem',
                border: `1px solid ${getStateColor(workflowState)}60`,
                padding: '0.35rem 0.6rem',
              }}
            />
          </Box>

          {/* Real-Time Processing Metrics Banner */}
          <div className="stats-banner glass-panel" style={{ margin: '1.25rem 0' }}>
            <div className="stat-item">
              <span className="stat-number">{vahanBatch.summary.total_records}</span>
              <span className="stat-label">Total Records</span>
            </div>
            <div className="stat-item">
              <span className="stat-number" style={{ color: '#10b981' }}>{vahanBatch.summary.successful_count}</span>
              <span className="stat-label">Successful</span>
            </div>
            <div className="stat-item">
              <span className="stat-number" style={{ color: vahanBatch.summary.failed_count > 0 ? '#ef4444' : '#94a3b8' }}>
                {vahanBatch.summary.failed_count}
              </span>
              <span className="stat-label">Failed</span>
            </div>
            <div className="stat-item">
              <span className="stat-number" style={{ color: vahanBatch.summary.skipped_count > 0 ? '#cbd5e1' : '#94a3b8' }}>
                {vahanBatch.summary.skipped_count || 0}
              </span>
              <span className="stat-label">Skipped</span>
            </div>
            <div className="stat-item">
              <span className="stat-number" style={{ color: vahanBatch.summary.unresolved_count > 0 ? '#f59e0b' : '#94a3b8' }}>
                {vahanBatch.summary.unresolved_count}
              </span>
              <span className="stat-label">Unresolved</span>
            </div>
            <div className="stat-item">
              <span className="stat-number" style={{ color: '#38bdf8' }}>{vahanBatch.summary.current_stage}</span>
              <span className="stat-label">Active Stage</span>
            </div>
          </div>

          {/* Active processing live status bar */}
          {workflowState === 'PROCESSING' && (
            <Box sx={{ mb: 2.5 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5, fontSize: '0.85rem' }}>
                <span style={{ color: '#cbd5e1' }}>
                  Processing Record #{vahanBatch.summary.current_record_index || 1} of {vahanBatch.summary.valid_records_count} (Source ID: {vahanBatch.summary.current_source_id || 'N/A'})
                </span>
                <span style={{ color: '#38bdf8', fontWeight: 700 }}>
                  {Math.round(((vahanBatch.summary.successful_count + vahanBatch.summary.failed_count) / (vahanBatch.summary.valid_records_count || 1)) * 100)}%
                </span>
              </Box>
              <LinearProgress
                variant="determinate"
                value={Math.round(((vahanBatch.summary.successful_count + vahanBatch.summary.failed_count) / (vahanBatch.summary.valid_records_count || 1)) * 100)}
                sx={{
                  height: 10,
                  borderRadius: 5,
                  backgroundColor: 'rgba(255, 255, 255, 0.08)',
                  '& .MuiLinearProgress-bar': {
                    background: 'linear-gradient(90deg, #6366f1 0%, #06b6d4 100%)',
                  },
                }}
              />
            </Box>
          )}

          {/* PAUSED_AUTH_REQUIRED Session Alert & Resume Handler */}
          {workflowState === 'PAUSED_AUTH_REQUIRED' && (
            <Alert
              severity="warning"
              action={
                <Button
                  variant="contained"
                  size="small"
                  disabled={isResuming}
                  onClick={handleResumeBatch}
                  sx={{
                    background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
                    color: '#fff',
                    fontWeight: 700,
                    textTransform: 'none',
                    borderRadius: '8px',
                    boxShadow: '0 4px 12px rgba(16, 185, 129, 0.4)'
                  }}
                >
                  {isResuming ? 'Resuming...' : 'Resume Batch'}
                </Button>
              }
              sx={{
                mb: 2.5,
                backgroundColor: 'rgba(245, 158, 11, 0.15)',
                color: '#fef3c7',
                border: '1px solid rgba(245, 158, 11, 0.4)',
                borderRadius: '12px',
                fontSize: '0.95rem',
                fontWeight: 600,
                alignItems: 'center'
              }}
            >
              <strong>Session Expired / Authentication Required:</strong> Portal session timed out or redirected to login during CSV row {vahanBatch.summary.current_record_index}. Please enter your credentials and CAPTCHA in Chrome and click <strong>Resume Batch</strong>.
            </Alert>
          )}

          {/* Last Confirmed Successful Record Banner */}
          {vahanBatch.summary.last_confirmed_record && (
            <Alert severity="success" sx={{ mb: 2, backgroundColor: 'rgba(16, 185, 129, 0.1)', color: '#6ee7b7' }}>
              <strong>Last Confirmed Record:</strong> {vahanBatch.summary.last_confirmed_record}
            </Alert>
          )}

          {/* Current Error Notice / Stop Reason */}
          {vahanBatch.summary.current_error_message && (
            <Alert severity="error" sx={{ mb: 2, backgroundColor: 'rgba(239, 68, 68, 0.12)', color: '#fca5a5' }}>
              <strong>Halt Diagnostic:</strong> {vahanBatch.summary.current_error_message}
            </Alert>
          )}

          {/* Validation Alert / Review Toggle */}
          {vahanBatch.summary.invalid_records_count > 0 ? (
            <Alert
              severity="warning"
              action={
                <Button color="inherit" size="small" onClick={() => setShowErrorReview(!showErrorReview)}>
                  {showErrorReview ? 'Hide Error Details' : 'Review Errors'}
                </Button>
              }
              sx={{ mb: 2, backgroundColor: 'rgba(245, 158, 11, 0.1)', color: '#fde68a' }}
            >
              Found {vahanBatch.summary.invalid_records_count} rows with schema validation issues (e.g. invalid IMEI or missing identifiers).
            </Alert>
          ) : (
            <Alert severity="success" sx={{ mb: 2, backgroundColor: 'rgba(16, 185, 129, 0.1)', color: '#6ee7b7' }}>
              All {vahanBatch.summary.valid_records_count} records passed schema constraints and are ready for portal entry.
            </Alert>
          )}

          {/* Collapsible Error Breakdown */}
          <Collapse in={showErrorReview}>
            <div className="glass-panel" style={{ padding: '1rem', marginBottom: '1.5rem', background: 'rgba(0, 0, 0, 0.25)' }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#f87171', mb: 1 }}>
                Validation Error Inventory ({vahanBatch.errors.length} issues detected):
              </Typography>
              <div style={{ maxHeight: 200, overflowY: 'auto' }}>
                {vahanBatch.errors.map((err, idx) => (
                  <div key={idx} style={{ padding: '0.4rem 0.75rem', borderBottom: '1px solid rgba(255, 255, 255, 0.05)', fontSize: '0.85rem' }}>
                    <span style={{ color: '#f87171', fontWeight: 700 }}>Row {err.row_number} (ID: {err.source_id || 'N/A'}): </span>
                    <span style={{ color: '#cbd5e1' }}>[{err.column}] {err.error_message}</span>
                  </div>
                ))}
              </div>
            </div>
          </Collapse>

          {/* Sequential Action Pipeline: Simplified Primary Controls & On Demand Services */}
          <Box id="vahan-actions-bar" sx={{ mt: 2, display: 'flex', gap: 1.5, flexWrap: 'wrap', alignItems: 'center' }}>
            {/* 1. Launch Portal */}
            <Button
              variant="contained"
              startIcon={isPortalActionLoading ? <CircularProgress size={18} color="inherit" /> : <OpenInBrowserIcon />}
              disabled={isPortalActionLoading || workflowState === 'PROCESSING'}
              onClick={handleLaunchPortal}
              sx={{
                background: 'linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%)',
                color: '#fff',
                fontWeight: 700,
                textTransform: 'none',
                borderRadius: '10px',
                px: 2.5,
                py: 1,
              }}
            >
              Launch Portal
            </Button>

            {/* 2. Confirm session Login */}
            <Button
              variant="contained"
              startIcon={isPortalActionLoading ? <CircularProgress size={18} color="inherit" /> : <FactCheckIcon />}
              disabled={isPortalActionLoading || workflowState === 'PROCESSING'}
              onClick={handleConfirmLoginAndInspect}
              sx={{
                background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
                color: '#fff',
                fontWeight: 700,
                textTransform: 'none',
                borderRadius: '10px',
                px: 2.5,
                py: 1,
              }}
            >
              Confirm session Login
            </Button>

            {/* 3. Batch Submit */}
            <Button
              variant="contained"
              startIcon={workflowState === 'PROCESSING' ? <CircularProgress size={18} color="inherit" /> : <PlayArrowIcon />}
              disabled={workflowState === 'PROCESSING' || !portalInventory?.is_authenticated}
              onClick={() => handleStartBatchProcessing(false)}
              sx={{
                background: 'linear-gradient(135deg, #8b5cf6 0%, #6366f1 100%)',
                color: '#fff',
                fontWeight: 800,
                textTransform: 'none',
                borderRadius: '10px',
                px: 2.5,
                py: 1,
                boxShadow: '0 4px 14px rgba(99, 102, 241, 0.4)',
              }}
            >
              {workflowState === 'PROCESSING' ? 'Processing Batch...' : 'Batch Submit'}
            </Button>

            {/* 4. On demand services Dropdown */}
            <Button
              variant="outlined"
              onClick={handleOpenOnDemand}
              sx={{
                color: '#e2e8f0',
                borderColor: 'rgba(255, 255, 255, 0.25)',
                background: 'rgba(30, 41, 59, 0.7)',
                fontWeight: 700,
                textTransform: 'none',
                borderRadius: '10px',
                px: 2.2,
                py: 1,
                '&:hover': {
                  borderColor: '#818cf8',
                  background: 'rgba(99, 102, 241, 0.15)',
                },
              }}
            >
              <MoreVertIcon/>
            </Button>

            <Menu
              anchorEl={onDemandAnchorEl}
              open={Boolean(onDemandAnchorEl)}
              onClose={handleCloseOnDemand}
              PaperProps={{
                sx: {
                  background: '#0f172a',
                  border: '1px solid rgba(255, 255, 255, 0.15)',
                  boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.6)',
                  borderRadius: '12px',
                  minWidth: 200,
                  color: '#e2e8f0',
                  mt: 0.5,
                  '& .MuiMenuItem-root': {
                    fontSize: '0.9rem',
                    fontWeight: 600,
                    py: 1,
                    px: 2,
                    '&:hover': {
                      backgroundColor: 'rgba(99, 102, 241, 0.15)',
                      color: '#a5b4fc',
                    },
                  },
                },
              }}
            >
              <MenuItem
                disabled={isDryRunning || !portalInventory?.is_authenticated || workflowState === 'PROCESSING'}
                onClick={() => {
                  handleCloseOnDemand();
                  handleExecuteDryRun();
                }}
              >
                Analyze(no submit)
              </MenuItem>
              <MenuItem
                disabled={workflowState === 'PROCESSING' || !portalInventory?.is_authenticated}
                onClick={() => {
                  handleCloseOnDemand();
                  handleStartSingleRecord();
                }}
              >
                test a record
              </MenuItem>
              {selectedRows.size > 0 && (
                <MenuItem
                  disabled={workflowState === 'PROCESSING' || !portalInventory?.is_authenticated}
                  onClick={() => {
                    handleCloseOnDemand();
                    handleStartBatchProcessing(true);
                  }}
                  sx={{ color: '#38bdf8 !important' }}
                >
                  Submit Selected ({selectedRows.size})
                </MenuItem>
              )}
              <Divider sx={{ borderColor: 'rgba(255, 255, 255, 0.1)', my: 0.5 }} />
              <MenuItem
                onClick={() => {
                  handleCloseOnDemand();
                  handleOpenMappingConfig();
                }}
              >
                Field Mapping
              </MenuItem>
              <MenuItem
                onClick={() => {
                  handleCloseOnDemand();
                  setShowExecutionReport((prev) => !prev);
                }}
              >
                {showExecutionReport ? 'Hide Execution Report' : 'Execution Report'}
              </MenuItem>
              <MenuItem
                onClick={() => {
                  handleCloseOnDemand();
                  handleOpenLogsModal();
                }}
              >
                Audit Logs ({executionLogs.length || vahanBatch.logs?.length || 0})
              </MenuItem>
            </Menu>

            {/* Controlled Stop Processing (Visible only when actively processing or waiting) */}
            {(workflowState === 'PROCESSING' || workflowState === 'WAITING_FOR_AUTHENTICATION' || isStopping) && (
              <Button
                variant="outlined"
                startIcon={isStopping ? <CircularProgress size={16} color="inherit" /> : <StopCircleIcon />}
                disabled={isStopping}
                onClick={handleStopProcessing}
                sx={{
                  color: '#ef4444',
                  borderColor: 'rgba(239, 68, 68, 0.5)',
                  background: 'rgba(239, 68, 68, 0.1)',
                  fontWeight: 700,
                  textTransform: 'none',
                  borderRadius: '10px',
                  px: 2,
                  py: 1,
                  '&:hover': { borderColor: '#ef4444', backgroundColor: 'rgba(239, 68, 68, 0.2)' },
                }}
              >
                {isStopping ? 'Stopping...' : 'Stop Processing'}
              </Button>
            )}
          </Box>

          {/* Phase C: Explicit Field Mapping Configuration Panel */}
          {showMappingConfig && fieldMapping && (
            <div id="vahan-section-mapping" style={{ marginTop: '1.75rem', padding: '1.5rem', background: 'rgba(15, 23, 42, 0.75)', borderRadius: '14px', border: '1px solid rgba(139, 92, 246, 0.3)' }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 1 }}>
                <div>
                  <Typography variant="h6" sx={{ fontWeight: 800, color: '#c084fc' }}>
                    Phase C — CSV to Portal Field Mapping Configuration
                  </Typography>
                  <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                    Map CSV data columns to official VAHAN portal elements. Select discovered fields or enter custom element IDs.
                  </Typography>
                </div>
                <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
                  <Button
                    variant="text"
                    size="small"
                    startIcon={<ArrowUpwardIcon />}
                    onClick={() => {
                      const el = document.getElementById('vahan-actions-bar');
                      if (el) el.scrollIntoView({ behavior: 'smooth' });
                    }}
                    sx={{ color: '#a5b4fc', textTransform: 'none', fontWeight: 600 }}
                  >
                    Back to Actions ↑
                  </Button>
                  <Button
                    variant="outlined"
                    size="small"
                    startIcon={<AutoAwesomeIcon />}
                    onClick={handleApplyVahanDefaults}
                    sx={{
                      color: '#a78bfa',
                      borderColor: 'rgba(167, 139, 250, 0.4)',
                      textTransform: 'none',
                      fontWeight: 700,
                      '&:hover': { borderColor: '#a78bfa', backgroundColor: 'rgba(167, 139, 250, 0.1)' }
                    }}
                  >
                    Quick-Apply VAHAN Defaults
                  </Button>
                  <Chip
                    label={fieldMapping.is_complete ? 'Mapping Complete & Verified' : `Incomplete: Missing ${fieldMapping.missing_required_fields.join(', ')}`}
                    size="small"
                    sx={{
                      backgroundColor: fieldMapping.is_complete ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)',
                      color: fieldMapping.is_complete ? '#34d399' : '#f87171',
                      fontWeight: 700,
                    }}
                  />
                  <Button
                    variant="contained"
                    size="small"
                    startIcon={<SaveIcon />}
                    onClick={handleSaveMapping}
                    sx={{ background: '#8b5cf6', textTransform: 'none', fontWeight: 700 }}
                  >
                    Save Mapping
                  </Button>
                </Box>
              </Box>

              {!fieldMapping.is_complete && (
                <Alert severity="warning" sx={{ mb: 2, backgroundColor: 'rgba(245, 158, 11, 0.1)', color: '#fde68a' }}>
                  Missing required mapping: <strong>{fieldMapping.missing_required_fields.join(', ')}</strong>. Fill in the element IDs below or click <strong>Quick-Apply VAHAN Defaults</strong>.
                </Alert>
              )}

              <div className="data-table-wrapper">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th style={{ width: '18%' }}>CSV Column</th>
                      <th style={{ width: '28%' }}>Discovered Portal Element</th>
                      <th style={{ width: '28%' }}>Target Element ID / Selector</th>
                      <th style={{ width: '14%' }}>Tag</th>
                      <th style={{ width: '12%' }}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(fieldMapping.mappings).map(([col, mapItem]) => {
                      const isMapped = col === 'ID' || Boolean(mapItem.target_field_id?.trim() || mapItem.target_field_name?.trim());
                      return (
                        <tr key={col}>
                          <td style={{ color: '#fff', fontWeight: 700 }}>
                            {col}
                            {col === 'ID' && <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Row ID (Skipped)</div>}
                          </td>
                          <td>
                            {col === 'ID' ? (
                              <span style={{ color: '#64748b' }}>Internal Reference</span>
                            ) : portalInventory?.fields && portalInventory.fields.length > 0 ? (
                              <FormControl size="small" fullWidth>
                                <Select
                                  value={
                                    portalInventory.fields.some((f) => f.id === mapItem.target_field_id || f.name === mapItem.target_field_id)
                                      ? mapItem.target_field_id
                                      : ''
                                  }
                                  onChange={(e) => {
                                    const val = e.target.value;
                                    const selectedField = portalInventory.fields.find((f) => f.id === val || f.name === val);
                                    const updatedMappings = {
                                      ...fieldMapping.mappings,
                                      [col]: {
                                        ...mapItem,
                                        target_field_id: selectedField ? (selectedField.id || selectedField.name) : '',
                                        target_field_name: selectedField ? (selectedField.name || selectedField.id) : '',
                                        target_field_label: selectedField ? selectedField.label : mapItem.target_field_label,
                                        element_tag: selectedField ? selectedField.tag : mapItem.element_tag,
                                      },
                                    };
                                    const missing = Object.entries(updatedMappings)
                                      .filter(([c, it]) => c !== 'ID' && !it.target_field_id?.trim() && !it.target_field_name?.trim())
                                      .map(([c]) => c);
                                    setFieldMapping({
                                      ...fieldMapping,
                                      mappings: updatedMappings,
                                      missing_required_fields: missing,
                                      is_complete: missing.length === 0,
                                    });
                                  }}
                                  displayEmpty
                                  sx={{ color: '#fff', backgroundColor: 'rgba(255, 255, 255, 0.05)', fontSize: '0.85rem' }}
                                >
                                  <MenuItem value=""><em>-- Custom / Unselected --</em></MenuItem>
                                  {portalInventory.fields.map((f, i) => (
                                    <MenuItem key={i} value={f.id || f.name}>
                                      {f.label ? `${f.label} (${f.id || f.name})` : (f.id || f.name)} [{f.tag}]
                                    </MenuItem>
                                  ))}
                                </Select>
                              </FormControl>
                            ) : (
                              <span style={{ color: '#94a3b8', fontSize: '0.85rem' }}>
                                {mapItem.target_field_label || 'Default Preset'}
                              </span>
                            )}
                          </td>
                          <td>
                            {col === 'ID' ? (
                              <code>N/A</code>
                            ) : (
                              <TextField
                                size="small"
                                fullWidth
                                placeholder="e.g. tf_maker_name"
                                value={mapItem.target_field_id || ''}
                                onChange={(e) => {
                                  const newVal = e.target.value.trim();
                                  const updatedMappings = {
                                    ...fieldMapping.mappings,
                                    [col]: {
                                      ...mapItem,
                                      target_field_id: newVal,
                                      target_field_name: newVal,
                                    },
                                  };
                                  const missing = Object.entries(updatedMappings)
                                    .filter(([c, it]) => c !== 'ID' && !it.target_field_id?.trim() && !it.target_field_name?.trim())
                                    .map(([c]) => c);
                                  setFieldMapping({
                                    ...fieldMapping,
                                    mappings: updatedMappings,
                                    missing_required_fields: missing,
                                    is_complete: missing.length === 0,
                                  });
                                }}
                                sx={{
                                  '& .MuiInputBase-input': {
                                    color: '#fff',
                                    fontFamily: 'monospace',
                                    fontSize: '0.85rem',
                                    padding: '6px 10px',
                                  },
                                  backgroundColor: 'rgba(255, 255, 255, 0.04)',
                                  borderRadius: '6px',
                                }}
                              />
                            )}
                          </td>
                          <td>
                            {col === 'ID' ? (
                              <code>-</code>
                            ) : (
                              <FormControl size="small" fullWidth>
                                <Select
                                  value={mapItem.element_tag || 'input'}
                                  onChange={(e) => {
                                    const updatedMappings = {
                                      ...fieldMapping.mappings,
                                      [col]: {
                                        ...mapItem,
                                        element_tag: e.target.value,
                                      },
                                    };
                                    setFieldMapping({
                                      ...fieldMapping,
                                      mappings: updatedMappings,
                                    });
                                  }}
                                  sx={{ color: '#fff', backgroundColor: 'rgba(255, 255, 255, 0.05)', fontSize: '0.85rem' }}
                                >
                                  <MenuItem value="input">input</MenuItem>
                                  <MenuItem value="select">select</MenuItem>
                                </Select>
                              </FormControl>
                            )}
                          </td>
                          <td>
                            {col === 'ID' ? (
                              <span style={{ color: '#64748b', fontSize: '0.8rem' }}>Optional</span>
                            ) : isMapped ? (
                              <Chip label="READY" size="small" sx={{ backgroundColor: 'rgba(16, 185, 129, 0.2)', color: '#34d399', fontWeight: 700 }} />
                            ) : (
                              <Chip label="REQUIRED" size="small" sx={{ backgroundColor: 'rgba(239, 68, 68, 0.2)', color: '#f87171', fontWeight: 700 }} />
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Phase D: Dry-Run Verification Report */}
          {dryRunResult && (
            <div id="vahan-section-dryrun" style={{ marginTop: '1.75rem', padding: '1.5rem', background: 'rgba(15, 23, 42, 0.75)', borderRadius: '14px', border: `1px solid ${dryRunResult.success ? '#10b981' : '#f59e0b'}` }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5, flexWrap: 'wrap', gap: 1 }}>
                <div>
                  <Typography variant="h6" sx={{ fontWeight: 800, color: dryRunResult.success ? '#34d399' : '#fbbf24' }}>
                    Phase D — Dry-Run Autofill Verification Report
                  </Typography>
                  <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                    Record ID: <code>{dryRunResult.record_id}</code> (Row {dryRunResult.row_number}) • Executed at {dryRunResult.executed_at}
                  </Typography>
                </div>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Button
                    variant="text"
                    size="small"
                    startIcon={<ArrowUpwardIcon />}
                    onClick={() => {
                      const el = document.getElementById('vahan-actions-bar');
                      if (el) el.scrollIntoView({ behavior: 'smooth' });
                    }}
                    sx={{ color: '#fbbf24', textTransform: 'none', fontWeight: 600 }}
                  >
                    Back to Actions ↑
                  </Button>
                  <Chip
                    label={dryRunResult.success ? 'Dry-Run Matched: Form Ready' : 'Discrepancy Detected'}
                    size="small"
                    sx={{
                      backgroundColor: dryRunResult.success ? 'rgba(16, 185, 129, 0.2)' : 'rgba(245, 158, 11, 0.2)',
                      color: dryRunResult.success ? '#34d399' : '#fbbf24',
                      fontWeight: 700,
                    }}
                  />
                </Box>
              </Box>

              <Alert severity={dryRunResult.success ? 'success' : 'warning'} sx={{ mb: 2 }}>
                {dryRunResult.summary_message}
              </Alert>

              <div className="data-table-wrapper">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>CSV Column</th>
                      <th>Portal Field Name</th>
                      <th>Intended Value (CSV)</th>
                      <th>Actual Value (Read-back)</th>
                      <th>Verification Status</th>
                      <th>Diagnostics</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dryRunResult.verifications.map((v, i) => (
                      <tr key={i}>
                        <td style={{ color: '#fff', fontWeight: 600 }}>{v.csv_column}</td>
                        <td>{v.portal_field}</td>
                        <td><code>{v.expected_value}</code></td>
                        <td><code>{v.actual_value}</code></td>
                        <td>
                          {v.matched ? (
                            <span className="tag-pill tag-number" style={{ background: 'rgba(16, 185, 129, 0.2)', color: '#34d399' }}>
                              MATCHED
                            </span>
                          ) : (
                            <span className="tag-pill tag-string" style={{ background: 'rgba(239, 68, 68, 0.2)', color: '#f87171' }}>
                              {v.status}
                            </span>
                          )}
                        </td>
                        <td style={{ color: v.matched ? '#94a3b8' : '#fca5a5', fontSize: '0.82rem' }}>
                          {v.message}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Phase F: Record-Level Execution Audit Report */}
          <Collapse in={showExecutionReport}>
            <div style={{ marginTop: '1.75rem', padding: '1.5rem', background: 'rgba(15, 23, 42, 0.85)', borderRadius: '14px', border: '1px solid rgba(192, 132, 252, 0.3)' }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 1 }}>
                <div>
                  <Typography variant="h6" sx={{ fontWeight: 800, color: '#c084fc' }}>
                    Phase F — Record-Level Execution Audit Report
                  </Typography>
                  <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                    Audited results for each CSV record processed through official portal workflow.
                  </Typography>
                </div>
                <Button
                  variant="contained"
                  size="small"
                  startIcon={<DownloadIcon />}
                  onClick={handleDownloadReport}
                  sx={{ background: '#9333ea', textTransform: 'none', fontWeight: 700 }}
                >
                  Download Report (JSON)
                </Button>
              </Box>

              <div className="data-table-wrapper" style={{ maxHeight: 320, overflowY: 'auto' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Row #</th>
                      <th>Source ID</th>
                      <th>VLTD Maker / Serial</th>
                      <th>IMEI Number</th>
                      <th>Execution Status</th>
                      <th>Official Confirmation Ref</th>
                      <th>Timestamp / Message</th>
                    </tr>
                  </thead>
                  <tbody>
                    {vahanBatch.records.map((r, i) => (
                      <tr key={i}>
                        <td style={{ color: '#fff', fontWeight: 700 }}>{r.row_number}</td>
                        <td><code>{r.id}</code></td>
                        <td>{r.vltd_maker} ({r.vltd_serial_number})</td>
                        <td><code>{r.imei_number}</code></td>
                        <td>
                          <span
                            className="tag-pill"
                            style={{
                              background:
                                r.status === 'SUBMITTED'
                                  ? 'rgba(16, 185, 129, 0.2)'
                                  : r.status === 'FAILED'
                                    ? 'rgba(239, 68, 68, 0.2)'
                                    : r.status === 'UNKNOWN'
                                      ? 'rgba(245, 158, 11, 0.2)'
                                      : 'rgba(148, 163, 184, 0.15)',
                              color:
                                r.status === 'SUBMITTED'
                                  ? '#34d399'
                                  : r.status === 'FAILED'
                                    ? '#f87171'
                                    : r.status === 'UNKNOWN'
                                      ? '#fde68a'
                                      : '#94a3b8',
                              fontWeight: 700,
                            }}
                          >
                            {r.status}
                          </span>
                        </td>
                        <td><code>{r.portal_confirmation_ref || '-'}</code></td>
                        <td style={{ fontSize: '0.82rem', color: '#cbd5e1' }}>
                          {r.executed_at ? `${r.executed_at}: ` : ''}
                          {r.execution_message || '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </Collapse>

          {/* Phase B Discovered Inventory Display */}
          {portalInventory && (
            <div style={{ marginTop: '1.75rem', padding: '1.25rem', background: 'rgba(15, 23, 42, 0.5)', borderRadius: '12px', border: '1px solid rgba(255, 255, 255, 0.08)' }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5, flexWrap: 'wrap', gap: 1 }}>
                <div>
                  <Typography variant="subtitle1" sx={{ fontWeight: 800, color: '#38bdf8' }}>
                    Official Form Inventory: {portalInventory.page_title}
                  </Typography>
                  <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                    Target: {portalInventory.portal_url} • Discovered at {portalInventory.discovered_at}
                  </Typography>
                </div>
                <Chip
                  label={portalInventory.is_authenticated ? 'Authenticated SLD Form Active' : 'Waiting for Authentication'}
                  size="small"
                  sx={{
                    backgroundColor: portalInventory.is_authenticated ? 'rgba(16, 185, 129, 0.2)' : 'rgba(245, 158, 11, 0.2)',
                    color: portalInventory.is_authenticated ? '#34d399' : '#fde68a',
                    fontWeight: 700,
                  }}
                />
              </Box>

              <Typography variant="body2" sx={{ color: '#cbd5e1', mb: 1.5 }}>
                {portalInventory.message}
              </Typography>

              {portalInventory.fields.length > 0 && (
                <div>
                  <Button size="small" onClick={() => setShowInventoryReview(!showInventoryReview)} sx={{ color: '#818cf8', textTransform: 'none', mb: 1 }}>
                    {showInventoryReview ? 'Hide Field Inventory' : `View All ${portalInventory.fields.length} Discovered Form Elements`}
                  </Button>

                  <Collapse in={showInventoryReview}>
                    <div className="data-table-wrapper" style={{ maxHeight: 260, overflowY: 'auto' }}>
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Field Label / Placeholder</th>
                            <th>Element Tag</th>
                            <th>ID / Name Selector</th>
                            <th>Type</th>
                            <th>Required?</th>
                            <th>Options Count</th>
                          </tr>
                        </thead>
                        <tbody>
                          {portalInventory.fields.map((f, i) => (
                            <tr key={i}>
                              <td style={{ color: '#fff', fontWeight: 600 }}>{f.label || '<unlabeled>'}</td>
                              <td><code>{f.tag}</code></td>
                              <td><code>{f.id || f.name || '<dynamic>'}</code></td>
                              <td>{f.input_type}</td>
                              <td>
                                {f.is_required ? (
                                  <span className="tag-pill tag-number">REQUIRED</span>
                                ) : (
                                  <span style={{ color: '#64748b' }}>Optional</span>
                                )}
                              </td>
                              <td>{f.options.length > 0 ? `${f.options.length} options` : '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Collapse>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* POPUP ERROR DIALOG: Pops up when link does not redirect to a CSV */}
      <Dialog
        open={errorDialogOpen}
        onClose={() => setErrorDialogOpen(false)}
        PaperProps={{
          sx: {
            backgroundColor: '#111827',
            color: '#fff',
            borderRadius: '16px',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            boxShadow: '0 20px 40px rgba(0, 0, 0, 0.8)',
            p: 1,
            maxWidth: 520,
          },
        }}
      >
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1.5, color: '#f87171', fontWeight: 800 }}>
          <ErrorOutlineIcon fontSize="large" />
          CSV Extraction / Validation Alert
        </DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ color: '#cbd5e1', fontSize: '0.98rem', mb: 2 }}>
            {errorDialogMessage}
          </DialogContentText>
          <Alert severity="warning" sx={{ backgroundColor: 'rgba(245, 158, 11, 0.1)', color: '#fde68a' }}>
            <AlertTitle sx={{ fontWeight: 700 }}>VAHAN VLTD Specification</AlertTitle>
            Ensure your file is a direct CSV containing valid columns: ID, VLTD Maker, VLTD Model, VLTD serial Number, Provider, IMEI Number (15 digits), and Registration Type.
          </Alert>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button
            onClick={() => setErrorDialogOpen(false)}
            variant="contained"
            sx={{
              backgroundColor: '#ef4444',
              color: '#fff',
              fontWeight: 700,
              borderRadius: '8px',
              textTransform: 'none',
              '&:hover': { backgroundColor: '#dc2626' },
            }}
          >
            Understood & Close
          </Button>
        </DialogActions>
      </Dialog>



      {/* Row Detail Inspection Modal */}
      <Dialog
        open={Boolean(selectedRowDetail)}
        onClose={() => setSelectedRowDetail(null)}
        PaperProps={{
          sx: {
            backgroundColor: '#111827',
            color: '#fff',
            borderRadius: '16px',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            maxWidth: 600,
            width: '100%',
          },
        }}
      >
        <DialogTitle sx={{ fontWeight: 800, borderBottom: '1px solid rgba(255, 255, 255, 0.08)' }}>
          Record Inspector
        </DialogTitle>
        <DialogContent sx={{ mt: 2 }}>
          {selectedRowDetail && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '0.75rem' }}>
              {Object.entries(selectedRowDetail).map(([key, val]) => (
                <div
                  key={key}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '0.65rem 1rem',
                    borderRadius: '8px',
                    background: 'rgba(255, 255, 255, 0.03)',
                  }}
                >
                  <span style={{ color: '#94a3b8', fontWeight: 600 }}>{key}</span>
                  <span style={{ color: '#fff', fontWeight: 500 }}>
                    {val !== null && val !== undefined ? String(val) : '<null>'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button
            onClick={() => setSelectedRowDetail(null)}
            variant="outlined"
            sx={{ color: '#a5b4fc', borderColor: '#6366f1' }}
          >
            Close
          </Button>
        </DialogActions>
      </Dialog>

      {/* Structured Execution Audit Logs Modal */}
      <Dialog
        open={showLogsModal}
        onClose={() => setShowLogsModal(false)}
        maxWidth="lg"
        fullWidth
        PaperProps={{
          sx: {
            backgroundColor: '#0f172a',
            color: '#fff',
            borderRadius: '16px',
            border: '1px solid rgba(56, 189, 248, 0.3)',
            boxShadow: '0 20px 40px rgba(0, 0, 0, 0.9)',
            maxHeight: '85vh'
          },
        }}
      >
        <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 1, borderBottom: '1px solid rgba(255, 255, 255, 0.08)' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <ReceiptLongIcon sx={{ color: '#38bdf8', fontSize: 28 }} />
            <div>
              <Typography variant="h6" sx={{ fontWeight: 800, color: '#fff' }}>
                Execution Audit Trail & Transaction Logs
              </Typography>
              <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                Timestamped in Asia/Kolkata (IST +05:30) • Batch: <code>{vahanBatch?.batch_id?.slice(0, 8) || '-'}</code>
              </Typography>
            </div>
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {['ALL', 'INFO', 'WARNING', 'ERROR'].map((lvl) => (
              <Chip
                key={lvl}
                label={lvl}
                size="small"
                clickable
                onClick={async () => {
                  setLogFilterLevel(lvl);
                  if (vahanBatch) {
                    const logs = await vahanApi.getExecutionLogs(vahanBatch.batch_id, {
                      level: lvl !== 'ALL' ? lvl : undefined
                    });
                    setExecutionLogs(logs);
                  }
                }}
                sx={{
                  backgroundColor: logFilterLevel === lvl ? 'rgba(56, 189, 248, 0.3)' : 'rgba(255, 255, 255, 0.05)',
                  color: logFilterLevel === lvl ? '#38bdf8' : '#94a3b8',
                  fontWeight: 700,
                  border: logFilterLevel === lvl ? '1px solid #38bdf8' : '1px solid rgba(255, 255, 255, 0.1)'
                }}
              />
            ))}
            <Button
              size="small"
              variant="outlined"
              onClick={handleOpenLogsModal}
              sx={{ color: '#38bdf8', borderColor: 'rgba(56, 189, 248, 0.4)', textTransform: 'none', ml: 1 }}
            >
              Refresh
            </Button>
          </Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%', mt: 1.5 }}>
            <Button
              size="small"
              variant={!showUnifiedRootLog ? "contained" : "outlined"}
              onClick={() => setShowUnifiedRootLog(false)}
              sx={{ textTransform: 'none', fontWeight: 700, borderRadius: '8px' }}
            >
              Structured Audit Trail
            </Button>
            <Button
              size="small"
              variant={showUnifiedRootLog ? "contained" : "outlined"}
              onClick={async () => {
                setShowUnifiedRootLog(true);
                await handleRefreshUnifiedRootLog();
              }}
              sx={{ textTransform: 'none', fontWeight: 700, borderRadius: '8px', color: '#38bdf8', borderColor: '#38bdf8' }}
            >
              Unified Root Log File (vahan_automation.log)
            </Button>
          </Box>
        </DialogTitle>
        <DialogContent sx={{ p: 2 }}>
          {showUnifiedRootLog ? (
            <div style={{ maxHeight: '55vh', overflowY: 'auto', background: '#020617', padding: '1rem', borderRadius: '10px', border: '1px solid #1e293b' }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
                <Typography variant="caption" sx={{ color: '#94a3b8', fontFamily: 'monospace' }}>
                  Target File: <strong>{unifiedRootLogPath}</strong>
                </Typography>
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => {
                    navigator.clipboard.writeText(unifiedRootLogText);
                    setToastMessage('Copied root log file content to clipboard!');
                    setToastOpen(true);
                  }}
                  sx={{ color: '#38bdf8', borderColor: 'rgba(56, 189, 248, 0.4)', textTransform: 'none' }}
                >
                  Copy Log Content
                </Button>
              </Box>
              <pre style={{ margin: 0, fontFamily: 'Consolas, monospace', fontSize: '0.8rem', color: '#e2e8f0', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                {unifiedRootLogText}
              </pre>
            </div>
          ) : (
            <div className="data-table-wrapper" style={{ maxHeight: '55vh', overflowY: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th style={{ width: '18%' }}>Timestamp (IST)</th>
                    <th style={{ width: '8%' }}>Level</th>
                    <th style={{ width: '15%' }}>Execution Type</th>
                    <th style={{ width: '10%' }}>Row / Txn</th>
                    <th style={{ width: '16%' }}>Stage & Action</th>
                    <th style={{ width: '8%' }}>Status</th>
                    <th style={{ width: '25%' }}>Message</th>
                  </tr>
                </thead>
                <tbody>
                  {executionLogs.length > 0 ? (
                    executionLogs.map((log, idx) => (
                      <tr key={idx}>
                        <td style={{ fontSize: '0.78rem', color: '#cbd5e1', fontFamily: 'monospace' }}>
                          {log.timestamp}
                        </td>
                        <td>
                          <span
                            className="tag-pill"
                            style={{
                              background:
                                log.level === 'ERROR' || log.level === 'CRITICAL'
                                  ? 'rgba(239, 68, 68, 0.2)'
                                  : log.level === 'WARNING'
                                    ? 'rgba(245, 158, 11, 0.2)'
                                    : 'rgba(16, 185, 129, 0.2)',
                              color:
                                log.level === 'ERROR' || log.level === 'CRITICAL'
                                  ? '#f87171'
                                  : log.level === 'WARNING'
                                    ? '#fbbf24'
                                    : '#34d399',
                              fontWeight: 700,
                              fontSize: '0.72rem'
                            }}
                          >
                            {log.level}
                          </span>
                        </td>
                        <td style={{ fontSize: '0.8rem', color: '#93c5fd', fontWeight: 600 }}>
                          {log.execution_type}
                        </td>
                        <td style={{ fontSize: '0.78rem', color: '#94a3b8', fontFamily: 'monospace' }}>
                          {log.csv_row ? `Row ${log.csv_row}` : '-'}{log.transaction_id ? ` (${log.transaction_id.slice(-6)})` : ''}
                        </td>
                        <td style={{ fontSize: '0.8rem', color: '#e2e8f0' }}>
                          <div style={{ fontWeight: 600 }}>{log.stage}</div>
                          <div style={{ fontSize: '0.72rem', color: '#64748b' }}>{log.action}</div>
                        </td>
                        <td>
                          <span
                            style={{
                              fontWeight: 700,
                              fontSize: '0.75rem',
                              color: log.result === 'SUCCESS' ? '#34d399' : log.result === 'FAILED' ? '#f87171' : '#fde68a'
                            }}
                          >
                            {log.result}
                          </span>
                        </td>
                        <td style={{ fontSize: '0.82rem', color: '#cbd5e1' }}>
                          {log.message}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={7} style={{ textAlign: 'center', padding: '2rem', color: '#94a3b8' }}>
                        No audit log entries found for this filter.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </DialogContent>
        <DialogActions sx={{ p: 2, borderTop: '1px solid rgba(255, 255, 255, 0.08)' }}>
          <Button
            onClick={() => setShowLogsModal(false)}
            variant="contained"
            sx={{
              background: '#38bdf8',
              color: '#0f172a',
              fontWeight: 700,
              borderRadius: '8px',
              textTransform: 'none',
              '&:hover': { background: '#0284c7', color: '#fff' }
            }}
          >
            Close Logs
          </Button>
        </DialogActions>
      </Dialog>

      {/* Snackbar Notification */}
      <Snackbar
        open={toastOpen}
        autoHideDuration={4000}
        onClose={() => setToastOpen(false)}
        message={toastMessage}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      />
    </div>
  );
}
