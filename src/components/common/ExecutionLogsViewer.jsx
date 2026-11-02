// src/components/common/ExecutionLogsViewer.jsx
import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Tabs,
  Tab,
  Button,
  TextField,
  Chip,
  IconButton,
  Tooltip
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import DownloadIcon from '@mui/icons-material/Download';
import SearchIcon from '@mui/icons-material/Search';
import ArticleIcon from '@mui/icons-material/Article';
import { commonApi } from '../../services/commonApi';

export default function ExecutionLogsViewer({ structuredLogs = [], title = 'Execution & Portal Audit Logs' }) {
  const [tabIndex, setTabIndex] = useState(0);
  const [unifiedLogs, setUnifiedLogs] = useState({ log_file: '', content: '' });
  const [filterText, setFilterText] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const fetchUnified = async () => {
    setIsLoading(true);
    try {
      const data = await commonApi.getUnifiedLogs(250);
      setUnifiedLogs(data);
    } catch {
      // ignore
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchUnified();
  }, []);

  const handleDownload = () => {
    const text = tabIndex === 0
      ? JSON.stringify(structuredLogs, null, 2)
      : (unifiedLogs.content || '');
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = tabIndex === 0 ? 'structured_audit_logs.json' : 'vahan_automation.log';
    a.click();
    URL.revokeObjectURL(url);
  };

  const filteredStructured = (structuredLogs || []).filter((l) => {
    if (!filterText) return true;
    const txt = `${l.timestamp} ${l.stage} ${l.action} ${l.message} ${l.result} ${l.error_code || ''}`.toLowerCase();
    return txt.includes(filterText.toLowerCase());
  });

  const filteredUnifiedLines = (unifiedLogs.content || '')
    .split('\n')
    .filter((line) => {
      if (!filterText) return true;
      return line.toLowerCase().includes(filterText.toLowerCase());
    });

  return (
    <div className="glass-panel" style={{ padding: '1.25rem 1.5rem', marginTop: '1.5rem' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 2, mb: 1.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <ArticleIcon sx={{ color: '#818cf8' }} />
          <Typography variant="h6" sx={{ fontWeight: 700, color: '#f8fafc', fontSize: '1.05rem' }}>
            {title}
          </Typography>
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          <TextField
            size="small"
            placeholder="Filter log entries..."
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            InputProps={{
              startAdornment: <SearchIcon fontSize="small" sx={{ color: '#94a3b8', mr: 0.5 }} />,
            }}
            sx={{
              width: 220,
              '& .MuiInputBase-input': { py: 0.6, fontSize: '0.85rem' },
              '& .MuiOutlinedInput-root': { backgroundColor: 'rgba(0, 0, 0, 0.2)' },
            }}
          />
          <Tooltip title="Refresh Unified Log File">
            <IconButton size="small" onClick={fetchUnified} disabled={isLoading} sx={{ color: '#94a3b8' }}>
              <RefreshIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Button
            variant="outlined"
            size="small"
            startIcon={<DownloadIcon />}
            onClick={handleDownload}
            sx={{ borderColor: 'rgba(255, 255, 255, 0.15)', color: '#cbd5e1', fontSize: '0.8rem' }}
          >
            Export
          </Button>
        </Box>
      </Box>

      <Tabs
        value={tabIndex}
        onChange={(_, val) => setTabIndex(val)}
        sx={{
          minHeight: 36,
          mb: 1.5,
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
          '& .MuiTab-root': { minHeight: 36, py: 0.5, fontSize: '0.85rem', textTransform: 'none' },
        }}
      >
        <Tab label={`Session Audit Logs (${filteredStructured.length})`} />
        <Tab label={`Unified Root Log (${unifiedLogs.log_file || 'vahan_automation.log'})`} />
      </Tabs>

      {tabIndex === 0 ? (
        <div style={{ maxHeight: 380, overflowY: 'auto', borderRadius: 8, backgroundColor: 'rgba(0, 0, 0, 0.35)', padding: '0.75rem' }}>
          {filteredStructured.length === 0 ? (
            <Typography variant="body2" sx={{ color: '#64748b', textAlign: 'center', py: 3 }}>
              No structured log entries recorded yet in this session.
            </Typography>
          ) : (
            filteredStructured.map((log, idx) => (
              <Box
                key={idx}
                sx={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 1.5,
                  py: 0.75,
                  borderBottom: '1px solid rgba(255, 255, 255, 0.04)',
                  fontSize: '0.82rem',
                  fontFamily: 'monospace',
                }}
              >
                <span style={{ color: '#64748b', whiteSpace: 'nowrap' }}>{log.timestamp}</span>
                <Chip
                  size="small"
                  label={log.level}
                  color={log.level === 'ERROR' || log.level === 'CRITICAL' ? 'error' : log.level === 'WARNING' ? 'warning' : 'info'}
                  sx={{ height: 18, fontSize: '0.68rem', fontWeight: 700 }}
                />
                <span style={{ color: '#a78bfa', fontWeight: 600 }}>[{log.stage || 'OP'}]</span>
                <span style={{ color: '#f1f5f9', flex: 1 }}>{log.message}</span>
                {log.result && (
                  <Chip
                    size="small"
                    label={log.result}
                    variant="outlined"
                    sx={{ height: 18, fontSize: '0.65rem', borderColor: 'rgba(255, 255, 255, 0.15)', color: '#94a3b8' }}
                  />
                )}
              </Box>
            ))
          )}
        </div>
      ) : (
        <pre
          style={{
            maxHeight: 380,
            overflowY: 'auto',
            borderRadius: 8,
            backgroundColor: 'rgba(0, 0, 0, 0.45)',
            padding: '0.85rem',
            margin: 0,
            color: '#38bdf8',
            fontSize: '0.78rem',
            fontFamily: 'Consolas, monospace',
            whiteSpace: 'pre-wrap',
            lineHeight: 1.45,
          }}
        >
          {filteredUnifiedLines.join('\n') || 'Unified log file is empty or awaiting entries.'}
        </pre>
      )}
    </div>
  );
}

