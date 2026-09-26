; Phase 16: custom install/uninstall steps for the bundled backend + Postgres, hooked
; into Tauri's own NSIS installer via tauri.conf.json's bundle.windows.nsis.installerHooks.
; Not compiled/run in this session (see docs/ROADMAP.md's Phase 16 entry for why an
; actual installer build+install was deliberately deferred pending your go-ahead) -
; reviewed carefully against documented NSIS macro syntax, but genuinely unverified until
; a real `npm run tauri build` compiles it.
;
; Delegates almost everything to PowerShell scripts (packaging/*.ps1) rather than writing
; the logic directly in NSIS script - those are independently testable and, in this
; phase, actually were tested; this file's job is just to invoke them with the right
; paths at the right install/uninstall step.

!macro NSIS_HOOK_POSTINSTALL
  DetailPrint "Vero.ai: generating first-run configuration..."
  nsExec::ExecToLog 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\packaging\generate_first_run_config.ps1"'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_OK|MB_ICONSTOP "Vero.ai setup failed while generating its configuration. Installation cannot continue."
    Abort
  ${EndIf}

  DetailPrint "Vero.ai: initializing the local database (this can take a minute)..."
  nsExec::ExecToLog 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\packaging\init_postgres.ps1" -PostgresBinDir "$INSTDIR\postgres\bin"'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_OK|MB_ICONSTOP "Vero.ai setup failed while initializing the local database. Installation cannot continue."
    Abort
  ${EndIf}

  DetailPrint "Vero.ai: registering background services..."
  nsExec::ExecToLog 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\packaging\register_services.ps1" -NssmExe "$INSTDIR\nssm\nssm.exe" -PostgresBinDir "$INSTDIR\postgres\bin" -PythonExe "$INSTDIR\pyruntime\Scripts\python.exe" -BackendDir "$INSTDIR\backend"'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_OK|MB_ICONSTOP "Vero.ai setup failed while registering its background services. Installation cannot continue."
    Abort
  ${EndIf}
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  DetailPrint "Vero.ai: stopping background services..."
  ; Uses $INSTDIR here too - it still points at the install directory during uninstall,
  ; before any files are removed (this hook runs pre-removal, per Tauri's own NSIS hook
  ; ordering: PREUNINSTALL before files/registry/shortcuts are touched).
  nsExec::ExecToLog 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\packaging\unregister_services.ps1" -NssmExe "$INSTDIR\nssm\nssm.exe"'
  Pop $0
  ; Deliberately does not Abort on a non-zero exit here - a failed service removal
  ; should not block the rest of the uninstall from proceeding.
!macroend
