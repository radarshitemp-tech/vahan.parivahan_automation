// src/pages/DeletePage.jsx
import { useState, useCallback } from 'react';
import {
  Box,
  Button,
  Typography,
  TextField,
  Autocomplete,
  Chip,
  CircularProgress,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Grid,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
  Paper,
  Tabs,
  Tab,
  Card,
  CardContent,
  Divider,
  Snackbar,
} from '@mui/material';
import Papa from 'papaparse';
import LockOpenIcon from '@mui/icons-material/LockOpen';
import RefreshIcon from '@mui/icons-material/Refresh';
import DirectionsCarIcon from '@mui/icons-material/DirectionsCar';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import PlaylistPlayIcon from '@mui/icons-material/PlaylistPlay';
import FileUploadIcon from '@mui/icons-material/FileUpload';

import ModuleHeader from '../components/common/ModuleHeader';
import BrowserSessionCard from '../components/common/BrowserSessionCard';
import { deleteApi } from '../services/deleteApi';

export default function DeletePage() {
  const [activeTab, setActiveTab] = useState(0); // 0: Single Vehicle Flow, 1: Batch File Untag

  // Single Vehicle State
  const [registrations, setRegistrations] = useState([]);
  const [selectedReg, setSelectedReg] = useState('');
  const [customRegInput, setCustomRegInput] = useState('');
  const [reason, setReason] = useState('Untag VLTD / Fitment Removal');
  const [vehicleInfo, setVehicleInfo] = useState(null);
  const [stage, setStage] = useState('IDLE'); // IDLE | SELECTING | SELECTED | MODAL_OPEN | CONFIRMING | DONE

  // Loading and error states
  const [isFetchingList, setIsFetchingList] = useState(false);
  const [isSelecting, setIsSelecting] = useState(false);
  const [isOpeningModal, setIsOpeningModal] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [statusMessage, setStatusMessage] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);

  // Operator Final Confirmation Modal
  const [isConfirmDialogOpen, setIsConfirmDialogOpen] = useState(false);

  // Toast Notification State
  const [toast, setToast] = useState({ open: false, message: '', severity: 'info' });

  // Execution Result History
  const [historyResults, setHistoryResults] = useState([]);

  // Batch Mode State
  const [batchText, setBatchText] = useState('');
  const [isBatchRunning, setIsBatchRunning] = useState(false);
  const [batchResults, setBatchResults] = useState(null);

  // Fetch registration numbers from portal dropdown
  const handleFetchRegistrations = useCallback(async () => {
    setIsFetchingList(true);
    setErrorMessage(null);
    try {
      const list = await deleteApi.getRegistrations();
      setRegistrations(list || []);
      if (list && list.length > 0) {
        setStatusMessage(`Loaded ${list.length} vehicle registration(s) from VAHAN portal dropdown (reg_label).`);
      } else {
        setStatusMessage('No registrations returned. Ensure browser is logged in and on SLD Fitting page.');
      }
    } catch (e) {
      setErrorMessage(`Failed to fetch registrations: ${e.message}`);
    } finally {
      setIsFetchingList(false);
    }
  }, []);

  // Step 1: Select vehicle registration and verify Release section
  const handleSelectRegistration = async (regToUse) => {
    const reg = (regToUse || selectedReg || customRegInput).trim().toUpperCase();
    if (!reg) {
      setErrorMessage('Please enter or select a vehicle registration number.');
      return;
    }

    setIsSelecting(true);
    setErrorMessage(null);
    setStatusMessage(null);
    setVehicleInfo(null);
    setStage('SELECTING');

    try {
      const res = await deleteApi.selectRegistration(reg);
      if (res.success) {
        setSelectedReg(reg);
        setVehicleInfo(res.vehicle_info || {});
        setStage('SELECTED');
        setStatusMessage(res.message || `Vehicle ${reg} selected. 'Release VLTD From Vehicle' section loaded.`);
      } else {
        setErrorMessage(res.message || `Failed to select vehicle ${reg}.`);
        setStage('IDLE');
      }
    } catch (e) {
      setErrorMessage(`Selection error: ${e.message}`);
      setStage('IDLE');
    } finally {
      setIsSelecting(false);
    }
  };

  // Step 2: Click first Unlock button (j_idt112) to reveal reason modal (Inputreject + j_idt122)
  const handleOpenReasonModal = async () => {
    setIsOpeningModal(true);
    setErrorMessage(null);
    try {
      const res = await deleteApi.openReasonModal();
      if (res.success) {
        setStage('MODAL_OPEN');
        setStatusMessage("Reason modal rendered on portal. Ready for operator approval.");
        setIsConfirmDialogOpen(true);
      } else {
        setErrorMessage(res.message || "Failed to trigger unlock modal ('j_idt112').");
      }
    } catch (e) {
      setErrorMessage(`Error triggering modal: ${e.message}`);
    } finally {
      setIsOpeningModal(false);
    }
  };

  // Step 3: Explicit operator sign-off and final execution (j_idt122)
  const handleFinalConfirmSubmit = async () => {
    setIsConfirmDialogOpen(false);
    setIsSubmitting(true);
    setErrorMessage(null);
    setStatusMessage(`Submitting unlock for ${selectedReg}...`);
    setStage('CONFIRMING');

    try {
      const res = await deleteApi.confirmUnlock(selectedReg, reason);
      setHistoryResults((prev) => [res, ...prev]);
      if (res.status === 'SUCCESS') {
        setStatusMessage(`VLTD Successfully Unlocked for ${selectedReg}! Ref: ${res.confirmation_ref || 'CONFIRMED'}`);
        setStage('DONE');
      } else {
        setErrorMessage(`Portal reported rejection: ${res.message}`);
        setStage('SELECTED');
      }
    } catch (e) {
      setErrorMessage(`Final confirmation failed: ${e.message}`);
      setStage('SELECTED');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Batch Mode Execution
  const handleRunBatch = async () => {
    const lines = batchText
      .split('\n')
      .map((l) => l.trim().toUpperCase())
      .filter((l) => l.length >= 4);

    if (lines.length === 0) {
      setErrorMessage('Please enter at least one valid vehicle registration number in the batch box.');
      return;
    }

    setIsBatchRunning(true);
    setErrorMessage(null);
    setBatchResults(null);

    try {
      const res = await deleteApi.batchUnlock(lines, reason);
      setBatchResults(res);
      if (res.results) {
        setHistoryResults((prev) => [...res.results, ...prev]);
      }
      setStatusMessage(`Batch complete: ${res.successful_count} unlocked, ${res.failed_count} failed.`);
    } catch (e) {
      setErrorMessage(`Batch execution error: ${e.message}`);
    } finally {
      setIsBatchRunning(false);
    }
  };

  // Helper to identify Vehicle Registration column variants
  const isRegistrationColumn = (name) => {
    if (!name) return false;
    const clean = String(name).toLowerCase().replace(/[^a-z0-9]/g, '');
    const aliases = [
      'vehicleregistrationno',
      'vehicleregistrationnumber',
      'vehicleregistration',
      'vehicleregno',
      'vehicleregnumber',
      'registrationno',
      'registrationnumber',
      'registration',
      'regno',
      'regnno',
      'regnum',
      'vehicleno',
      'vehiclenumber',
      'rcnumber',
      'rcno',
    ];
    if (aliases.includes(clean)) return true;
    if (clean.includes('reg') && (clean.includes('no') || clean.includes('num') || clean.includes('veh') || clean.includes('rc'))) {
      return true;
    }
    return false;
  };

  // Handle CSV file upload for batch - extracts 'Vehicle Registration No' column
  const handleCsvFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Reset file input so selecting the same file again triggers onChange
    e.target.value = '';

    Papa.parse(file, {
      skipEmptyLines: 'greedy',
      complete: (results) => {
        const { data } = results;
        if (!data || data.length === 0) {
          const err = 'The uploaded CSV file is empty.';
          setErrorMessage(err);
          setToast({ open: true, message: err, severity: 'error' });
          return;
        }

        // Search the first row for the vehicle registration column
        const headers = (data[0] || []).map((h) => String(h || '').trim());
        let targetColIndex = -1;
        let matchedColName = '';

        for (let i = 0; i < headers.length; i++) {
          if (isRegistrationColumn(headers[i])) {
            targetColIndex = i;
            matchedColName = headers[i];
            break;
          }
        }

        if (targetColIndex === -1) {
          const err = `No 'Vehicle Registration No' column found in '${file.name}'. Found columns: ${headers.filter(Boolean).join(', ') || 'None'}`;
          setErrorMessage(err);
          setToast({
            open: true,
            message: `Error: Could not find 'Vehicle Registration No' column in uploaded CSV file (${file.name}).`,
            severity: 'error',
          });
          return;
        }

        // Extract values from the identified registration column (rows 1 to N)
        const extracted = [];
        for (let r = 1; r < data.length; r++) {
          const row = data[r];
          if (!row || row.length <= targetColIndex) continue;
          const val = String(row[targetColIndex] || '').trim().replace(/["']/g, '').toUpperCase();
          if (val && val.length >= 4 && !isRegistrationColumn(val)) {
            extracted.push(val);
          }
        }

        if (extracted.length === 0) {
          const warn = `Column '${matchedColName}' was found in '${file.name}', but it contains no valid registration numbers.`;
          setErrorMessage(warn);
          setToast({ open: true, message: warn, severity: 'warning' });
          return;
        }

        setBatchText(extracted.join('\n'));
        setErrorMessage(null);
        const successMsg = `Loaded ${extracted.length} vehicle registration number(s) from column '${matchedColName}' (${file.name}).`;
        setStatusMessage(successMsg);
        setToast({ open: true, message: successMsg, severity: 'success' });
      },
      error: (err) => {
        const errMsg = `Failed to parse CSV file: ${err.message}`;
        setErrorMessage(errMsg);
        setToast({ open: true, message: errMsg, severity: 'error' });
      },
    });
  };

  return (
    <div className="fade-in">
      {/* Central Module Header */}
      <ModuleHeader
        currentModuleId="delete_vltd"
        title="Delete / Unlock VLTD Module"
        badge="Release VLTD"
        description="Safely release and untag VLTD devices from vehicles on the Parivahan VAHAN portal with explicit operator verification."
        color="#ef4444"
      />

      {/* Shared Browser Session Card */}
      <BrowserSessionCard />

      {/* Mode Tabs */}
      <div className="glass-panel" style={{ padding: '0.5rem 1.5rem', marginBottom: '1.5rem' }}>
        <Tabs
          value={activeTab}
          onChange={(_, val) => setActiveTab(val)}
          sx={{
            '& .MuiTab-root': {
              fontWeight: 700,
              fontSize: '0.95rem',
              textTransform: 'none',
              color: '#94a3b8',
              '&.Mui-selected': { color: '#f87171' },
            },
            '& .MuiTabs-indicator': { backgroundColor: '#ef4444' },
          }}
        >
          <Tab icon={<DirectionsCarIcon fontSize="small" />} iconPosition="start" label="Interactive Single Vehicle Untag" />
          <Tab icon={<PlaylistPlayIcon fontSize="small" />} iconPosition="start" label="Batch Registration Unlock" />
        </Tabs>
      </div>

      {/* Messages */}
      {statusMessage && (
        <Alert severity="success" sx={{ mb: 2, backgroundColor: 'rgba(16, 185, 129, 0.1)', color: '#6ee7b7' }}>
          {statusMessage}
        </Alert>
      )}
      {errorMessage && (
        <Alert severity="error" sx={{ mb: 2, backgroundColor: 'rgba(239, 68, 68, 0.1)', color: '#fca5a5' }}>
          {errorMessage}
        </Alert>
      )}

      {/* TAB 0: Single Vehicle Flow */}
      {activeTab === 0 && (
        <Grid container spacing={3}>
          {/* Left Column: Form Controls */}
          <Grid item xs={12} md={6}>
            <div className="glass-panel" style={{ padding: '1.75rem', height: '100%' }}>
              <Typography variant="h6" sx={{ fontWeight: 700, color: '#f8fafc', mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                <span>Step 1: Vehicle Registration</span>
              </Typography>

              {/* Registration Select & Live Fetch */}
              <Box sx={{ mb: 3 }}>
                <Box sx={{ display: 'flex', gap: 1, mb: 1.5 }}>
                  <Autocomplete
                    freeSolo
                    options={registrations}
                    value={selectedReg}
                    onChange={(_, val) => setSelectedReg(val || '')}
                    onInputChange={(_, val) => setCustomRegInput(val || '')}
                    sx={{ flex: 1 }}
                    renderInput={(params) => (
                      <TextField
                        {...params}
                        label="Vehicle Registration Number"
                        placeholder="e.g. DL01AB1234 or select from portal"
                        helperText="Matches portal select tag with label id (reg_label)"
                      />
                    )}
                  />
                  <Button
                    variant="outlined"
                    startIcon={isFetchingList ? <CircularProgress size={16} /> : <RefreshIcon />}
                    onClick={handleFetchRegistrations}
                    disabled={isFetchingList}
                    sx={{ borderColor: 'rgba(255, 255, 255, 0.15)', color: '#cbd5e1', height: 54 }}
                  >
                    Fetch Portal Options
                  </Button>
                </Box>

                <Button
                  variant="contained"
                  fullWidth
                  disabled={isSelecting || (!selectedReg && !customRegInput)}
                  onClick={() => handleSelectRegistration()}
                  sx={{
                    py: 1.2,
                    fontWeight: 700,
                    backgroundColor: '#6366f1',
                    '&:hover': { backgroundColor: '#4f46e5' },
                  }}
                >
                  {isSelecting ? <CircularProgress size={20} color="inherit" /> : 'Inspect Vehicle & Detect Release Section'}
                </Button>
              </Box>

              <Divider sx={{ my: 2.5, borderColor: 'rgba(255, 255, 255, 0.08)' }} />

              {/* Step 2: Reason & Unlock Trigger */}
              <Typography variant="h6" sx={{ fontWeight: 700, color: '#f8fafc', mb: 2 }}>
                Step 2: Unlock Reason & Trigger
              </Typography>

              <TextField
                fullWidth
                multiline
                rows={2}
                label="Unlock Reason (Inputreject)"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Reason for releasing VLTD from vehicle..."
                helperText="Will be filled into portal modal field id: Inputreject"
                sx={{ mb: 2.5 }}
              />

              <Button
                variant="contained"
                fullWidth
                disabled={stage !== 'SELECTED' || isOpeningModal}
                onClick={handleOpenReasonModal}
                sx={{
                  py: 1.4,
                  fontWeight: 700,
                  fontSize: '0.95rem',
                  backgroundColor: stage === 'SELECTED' ? '#ef4444' : 'rgba(239, 68, 68, 0.3)',
                  color: '#fff',
                  '&:hover': { backgroundColor: '#dc2626' },
                }}
              >
                {isOpeningModal ? (
                  <CircularProgress size={20} color="inherit" />
                ) : (
                  <>
                    <LockOpenIcon sx={{ mr: 1 }} />
                    Trigger 'Unlock VLTD' (Button: j_idt112)
                  </>
                )}
              </Button>
            </div>
          </Grid>

          {/* Right Column: Vehicle Details & Status Card */}
          <Grid item xs={12} md={6}>
            <div className="glass-panel" style={{ padding: '1.75rem', height: '100%' }}>
              <Typography variant="h6" sx={{ fontWeight: 700, color: '#f8fafc', mb: 2 }}>
                Vehicle Inspection & Release Status
              </Typography>

              {vehicleInfo && Object.keys(vehicleInfo).length > 0 ? (
                <div style={{ backgroundColor: 'rgba(0,0,0,0.25)', borderRadius: 8, padding: '1rem', marginBottom: '1.5rem' }}>
                  <Typography variant="subtitle2" sx={{ color: '#10b981', fontWeight: 700, mb: 1, display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <CheckCircleOutlineIcon fontSize="small" />
                    Portal Release Section Active
                  </Typography>
                  <Table size="small">
                    <TableBody>
                      {Object.entries(vehicleInfo).map(([k, v]) => (
                        <TableRow key={k} sx={{ '& td': { borderBottom: '1px solid rgba(255,255,255,0.05)', py: 0.5 } }}>
                          <TableCell sx={{ color: '#94a3b8', fontWeight: 600, width: '40%' }}>{k}</TableCell>
                          <TableCell sx={{ color: '#f8fafc', fontFamily: 'monospace' }}>{v}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              ) : (
                <Box
                  sx={{
                    p: 4,
                    textAlign: 'center',
                    border: '1px dashed rgba(255, 255, 255, 0.15)',
                    borderRadius: 2,
                    mb: 2,
                  }}
                >
                  <DirectionsCarIcon sx={{ fontSize: 48, color: '#64748b', mb: 1 }} />
                  <Typography variant="body2" sx={{ color: '#94a3b8' }}>
                    Select a vehicle registration on the left to inspect its active VLTD details and load the portal Release container.
                  </Typography>
                </Box>
              )}

              {/* Lifecycle Stage Indicator */}
              <Box sx={{ mt: 2 }}>
                <Typography variant="caption" sx={{ color: '#94a3b8', textTransform: 'uppercase', letterSpacing: 1, fontWeight: 700 }}>
                  Automation Stage
                </Typography>
                <Box sx={{ display: 'flex', gap: 1, mt: 1, flexWrap: 'wrap' }}>
                  <Chip
                    label="1. Selection"
                    color={stage === 'SELECTING' ? 'primary' : stage !== 'IDLE' ? 'success' : 'default'}
                    size="small"
                  />
                  <Chip
                    label="2. Release Section"
                    color={stage === 'SELECTED' ? 'warning' : ['MODAL_OPEN', 'CONFIRMING', 'DONE'].includes(stage) ? 'success' : 'default'}
                    size="small"
                  />
                  <Chip
                    label="3. Reason Modal"
                    color={stage === 'MODAL_OPEN' ? 'warning' : ['CONFIRMING', 'DONE'].includes(stage) ? 'success' : 'default'}
                    size="small"
                  />
                  <Chip
                    label="4. Final Unlock"
                    color={stage === 'DONE' ? 'success' : stage === 'CONFIRMING' ? 'error' : 'default'}
                    size="small"
                  />
                </Box>
              </Box>
            </div>
          </Grid>
        </Grid>
      )}

      {/* TAB 1: Batch Mode */}
      {activeTab === 1 && (
        <div className="glass-panel" style={{ padding: '1.75rem' }}>
          <Typography variant="h6" sx={{ fontWeight: 700, color: '#f8fafc', mb: 1 }}>
            Batch Vehicle Untag & Unlock
          </Typography>
          <Typography variant="body2" sx={{ color: '#94a3b8', mb: 3 }}>
            Paste a list of vehicle registration numbers (one per line) or upload a CSV file to execute sequential untagging.
          </Typography>

          <Grid container spacing={3}>
            <Grid item xs={12} md={7}>
              <TextField
                fullWidth
                multiline
                rows={8}
                label="Vehicle Registration Numbers (One per line)"
                placeholder="DL01AB1234&#10;UP16XY9999&#10;HR26CD5678"
                value={batchText}
                onChange={(e) => setBatchText(e.target.value)}
                sx={{ mb: 2, fontFamily: 'monospace' }}
              />

              <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', mb: 2 }}>
                <Button
                  variant="outlined"
                  component="label"
                  startIcon={<FileUploadIcon />}
                  sx={{ borderColor: 'rgba(255, 255, 255, 0.15)', color: '#cbd5e1' }}
                >
                  Upload CSV File
                  <input type="file" hidden accept=".csv,.txt" onChange={handleCsvFileUpload} />
                </Button>
                <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                  Accepts CSV containing 'Vehicle Registration Number' column.
                </Typography>
              </Box>

              <TextField
                fullWidth
                size="small"
                label="Batch Default Reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                sx={{ mb: 3 }}
              />

              <Button
                variant="contained"
                size="large"
                disabled={isBatchRunning || !batchText.trim()}
                onClick={handleRunBatch}
                sx={{
                  backgroundColor: '#ef4444',
                  fontWeight: 700,
                  px: 4,
                  py: 1.2,
                  '&:hover': { backgroundColor: '#dc2626' },
                }}
              >
                {isBatchRunning ? <CircularProgress size={20} color="inherit" /> : 'Start Batch Unlock Sequence'}
              </Button>
            </Grid>

            {/* Batch Metrics / Results summary */}
            <Grid item xs={12} md={5}>
              {batchResults && (
                <div style={{ backgroundColor: 'rgba(0,0,0,0.25)', borderRadius: 12, padding: '1.25rem', border: '1px solid rgba(255,255,255,0.08)' }}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#f8fafc', mb: 1.5 }}>
                    Batch Execution Summary
                  </Typography>
                  <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
                    <Card sx={{ flex: 1, backgroundColor: 'rgba(99, 102, 241, 0.15)', textAlign: 'center' }}>
                      <CardContent sx={{ py: 1.5 }}>
                        <Typography variant="h5" sx={{ fontWeight: 800, color: '#818cf8' }}>
                          {batchResults.total_count}
                        </Typography>
                        <Typography variant="caption" sx={{ color: '#94a3b8' }}>Total</Typography>
                      </CardContent>
                    </Card>
                    <Card sx={{ flex: 1, backgroundColor: 'rgba(16, 185, 129, 0.15)', textAlign: 'center' }}>
                      <CardContent sx={{ py: 1.5 }}>
                        <Typography variant="h5" sx={{ fontWeight: 800, color: '#10b981' }}>
                          {batchResults.successful_count}
                        </Typography>
                        <Typography variant="caption" sx={{ color: '#94a3b8' }}>Success</Typography>
                      </CardContent>
                    </Card>
                    <Card sx={{ flex: 1, backgroundColor: 'rgba(239, 68, 68, 0.15)', textAlign: 'center' }}>
                      <CardContent sx={{ py: 1.5 }}>
                        <Typography variant="h5" sx={{ fontWeight: 800, color: '#ef4444' }}>
                          {batchResults.failed_count}
                        </Typography>
                        <Typography variant="caption" sx={{ color: '#94a3b8' }}>Failed</Typography>
                      </CardContent>
                    </Card>
                  </Box>
                </div>
              )}
            </Grid>
          </Grid>
        </div>
      )}

      {/* Operator Review & Confirmation Dialog */}
      <Dialog
        open={isConfirmDialogOpen}
        onClose={() => setIsConfirmDialogOpen(false)}
        maxWidth="sm"
        fullWidth
        PaperProps={{
          style: {
            backgroundColor: '#111827',
            border: '1px solid rgba(239, 68, 68, 0.4)',
            borderRadius: 16,
            color: '#f8fafc',
          },
        }}
      >
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1.5, color: '#f87171', fontWeight: 800 }}>
          <WarningAmberIcon />
          Confirm VLTD Device Release
        </DialogTitle>
        <DialogContent dividers sx={{ borderColor: 'rgba(255, 255, 255, 0.1)' }}>
          <Typography variant="body1" sx={{ mb: 2, color: '#f8fafc' }}>
            Are you sure you want to permanently untag and release the VLTD device from vehicle:
          </Typography>

          <Box sx={{ p: 2, backgroundColor: 'rgba(0, 0, 0, 0.4)', borderRadius: 2, mb: 2 }}>
            <Typography variant="h5" sx={{ fontWeight: 800, color: '#38bdf8', fontFamily: 'monospace', mb: 1 }}>
              {selectedReg}
            </Typography>
            <Typography variant="body2" sx={{ color: '#94a3b8' }}>
              <strong>Reason:</strong> {reason}
            </Typography>
            <Typography variant="caption" sx={{ color: '#64748b', display: 'block', mt: 0.5 }}>
              Portal Action: Click confirm button id (j_idt122) in modal dialog.
            </Typography>
          </Box>

          <Alert severity="warning" sx={{ backgroundColor: 'rgba(245, 158, 11, 0.1)', color: '#fcd34d' }}>
            This action will disconnect the device mapping in the official VAHAN portal. Please ensure vehicle details are verified.
          </Alert>
        </DialogContent>
        <DialogActions sx={{ p: 2, borderColor: 'rgba(255, 255, 255, 0.1)' }}>
          <Button onClick={() => setIsConfirmDialogOpen(false)} sx={{ color: '#94a3b8' }}>
            Cancel
          </Button>
          <Button
            variant="contained"
            color="error"
            onClick={handleFinalConfirmSubmit}
            sx={{ fontWeight: 700, px: 3 }}
          >
            Yes, Confirm & Unlock (j_idt122)
          </Button>
        </DialogActions>
      </Dialog>

      {/* Execution Results Table */}
      {historyResults.length > 0 && (
        <div className="glass-panel" style={{ padding: '1.5rem', marginTop: '1.5rem' }}>
          <Typography variant="h6" sx={{ fontWeight: 700, color: '#f8fafc', mb: 1.5 }}>
            Recent Unlock Transactions ({historyResults.length})
          </Typography>
          <Paper sx={{ backgroundColor: 'rgba(0, 0, 0, 0.25)', overflow: 'hidden' }}>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ '& th': { color: '#94a3b8', fontWeight: 700 } }}>
                  <TableCell>Vehicle Registration</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Reason</TableCell>
                  <TableCell>Portal Message / Reference</TableCell>
                  <TableCell>Timestamp</TableCell>
                  <TableCell align="right">Duration</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {historyResults.map((r, i) => (
                  <TableRow key={i} sx={{ '& td': { color: '#f8fafc', borderColor: 'rgba(255,255,255,0.05)' } }}>
                    <TableCell sx={{ fontWeight: 700, fontFamily: 'monospace' }}>{r.registration_number}</TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        label={r.status}
                        color={r.status === 'SUCCESS' ? 'success' : 'error'}
                        sx={{ fontWeight: 700, fontSize: '0.72rem' }}
                      />
                    </TableCell>
                    <TableCell sx={{ color: '#94a3b8' }}>{r.reason}</TableCell>
                    <TableCell sx={{ fontSize: '0.82rem' }}>
                      {r.message} {r.confirmation_ref && <span style={{ color: '#38bdf8' }}>({r.confirmation_ref})</span>}
                    </TableCell>
                    <TableCell sx={{ color: '#64748b', fontSize: '0.75rem' }}>{r.executed_at}</TableCell>
                    <TableCell align="right" sx={{ color: '#64748b', fontSize: '0.75rem' }}>
                      {r.duration_seconds ? `${r.duration_seconds}s` : '-'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>
        </div>
      )}

      {/* Floating Error / Success Toast Notification */}
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
            border: '1px solid rgba(255, 255, 255, 0.2)',
          }}
        >
          {toast.message}
        </Alert>
      </Snackbar>
    </div>
  );
}

