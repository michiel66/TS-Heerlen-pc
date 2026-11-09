# Teamspeak Heerlen PC

Windows 10/11-versie van het Heerlen donkerblauw/cyaan thema.

**Status:** nieuw project; de Windows-client wordt gebouwd met Python/PySide6, en bestuurt de **geïnstalleerde TeamSpeak 3-client via de ClientQuery-plugin**. Hierdoor werkt bestaande TeamSpeak-audio via de officiële pc-client. Dit is geen directe Windows-compilatie van de Android-app, noch een zelfstandige TeamSpeak voice-client.

De oorspronkelijke Android-repositories [TS-Heerlen-app](https://github.com/michiel66/TS-Heerlen-app) en [TS6-Droid-NL](https://github.com/michiel66/TS6-Droid-NL) blijven ongewijzigd.

## Voorwaarden

- Windows 10 of 11 (x64)
- TeamSpeak 3 client met de ClientQuery-plugin ingeschakeld
- De API-sleutel vind je in TeamSpeak 3 bij **Tools/Extra → Options/Opties → Addons → ClientQuery → Settings/Instellingen**.
- Start TeamSpeak 3 en verbind met een server voordat je de Heerlen PC-app opent.

## Wat werkt

- Neon Windows-interface in donkerblauw, cyaan en groen
- Weergave van online gebruikers en kanalen van het **actieve** TeamSpeak 3-tabblad
- Omschakeling tussen Kanalen en Live Monitor (spreekindicator als ClientQuery die meldt)
- Kanaalwissel door dubbelklikken, ook klikken op spacerregels (rechten van server gelden)
- Kanaal-chat via ClientQuery
- PTT-drukknop waarmee de microfoondemping via ClientQuery wordt geregeld
- API-sleutel bewaren via Windows Credential Manager (keyring)
- Thema- en gebruikersinstellingen lokaal bewaren

Niet geïmplementeerd: een onafhankelijke TeamSpeak-audio-engine, zonder TS3-client verbinden met een server, native Android-APK-functionaliteit zoals mobiele knoppen en rogerpiep.

## EXE bouwen

1. Open de **Actions**-tab van deze repository.
2. Selecteer **Bouw Teamspeak Heerlen PC EXE** en klik op **Run workflow** (of wacht op push-build).
3. Download het artifact **Teamspeak-Heerlen-PC-Windows-EXE**.
4. Pak uit en start **Teamspeak-Heerlen-PC.exe**.

GitHub Actions bouwt de EXE op een Windows-runner; een aangeleverde build is niet automatisch getest met een echte TeamSpeak-server. Ongetekende uitvoerbare bestanden kunnen een Windows SmartScreen-waarschuwing veroorzaken.

## Lokaal starten

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Licentie

Deze eigen Windows-implementatie is onder GPL-3.0-or-later gepubliceerd ter aansluiting bij het Heerlen/TS6-Droid-project. TeamSpeak is een handelsmerk van de betreffende eigenaar. De TeamSpeak 3-client wordt **niet** meegeleverd.
