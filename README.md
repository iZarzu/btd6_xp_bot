# BTD6 XP Bot

**[English](#english) · [Polski](#polski)**

---

## English

A bot for **Bloons TD 6** that replays a map in **Deflation** mode over and over
(places the configured towers, starts the rounds on fast forward, waits for the win, repeats)
to farm account XP and, with it, **Monkey Knowledge** points.
The default strategy is the well-known **Infernal Deflation** farm
(Village 2-0-2, Sniper 0-2-4, Alchemist 4-2-0, ~6 minutes per game).

### How it works

The bot behaves like a person at the computer - it **does not modify the game or its memory**:

1. it grabs frames of the game window and looks for small template images in them (OpenCV),
   e.g. the *Victory* text,
2. it clicks and uses the game's hotkeys (`Z` = Sniper, `,` `.` `/` = upgrades, space = start),
3. every position is stored **relative** to the game area (0-1) and templates remember the
   resolution they were captured at, so one setup works on Full HD, 1440p and 4K.

```
menu -> Play -> Infernal -> Easy -> Deflation -> place towers -> space x2 -> ... -> Victory
  ^                                                                                    |
  +------------------------------------ Next -> Home <-----------------------------------+
```

### Working while the bot plays

| Setting | What happens | Your PC |
|---|---|---|
| `capture_mode: auto` / `window` | frames are captured with the `PrintWindow` API, even when the game is **covered** by other windows | free to use |
| `input_mode: burst` (default) | the bot activates the game only for the few seconds it needs to click (placing towers, menus ~ every 6 min) and then **gives focus and the cursor back** | free to use, short interruptions |
| `input_mode: background` | experimental: window messages straight to the game, nothing moves on your screen. Unity games sometimes ignore them - check with *Test input* in the GUI | fully free, if it works |
| `input_mode: foreground` | classic: the game must stay on top | busy |

Limits: the game window **must not be minimized** (Windows stops rendering it) - leave it behind
other windows or on a second monitor. Run the game in **windowed / borderless mode with a 16:9 size**.

### Installation (Windows)

```bash
git clone -b claude/eager-johnson-sbuq7p https://github.com/iZarzu/btd6_xp_bot.git
cd btd6_xp_bot
start.bat                  # first run: creates .venv + installs requirements, then opens the GUI
```

`start.bat` uses its own `.venv`, so it does not matter which `python` is first on your PATH.

In the game: enable **Auto Start**, keep default hotkeys (or edit them in `config.yaml`).

### Setup in the GUI

The GUI language (English / Polski) is picked in the top-right corner and remembered;
the version is shown in the bottom-right corner.

1. **Game** - click *Detect window*; it should show the game size. Choose capture/input mode, *Save settings*.
2. **Templates** - open the right screen in the game (main menu, map list, win screen...), select a row
   and *Capture selected*, then drag a rectangle around a small, distinctive fragment.
   *Test on current screen* shows what is recognized right now.
3. **Monkeys** - the towers placed at the start of each game, in order, with three upgrade pickers
   (only combinations allowed by the game can be selected). Open a fresh game on the map, click
   **Set position** next to a monkey: the bot switches to the game and presses its hotkey, you move the
   mouse and click where it should stand - that exact click is saved. Changes are saved immediately.
   The **Strategy (YAML)** tab shows the same strategy as text for advanced edits.
4. **Run** - first try `Games = 1`, then `0` (endless). **F7** pause, **F8** stop.

Without the GUI: `python -m btd6bot run strategies/infernal_deflation.yaml --games 1`.

### Strategy format

```yaml
start_game:                       # main menu -> map
  - click_template: play
  - click_template: map
  - click_template: easy
  - click_template: deflation

steps:                            # done at the start of each game
  - place: {tower: village, name: village, at: [0.46, 0.50]}
  - upgrade: {name: village, path: [2, 0, 2]}   # top / middle / bottom
```

| Step | Description |
|---|---|
| `place: {tower, name, at}` | place a tower (name from `hotkeys.towers`) at `at` |
| `upgrade: {name, path: [t, m, b]}` | select the tower and press the upgrade keys |
| `sell: name` | sell a tower |
| `click: [x, y]` / `click: button` | click a point / a named button from `config.yaml -> buttons` |
| `click_template: name` | wait for an image and click it (`optional`, `timeout`) |
| `click_template: name` + `next_page: arrow_right` | not on this page -> click the arrow (template or `[x, y]`) and search the next page (`max_pages`) |
| `wait_for: name` | wait for an image |
| `key: esc` | press a key (`times`) |
| `wait: 2` | wait N seconds |

After a win BTD6 only offers Home / Preview / Freeplay, so each game starts again from the menu. After a defeat
the strategy's `on_defeat` decides (Monkeys tab): `restart` (default, needs the `restart` template),
`menu` or `stop`. Defeats are checked during the whole game.
Optional timings in `config.yaml`: `key_delay` (0.08 s between key presses), `after_click_delay`
(0.3 s after a menu click - the next step waits for its own button), `page_delay` (0.6 s after the map-list arrow).

Top-level `end_check_delay: 295` (set in the Monkeys tab) - start looking for the end of the game only
N seconds after the rounds started; the log shows how long each game took.

### Project layout

```
btd6bot/
  window.py   - finding the game window, relative <-> absolute coordinates
  capture.py  - frame capture (PrintWindow in the background / screen)
  vision.py   - template matching with automatic rescaling
  inputs.py   - input backends (foreground / burst / background)
  bot.py      - the farming loop and strategy steps
  gui.py      - tkinter configuration window
  app.py      - shared setup, global hotkeys
  i18n.py     - GUI translations (en / pl)
  strategy.py - monkeys <-> strategy steps, BTD6 upgrade rules
  recorder.py - catching the user's click in the game (Set position)
config.yaml   - settings, hotkeys, post-game sequences
strategies/   - strategies (YAML)
templates/    - your captured template images
```

### Versioning

`X.Y.Z` in `btd6bot/__init__.py` - `Z` goes up with every commit, `X`/`Y` for bigger milestones.
Check it with `python -m btd6bot --version`.

### Disclaimer

Automating the game may break Ninja Kiwi's terms of service. The bot does not touch game files or
memory, but you use it at your own risk.

---

## Polski

Bot do **Bloons TD 6**, który w kółko gra mapę w trybie **Deflation**
(stawia zdefiniowane wieże, startuje rundy z przyspieszeniem, czeka na wygraną i zaczyna od nowa),
żeby nabijać XP konta, a z nim punkty **Monkey Knowledge**.
Domyślna strategia to znana farma **Infernal Deflation**
(Village 2-0-2, Sniper 0-2-4, Alchemik 4-2-0, ok. 6 minut na grę).

### Jak to działa

Bot działa jak człowiek przy komputerze - **nie modyfikuje gry ani jej pamięci**:

1. pobiera obraz okna gry i szuka w nim małych obrazków-szablonów (OpenCV), np. napisu *Victory*,
2. klika i używa skrótów klawiszowych gry (`Z` = Sniper, `,` `.` `/` = ulepszenia, spacja = start),
3. każda pozycja jest zapisana **względnie** (0-1), a szablony pamiętają rozdzielczość, w której je
   wycięto - więc jedna konfiguracja działa na Full HD, 1440p i 4K.

### Praca na komputerze w trakcie farmienia

| Ustawienie | Co się dzieje | Twój komputer |
|---|---|---|
| `capture_mode: auto` / `window` | obraz pobierany przez API `PrintWindow`, także gdy gra jest **zasłonięta** innymi oknami | wolny |
| `input_mode: burst` (domyślnie) | bot aktywuje grę tylko na kilka sekund, gdy musi kliknąć (stawianie wież, menu ~ co 6 min), a potem **oddaje Ci okno i kursor** | wolny, krótkie przerwy |
| `input_mode: background` | eksperymentalny: komunikaty prosto do okna gry, nic się nie rusza na ekranie. Gry Unity czasem je ignorują - sprawdź przyciskiem *Test sterowania* w GUI | w pełni wolny, jeśli zadziała |
| `input_mode: foreground` | klasyczny: gra musi być cały czas na wierzchu | zajęty |

Ograniczenia: okna gry **nie wolno minimalizować** (Windows przestaje je wtedy rysować) - zostaw je
pod innymi oknami albo na drugim monitorze. Uruchom grę **w oknie / bez ramki, w rozmiarze 16:9**.

### Instalacja (Windows)

```bash
git clone -b claude/eager-johnson-sbuq7p https://github.com/iZarzu/btd6_xp_bot.git
cd btd6_xp_bot
start.bat                  # pierwsze uruchomienie: tworzy .venv, instaluje biblioteki i otwiera GUI
```

`start.bat` używa własnego `.venv`, więc nie ma znaczenia, który `python` jest pierwszy w PATH.

W grze: włącz **Auto Start**, zostaw domyślne skróty (albo popraw je w `config.yaml`).

### Konfiguracja w GUI

Język GUI (English / Polski) wybierasz w prawym górnym rogu i jest zapamiętywany;
wersja programu jest w prawym dolnym rogu.

1. **Gra** - kliknij *Wykryj okno*, powinien pokazać się rozmiar gry. Wybierz tryb obrazu/sterowania, *Zapisz ustawienia*.
2. **Szablony** - otwórz w grze odpowiedni ekran (menu główne, lista map, ekran wygranej...), zaznacz wiersz,
   *Wytnij zaznaczony* i zaznacz myszką mały, charakterystyczny fragment.
   *Test na obecnym ekranie* pokaże, co bot teraz rozpoznaje.
3. **Małpki** - wieże stawiane na początku każdej gry, w kolejności, z trzema polami ulepszeń
   (da się wybrać tylko kombinacje dozwolone w grze). Wejdź w grze na mapę, kliknij **Ustaw pozycję**
   przy małpce: bot przełączy na grę i wciśnie jej skrót, a Ty najeżdżasz myszką i klikasz, gdzie ma stać -
   zapisuje się dokładnie to kliknięcie. Zmiany zapisują się od razu.
   Zakładka **Strategia (YAML)** pokazuje tę samą strategię jako tekst do zaawansowanej edycji.
4. **Uruchom** - najpierw `Gier = 1`, potem `0` (bez końca). **F7** pauza, **F8** stop.

Bez GUI: `python -m btd6bot run strategies/infernal_deflation.yaml --games 1`.

Format strategii i lista kroków - patrz sekcja angielska powyżej (tabela *Step*): `place`, `upgrade`,
`sell`, `click`, `click_template`, `wait_for`, `key`, `wait`.
`click_template` z opcją `next_page: arrow_right` szuka mapy na kolejnych stronach listy map
(klika strzałkę w prawo, dopóki jej nie znajdzie).
Po wygranej BTD6 daje tylko Home / Preview / Freeplay, więc każda gra zaczyna się od menu. Po przegranej
decyduje `on_defeat` w strategii (zakładka Małpki): `restart` (domyślnie, wymaga szablonu `restart`),
`menu` albo `stop`. Przegrana jest sprawdzana przez całą grę.
Opcjonalne czasy w `config.yaml`: `key_delay`, `after_click_delay`, `page_delay` (opis w sekcji angielskiej).
`end_check_delay: 295` (pole w zakładce Małpki) - koniec gry jest sprawdzany dopiero N sekund po starcie
rund; w logu widać, ile trwała każda gra.

### Jak farmić najefektywniej

- Mapy Expert (np. Infernal) dają +30% XP względem Beginner.
- Pewność > mnożnik: jedna przegrana kosztuje więcej niż różnica w XP - najpierw przetestuj build ręcznie.
- Wytnij szablon `ingame` - bot zacznie stawiać małpki od razu po załadowaniu mapy.

### Uwaga

Automatyzacja gry może naruszać regulamin Ninja Kiwi. Bot nie dotyka plików ani pamięci gry,
ale używasz go na własną odpowiedzialność.
