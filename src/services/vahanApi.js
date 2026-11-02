// src/services/vahanApi.js
/**
 * Unified API Facade for VAHAN Automation Studio.
 * Re-exports commonApi, addApi, and deleteApi methods to guarantee
 * full backward compatibility with existing components and hooks.
 */

import { commonApi } from './commonApi';
import { addApi } from './addApi';
import { deleteApi } from './deleteApi';

export { commonApi } from './commonApi';
export { addApi } from './addApi';
export { deleteApi } from './deleteApi';

export const vahanApi = {
  // Common endpoints
  checkHealth: commonApi.checkHealth,
  getSessionStatus: commonApi.getSessionStatus,
  closeBrowser: commonApi.closeBrowser,
  getUnifiedLogs: commonApi.getUnifiedLogs,
  listModules: commonApi.listModules,

  // Add Module endpoints (Preserved with existing signatures)
  uploadBatch: addApi.uploadBatch,
  getBatch: addApi.getBatch,
  inspectPortal: addApi.inspectPortal,
  confirmLoginAndInspect: addApi.confirmLoginAndInspect,
  getFieldMapping: addApi.getFieldMapping,
  saveFieldMapping: addApi.saveFieldMapping,
  executeDryRun: addApi.executeDryRun,
  startBatchProcessing: addApi.startBatchProcessing,
  resumeBatch: addApi.resumeBatch,
  stopBatch: addApi.stopBatch,
  getExecutionLogs: addApi.getExecutionLogs,
  getBatchReport: addApi.getBatchReport,

  // Delete Module endpoints
  getDeleteStatus: deleteApi.getStatus,
  getDeleteRegistrations: deleteApi.getRegistrations,
  selectDeleteRegistration: deleteApi.selectRegistration,
  openDeleteReasonModal: deleteApi.openReasonModal,
  confirmDeleteUnlock: deleteApi.confirmUnlock,
  batchDeleteUnlock: deleteApi.batchUnlock,
};

export default vahanApi;
