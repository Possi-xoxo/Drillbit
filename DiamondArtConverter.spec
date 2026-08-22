# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.win32.versioninfo import (FixedFileInfo,StringFileInfo,StringStruct,
    StringTable,VarFileInfo,VarStruct,VSVersionInfo)

release_identity={}
exec((Path(SPECPATH)/"app"/"version.py").read_text(encoding="utf-8"),release_identity)
APP_NAME=release_identity["APP_NAME"];APP_VERSION=release_identity["APP_VERSION"]
version_numbers=tuple(int(part) for part in APP_VERSION.split("."))+(0,)
version_info=VSVersionInfo(
    ffi=FixedFileInfo(filevers=version_numbers,prodvers=version_numbers,mask=0x3F,flags=0x0,
        OS=0x40004,fileType=0x1,subtype=0x0,date=(0,0)),
    kids=[
        StringFileInfo([StringTable("040904B0",[
            StringStruct("FileDescription",APP_NAME),StringStruct("FileVersion",APP_VERSION),
            StringStruct("InternalName",APP_NAME),StringStruct("OriginalFilename","Drillbit.exe"),
            StringStruct("ProductName",APP_NAME),StringStruct("ProductVersion",APP_VERSION),
        ])]),
        VarFileInfo([VarStruct("Translation",[1033,1200])]),
    ],
)

a=Analysis(["main.py"],pathex=[],binaries=[],datas=[("palettes/dmc.json","palettes"),("palettes/LICENSE-pyxstitch-GPL3.txt","palettes")],
    hiddenimports=[],hookspath=[],hooksconfig={},runtime_hooks=[],excludes=["tkinter"],noarchive=False,optimize=1)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name=APP_NAME,debug=False,bootloader_ignore_signals=False,
    strip=False,upx=True,console=False,disable_windowed_traceback=False,argv_emulation=False,target_arch=None,
    codesign_identity=None,entitlements_file=None,icon="Drillbit.ico",version=version_info)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=True,upx_exclude=[],name=APP_NAME)
