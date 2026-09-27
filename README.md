# BTD6 XP Bot

Prosty bot do **Bloons TD 6**, który w kółko gra wybraną mapę w trybie **Deflation**
(stawia zdefiniowane wieże, startuje rundy z przyspieszeniem, czeka na wygraną i zaczyna od nowa),
żeby w tle nabijać XP konta, a z nim punkty **Monkey Knowledge**.

## Jak to działa

Bot działa jak człowiek przy komputerze - **nie modyfikuje gry ani jej pamięci**:

1. robi zrzuty ekranu (`mss`) i szuka na nich małych obrazków-szablonów (`OpenCV`), np. napisu *Victory*,
2. klika myszką i używa skrótów klawiszowych gry (`Q` = Dart, `D` = Ninja, `,` `.` `/` = ulepszenia, spacja = start),
3. wszystkie pozycje zapisuje jako **względne** (0-1), więc działają na każdej rozdzielczości 16:9.

Deflation nadaje się idealnie: dostajesz stałą kasę na start (bez dochodu), więc wszystkie wieże
stawia się **raz, przed pierwszą rundą** - potem bot tylko czeka do rundy 60.

```
menu -> Play -> mapa -> trudność -> Deflation -> postaw wieże -> spacja x2 -> ... -> Victory
  ^                                                                                  |
  +------------------------------ Next -> Home (lub Restart) <-----------------------+
```

## Instalacja (Windows)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

W grze:
- włącz **Auto Start** (Ustawienia) - kolejne rundy startują same,
- najlepiej tryb pełnoekranowy okienkowy / okno o stałym rozmiarze, **nie zasłaniaj gry** podczas pracy bota,
- zostaw domyślne skróty klawiszowe (albo popraw je w `config.yaml`).

## Konfiguracja krok po kroku

1. **Szablony obrazków** - wytnij je według [templates/README.md](templates/README.md):
   ```bash
   python -m btd6bot capture victory
   python -m btd6bot capture next
   ...
   ```
2. **Pozycje wież** - wejdź ręcznie na mapę, najeżdżaj myszką na miejsca i wciskaj F9:
   ```bash
   python -m btd6bot pos
   ```
   Wklej wyniki do `strategies/<twoja_strategia>.yaml` (wzór: `strategies/deflation_example.yaml`).
3. **Test** - `python -m btd6bot test` pokazuje, które szablony są widoczne na ekranie.
4. **Próba jednej gry**:
   ```bash
   python -m btd6bot run strategies/deflation_example.yaml --games 1
   ```
5. **Farmienie bez końca**:
   ```bash
   python -m btd6bot run strategies/deflation_example.yaml
   ```

Sterowanie: **F7** pauza/wznowienie, **F8** stop, mysz w **lewy górny róg ekranu** = awaryjne zatrzymanie.

## Format strategii

```yaml
start_game:                       # jak z menu głównego dojść do mapy
  - click_template: play
  - click_template: map
  - click_template: hard
  - click_template: deflation

steps:                            # co zrobić na początku gry
  - place: {tower: ninja, name: ninja1, at: [0.42, 0.45]}
  - upgrade: {name: ninja1, path: [4, 0, 2]}   # góra / środek / dół
```

Dostępne kroki (w `steps`, `start_game`, `after_victory` itd.):

| Krok | Opis |
|---|---|
| `place: {tower, name, at}` | postaw wieżę (nazwa z `hotkeys.towers`) w punkcie `at` |
| `upgrade: {name, path: [g, s, d]}` | kliknij wieżę i wciśnij ulepszenia tyle razy |
| `sell: nazwa` | sprzedaj wieżę |
| `click: [x, y]` lub `click: przycisk` | klik w punkt / nazwany przycisk z `config.yaml -> buttons` |
| `click_template: nazwa` | poczekaj aż obrazek się pojawi i kliknij go (`optional`, `timeout`) |
| `wait_for: nazwa` | poczekaj na obrazek |
| `key: esc` | wciśnij klawisz (`times` = ile razy) |
| `wait: 2` | poczekaj N sekund |

## Jak farmić najefektywniej

- XP za grę rośnie z numerem rundy - Deflation (31-60) daje sporo XP za relatywnie krótką grę.
- Trudniejsze kategorie map (Advanced / Expert) mają wyższy mnożnik XP, ale strategia musi być pewna -
  **jedna przegrana kosztuje więcej niż różnica w mnożniku**. Zacznij od łatwej mapy, potem przenieś build.
- Pętla `Next -> Restart` (patrz koniec pliku przykładowej strategii) jest szybsza i odporniejsza niż klikanie przez menu.
- Monkey Knowledge dostajesz za kolejne poziomy konta, więc liczy się po prostu łączne XP na godzinę.

## Uwaga

Automatyzacja gry może naruszać regulamin Ninja Kiwi. Bot nie dotyka plików ani pamięci gry,
ale używasz go na własną odpowiedzialność.
