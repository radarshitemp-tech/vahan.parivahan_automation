// src/components/Navbar.jsx
import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useCsv } from '../context/CsvContext';
import {
  Tooltip,
  IconButton
} from '@mui/material';
import TableChartIcon from '@mui/icons-material/TableChart';
import HomeIcon from '@mui/icons-material/Home';
import AddCircleOutlineIcon from '@mui/icons-material/AddCircleOutline';
import LockOpenIcon from '@mui/icons-material/LockOpen';
import SyncAltIcon from '@mui/icons-material/SyncAlt';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';

export default function Navbar() {
  const { csvData, fileName, clearData } = useCsv();
  const navigate = useNavigate();

  return (
    <nav className="navbar">
      <div className="nav-brand" onClick={() => navigate('/')}>
        <div className="brand-icon">
          <TableChartIcon fontSize="medium" />
        </div>
        <div className="brand-title">
          VAHAN <span className="brand-badge">Studio</span>
        </div>
      </div>

      <div className="nav-links">
        <NavLink
          to="/"
          className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          end
        >
          <HomeIcon fontSize="small" />
          <span>Dashboard</span>
        </NavLink>

        <NavLink
          to="/modules/add"
          className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
        >
          <AddCircleOutlineIcon fontSize="small" />
          <span>Add VLTD</span>
        </NavLink>

        <NavLink
          to="/modules/delete"
          className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
        >
          <LockOpenIcon fontSize="small" />
          <span>Unlock / Delete</span>
        </NavLink>

        <NavLink
          to="/modules/untag"
          className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
        >
          <SyncAltIcon fontSize="small" />
          <span>Untag VLTD</span>
        </NavLink>
      </div>

      <div className="nav-status">
        {csvData.length > 0 ? (
          <div className="dataset-pill">
            <span className="pill-dot"></span>
            <span>{fileName || 'Active Dataset'} ({csvData.length.toLocaleString()} rows)</span>
            <Tooltip title="Clear Active Dataset">
              <IconButton
                size="small"
                onClick={(e) => {
                  e.stopPropagation();
                  clearData();
                }}
                sx={{ color: '#ef4444', p: 0.3 }}
              >
                <DeleteOutlineIcon fontSize="inherit" />
              </IconButton>
            </Tooltip>
          </div>
        ) : (
          <div className="dataset-pill empty">
            <span className="pill-dot"></span>
            <span>No CSV Loaded</span>
          </div>
        )}
      </div>
    </nav>
  );
}
