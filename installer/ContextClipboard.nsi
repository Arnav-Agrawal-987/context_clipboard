; Context Clipboard NSIS Installer Script
; Packages the PyInstaller --onedir output into a per-user Windows installer.

!include "MUI2.nsh"
!include "LogicLib.nsh"

!define APPNAME "Context Clipboard"
!define COMPANYNAME "ContextClipboard"
!define DESCRIPTION "Clipboard manager with context awareness"
!define VERSIONMAJOR 1
!define VERSIONMINOR 0
!define VERSIONBUILD 0
!define HELPURL "https://github.com/Arnav-Agrawal-987/context_clipboard/issues"
!define UPDATEURL "https://github.com/Arnav-Agrawal-987/context_clipboard/releases"
!define ABOUTURL "https://github.com/Arnav-Agrawal-987/context_clipboard"

RequestExecutionLevel user
SetCompressor lzma

Name "${APPNAME}"
OutFile "ContextClipboard-Setup-v${VERSIONMAJOR}.${VERSIONMINOR}.${VERSIONBUILD}.exe"
InstallDir "$LOCALAPPDATA\Programs\${APPNAME}"
ShowInstDetails show

;--------------------------------
; MUI Settings
;--------------------------------
!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}\Contrib\Graphics\Icons\modern-install.ico"
!define MUI_UNICON "${NSISDIR}\Contrib\Graphics\Icons\modern-uninstall.ico"

;--------------------------------
; Welcome Page
;--------------------------------
!define MUI_WELCOMEPAGE_TITLE "Welcome to the Context Clipboard Setup Wizard"
!define MUI_WELCOMEPAGE_TEXT "This wizard will guide you through the installation of Context Clipboard, a lightweight Windows clipboard manager that remembers what you copied and lets you search your full copy history via a global hotkey.$\r$\n$\r$\nClick Next to continue."
!insertmacro MUI_PAGE_WELCOME

;--------------------------------
; License Page (MIT License)
;--------------------------------
!insertmacro MUI_PAGE_LICENSE "..\LICENSE"

;--------------------------------
; Components Page
;--------------------------------
!insertmacro MUI_PAGE_COMPONENTS

;--------------------------------
; Directory Page
;--------------------------------
!insertmacro MUI_PAGE_DIRECTORY

;--------------------------------
; Instfiles Page
;--------------------------------
!insertmacro MUI_PAGE_INSTFILES

;--------------------------------
; Finish Page
;--------------------------------
!define MUI_FINISHPAGE_TITLE "Context Clipboard has been installed successfully"
!define MUI_FINISHPAGE_TEXT "Click Finish to close Setup."
!define MUI_FINISHPAGE_RUN "$INSTDIR\ContextClipboard.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Launch Context Clipboard"
!define MUI_FINISHPAGE_LINK "Visit the GitHub repository"
!define MUI_FINISHPAGE_LINK_LOCATION "${ABOUTURL}"
!insertmacro MUI_PAGE_FINISH

;--------------------------------
; Uninstaller Pages
;--------------------------------
!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

;--------------------------------
; Languages
;--------------------------------
!insertmacro MUI_LANGUAGE "English"

;--------------------------------
; Functions
;--------------------------------

Function KillRunningApp
    DetailPrint "Checking for running Context Clipboard..."
    nsExec::ExecToStack '"taskkill" /F /IM ContextClipboard.exe /T'
    Pop $R0
    ${If} $R0 == "0"
        DetailPrint "Closed running Context Clipboard."
        Sleep 1000
    ${Else}
        DetailPrint "No running instance found (or already closed)."
    ${EndIf}
FunctionEnd

; Check if auto-start is enabled in registry
Function IsAutoStartEnabled
    ReadRegStr $R0 HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${APPNAME}"
    StrCmp $R0 "" 0 +3
        Push "0"
        Return
    Push "1"
    Return
FunctionEnd

;--------------------------------
; Sections
;--------------------------------
Section "!Context Clipboard" SecMain
    SectionIn RO

    ; Kill any running instance before installing
    Call KillRunningApp

    SetOutPath "$INSTDIR"

    ; Copy entire PyInstaller --onedir output
    File /r "..\dist\ContextClipboard\*.*"

    ; Write uninstaller
    WriteUninstaller "$INSTDIR\uninstall.exe"

    ; Start Menu shortcut
    CreateDirectory "$SMPROGRAMS\${APPNAME}"
    CreateShortcut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\ContextClipboard.exe"
    CreateShortcut "$SMPROGRAMS\${APPNAME}\Uninstall.lnk" "$INSTDIR\uninstall.exe"

    ; Registry: uninstall info (Add/Remove Programs)
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayName" "${APPNAME}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "UninstallString" "$\"$INSTDIR\uninstall.exe$\""
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayIcon" "$INSTDIR\ContextClipboard.exe"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "Publisher" "${COMPANYNAME}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "HelpLink" "${HELPURL}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "URLUpdateInfo" "${UPDATEURL}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "URLInfoAbout" "${ABOUTURL}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "DisplayVersion" "${VERSIONMAJOR}.${VERSIONMINOR}.${VERSIONBUILD}"
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "NoModify" 1
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}" "NoRepair" 1
SectionEnd

Section "Desktop Shortcut" SecDesktop
    CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\ContextClipboard.exe"
SectionEnd

Section /o "Auto-start on boot" SecAutoStart
    ; Add to HKCU Run key
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${APPNAME}" "$\"$INSTDIR\ContextClipboard.exe$\""
SectionEnd

;--------------------------------
; .onInit — sync auto-start checkbox with existing registry state
;--------------------------------
Function .onInit
    Call IsAutoStartEnabled
    Pop $R0
    ${If} $R0 == "1"
        ; Auto-start is already enabled, check the box by default
        SectionSetFlags ${SecAutoStart} ${SF_SELECTED}
    ${Else}
        ; Auto-start not enabled, uncheck by default
        SectionSetFlags ${SecAutoStart} 0
    ${EndIf}
FunctionEnd

;--------------------------------
; Descriptions
;--------------------------------
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} "Core application files. Required."
    !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "Create a shortcut on the Desktop."
    !insertmacro MUI_DESCRIPTION_TEXT ${SecAutoStart} "Start Context Clipboard automatically when Windows boots."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

;--------------------------------
; Uninstaller Section
;--------------------------------
Section "Uninstall"
    ; Kill running process first
    Call un.KillRunningApp

    ; Remove installed files
    RMDir /r "$INSTDIR"

    ; Remove shortcuts
    Delete "$DESKTOP\${APPNAME}.lnk"
    RMDir /r "$SMPROGRAMS\${APPNAME}"

    ; Remove auto-start registry entry
    DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "${APPNAME}"

    ; Remove AppData (database, screenshots, logs)
    RMDir /r "$LOCALAPPDATA\${APPNAME}"

    ; Remove registry keys
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
SectionEnd

;--------------------------------
; Uninstaller Functions
;--------------------------------
Function un.KillRunningApp
    DetailPrint "Checking for running Context Clipboard..."
    nsExec::ExecToStack '"taskkill" /F /IM ContextClipboard.exe /T'
    Pop $R0
    ${If} $R0 == "0"
        DetailPrint "Closed running Context Clipboard."
        Sleep 1000
    ${Else}
        DetailPrint "No running instance found (or already closed)."
    ${EndIf}
FunctionEnd
