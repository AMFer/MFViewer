# VSCode Configuration for MFViewer

This folder contains VSCode workspace settings for the MFViewer project.

## Automatic Virtual Environment Activation

The terminal is configured to **automatically activate the Python virtual environment** when you open a new terminal in VSCode.

### Terminal Profiles Available:

1. **Command Prompt** (Default)
   - Automatically activates `venv` using `activate.bat`
   - Best compatibility, no execution policy issues

2. **PowerShell (venv)**
   - Activates `venv` using PowerShell with bypassed execution policy
   - Use if you prefer PowerShell

3. **Git Bash**
   - Standard Git Bash terminal (manual venv activation required)

### How to Use:

1. **Open a new terminal**: Press `` Ctrl+` `` or `Terminal > New Terminal`
   - The venv should activate automatically (you'll see `(venv)` in the prompt)

2. **Switch terminal profiles**: Click the `+` dropdown in the terminal panel

3. **Run MFViewer**: Just type `python run.py` (venv is already active)

### If Auto-Activation Doesn't Work:

**Option 1: Reload VSCode Window**
- Press `Ctrl+Shift+P` > Type "Reload Window" > Press Enter

**Option 2: Manual Activation**
```cmd
venv\Scripts\activate
```

**Option 3: Use the Task**
- Press `Ctrl+Shift+P` > Type "Tasks: Run Task" > Select "Activate venv"

### Python Interpreter

The workspace is configured to use: `${workspaceFolder}/venv/Scripts/python.exe`

To verify:
- Press `Ctrl+Shift+P`
- Type "Python: Select Interpreter"
- Ensure the venv interpreter is selected
