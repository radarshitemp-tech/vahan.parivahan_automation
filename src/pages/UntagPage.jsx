// src/pages/ReplacePage.jsx
import React, { useState, useEffect } from 'react';
import {
  Typography,
  Box,
  Button,
  Grid,
  Chip,
  Card,
  RadioGroup,
  FormControlLabel,
  Radio,
  TextField,
  CircularProgress,
  Alert,
  Snackbar,
  LinearProgress,
  Tooltip,
  IconButton
} from '@mui/material';
import SyncAltIcon from '@mui/icons-material/SyncAlt';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import OpenInBrowserIcon from '@mui/icons-material/OpenInBrowser';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import RefreshIcon from '@mui/icons-material/Refresh';
import Papa from 'papaparse';

import ModuleHeader from '../components/common/ModuleHeader';
import BrowserSessionCard from '../components/common/BrowserSessionCard';
import { replaceApi } from '../services/untagApi';

const REASON_OPTIONS = [
  {
    id: 'S',
    value: 'S',
    title: 'REPLACE DEVICE - WITH SAME MARKER',
    label: 'Replace device - with same maker',
    description: 'Replace existing unit with a new VLTD device from the same manufacturer.',
  },
  {
    id: 'D',
    value: 'D',
    title: 'REPLACE DEVICE - WITH DIFFERENT MARKER',
    label: 'Replace device - with different maker',
    description: 'Replace existing unit with a VLTD device from a different manufacturer.',
  },
  {
    id: 'I',
    value: 'I',
    title: 'CHANGE ICCID',
    label: 'Change ICCID',
    description: 'Update the integrated subscriber SIM ICCID for an existing registered device.',
  },
];

