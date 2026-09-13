"""
Einmaliger, interaktiver Garmin-Login. Legt einen Sitzungs-Token unter
sync/.garmin_tokens/ ab (git-ignoriert), damit garmin_sync.py danach ohne
erneutes Passwort laufen kann.

WICHTIG: Dieses Skript braucht ein echtes Terminal (fuer getpass und eine
etwaige 2FA-Abfrage). Fuehr es selbst lokal aus:

    sync/.venv/bin/python sync/garmin_login.py

Das Passwort wird nirgends gespeichert, geloggt oder ausgegeben -- nur einmal
an garminconnect zur Anmeldung uebergeben.
"""
import getpass
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".venv", "lib",
                 f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages"))

from garminconnect import Garmin  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_DIR = os.path.join(HERE, ".garmin_tokens")


def ask_mfa_code():
    return input("2FA-Code von Garmin (per Mail/App): ").strip()


def main():
    email = input("Garmin-Connect-Mailadresse: ").strip()
    password = getpass.getpass("Garmin-Connect-Passwort (wird nicht angezeigt): ")

    os.makedirs(TOKEN_DIR, exist_ok=True)
    client = Garmin(email=email, password=password, prompt_mfa=ask_mfa_code)
    # login(tokenstore=...) handles the 2FA callback internally (if Garmin asks
    # for one) and persists the session token to TOKEN_DIR on success.
    client.login(tokenstore=TOKEN_DIR)
    print(f"Angemeldet und Sitzungs-Token unter {TOKEN_DIR} gespeichert.")
    print("Ab jetzt reicht `sync/.venv/bin/python sync/garmin_sync.py` ohne erneutes Passwort,")
    print("bis Garmin die Sitzung irgendwann von sich aus ablaufen laesst -- dann dieses Skript")
    print("einfach noch einmal ausfuehren.")


if __name__ == "__main__":
    main()
