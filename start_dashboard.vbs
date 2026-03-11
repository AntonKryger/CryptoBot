Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\ak\OneDrive - onecom38e07c2a7c\Vibecode\Vibecoding\Claude Projekter\CryptoBot"
WshShell.Run "pythonw scripts\sync_vps.py", 0, False
WshShell.Run "pythonw dashboard.py", 0, False
