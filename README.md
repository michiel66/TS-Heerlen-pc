# Teamspeak Heerlen PC — zelfstandige Windows-client

Windows 10/11, 64-bit. Eigen TeamSpeak-verbinding en Opus-audio-engine uit dezelfde Rust-familie als de Android-versie (`tslib_multi`). **Er is geen TeamSpeak 3-desktopprogramma of ClientQuery API-sleutel nodig.**

## Voor gebruikers

1. Start `Teamspeak-Heerlen-PC.exe`.
2. Typ je gebruikersnaam in en klik **Verbinden met Heerlen**. De server is vast ingesteld op **heerlen.mijnts3.nl**.
3. Via **Instellingen** kies je de PTT-toets (F6-F12, spatie, rechter Ctrl/Alt of muis-zijknop).
4. Zet de **3-tonige rogerpiep** aan of uit. De tonen worden bij loslaten PTT naar het TeamSpeak-kanaal verstuurd.
5. Kies een achtergrond: Nachtblauw, Radio groen, Neon paars, Zwart of een eigen PNG/JPG/WEBP-afbeelding.
6. Bekijk de kanalen en live gebruikersmonitor, wissel met dubbelklik van kanaal en gebruik kanaalchat.

Je TeamSpeak-identiteit wordt bij de eerste start lokaal aangemaakt en voor volgende verbindingen bewaard in de Windows AppData-map. Bewaar een back-up van de identiteit als je serverrechten aan je account hebt gekoppeld.

## Techniek en beperkingen

- De Windows-interface is gebouwd met PySide6. De zelfstandige TeamSpeak-verbinding draait in een eigen Rust-proces dat via JSON-pipes met de app communiceert.
- Rust-dependencies: `tslib-core`, `tslib-audio`, `tsclientlib`, Opus en Windows audio (WASAPI).
- De Windows-build haalt een vastgepinde versie van `wslinnn/tslib_multi` op. De native engine wordt door PyInstaller als extra binary in de EXE opgenomen.
- Nog geen praktijkverificatie met de echte Heerlen-server, microfoon, luidspreker, kanaalrechten en rogerpiep. Een geslaagde GitHub-build controleert het compileren, niet alle apparaten.
- PTT is een door de gebruiker gekozen toets of muisknop, die ook werkt buiten het app-venster.
- De server kan alsnog een wachtwoord, beveiligingsniveau of andere rechten eisen. De app omzeilt die niet.
- Een geselecteerde afbeelding wordt verkleind opgeslagen in de lokale instellingenmap.
- TeamSpeak is een handelsmerk van de betreffende rechthebbende; dit is geen officiële TeamSpeak-client.

## EXE downloaden en bouwen

1. Open [GitHub Actions](https://github.com/michiel66/TS-Heerlen-pc/actions/workflows/windows-exe.yml).
2. Kies de nieuwste **groene** run van `Bouw Teamspeak Heerlen PC EXE`.
3. Download bij **Artifacts** `Teamspeak-Heerlen-PC-Windows-EXE` en pak de ZIP uit.
4. Start `Teamspeak-Heerlen-PC.exe`.

De GitHub Action compileert eerst de Rust-audio-engine en voert unit tests uit. Daarna maakt PyInstaller de Windows EXE.

## Broncode en herkomst

- Android-app: https://github.com/michiel66/TS-Heerlen-app (blijft intact).
- Rust: https://github.com/wslinnn/tslib_multi (MIT/Apache-2.0).
- Windows-bronbestanden: `native/src/main.rs`, `heerlen/native.py`, `heerlen/ui.py`, `heerlen/background.py`, `heerlen/hotkeys.py`, `heerlen/storage.py`.
- PC-broncode: GPL-3.0-or-later; respecteer de licenties van alle gebruikte afhankelijkheden.
