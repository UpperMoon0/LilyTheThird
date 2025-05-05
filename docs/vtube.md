# VTube Studio Integration Documentation

This document outlines the features and implementation of the VTube Studio (VTS) integration within the application, allowing users to connect to VTS, manage custom animations (parameter presets), and trigger them.

## Core Components

The VTube integration relies on several Kivy widgets and their corresponding Python logic:

*   **`views/vtube_tab.py` & `views/vtubetab.kv`**:
    *   The main container widget (`VTubeTab`) for the VTube feature tab.
    *   Manages the connection state and interaction with the `pyvts` library.
    *   Handles authentication, parameter fetching, and acts as the central coordinator for events from child components.
    *   Defines the overall layout of the tab, including the connection status, animation list, and editor panel areas.
*   **`views/components/vts_animation_list.py` & `views/components/vtsanimationlist.kv`**:
    *   The `VTSAnimationList` widget displays saved animations loaded from JSON files.
    *   Provides UI elements for triggering, editing, deleting, and adding new animations.
    *   Includes a search bar for filtering the animation list.
    *   Uses `VTSAnimationListItem` to represent each animation in the list.
*   **`views/components/animation_editor_panel.py` & `views/components/animationeditorpanel.kv`**:
    *   The `AnimationEditorPanel` widget provides an inline interface for creating or modifying animations.
    *   It's populated with available VTS parameters and the data of the animation being edited.
    *   Contains input fields for the animation name and the `VTSParamList` for parameter adjustments.
    *   Includes buttons for saving, cancelling, and clipboard operations.
*   **`views/components/vts_param_list.py` & `views/components/vtsparamlist.kv`**:
    *   The `VTSParamList` widget displays a list of VTS parameters within the `AnimationEditorPanel`.
    *   Allows users to adjust parameter values using sliders.
    *   Includes a search bar for filtering parameters.
    *   Uses `VTSParamListItem` to represent each parameter with its name, value, and slider.
*   **`pyvts` library**: The external Python library used for communicating with the VTube Studio API via WebSocket.

## Key Functionalities

### 1. Connection & Setup

*   **Initiation**: User clicks the "Connect" button in the `VTubeTab`.
*   **Process (`VTubeTab._connect_vts`)**:
    *   Attempts WebSocket connection to VTS (default: `127.0.0.1:8001`).
    *   Checks authentication status using `vts.request_authenticate()`.
    *   If not authenticated, requests a new token using `vts.request_authenticate_token()`, prompting the user in VTS.
    *   Polls `vts.request_authenticate()` until success or timeout (30 seconds).
    *   On successful connection and authentication:
        *   Sets `is_connected = True`.
        *   Updates status text and button text.
        *   Asynchronously calls `_fetch_available_parameters`.
*   **Parameter Fetching (`VTubeTab._fetch_available_parameters`)**:
    *   Sends an `InputParameterListRequest` to VTS.
    *   Parses the response to get lists of default and custom parameters.
    *   Stores the combined list of parameter dictionaries (including name, value, min, max) in `VTubeTab.available_parameters`.
*   **Disconnection (`VTubeTab._disconnect_vts`)**:
    *   Closes the WebSocket connection via `vts.close()`.
    *   Resets connection status (`is_connected = False`), button text, and clears `available_parameters`.

### 2. Animation Storage

*   **Location**: Animations are stored as individual JSON files in `%APPDATA%/NsTut/LilyTheThird/vtube/animations`. The application creates this directory if it doesn't exist.
*   **Format**: Each `.json` file contains a dictionary representing one animation:
    ```json
    {
        "name": "Animation Name",
        "parameters": {
            "ParameterName1": 0.75,
            "ParameterName2": -0.5,
            "AnotherParam": 1.0
        }
    }
    ```
    *   `name`: (String) The display name of the animation.
    *   `parameters`: (Dictionary) Maps VTS parameter names (strings) to their target numerical values (floats/integers).

### 3. Animation Loading & Display

*   **Process (`VTSAnimationList.load_animations`)**:
    *   Called on initialization and when a refresh is needed (e.g., after saving/deleting).
    *   Lists all `.json` files in the animations directory.
    *   Reads each file, parses the JSON, and validates the basic structure (`name` and `parameters` keys).
    *   Stores the loaded data (including the filename without extension as `_filename`) in `_all_loaded_animations`.
*   **Display (`VTSAnimationList.update_animations_display`)**:
    *   Clears the existing items in the `animations_container`.
    *   Creates a `VTSAnimationListItem` for each loaded (or filtered) animation.
    *   The `VTSAnimationListItem` (`vtsanimationlist.kv`) shows the animation name on a button, plus "Edit" and "Delete" buttons.
*   **Filtering (`VTSAnimationList.filter_display`, `VTubeTab.filter_animations`)**:
    *   The search bar in `VTubeTab` calls `filter_animations`, which in turn calls `filter_display` on `VTSAnimationList`.
    *   Filters the `_all_loaded_animations` list based on whether the search text is present in the animation name (case-insensitive).
    *   Calls `update_animations_display` with the filtered list.

### 4. Triggering Animations

