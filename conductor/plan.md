# Plan: Simplified UI, CLI, & Atlas Charts Migration

## Objective

Modernize and simplify the Web Contractor tool by offloading complex analytics to MongoDB Atlas Charts, replacing the resource-heavy Streamlit UI with a lightweight Tkinter dashboard, and formalizing core tasks into CLI scripts.

## Key Changes

- **Database Reliability**: Implement a mandatory pre-flight connection check in `main.py` and a persistent health indicator in the UI.
- **Analytics Migration (Atlas Charts)**: Move all lead, campaign, and query visualizations to MongoDB Atlas Charts dashboards.
- **Simplified UI (Tkinter)**: Develop a single-window Tkinter application for triggering long-running tasks.
- **CLI Tooling**: Create standalone Python scripts in `scripts/` for management tasks.
- **Surgical Cleanup**: Remove all code related to the old UI, including Streamlit pages, visualization logic, and any logging specifically tied to the old analytics system.

## Implementation Steps

### Phase 1: Database Readiness & Infrastructure

1. **DB Pre-flight Check**: Update `main.py` to verify MongoDB connectivity before launching any interface.
2. **Bucket Manager CLI (`scripts/manage_buckets.py`)**:
    - Implement an interactive CLI wizard using `src/discovery/engine.py:BucketGenerator`.
3. **Logging Refactor**:
    - Simplify `src/infra/logging.py`.
    - **Remove visualization-specific logging** that is no longer needed in the new architecture.
    - Implement a thread-safe log streamer for the Tkinter GUI.

### Phase 2: Simplified UI (Tkinter)

1. **Main View (`src/gui_new.py`)**:
    - Dashboard with DB status indicator, quick stats, and action buttons.
    - Scrolling console for real-time engine logs.
2. **Atlas Integration**:
    - "View Analytics (Atlas)" button and a setup guide in `docs/atlas-charts-setup.md`.

### Phase 3: Surgical Cleanup

1. **Remove Old UI Code**: Delete `src/pages/`, `src/app.py`, and `src/ui/visualizations.py`.
2. **Remove Redundant Utilities**: Clean `src/ui/utils.py` of any Streamlit-specific helper functions.
3. **Dep-Cleanup**: Remove `streamlit` and `plotly` from `pyproject.toml`.

## Verification & Testing

1. **DB Failure Test**: Verify `main.py` exits gracefully or shows an error if MongoDB is down.
2. **CLI & Threading Test**: Verify bucket management and background task execution in the GUI.
3. **Atlas Shortcut Test**: Verify the Analytics button opens the dashboard.
4. **Final Cleanup Test**: Ensure the app runs without any `streamlit` or `plotly` modules present.
