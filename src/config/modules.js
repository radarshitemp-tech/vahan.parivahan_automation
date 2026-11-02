// src/config/modules.js
/**
 * Centralized Module Registry for VAHAN Automation Studio.
 * Allows adding or configuring modules without modifying core application code.
 */

export const MODULE_IDS = {
  ADD_VLTD: 'add_vltd',
  DELETE_VLTD: 'delete_vltd',
};

export const MODULES = [
  {
    id: MODULE_IDS.ADD_VLTD,
    name: 'Add / Fitment VLTD',
    shortTitle: 'Add VLTD',
    badge: 'Fitment Details',
    description: 'Bulk CSV ingestion and automated vehicle retrofitment registration on Parivahan VAHAN portal.',
    route: '/modules/add',
    aliasRoute: '/extract',
    apiPrefix: '/api/vahan',
    color: '#6366f1',
    gradient: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
    icon: 'add_circle',
    enabled: true,
    features: [
      'CSV Upload & Data Integrity Validation',
      'Dynamic Field Auto-Mapping (11 Columns)',
      'Dry-Run Form Verification (Non-submitting)',
      'Sequential Batch Submission & Error Recovery',
      'Real-time Portal Audit Logs',
    ],
  },
  {
    id: MODULE_IDS.DELETE_VLTD,
    name: 'Delete / Unlock VLTD',
    shortTitle: 'Unlock / Untag VLTD',
    badge: 'Release VLTD',
    description: 'Automated release and untagging of VLTD devices from registered vehicles with operator confirmation.',
    route: '/modules/delete',
    aliasRoute: '/delete',
    apiPrefix: '/api/modules/delete',
    color: '#ef4444',
    gradient: 'linear-gradient(135deg, #ef4444 0%, #f43f5e 100%)',
    icon: 'lock_open',
    enabled: true,
    features: [
      'Registration Number Selector (select tag: reg_label)',
      'Release Section Detection (button: j_idt112)',
      'Interactive Reason Input Modal (field: Inputreject)',
      'Operator Final Approval Dialog before j_idt122 submission',
      'Authoritative Portal Result Verification & Batch Mode',
    ],
  },
];

export const getEnabledModules = () => MODULES.filter((m) => m.enabled);

export const getModuleById = (id) => MODULES.find((m) => m.id === id) || null;

export const getModuleByRoute = (path) =>
  MODULES.find((m) => m.route === path || m.aliasRoute === path) || null;