export default function ReplacePage() {
  const [selectedOption, setSelectedOption] = useState('S');
  const [isApplyingOption, setIsApplyingOption] = useState(false);
  const [revealedFields, setRevealedFields] = useState([]);
  const [statusMessage, setStatusMessage] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [isNavigating, setIsNavigating] = useState(false);

  // Single record inputs
  const [singleData, setSingleData] = useState({
    maker: '',
    model: '',
    serial_no: '',
    imei: '',
    iccid: '',
    reg_type: 'Old Vehicle',
  });
  const [isSubmittingSingle, setIsSubmittingSingle] = useState(false);

  // CSV Batch mode
  const [csvRecords, setCsvRecords] = useState([]);
  const [csvFileName, setCsvFileName] = useState('');
  const [isBatchRunning, setIsBatchRunning] = useState(false);
  const [batchProgress, setBatchProgress] = useState({ total: 0, current: 0, success: 0, fail: 0 });

  // Toast
  const [toast, setToast] = useState({ open: false, message: '', severity: 'info' });

  // Explicitly navigate to the replacement portal URL
  const handleNavigatePortal = async () => {
    setIsNavigating(true);
    setErrorMessage(null);
    try {
      const res = await replaceApi.navigateToPortal();
      setStatusMessage(res.message || 'Navigated to SLD Fitting / Replacement page.');
      setToast({ open: true, message: 'Browser redirected to sldfittingDetails.xhtml', severity: 'success' });
    } catch (e) {
      setErrorMessage(`Navigation error: ${e.message}`);
      setToast({ open: true, message: e.message, severity: 'error' });
    } finally {
      setIsNavigating(false);
    }
  };

  // Step 1: Apply Option to Portal (select_optn)
  const handleApplyOption = async () => {
    setIsApplyingOption(true);
    setErrorMessage(null);
    setStatusMessage(null);
    try {
      const res = await replaceApi.selectOption(selectedOption);
      if (res.success) {
        setRevealedFields(res.revealed_fields || []);
        const msg = res.message || `Option applied to select_optn. Revealed ${res.revealed_fields?.length || 0} fields.`;
        setStatusMessage(msg);
        setToast({ open: true, message: msg, severity: 'success' });
      } else {
        setErrorMessage(res.message || 'Failed to apply option to portal.');
        setToast({ open: true, message: res.message || 'Selection failed', severity: 'error' });
      }
    } catch (e) {
      setErrorMessage(`Option selection error: ${e.message}`);
      setToast({ open: true, message: e.message, severity: 'error' });
    } finally {
      setIsApplyingOption(false);
    }
  };

  // Single Record Submit
  const handleExecuteSingle = async () => {
    setIsSubmittingSingle(true);
    setErrorMessage(null);
    try {
      const res = await replaceApi.executeSingle({
        option_key: selectedOption,
        ...singleData,
      });
      if (res.status === 'SUCCESS') {
        const msg = res.message || 'Fitment record processed successfully.';
        setStatusMessage(msg);
        setToast({ open: true, message: msg, severity: 'success' });
      } else {
        setErrorMessage(res.message || 'Fitment execution failed.');
        setToast({ open: true, message: res.message || 'Execution failed', severity: 'error' });
      }
    } catch (e) {
      setErrorMessage(`Execution error: ${e.message}`);
      setToast({ open: true, message: e.message, severity: 'error' });
    } finally {
      setIsSubmittingSingle(false);
    }
  };

  // CSV file parser
  const handleFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setCsvFileName(file.name);
    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        const rows = results.data || [];
        setCsvRecords(rows);
        setBatchProgress({ total: rows.length, current: 0, success: 0, fail: 0 });
        const msg = `Loaded ${rows.length} record(s) from ${file.name}.`;
        setStatusMessage(msg);
        setToast({ open: true, message: msg, severity: 'success' });
      },
      error: (err) => {
        setErrorMessage(`Failed to parse CSV: ${err.message}`);
        setToast({ open: true, message: err.message, severity: 'error' });
      },
    });
  };

  // Execute Batch
  const handleExecuteBatch = async () => {
    if (csvRecords.length === 0) return;
    setIsBatchRunning(true);
    setErrorMessage(null);

    try {
      const res = await replaceApi.executeBatch(selectedOption, csvRecords);
      setBatchProgress({
        total: res.total_count,
        current: res.total_count,
        success: res.successful_count,
        fail: res.failed_count,
      });
      const msg = `Batch finished: ${res.successful_count} succeeded, ${res.failed_count} failed.`;
      setStatusMessage(msg);
      setToast({ open: true, message: msg, severity: res.failed_count === 0 ? 'success' : 'warning' });
    } catch (e) {
      setErrorMessage(`Batch execution error: ${e.message}`);
      setToast({ open: true, message: e.message, severity: 'error' });
    } finally {
      setIsBatchRunning(false);
    }
  };

  return (
    <div className="fade-in">
      {/* Central Module Header */}
      <ModuleHeader
        currentModuleId="replace_vltd"
        title="Untag / Replace VLTD Module"
        badge="Replace / Change"
        description="Select reason in select_optn (Same Maker, Different Maker, or Change ICCID), inspect revealed fitment fields, and execute transactions."
        color="#10b981"
      />

      {/* Shared Browser Session Card */}
      <BrowserSessionCard compact />

      {/* Feedback Alerts */}
      {errorMessage && (
        <Alert severity="error" sx={{ mb: 2.5, backgroundColor: 'rgba(239, 68, 68, 0.15)', color: '#fca5a5' }} onClose={() => setErrorMessage(null)}>
          {errorMessage}
        </Alert>
      )}

      {statusMessage && (
        <Alert severity="success" sx={{ mb: 2.5, backgroundColor: 'rgba(16, 185, 129, 0.15)', color: '#6ee7b7' }} onClose={() => setStatusMessage(null)}>
          {statusMessage}
        </Alert>
      )}

      <Grid container spacing={3} sx={{ mb: 3 }}>
        {/* Step 1: Select Untag VLTD Reason (select_optn) */}
        <Grid item xs={12} md={6}>
          <div className="glass-panel" style={{ padding: '1.75rem', height: '100%' }}>
            <Typography variant="h6" sx={{ fontWeight: 700, color: '#f8fafc', mb: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
              <span>Step 1: Select Untag VLTD Reason</span>
            </Typography>
            <Typography variant="caption" sx={{ color: '#94a3b8', display: 'block', mb: 2 }}>
              Select transaction type to dynamically reveal the fitment fields via PrimeFaces AJAX.
            </Typography>

            <RadioGroup
              value={selectedOption}
              onChange={(e) => setSelectedOption(e.target.value)}
              sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, mb: 3 }}
            >
              {REASON_OPTIONS.map((opt) => (
                <Card
                  key={opt.id}
                  onClick={() => setSelectedOption(opt.value)}
                  sx={{
                    p: 1.5,
                    cursor: 'pointer',
                    borderRadius: '10px',
                    border: selectedOption === opt.value ? '2px solid #10b981' : '1px solid rgba(255, 255, 255, 0.08)',
                    background: selectedOption === opt.value ? 'rgba(16, 185, 129, 0.08)' : 'rgba(255, 255, 255, 0.02)',
                    transition: 'all 0.2s ease',
                  }}
                >
                  <FormControlLabel
                    value={opt.value}
                    control={<Radio sx={{ color: '#10b981', '&.Mui-checked': { color: '#10b981' } }} />}
                    label={
                      <div>
                        <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#f8fafc' }}>
                          {opt.title}
                        </Typography>
                        <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                          {opt.description}
                        </Typography>
                      </div>
                    }
                    sx={{ width: '100%', m: 0 }}
                  />
                </Card>
              ))}
            </RadioGroup>

            <Button
              variant="contained"
              fullWidth
              startIcon={isApplyingOption ? <CircularProgress size={18} sx={{ color: '#fff' }} /> : <PlayArrowIcon />}
              onClick={handleApplyOption}
              disabled={isApplyingOption}
              sx={{
                backgroundColor: '#10b981',
                fontWeight: 700,
                py: 1.2,
                '&:hover': { backgroundColor: '#059669' },
              }}
            >
              Apply Option to Portal
            </Button>

            {revealedFields.length > 0 && (
              <Box sx={{ mt: 2.5, p: 1.5, borderRadius: '8px', background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.25)' }}>
                <Typography variant="caption" sx={{ color: '#6ee7b7', fontWeight: 700, display: 'block', mb: 1 }}>
                  ✓ Fields Revealed on Portal ({revealedFields.length}):
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.8 }}>
                  {revealedFields.map((f) => (
                    <Chip key={f} label={f} size="small" sx={{ fontSize: '0.72rem', backgroundColor: 'rgba(255, 255, 255, 0.08)', color: '#e2e8f0' }} />
                  ))}
                </Box>
              </Box>
            )}
          </div>
        </Grid>

        {/* Step 2: Fitment Data Input & Submission */}
        <Grid item xs={12} md={6}>
          <div className="glass-panel" style={{ padding: '1.75rem', height: '100%' }}>
            <Typography variant="h6" sx={{ fontWeight: 700, color: '#f8fafc', mb: 1 }}>
              Step 2: Fitment Data Entry & Submission
            </Typography>
            <Typography variant="caption" sx={{ color: '#94a3b8', display: 'block', mb: 2 }}>
              Populate device fields, trigger "Get Details" (j_idt143), and execute replacement.
            </Typography>

            <Grid container spacing={2}>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  size="small"
                  label="VLTD Maker"
                  value={singleData.maker}
                  onChange={(e) => setSingleData({ ...singleData, maker: e.target.value })}
                  placeholder="e.g. VASP INFOTECH"
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  size="small"
                  label="VLTD Model"
                  value={singleData.model}
                  onChange={(e) => setSingleData({ ...singleData, model: e.target.value })}
                  placeholder="Model name"
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  size="small"
                  label="VLTD Serial Number"
                  value={singleData.serial_no}
                  onChange={(e) => setSingleData({ ...singleData, serial_no: e.target.value })}
                  placeholder="Device Serial No"
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  size="small"
                  label="IMEI Number"
                  value={singleData.imei}
                  onChange={(e) => setSingleData({ ...singleData, imei: e.target.value })}
                  placeholder="15-digit IMEI"
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  size="small"
                  label="ICC ID"
                  value={singleData.iccid}
                  onChange={(e) => setSingleData({ ...singleData, iccid: e.target.value })}
                  placeholder="20-digit ICCID"
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  size="small"
                  label="Registration Type"
                  value={singleData.reg_type}
                  onChange={(e) => setSingleData({ ...singleData, reg_type: e.target.value })}
                />
              </Grid>
            </Grid>

            <Box sx={{ mt: 3, display: 'flex', gap: 1.5 }}>
              <Button
                variant="contained"
                fullWidth
                startIcon={isSubmittingSingle ? <CircularProgress size={18} sx={{ color: '#fff' }} /> : <PlayArrowIcon />}
                onClick={handleExecuteSingle}
                disabled={isSubmittingSingle}
                sx={{
                  backgroundColor: '#6366f1',
                  fontWeight: 700,
                  py: 1.1,
                  '&:hover': { backgroundColor: '#4f46e5' },
                }}
              >
                Execute Single Record
              </Button>
            </Box>

            {/* CSV Batch Accordion */}
            <Box sx={{ mt: 3, pt: 2.5, borderTop: '1px solid rgba(255, 255, 255, 0.08)' }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 700, color: '#f8fafc', mb: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
                <UploadFileIcon fontSize="small" sx={{ color: '#10b981' }} />
                Or Process via CSV Dataset
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
                <Button
                  component="label"
                  variant="outlined"
                  size="small"
                  sx={{ borderColor: 'rgba(255, 255, 255, 0.2)', color: '#e2e8f0' }}
                >
                  Upload CSV
                  <input type="file" accept=".csv" hidden onChange={handleFileUpload} />
                </Button>
                {csvFileName && (
                  <Typography variant="caption" sx={{ color: '#10b981', fontWeight: 600 }}>
                    {csvFileName} ({csvRecords.length} records)
                  </Typography>
                )}
                {csvRecords.length > 0 && (
                  <Button
                    variant="contained"
                    size="small"
                    onClick={handleExecuteBatch}
                    disabled={isBatchRunning}
                    sx={{ backgroundColor: '#10b981', '&:hover': { backgroundColor: '#059669' } }}
                  >
                    {isBatchRunning ? <CircularProgress size={16} sx={{ color: '#fff' }} /> : 'Execute Batch'}
                  </Button>
                )}
              </Box>

              {isBatchRunning && (
                <Box sx={{ mt: 2 }}>
                  <LinearProgress sx={{ borderRadius: 4, height: 6 }} />
                  <Typography variant="caption" sx={{ color: '#94a3b8', mt: 0.5, display: 'block' }}>
                    Processing {batchProgress.total} records...
                  </Typography>
                </Box>
              )}
            </Box>
          </div>
        </Grid>
      </Grid>

      {/* Floating Notifications */}
      <Snackbar
        open={toast.open}
        autoHideDuration={6000}
        onClose={() => setToast((prev) => ({ ...prev, open: false }))}
        anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
      >
        <Alert
          onClose={() => setToast((prev) => ({ ...prev, open: false }))}
          severity={toast.severity}
          variant="filled"
          sx={{
            width: '100%',
            fontWeight: 700,
            fontSize: '0.9rem',
            boxShadow: '0 8px 24px rgba(0, 0, 0, 0.45)',
          }}
        >
          {toast.message}
        </Alert>
      </Snackbar>
    </div>
  );
}

