"""Constants for the Smoobu Workflow integration."""
from __future__ import annotations

from homeassistant.const import Platform

# Legacy domain kept intentionally for update compatibility.
DOMAIN = "smoobu_mittelhof"
INTEGRATION_NAME = "Smoobu Workflow"

PLATFORMS = [
    Platform.CALENDAR,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SELECT,
]

CONF_API_KEY = "api_key"
CONF_API_SECRET = "api_secret"
CONF_HOUSES = "houses"
CONF_UPDATE_INTERVAL_MINUTES = "update_interval_minutes"
CONF_HORIZON_DAYS = "horizon_days"
CONF_LOOKBACK_DAYS = "lookback_days"
CONF_SHOW_GUEST_NAMES = "show_guest_names"
CONF_CONFIG_DIRECTORY = "config_directory"

CONF_NOTIFY_SERVICE = "notify_service"
CONF_LAUNDRY_ENABLED = "laundry_enabled"
CONF_NUKI_ENABLED = "nuki_enabled"
CONF_LAUNDRY_LEAD_DAYS = "laundry_lead_days"
CONF_LAUNDRY_REMINDER_HOURS = "laundry_reminder_hours"
CONF_LAUNDRY_EMAIL = "laundry_email"
CONF_NUKI_LEAD_DAYS = "nuki_lead_days"
CONF_NUKI_REMINDER_HOURS = "nuki_reminder_hours"
CONF_NUKI_TEST_MODE = "nuki_test_mode"
CONF_NUKI_TEST_EMAIL = "nuki_test_email"
CONF_NOTIFICATION_START_HOUR = "notification_start_hour"
CONF_NOTIFICATION_END_HOUR = "notification_end_hour"

CONF_SMTP_HOST = "smtp_host"
CONF_SMTP_PORT = "smtp_port"
CONF_SMTP_USERNAME = "smtp_username"
CONF_SMTP_PASSWORD = "smtp_password"
CONF_SMTP_SENDER = "smtp_sender"
CONF_SMTP_STARTTLS = "smtp_starttls"
CONF_SMTP_SSL = "smtp_ssl"

DEFAULT_UPDATE_INTERVAL_MINUTES = 240
DEFAULT_HORIZON_DAYS = 45
DEFAULT_LOOKBACK_DAYS = 2
DEFAULT_SHOW_GUEST_NAMES = True
DEFAULT_CONFIG_DIRECTORY = "smoobu_workflow"

DEFAULT_NOTIFY_SERVICE = ""
DEFAULT_LAUNDRY_ENABLED = False
DEFAULT_NUKI_ENABLED = False
DEFAULT_LAUNDRY_LEAD_DAYS = 5
DEFAULT_LAUNDRY_REMINDER_HOURS = 4
DEFAULT_LAUNDRY_EMAIL = ""
DEFAULT_NUKI_LEAD_DAYS = 6
DEFAULT_NUKI_REMINDER_HOURS = 4
DEFAULT_NUKI_TEST_MODE = True
DEFAULT_NUKI_TEST_EMAIL = ""
DEFAULT_NOTIFICATION_START_HOUR = 7
DEFAULT_NOTIFICATION_END_HOUR = 23

DEFAULT_SMTP_HOST = ""
DEFAULT_SMTP_PORT = 587
DEFAULT_SMTP_USERNAME = ""
DEFAULT_SMTP_PASSWORD = ""
DEFAULT_SMTP_SENDER = ""
DEFAULT_SMTP_STARTTLS = True
DEFAULT_SMTP_SSL = False

VALID_BOOKING_TYPES = {"reservation", "modification of booking"}

SERVICE_GET_BOOKINGS = "get_bookings"
SERVICE_GENERATE_STATISTICS = "generate_it_nrw_statistics"
SERVICE_GENERATE_SELECTED_STATISTICS = "generate_selected_it_nrw_statistics"
SERVICE_PREVIEW_TEMPLATE = "preview_template"
SERVICE_CALCULATE_LAUNDRY = "calculate_laundry"
SERVICE_RELOAD_FILES = "reload_files"
SERVICE_PROCESS_WORKFLOWS = "process_workflows"
SERVICE_LAUNDRY_COMMAND = "laundry_command"
SERVICE_NUKI_COMMAND = "nuki_command"
SERVICE_SEND_TEST_EMAIL = "send_test_email"
SERVICE_SEND_TEST_NOTIFICATION = "send_test_notification"
SERVICE_RESET_LAUNDRY = "reset_laundry"
SERVICE_RESET_NUKI = "reset_nuki"
SERVICE_RESET_ALL_WORKFLOW_STATE = "reset_all_workflow_state"

SIGNAL_STATISTICS_UPDATED = f"{DOMAIN}_statistics_updated"
SIGNAL_STATISTICS_SELECTION_UPDATED = f"{DOMAIN}_statistics_selection_updated"
SIGNAL_WORKFLOW_UPDATED = f"{DOMAIN}_workflow_updated"

EVENT_NOTIFICATION_ACTION = "mobile_app_notification_action"
LAUNDRY_ACTION_PREFIX = "SMOOBU_LAUNDRY"
NUKI_ACTION_PREFIX = "SMOOBU_NUKI"

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.state"
