# TeamSpeak Heerlen PC — Windows EXE

**Nieuwe audiobasis (november 2026): gebaseerd op de werkende PTTConnect-PC.**
De eerdere PySide6/Rust-audioversie herkende op sommige Windows-pc's geen microfoon. Daarom bouwt de nieuwste workflow geen CPAL-variant meer, maar een Windows-app met dezelfde **Chromium getUserMedia()/WebAudio microfoonketen** en TeamSpeak gateway/Opus connector als de werkende PTTConnect-PC.

## Zo werkt het

1. Download de nieuwste **groene** build uit [Windows Actions](https://github.com/michiel66/TS-Heerlen-pc/actions/workflows/windows-exe.yml).
2. Pak het artifact **TeamSpeak-Heerlen-PC-PTTConnect-Windows** uit.
3. Gebruik de **portable EXE** zonder installatie, of kies de **Setup EXE**.
4. Vul de TeamSpeak-naam in en klik **Verbinden met Heerlen**. De server is vast ingesteld op **heerlen.mijnts3.nl**.
5. Selecteer zo nodig microfoon en luidspreker onder **Settings → Recording / Playback**; de keuzelijsten en microfoontest gebruiken Windows via Chromium.
6. Gebruik de grote **PTT**-knop (ingedrukt houden) of stel onder **Settings → Hotkeys** een PTT-toets in. De toetsen werken in het app-venster.
7. Zet de **3-tonige rogerpiep** aan/uit, kies de achtergrond (Nachtblauw, Radio groen, Neon paars of Zwart). Deze voorkeuren blijven lokaal bewaard.

## Verschil met de eerdere builds

- **Wel:** TeamSpeak direct verbinden zonder geïnstalleerde TeamSpeak 3-client; Opus RX/TX; echte audioapparaatkeuze en microfoon-test; kanalen, gebruikers en PTT via de beproefde PTTConnect-keten.
- **Niet:** De oude PySide6-client is niet de nieuwe Windows-runtime. De bestaande Qt/Rust-bestanden blijven in de repository staan als historisch materiaal maar worden niet meer verpakt.
- De Windows-app gebruikt een Electron/Chromium-interface in plaats van de oude Qt-interface. De naam en kleuren zijn op Heerlen afgestemd. De bron van PTTConnect zelf wordt **niet gewijzigd**.
- De rogerpiep wordt na het loslaten van de grote PTT-knop via de reguliere TeamSpeak audioweg verzonden. Een ingestelde toetsenbord-PTT gebruikt de originele PTTConnect-routine; de rogerpiep is daar momenteel nog niet aan gekoppeld.
- Verbindingscontrole en echte geluidskwaliteit zijn afhankelijk van de TeamSpeak-server, Windows-microfoontoegang en daadwerkelijke hardware. **Een groene CI-build bevestigt niet dat een fysieke microfoon op jouw pc werkt.**
- Een serverwachtwoord of gebruikersrechten van TeamSpeak blijven gelden; de app omzeilt die niet.
- Het project bevat beide oude en nieuwe implementaties om bestaande code niet te verliezen.

## Bron en licenties

De nieuwe Windows-build gebruikt vastgepinde versies van:
- [PTTConnect-PC](https://github.com/michiel66/PTTConnect-PC), commit `d4d394c8d30a002afc38b64e810f4e81edff5554`. De workflow voert het bestaande werkende patchscript op de eigen checkout uit.
- [WebSpeak3](https://github.com/WebSpeak3/webspeak3), commit `c2b52b323d2ef10e388b2b600444a98390c5cc7a`. MIT-licentie (Copyright 2026 Moepchi), verstrekt in de Windows runtime.
- Eigen Heerlen-wijzigingen: `desktop/main.cjs`, `desktop/patch_heerlen.py`, `desktop/package.json`.

De oorspronkelijke Android-app, PTTConnect-PC en 3D Café blijven intact. Dit is geen officiële TeamSpeak-client.

## Voor ontwikkelaars

De workflow `.github/workflows/windows-exe.yml` bouwt op Windows. Daarin worden de PTTConnect- en WebSpeak3-bronnen opgehaald op **vaste commits**, de bestaande PTTConnect-patch toegepast, vervolgens de Heerlen-voorkeuren en branding. Daarna worden de Rust connector, Node gateway, React webinterface en Electron portable/setup gebouwd.

De opgeslagen TeamSpeak-identiteit zit in de persoonlijke Electron app-opslag op de Windows-computer. Bewaar daarvan een back-up wanneer serverrechten aan die identiteit gekoppeld zijn.
