# backend/modules/registry.py
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

class ModuleDefinition(BaseModel):
    module_id: str
    name: str
    short_title: str
    description: str
    frontend_route: str
    api_prefix: str
    icon: str = "settings"
    badge: str = ""
    is_enabled: bool = True
    required_fields: List[str] = Field(default_factory=list)
    config: Dict[str, Any] = Field(default_factory=dict)

class ModuleRegistry:
    """
    Central registry for automation modules in the VAHAN Bulk platform.
    Allows registering new modules without altering the core framework.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ModuleRegistry, cls).__new__(cls)
            cls._instance._modules: Dict[str, ModuleDefinition] = {}
        return cls._instance

    def register(self, module_def: ModuleDefinition):
        self._modules[module_def.module_id] = module_def

    def get(self, module_id: str) -> Optional[ModuleDefinition]:
        return self._modules.get(module_id)

    def list_all(self) -> List[ModuleDefinition]:
        return list(self._modules.values())

    def list_enabled(self) -> List[ModuleDefinition]:
        return [m for m in self._modules.values() if m.is_enabled]

module_registry = ModuleRegistry()

# Register standard built-in modules
module_registry.register(ModuleDefinition(
    module_id="add_vltd",
    name="Add / Fitment VLTD",
    short_title="Add VLTD",
    description="Bulk device fitment and registration tagging on Parivahan VAHAN portal.",
    frontend_route="/modules/add",
    api_prefix="/api/modules/add",
    icon="add_circle",
    badge="Fitment Details",
    is_enabled=True,
    required_fields=[
        "VLTD Maker", "VLTD Model", "VLTD serial Number",
        "Provider", "IMEI Number", "Registration Type"
    ]
))

module_registry.register(ModuleDefinition(
    module_id="delete_vltd",
    name="Delete / Unlock VLTD",
    short_title="Unlock / Untag VLTD",
    description="Release and untag VLTD devices from registered vehicles with audit logging.",
    frontend_route="/modules/delete",
    api_prefix="/api/modules/delete",
    icon="lock_open",
    badge="Release VLTD",
    is_enabled=True,
    required_fields=["Vehicle Registration Number"]
))

