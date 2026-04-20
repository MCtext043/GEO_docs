# PyInstaller: pyinstaller build_normdocs_exe.spec
# Результат: dist/NormDocsLangflow/NormDocsLangflow.exe
#
# Windows: если PermissionError при очистке dist\NormDocsLangflow — процесс
# NormDocsLangflow.exe ещё запущен, или папку держит Проводник / антивирус.
# Закройте exe и окно с этой папкой, либо запустите build_normdocs.bat

from pathlib import Path

block_cipher = None
root = Path(SPECPATH).resolve()

a = Analysis(
    [str(root / "run_desktop.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "dotenv",
        "normdocs_app.services.flow_resolve",
        "fitz",
        "docx",
        "rarfile",
        "tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.messagebox",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # venv с Langflow тянет сотни пакетов; приложению они не нужны
        "torch",
        "torchvision",
        "torchaudio",
        "tensorflow",
        "pandas",
        "scipy",
        "sklearn",
        "IPython",
        "jupyter",
        "notebook",
        "langflow",
        "langflow_base",
        "lfx",
        "chromadb",
        "sqlalchemy",
        "pydantic_ai",
        "litellm",
        "openai",
        "anthropic",
        "transformers",
        "onnxruntime",
        "pytest",
        "black",
        "botocore",
        "boto3",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NormDocsLangflow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="NormDocsLangflow",
)
