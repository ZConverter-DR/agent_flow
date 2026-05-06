from .compute import get_server_info_tool, create_vm_tool
from .recovery import execute_recovery_tool, get_recovery_status_tool
from .history import generate_policy_tool, generate_report_tool, save_history_tool

ALL_TOOLS = [
    get_server_info_tool,
    create_vm_tool,
    execute_recovery_tool,
    get_recovery_status_tool,
    generate_policy_tool,
    generate_report_tool,
    save_history_tool,
]