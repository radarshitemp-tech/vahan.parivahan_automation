// src/services/vahanApi.js
import { commonApi } from './commonApi';
import { addApi } from './addApi';
import { deleteApi } from './deleteApi';
import { replaceApi } from './untagApi';

export { commonApi } from './commonApi';
export { addApi } from './addApi';
export { deleteApi } from './deleteApi';
export { replaceApi } from './untagApi';

export const vahanApi = {
  // Common endpoints
  checkHealth: commonApi.checkHealth,
  getSessionStatus: commonApi.getSessionStatus,
  closeBrowser: commonApi.closeBrowser,
  getUnifiedLogs: commonApi.getUnifiedLogs,
  getSessionStructuredLogs: commonApi.getSessionStructuredLogs,
  startNewLogSession: commonApi.startNewLogSession,
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
  navigateToDeletePortal: deleteApi.navigateToPortal,
  getDeleteRegistrations: deleteApi.getRegistrations,
  selectDeleteRegistration: deleteApi.selectRegistration,
  openDeleteReasonModal: deleteApi.openReasonModal,
  confirmDeleteUnlock: deleteApi.confirmUnlock,
  batchDeleteUnlock: deleteApi.batchUnlock,

  // Replace Module endpoints
  getReplaceStatus: replaceApi.getStatus,
  getReplaceOptions: replaceApi.getOptions,
  navigateToReplacePortal: replaceApi.navigateToPortal,
  selectReplaceOption: replaceApi.selectOption,
  inspectReplaceFields: replaceApi.inspectFields,
  executeSingleReplace: replaceApi.executeSingle,
  executeBatchReplace: replaceApi.executeBatch,
};

export default vahanApi;
