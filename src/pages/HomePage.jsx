import { useNavigate } from 'react-router-dom';
import { useCsv } from '../context/CsvContext';
import {
  Button,
  Typography,
  Box,
  Alert
} from '@mui/material';
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';

export default function HomePage() {
  const navigate = useNavigate();
  const { csvData, fileName, metadata, loadSampleData, isLoading, error } = useCsv();

  const handleLoadSample = async () => {
    try {
      await loadSampleData();
      navigate('/extract');
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="fade-in">
      {/* Hero Section */}
      <section className="hero-wrapper">
        <div className="hero-pill">
          <span>⚡ High-Performance CSV Ingestion & Extraction</span>
        </div>
        <h1 className="hero-title">
          <span className="hero-gradient-text">Data Extraction Platform</span>
        </h1>
        <p className="hero-subtitle">
          Upload standard CSV directly from your local device or provide a remote link.
        </p>

        {error && (
          <Box sx={{ maxWidth: 650, mx: 'auto', mb: 3 }}>
            <Alert severity="error" sx={{ backgroundColor: 'rgba(239, 68, 68, 0.1)', color: '#fca5a5' }}>
              {error}
            </Alert>
          </Box>
        )}

        {/* Home Screen Action Buttons */}
        <div className="hero-actions">
          <Button
            variant="contained"
            size="large"
            startIcon={<FileDownloadIcon />}
            onClick={() => navigate('/extract')}
            sx={{
              background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
              color: '#fff',
              fontWeight: 700,
              fontSize: '1rem',
              padding: '0.85rem 2rem',
              borderRadius: '12px',
              textTransform: 'none',
              boxShadow: '0 8px 24px rgba(99, 102, 241, 0.4)',
              '&:hover': {
                background: 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
                boxShadow: '0 12px 28px rgba(99, 102, 241, 0.6)',
              },
            }}
          >
            Go to /extract Page
          </Button>
        </div>
      </section>

      {/* Dataset Loaded Banner (if data exists) */}
      {csvData.length > 0 && metadata && (
        <div className="glass-panel" style={{ padding: '1.5rem 2rem', marginBottom: '3rem', border: '1px solid rgba(16, 185, 129, 0.3)' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
              <CheckCircleIcon sx={{ color: '#10b981', fontSize: 32 }} />
              <div>
                <Typography variant="h6" sx={{ color: '#fff', fontWeight: 700 }}>
                  Active Dataset: {fileName}
                </Typography>
                <Typography variant="body2" sx={{ color: '#94a3b8' }}>
                  Parsed {metadata.rowCount} rows & {metadata.columnCount} columns in {metadata.parseTimeMs}ms
                </Typography>
              </div>
            </Box>
            <Box sx={{ display: 'flex', gap: 1.5 }}>
              <Button
                variant="contained"
                size="small"
                onClick={() => navigate('/extract')}
                sx={{ backgroundColor: '#10b981', '&:hover': { backgroundColor: '#059669' } }}
              >
                Inspect Data in /extract
              </Button>
            </Box>
          </Box>
        </div>
      )}

      {/* Clean Feature Overview
      <div className="features-grid">
        <div className="glass-panel feature-card">
          <div className="feature-icon-box" style={{ background: 'rgba(99, 102, 241, 0.15)', color: '#818cf8' }}>
            <CloudUploadIcon />
          </div>
          <h3>Local File & Direct URL Ingestion</h3>
          <p>
            Upload CSV files from your local drive with drag-and-drop or fetch raw CSV data via web links directly.
          </p>
        </div>

        <div className="glass-panel feature-card">
          <div className="feature-icon-box" style={{ background: 'rgba(236, 72, 153, 0.15)', color: '#f472b6' }}>
            <SecurityIcon />
          </div>
          <h3>Redirect & Format Validation</h3>
          <p>
            If a link fails to redirect to a valid CSV or returns an HTML webpage, a clear popup error alerts you immediately.
          </p>
        </div>

        <div className="glass-panel feature-card">
          <div className="feature-icon-box" style={{ background: 'rgba(6, 182, 212, 0.15)', color: '#38bdf8' }}>
            <SpeedIcon />
          </div>
          <h3>Instant Data Display & Filtering</h3>
          <p>
            Extracts headers and rows into a searchable, paginated table with individual record inspection.
          </p>
        </div>
      </div> */}
    </div>
  );
}
