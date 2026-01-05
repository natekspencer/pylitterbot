"""Textual-based debug UI for Litter-Robot."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

TOKEN_PATH = Path("/tmp/litter_robot.token")

# Check for optional dependencies before importing
try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical
    from textual.logging import TextualHandler
    from textual.screen import ModalScreen
    from textual.widgets import (
        Button,
        DataTable,
        Footer,
        Header,
        Input,
        Label,
        ListItem,
        ListView,
        Static,
        TabbedContent,
        TabPane,
    )
except ImportError:
    print("Debug UI requires optional dependencies.")
    print("Install them with:")
    print()
    print("  poetry install --with debug")
    print()
    print("Or with pip:")
    print()
    print("  pip install textual")
    print()
    sys.exit(1)

from pylitterbot import Account
from pylitterbot.robot.litterrobot4 import LitterRobot4

# Store stderr handler globally so we can switch to it on exit
_STDERR_HANDLER: logging.Handler | None = None
_TEXTUAL_HANDLER: logging.Handler | None = None


def _configure_logging() -> None:
    """Configure logging to use Textual's handler for pylitterbot loggers.

    Set DEBUG_STDERR=1 to log to stderr instead of Textual console.
    """
    global _STDERR_HANDLER, _TEXTUAL_HANDLER

    log_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )

    # Create a stderr handler
    _STDERR_HANDLER = logging.StreamHandler(sys.stderr)
    _STDERR_HANDLER.setFormatter(log_format)
    _STDERR_HANDLER.setLevel(logging.DEBUG)

    # Use stderr if DEBUG_STDERR is set, otherwise use Textual handler
    use_stderr = os.environ.get("DEBUG_STDERR", "").lower() in ("1", "true", "yes")

    if use_stderr:
        handler: logging.Handler = _STDERR_HANDLER
    else:
        # Create the Textual handler
        _TEXTUAL_HANDLER = TextualHandler()
        _TEXTUAL_HANDLER.setFormatter(log_format)
        _TEXTUAL_HANDLER.setLevel(logging.DEBUG)
        handler = _TEXTUAL_HANDLER

    # Configure pylitterbot logger
    # (don't use root logger to avoid noise from other libs)
    pylitterbot_logger = logging.getLogger("pylitterbot")
    pylitterbot_logger.setLevel(logging.DEBUG)
    pylitterbot_logger.addHandler(handler)

    # Also configure this module's logger
    debug_ui_logger = logging.getLogger(__name__)
    debug_ui_logger.setLevel(logging.DEBUG)
    debug_ui_logger.addHandler(handler)


def _switch_to_stderr_logging() -> None:
    """Switch all loggers to stderr handler for shutdown logging."""
    global _TEXTUAL_HANDLER

    pylitterbot_logger = logging.getLogger("pylitterbot")
    debug_ui_logger = logging.getLogger(__name__)

    # Remove Textual handler and add stderr handler
    for logger in [pylitterbot_logger, debug_ui_logger]:
        if _TEXTUAL_HANDLER and _TEXTUAL_HANDLER in logger.handlers:
            logger.removeHandler(_TEXTUAL_HANDLER)
        if _STDERR_HANDLER and _STDERR_HANDLER not in logger.handlers:
            logger.addHandler(_STDERR_HANDLER)


_configure_logging()
_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from pylitterbot.pet import Pet


@dataclass
class WeightAuditEntry:
    """A weight entry with its current pet assignment."""

    timestamp: datetime  # Robot's timestamp (for display)
    weight: float
    assigned_pet_id: str | None
    assigned_pet_name: str | None
    robot_serial: str
    pet_timestamp: datetime | None = None  # Pet's timestamp (for API calls)

    @property
    def timestamp_str(self) -> str:
        """Return the timestamp as a string for display."""
        return self.timestamp.isoformat()

    @property
    def api_timestamp_str(self) -> str:
        """Return the timestamp to use for API calls (pet timestamp if available)."""
        ts = self.pet_timestamp if self.pet_timestamp else self.timestamp
        # API expects UTC without timezone suffix, accurate to the second
        return ts.strftime("%Y-%m-%dT%H:%M:%S")


class LoginScreen(ModalScreen[dict | None]):
    """Login screen for username/password entry."""

    CSS = """
    LoginScreen {
        align: center middle;
    }

    #login-container {
        width: 60;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #login-container Label {
        margin-bottom: 1;
    }

    #login-container Input {
        margin-bottom: 1;
    }

    #button-row {
        margin-top: 1;
        align: center middle;
    }

    #button-row Button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose the login screen."""
        with Vertical(id="login-container"):
            yield Label("Litter-Robot Login")
            yield Label("Username:")
            yield Input(placeholder="email@example.com", id="username")
            yield Label("Password:")
            yield Input(placeholder="password", password=True, id="password")
            with Horizontal(id="button-row"):
                yield Button("Login", variant="primary", id="login-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "login-btn":
            username = self.query_one("#username", Input).value
            password = self.query_one("#password", Input).value
            if username and password:
                self.dismiss({"username": username, "password": password})
        elif event.button.id == "cancel-btn":
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle enter key in input fields."""
        if event.input.id == "username":
            self.query_one("#password", Input).focus()
        elif event.input.id == "password":
            username = self.query_one("#username", Input).value
            password = self.query_one("#password", Input).value
            if username and password:
                self.dismiss({"username": username, "password": password})


class LitterRobotDebugApp(App[None]):
    """Debug UI for Litter-Robot."""

    CSS = """
    #main-container {
        height: 1fr;
    }

    TabbedContent {
        height: 1fr;
    }

    TabPane {
        height: 1fr;
        padding: 0;
    }

    #history-container {
        layout: horizontal;
        height: 1fr;
    }

    #left-panel {
        width: 1fr;
        border: solid $primary;
        padding: 1;
    }

    #right-panel {
        width: 1fr;
        border: solid $primary;
        padding: 1;
    }

    #detail-panel {
        width: 2fr;
        border: solid $primary;
        padding: 1;
    }

    .panel-title {
        text-style: bold;
        margin-bottom: 1;
    }

    #status-bar {
        height: 3;
        border: solid $secondary;
        padding: 0 1;
    }

    ListView {
        height: 1fr;
    }

    DataTable {
        height: 1fr;
    }

    .list-item-selected {
        background: $accent;
    }

    /* Weight Audit tab styles */
    #audit-container {
        layout: horizontal;
        height: 1fr;
    }

    #audit-robot-panel {
        width: 1fr;
        border: solid $primary;
        padding: 1;
    }

    #audit-table-panel {
        width: 3fr;
        border: solid $primary;
        padding: 1;
    }

    #audit-info {
        height: 3;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("l", "login", "Login"),
        Binding("c", "copy_id", "Copy ID", show=True),
    ]

    def __init__(self) -> None:
        """Initialize the app."""
        super().__init__()
        self.account: Account | None = None
        self._selected_robot: LitterRobot4 | None = None
        self._selected_pet: Pet | None = None
        # Weight audit state
        self._audit_robot: LitterRobot4 | None = None
        self._audit_entries: list[WeightAuditEntry] = []
        self._pet_weight_timestamps: dict[str, set[str]] = {}

    def compose(self) -> ComposeResult:
        """Compose the UI."""
        yield Header()
        with Vertical(id="main-container"):
            with TabbedContent():
                with TabPane("History", id="tab-history"):
                    with Horizontal(id="history-container"):
                        with Vertical(id="left-panel"):
                            yield Static("Litter Robots", classes="panel-title")
                            yield ListView(id="robot-list")
                        with Vertical(id="right-panel"):
                            yield Static("Pets", classes="panel-title")
                            yield ListView(id="pet-list")
                        with Vertical(id="detail-panel"):
                            yield Static(
                                "Details", classes="panel-title", id="detail-title"
                            )
                            yield DataTable(id="detail-table")
                with TabPane("Weight Audit", id="tab-weight-audit"):
                    with Horizontal(id="audit-container"):
                        with Vertical(id="audit-robot-panel"):
                            yield Static("Select Robot", classes="panel-title")
                            yield ListView(id="audit-robot-list")
                        with Vertical(id="audit-table-panel"):
                            yield Static(
                                "Weight Entries - Select a robot",
                                classes="panel-title",
                                id="audit-title",
                            )
                            yield Static(
                                "Navigate with arrows, press SPACE to assign",
                                id="audit-info",
                            )
                            yield DataTable(id="audit-table")
        yield Static("Not connected", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Handle mount event."""
        # Configure the history detail table
        table = self.query_one("#detail-table", DataTable)
        table.add_columns("Timestamp", "Value", "Details")
        table.cursor_type = "row"

        # Configure the audit table with cell cursor for selection
        audit_table = self.query_one("#audit-table", DataTable)
        audit_table.cursor_type = "cell"

        # Try to load saved token
        self.run_worker(self._try_load_token())

    async def _try_load_token(self) -> None:
        """Try to load saved refresh token."""
        if TOKEN_PATH.exists():
            try:
                token_data = json.loads(TOKEN_PATH.read_text())
                self._update_status("Connecting with saved token...")
                await self._connect_with_token(token_data)
            except Exception as e:
                self._update_status(f"Token load failed: {e}")
                await self._prompt_login()
        else:
            await self._prompt_login()

    async def _prompt_login(self) -> None:
        """Prompt for login credentials."""
        result = await self.push_screen_wait(LoginScreen())
        if result:
            await self._login(result["username"], result["password"])

    async def _login(self, username: str, password: str) -> None:
        """Login with username and password."""
        self._update_status("Logging in...")
        try:
            self.account = Account(
                token_update_callback=self._save_token,
            )
            await self.account.connect(
                username=username,
                password=password,
                load_robots=True,
                load_pets=True,
            )
            self._save_token(self.account.session.tokens)
            self._update_status(
                f"Connected as {username} - "
                f"{len(self.account.robots)} robots, {len(self.account.pets)} pets"
            )
            await self._populate_lists()
        except Exception as e:
            self._update_status(f"Login failed: {e}")

    async def _connect_with_token(self, token_data: dict) -> None:
        """Connect using saved token."""
        try:
            self.account = Account(
                token=token_data,
                token_update_callback=self._save_token,
            )
            await self.account.connect(
                load_robots=True,
                load_pets=True,
            )
            self._update_status(
                f"Connected - "
                f"{len(self.account.robots)} robots, {len(self.account.pets)} pets"
            )
            await self._populate_lists()
        except Exception as e:
            self._update_status(f"Token auth failed: {e}")
            # Delete invalid token
            TOKEN_PATH.unlink(missing_ok=True)
            await self._prompt_login()

    def _save_token(self, tokens: dict | None) -> None:
        """Save tokens to disk."""
        if tokens:
            TOKEN_PATH.write_text(json.dumps(tokens))
            TOKEN_PATH.chmod(0o600)

    def _update_status(self, message: str) -> None:
        """Update the status bar."""
        self.query_one("#status-bar", Static).update(message)

    async def _populate_lists(self) -> None:
        """Populate robot and pet lists."""
        if not self.account:
            return

        # Populate robots in History tab
        robot_list = self.query_one("#robot-list", ListView)
        await robot_list.clear()
        for robot in self.account.robots:
            item = ListItem(
                Label(f"{robot.name} ({robot.serial})"),
                id=f"robot-{robot.serial}",
            )
            item.data = robot  # noqa: attr-defined
            await robot_list.append(item)

        # Populate pets in History tab
        pet_list = self.query_one("#pet-list", ListView)
        await pet_list.clear()
        for pet in self.account.pets:
            item = ListItem(
                Label(f"{pet.name} ({pet.id[:8]}...)"),
                id=f"pet-{pet.id}",
            )
            item.data = pet  # noqa: attr-defined
            await pet_list.append(item)

        # Populate robots in Weight Audit tab
        audit_robot_list = self.query_one("#audit-robot-list", ListView)
        await audit_robot_list.clear()
        for robot in self.account.robots:
            if isinstance(robot, LitterRobot4):
                item = ListItem(
                    Label(f"{robot.name}"),
                    id=f"audit-robot-{robot.serial}",
                )
                item.data = robot  # noqa: attr-defined
                await audit_robot_list.append(item)

        # Setup audit table columns based on pets
        await self._setup_audit_table_columns()

    async def _setup_audit_table_columns(self) -> None:
        """Set up the audit table columns based on available pets."""
        if not self.account:
            return

        audit_table = self.query_one("#audit-table", DataTable)
        audit_table.clear(columns=True)

        # Add columns: Timestamp, Weight, then each pet name, then Unassigned
        audit_table.add_column("Timestamp", key="timestamp")
        audit_table.add_column("Weight", key="weight")
        for pet in self.account.pets:
            audit_table.add_column(pet.name, key=f"pet-{pet.id}")
        audit_table.add_column("Unassigned", key="unassigned")

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle list item selection."""
        item = event.item
        if not hasattr(item, "data"):
            return

        data = item.data  # noqa: attr-defined
        list_id = event.list_view.id

        # Handle History tab selections
        if list_id in ("robot-list", "pet-list"):
            if isinstance(data, LitterRobot4):
                self._selected_robot = data
                self._selected_pet = None
                await self._show_robot_history(data)
            elif hasattr(data, "weight_history"):
                # It's a Pet
                self._selected_pet = data
                self._selected_robot = None
                await self._show_pet_history(data)

        # Handle Weight Audit tab robot selection
        elif list_id == "audit-robot-list":
            if isinstance(data, LitterRobot4):
                self._audit_robot = data
                await self._load_weight_audit(data)

    async def _show_robot_history(self, robot: LitterRobot4) -> None:
        """Show activity history for a robot."""
        self.query_one("#detail-title", Static).update(
            f"History: {robot.name} ({robot.serial})"
        )

        table = self.query_one("#detail-table", DataTable)
        table.clear()

        self._update_status(f"Loading history for {robot.name}...")

        try:
            activities = await robot.get_activity_history(limit=100)
            for activity in activities:
                timestamp = (
                    activity.timestamp.isoformat()
                    if hasattr(activity.timestamp, "isoformat")
                    else str(activity.timestamp)
                )
                action = (
                    activity.action.text
                    if hasattr(activity.action, "text")
                    else str(activity.action)
                )
                table.add_row(timestamp, action, "")

            self._update_status(f"Loaded {len(activities)} activities for {robot.name}")
        except Exception as e:
            self._update_status(f"Failed to load history: {e}")

    async def _show_pet_history(self, pet: Pet) -> None:
        """Show weight history for a pet."""
        self.query_one("#detail-title", Static).update(
            f"Weight History: {pet.name} ({pet.id[:8]}...)"
        )

        table = self.query_one("#detail-table", DataTable)
        table.clear()

        self._update_status(f"Loading weight history for {pet.name}...")

        try:
            weight_history = await pet.fetch_weight_history(limit=100)
            for entry in weight_history:
                timestamp = entry.timestamp.isoformat()
                weight = f"{entry.weight} lbs"
                table.add_row(timestamp, weight, "")

            self._update_status(
                f"Loaded {len(weight_history)} weight entries for {pet.name}"
            )
        except Exception as e:
            self._update_status(f"Failed to load weight history: {e}")

    async def _load_weight_audit(self, robot: LitterRobot4) -> None:
        """Load weight audit data for a robot."""
        if not self.account:
            return

        self.query_one("#audit-title", Static).update(f"Weight Entries: {robot.name}")

        audit_table = self.query_one("#audit-table", DataTable)
        audit_table.clear()

        self._update_status(f"Loading weight audit for {robot.name}...")

        try:
            # Use get_weight_history which returns pet assignment info directly
            # This query uses the weightHistory GraphQL endpoint with raw id_token
            weight_history = await robot.get_weight_history(days=7)
            _LOGGER.debug(
                "Found %d weight entries from weightHistory", len(weight_history)
            )

            # Build pet ID -> name lookup
            pet_name_map: dict[str, str] = {
                pet.id: pet.name for pet in self.account.pets
            }

            # Build audit entries directly from weight history
            self._audit_entries = []
            for entry in weight_history:
                assigned_pet_name = (
                    pet_name_map.get(entry.pet_id) if entry.pet_id else None
                )
                _LOGGER.debug(
                    "Entry %s: weight=%.2f, pet_id=%s, pet_name=%s",
                    entry.timestamp.isoformat(),
                    entry.weight,
                    entry.pet_id,
                    assigned_pet_name,
                )

                audit_entry = WeightAuditEntry(
                    timestamp=entry.timestamp,
                    weight=entry.weight,
                    assigned_pet_id=entry.pet_id,
                    assigned_pet_name=assigned_pet_name,
                    robot_serial=robot.serial,
                    pet_timestamp=entry.timestamp,  # weightHistory timestamp IS the API timestamp
                )
                self._audit_entries.append(audit_entry)

            # Sort by timestamp descending (most recent first)
            self._audit_entries.sort(key=lambda e: e.timestamp, reverse=True)

            # Populate the table
            for audit_entry in self._audit_entries:
                row_data: list[str] = [
                    audit_entry.timestamp_str,
                    f"{audit_entry.weight:.2f} lbs",
                ]

                # Add a marker for each pet column and unassigned
                for pet in self.account.pets:
                    if audit_entry.assigned_pet_id == pet.id:
                        row_data.append("[X]")
                    else:
                        row_data.append("[ ]")

                # Unassigned column
                if audit_entry.assigned_pet_id is None:
                    row_data.append("[X]")
                else:
                    row_data.append("[ ]")

                audit_table.add_row(*row_data, key=audit_entry.timestamp_str)

            self._update_status(
                f"Loaded {len(self._audit_entries)} weight entries for {robot.name}"
            )

        except Exception as e:
            _LOGGER.exception("Failed to load weight audit: %s", e)
            self._update_status(f"Failed to load weight audit: {e}")

    def _get_pet_id_for_column(self, column_index: int) -> str | None:
        """Get the pet ID for a given column index in the audit table.

        Columns are: Timestamp, Weight, Pet1, Pet2, ..., Unassigned
        So pet columns start at index 2.
        """
        if not self.account:
            return None

        pet_column_start = 2
        pet_count = len(self.account.pets)

        if column_index < pet_column_start:
            # Timestamp or Weight column - not assignable
            return "__INVALID__"
        elif column_index < pet_column_start + pet_count:
            # Pet column
            pet_index = column_index - pet_column_start
            return self.account.pets[pet_index].id
        elif column_index == pet_column_start + pet_count:
            # Unassigned column
            return None
        else:
            return "__INVALID__"

    def on_key(self, event: Any) -> None:
        """Handle key presses."""
        # Only handle space key on audit table
        if event.key != "space":
            return

        audit_table = self.query_one("#audit-table", DataTable)
        if not audit_table.has_focus:
            return

        if not self.account or not self._audit_robot:
            return

        # Get current cursor position
        cursor_row = audit_table.cursor_row
        cursor_column = audit_table.cursor_column

        if cursor_row < 0 or cursor_row >= len(self._audit_entries):
            return

        # Get the entry for this row
        entry = self._audit_entries[cursor_row]

        # Get the pet ID for this column
        new_pet_id = self._get_pet_id_for_column(cursor_column)

        if new_pet_id == "__INVALID__":
            self._update_status("Select a pet column or Unassigned to reassign")
            return

        # Run reassignment in a worker
        self.run_worker(self._reassign_weight_entry(entry, new_pet_id))

    async def _reassign_weight_entry(
        self, entry: WeightAuditEntry, new_pet_id: str | None
    ) -> None:
        """Reassign a weight entry to a different pet."""
        if not self.account or not self._audit_robot:
            return

        # Skip if no change
        if entry.assigned_pet_id == new_pet_id:
            self._update_status("No change - pet assignment is the same")
            return

        self._update_status(
            f"Reassigning {entry.timestamp_str} from "
            f"{entry.assigned_pet_name or 'Unassigned'} to "
            f"{self._get_pet_name(new_pet_id) or 'Unassigned'}..."
        )

        _LOGGER.debug(
            "Reassigning with API timestamp: %s (pet_ts: %s)",
            entry.api_timestamp_str,
            entry.pet_timestamp.isoformat() if entry.pet_timestamp else "none",
        )

        try:
            success = await self._audit_robot.reassign_visit(
                visit_timestamp=entry.api_timestamp_str,
                from_pet_id=entry.assigned_pet_id,
                to_pet_id=new_pet_id,
            )

            if success:
                self._update_status(
                    f"Successfully reassigned to "
                    f"{self._get_pet_name(new_pet_id) or 'Unassigned'}"
                )
                # Reload the audit data
                await self._load_weight_audit(self._audit_robot)
            else:
                self._update_status("Reassignment failed - API returned failure")

        except Exception as e:
            self._update_status(f"Reassignment failed: {e}")

    def _get_pet_name(self, pet_id: str | None) -> str | None:
        """Get pet name by ID."""
        if not pet_id or not self.account:
            return None
        for pet in self.account.pets:
            if pet.id == pet_id:
                return pet.name
        return None

    async def action_refresh(self) -> None:
        """Refresh data."""
        if not self.account:
            return

        self._update_status("Refreshing...")
        try:
            await self.account.refresh_robots()
            await self.account.load_pets()
            await self._populate_lists()

            # Refresh current detail view in History tab
            if self._selected_robot:
                await self._show_robot_history(self._selected_robot)
            elif self._selected_pet:
                await self._show_pet_history(self._selected_pet)

            # Refresh Weight Audit tab if a robot is selected
            if self._audit_robot:
                await self._load_weight_audit(self._audit_robot)

            self._update_status("Refreshed")
        except Exception as e:
            self._update_status(f"Refresh failed: {e}")

    async def action_login(self) -> None:
        """Trigger login."""
        await self._disconnect_account()
        await self._prompt_login()

    def action_copy_id(self) -> None:
        """Copy the selected pet/robot ID to clipboard."""
        if self._selected_pet:
            self.copy_to_clipboard(self._selected_pet.id)
            self._update_status(f"Copied pet ID: {self._selected_pet.id}")
        elif self._selected_robot:
            self.copy_to_clipboard(self._selected_robot.serial)
            self._update_status(f"Copied robot serial: {self._selected_robot.serial}")
        else:
            self._update_status("No pet or robot selected")

    async def action_quit(self) -> None:
        """Quit the app."""
        self.exit()

    async def _disconnect_account(self) -> None:
        """Disconnect the account if connected."""
        if self.account:
            _LOGGER.debug("Disconnecting account...")
            try:
                await self.account.disconnect()
                _LOGGER.debug("Account disconnected")
            except Exception as e:
                _LOGGER.warning("Error disconnecting account: %s", e)
            finally:
                self.account = None


def main() -> None:
    """Run the debug UI."""
    app = LitterRobotDebugApp()
    try:
        app.run()
    except asyncio.CancelledError:
        pass  # Normal exit
    finally:
        # Switch to stderr logging so shutdown logs are visible
        _switch_to_stderr_logging()
        _LOGGER.debug("App exited, cleaning up...")

        # Run cleanup in a new event loop if account still connected
        if app.account:
            _LOGGER.debug("Running async cleanup...")
            try:
                asyncio.run(app._disconnect_account())
            except Exception as e:
                _LOGGER.warning("Cleanup error: %s", e)

        _LOGGER.debug("Shutdown complete")


if __name__ == "__main__":
    main()
