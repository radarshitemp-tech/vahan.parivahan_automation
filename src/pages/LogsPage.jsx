// src/pages/LogsPage.jsx
import React from 'react';
import ModuleHeader from '../components/common/ModuleHeader';
import BrowserSessionCard from '../components/common/BrowserSessionCard';
import ExecutionLogsViewer from '../components/common/ExecutionLogsViewer';

export default function LogsPage() {
  return (
    <div className="fade-in">
      <ModuleHeader
        currentModuleId="logs"
        title="Centralized VAHAN Audit & Diagnostics Hub"
        badge="System Logs"
        description="Real-time multi-tier execution audit trail, session events, PrimeFaces transaction logs, and single root file vahan_automation.log."
        color="#38bdf8"
      />

      <BrowserSessionCard compact />

      <ExecutionLogsViewer title="Real-Time Unified VAHAN Audit Trail" />
    </div>
  );
}