*   **Action**: User clicks the button displaying the animation name in `VTSAnimationListItem`.
*   **Event Flow**:
    1.  `VTSAnimationListItem.trigger_animation` dispatches `on_trigger_animation` with its `animation_data`.
    2.  `VTSAnimationList` catches and re-dispatches the event.
    3.  `VTubeTab`'s KV binding (`on_trigger_animation: root.trigger_vts_animation(args[1])`) calls `VTubeTab.trigger_vts_animation`.
*   **Execution (`VTubeTab.trigger_vts_animation` -> `VTubeTab.set_parameter_values`)**:
    *   Retrieves the `parameters` dictionary from the animation data.
    *   Converts the `{name: value}` dictionary into the list format required by VTS: `[{"id": name, "value": value}, ...]`.
    *   Calls the async `set_parameter_values` method.
    *   `set_parameter_values` constructs the full `InjectParameterDataRequest` payload with the parameter list and sends it to VTS using `vts.request()`.

### 5. Adding/Editing Animations

*   **Action**: User clicks "Add New Animation" or the "Edit" button on an item.
*   **Event Flow**:
    1.  `VTSAnimationList` or `VTSAnimationListItem` dispatches `on_add_animation` or `on_edit_animation`.
    2.  `VTubeTab` handles these events (`handle_add_new_animation_button`, `handle_edit_animation_selection`).
*   **Editor Activation (`VTubeTab`)**:
    *   Sets `VTubeTab.is_editing = True`, making the `AnimationEditorPanel` visible.
    *   Stores the `animation_data` being edited (if applicable) in `editing_animation_data`.
    *   Calls `AnimationEditorPanel.populate_editor`, passing the `available_vts_params` and the `animation_data` (or `None` if adding).
*   **Editor Population (`AnimationEditorPanel.populate_editor` -> `_populate_fields_internal`)**:
    *   Sets the editor title ("Add" or "Edit").
    *   Sets the `animation_name_input` text.
    *   Calls `VTSParamList.set_parameters`, providing the list of all available VTS parameters. For each parameter, it uses the value from the `animation_data` being edited, or the default value from VTS if adding.
*   **Parameter Adjustment (`VTSParamList`, `VTSParamListItem`)**:
    *   The `VTSParamList` displays each parameter using `VTSParamListItem`.
    *   The `VTSParamListItem` shows the name, current value, and a slider.
    *   Moving a slider updates the `param_value` in the item and calls `VTSParamList.update_param_cache` to store the current value.
    *   A search bar allows filtering the parameters displayed in the editor list.
*   **Saving (`AnimationEditorPanel.trigger_save` -> `VTubeTab.save_edited_animation`)**:
    1.  User clicks "Save".
    2.  `AnimationEditorPanel.trigger_save` validates the name, gets the current parameter values dictionary from `VTSParamList.get_current_parameter_values()`, includes the original `_filename` if editing, and dispatches `on_save_animation` with this data.
    3.  `VTubeTab.save_edited_animation` receives the data.
    4.  Determines the target filename (using `_filename` if editing, generating from the name if adding).
    5.  Writes the data (name and parameters dictionary) to the JSON file in the animations directory, overwriting if necessary.
    6.  Calls `_refresh_animation_list` to update the display.
    7.  Calls `cancel_edit` to hide the editor panel.
*   **Cancelling (`AnimationEditorPanel.trigger_cancel` -> `VTubeTab.cancel_edit`)**:
    1.  User clicks "Cancel".
    2.  `AnimationEditorPanel.trigger_cancel` dispatches `on_cancel_edit`.
    3.  `VTubeTab.cancel_edit` sets `is_editing = False`, hiding the panel.

### 6. Deleting Animations

*   **Action**: User clicks the "Delete" button on a `VTSAnimationListItem`.
*   **Event Flow**:
    1.  `VTSAnimationListItem.delete_animation` dispatches `on_delete_animation`.
    2.  `VTubeTab` handles this (`handle_delete_animation`).
*   **Process (`VTubeTab.handle_delete_animation` -> `_perform_delete`)**:
    *   Shows a confirmation popup.
    *   If confirmed, `_perform_delete` gets the `_filename` from the animation data.
    *   Constructs the full path to the JSON file.
    *   Deletes the file using `os.remove()`.
    *   Refreshes the `VTSAnimationList`.
    *   If the deleted animation was being edited, it also cancels the edit.

### 7. Clipboard Functions

*   **Copy Parameter Names (`AnimationEditorPanel.trigger_copy_names` -> `VTubeTab.copy_param_names_to_clipboard`)**:
    *   Gets the list of available parameter names from `VTubeTab.available_parameters`.
    *   Formats this list as a JSON string.
    *   Copies the JSON string to the system clipboard using `kivy.core.clipboard.Clipboard`.
*   **Set from JSON (`AnimationEditorPanel.trigger_set_from_clipboard` -> `VTubeTab.set_animation_from_clipboard`)**:
    *   Pastes content from the clipboard.
    *   Attempts to parse it as JSON, expecting the format `{"name": "...", "parameters": {"Param1": val1, ...}}`.
    *   Validates the structure.
    *   Updates the `animation_name_input` in the editor panel.
    *   Iterates through the parameters currently displayed in the editor's `VTSParamList` and updates their values (and sliders) based on the data from the clipboard JSON.
