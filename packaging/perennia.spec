# Receita do PyInstaller para a Perennia.
#
# Não se corre à mão: os scripts build_windows.bat e build.sh tratam disto.
# Gera dist/Perennia/ (Windows e Linux) ou dist/Perennia.app (macOS),
# com o Python e todas as bibliotecas lá dentro.
#
# Modo «pasta» e não «ficheiro único»: arranca mais depressa, e os
# antivírus desconfiam menos de uma pasta do que de um .exe que se
# descomprime sozinho.

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).parent

datas = [(str(ROOT / "tests" / "teste.gpx"), "tests"),
         (str(ROOT / "velo" / "assets"), "velo/assets")]      # ícones
binaries = []
hidden = (collect_submodules("velo")
          + collect_submodules("pyglet")      # a pyglet carrega módulos à medida
          + ["usb.backend.libusb1", "usb.backend.libusb0", "usb.backend.openusb"])


def take(package):
    """Inclui um pacote inteiro (código, dados e bibliotecas nativas), se existir."""
    global datas, binaries, hidden
    try:
        d, b, h = collect_all(package)
    except Exception as e:                   # pacote opcional ausente
        print(f"[perennia] sem {package}: {e}")
        return
    datas += d
    binaries += b
    hidden += h


take("bleak")             # Bluetooth
take("libusb_package")    # a libusb da antena ANT+ (Windows e macOS)
take("openpyxl")          # importar o Excel das análises
if sys.platform == "win32":
    take("winrt")         # o Bluetooth do Windows, usado pelo bleak
    take("bleak_winrt")
elif sys.platform == "darwin":
    take("objc")
    take("CoreBluetooth")
else:
    take("dbus_fast")     # o Bluetooth do Linux (BlueZ)

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "matplotlib", "numpy"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Perennia",
    console=False,            # sem janela preta; os erros vão para perennia-erro.log
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name="Perennia", upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Perennia.app",
        bundle_identifier="pt.perennia.app",
        info_plist={
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
            # sem esta frase o macOS não deixa usar o Bluetooth
            "NSBluetoothAlwaysUsageDescription":
                "A Perennia liga-se ao rolo, aos pedais de potência e à cinta.",
        },
    )
