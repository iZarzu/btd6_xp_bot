"""GUI translations. Add a language by adding a column to every entry and to LANGUAGES.

PL: Tłumaczenia GUI. Nowy język = nowa kolumna w każdym wpisie i w LANGUAGES.
"""
from __future__ import annotations

import locale

LANGUAGES = {"en": "English", "pl": "Polski"}

STRINGS: dict[str, dict[str, str]] = {
    # --- game box / ramka gry
    "game": {"en": "Game", "pl": "Gra"},
    "window_title": {"en": "Window title:", "pl": "Tytuł okna:"},
    "capture": {"en": "Capture:", "pl": "Obraz:"},
    "input": {"en": "Input:", "pl": "Sterowanie:"},
    "match": {"en": "Match:", "pl": "Dopasowanie:"},
    "language": {"en": "Language:", "pl": "Język:"},
    "detect": {"en": "Detect window", "pl": "Wykryj okno"},
    "test_input": {"en": "Test input", "pl": "Test sterowania"},
    "save_settings": {"en": "Save settings", "pl": "Zapisz ustawienia"},
    "win_found": {"en": "Window: {w}x{h}, capture: {cap}", "pl": "Okno: {w}x{h}, obraz: {cap}"},
    "win_monitor": {"en": "WHOLE MONITOR (game not found): {w}x{h}",
                    "pl": "CAŁY MONITOR (nie znaleziono gry): {w}x{h}"},
    "settings_saved": {"en": "Settings saved.", "pl": "Zapisano ustawienia."},
    "capture_failed": {"en": "Capture failed:\n{err}", "pl": "Błąd przechwytywania obrazu:\n{err}"},
    "no_image": {"en": "No image - is the game minimized?", "pl": "Brak obrazu - czy gra jest zminimalizowana?"},
    "test_click_sent": {"en": "Test click sent at {pos} ({mode}). Did the game react?",
                        "pl": "Wysłano testowe kliknięcie w {pos} ({mode}). Czy gra zareagowała?"},
    # --- templates tab / zakładka szablonów
    "tab_templates": {"en": "1. Templates", "pl": "1. Szablony"},
    "templates_help": {
        "en": "Open the right game screen (e.g. the win screen for 'victory'), select a row and click "
              "Capture. Templates are rescaled automatically for other resolutions.",
        "pl": "Otwórz w grze odpowiedni ekran (np. ekran wygranej dla 'victory'), zaznacz wiersz i kliknij "
              "Wytnij. Szablony są automatycznie skalowane do innych rozdzielczości."},
    "col_name": {"en": "Name", "pl": "Nazwa"},
    "col_required": {"en": "Required", "pl": "Wymagany"},
    "col_description": {"en": "What to capture", "pl": "Co wyciąć"},
    "col_status": {"en": "Captured at", "pl": "Wycięty przy"},
    "col_visible": {"en": "Visible now", "pl": "Widoczny teraz"},
    "yes": {"en": "yes", "pl": "tak"},
    "no": {"en": "no", "pl": "nie"},
    "missing": {"en": "✗ missing", "pl": "✗ brak"},
    "visible_yes": {"en": "✓ YES", "pl": "✓ TAK"},
    "custom": {"en": "custom template", "pl": "własny szablon"},
    "btn_capture": {"en": "Capture selected", "pl": "Wytnij zaznaczony"},
    "btn_capture_custom": {"en": "Capture custom…", "pl": "Własny…"},
    "btn_delete": {"en": "Delete", "pl": "Usuń"},
    "btn_test_templates": {"en": "Test on current screen", "pl": "Test na obecnym ekranie"},
    "template_saved": {"en": "Saved template {name} ({tw}x{th} px) from a {w}x{h} game.",
                       "pl": "Zapisano szablon {name} ({tw}x{th} px) z gry {w}x{h}."},
    "select_row": {"en": "Select a row first.", "pl": "Najpierw zaznacz wiersz."},
    "template_name_prompt": {"en": "Template name (a-z, 0-9, _):", "pl": "Nazwa szablonu (a-z, 0-9, _):"},
    # --- template descriptions / opisy szablonów
    "tpl_victory": {"en": "'Victory' text on the win screen", "pl": "napis 'Victory' po wygranej"},
    "tpl_defeat": {"en": "text on the defeat screen", "pl": "napis na ekranie przegranej"},
    "tpl_next": {"en": "'Next' button on the win screen", "pl": "przycisk 'Next' po wygranej"},
    "tpl_home": {"en": "home button after a game", "pl": "przycisk domku po grze"},
    "tpl_play": {"en": "'Play' button in the main menu", "pl": "przycisk 'Play' w menu głównym"},
    "tpl_expert": {"en": "'Expert' map category tab", "pl": "zakładka map 'Expert'"},
    "tpl_arrow_right": {"en": "right arrow in the map list (next page)",
                        "pl": "strzałka w prawo na liście map (następna strona)"},
    "tpl_map": {"en": "map thumbnail (e.g. Infernal)", "pl": "miniatura mapy (np. Infernal)"},
    "tpl_easy": {"en": "'Easy' difficulty button", "pl": "przycisk trudności 'Easy'"},
    "tpl_deflation": {"en": "'Deflation' mode button", "pl": "przycisk trybu 'Deflation'"},
    "tpl_ok": {"en": "'OK' in the mode rules popup", "pl": "'OK' w okienku zasad trybu"},
    "tpl_ingame": {"en": "static in-game HUD element (speeds up loading)",
                   "pl": "stały element HUD w grze (przyspiesza ładowanie)"},
    "tpl_levelup": {"en": "level-up popup", "pl": "okienko awansu poziomu"},
    # --- monkeys tab / zakładka małpek
    "tab_monkeys": {"en": "2. Monkeys", "pl": "2. Małpki"},
    "monkeys_help": {
        "en": "Monkeys placed at the start of every game, in this order. Pick the upgrades (only combinations "
              "allowed by the game can be chosen). 'Set position': open a fresh game on the map first - the bot "
              "switches to the game and presses the monkey's hotkey, you just move the mouse and click where it "
              "should stand (Esc cancels). Changes are saved to the strategy file right away.",
        "pl": "Małpki stawiane na początku każdej gry, w tej kolejności. Wybierz ulepszenia (da się wybrać tylko "
              "kombinacje dozwolone w grze). 'Ustaw pozycję': najpierw wejdź w grze na mapę - bot przełączy na grę "
              "i wciśnie skrót małpki, a Ty tylko najeżdżasz myszką i klikasz, gdzie ma stać (Esc anuluje). "
              "Zmiany od razu zapisują się w pliku strategii."},
    "monkeys_file": {"en": "Strategy file: {name} (change it in the Strategy tab)",
                     "pl": "Plik strategii: {name} (zmienisz go w zakładce Strategia)"},
    "col_monkey": {"en": "Monkey", "pl": "Małpka"},
    "col_top": {"en": "Top", "pl": "Góra"},
    "col_middle": {"en": "Middle", "pl": "Środek"},
    "col_bottom": {"en": "Bottom", "pl": "Dół"},
    "col_position": {"en": "Position", "pl": "Pozycja"},
    "not_set": {"en": "not set", "pl": "nieustawiona"},
    "set_position": {"en": "Set position", "pl": "Ustaw pozycję"},
    "add_monkey": {"en": "+ Add monkey", "pl": "+ Dodaj małpkę"},
    "end_check_delay": {"en": "Check for the end of the game after (s):", "pl": "Sprawdzaj koniec gry dopiero po (s):"},
    "end_check_hint": {"en": "counted from the start of the rounds; 0 = right away. The log shows how long a game took.",
                       "pl": "liczone od startu rund; 0 = od razu. W logu widać, ile trwała gra."},
    "monkeys_saved": {"en": "Saved to {name}.", "pl": "Zapisano w {name}."},
    "place_waiting": {"en": "In the game: move the mouse and click where the {monkey} should stand (Esc cancels)...",
                      "pl": "W grze: najedź myszką i kliknij, gdzie ma stać {monkey} (Esc anuluje)..."},
    "game_not_found": {"en": "Game window not found - start the game (check 'Window title' at the top).",
                       "pl": "Nie znaleziono okna gry - uruchom grę (sprawdź 'Tytuł okna' u góry)."},
    "place_manual_key": {"en": "Could not switch to the game - switch manually, press '{key}' and click on the map.",
                         "pl": "Nie udało się przełączyć na grę - przełącz ręcznie, wciśnij '{key}' i kliknij na mapie."},
    "place_saved": {"en": "{monkey}: position {pos} saved.", "pl": "{monkey}: zapisano pozycję {pos}."},
    "place_cancelled": {"en": "Setting the position cancelled.", "pl": "Anulowano ustawianie pozycji."},
    "place_timeout": {"en": "No click within 60 s - cancelled.", "pl": "Brak kliknięcia przez 60 s - anulowano."},
    "other_steps": {"en": "The strategy contains other steps (sell, wait...) that this tab can't show. "
                          "Saving from here will remove them. Continue?",
                    "pl": "Strategia zawiera inne kroki (sell, wait...), których ta zakładka nie pokazuje. "
                          "Zapis stąd je usunie. Kontynuować?"},
    "yaml_broken": {"en": "The strategy YAML has errors - fix it in the Strategy tab.",
                    "pl": "YAML strategii ma błędy - popraw go w zakładce Strategia."},
    # --- tower names / nazwy małpek (as in the game / jak w grze)
    "tower_hero": {"en": "Hero", "pl": "Bohater"},
    "tower_dart": {"en": "Dart Monkey", "pl": "Dart Monkey"},
    "tower_boomerang": {"en": "Boomerang Monkey", "pl": "Boomerang Monkey"},
    "tower_bomb": {"en": "Bomb Shooter", "pl": "Bomb Shooter"},
    "tower_tack": {"en": "Tack Shooter", "pl": "Tack Shooter"},
    "tower_ice": {"en": "Ice Monkey", "pl": "Ice Monkey"},
    "tower_glue": {"en": "Glue Gunner", "pl": "Glue Gunner"},
    "tower_sniper": {"en": "Sniper Monkey", "pl": "Sniper Monkey (snajper)"},
    "tower_sub": {"en": "Monkey Sub", "pl": "Monkey Sub"},
    "tower_buccaneer": {"en": "Monkey Buccaneer", "pl": "Monkey Buccaneer"},
    "tower_ace": {"en": "Monkey Ace", "pl": "Monkey Ace"},
    "tower_heli": {"en": "Heli Pilot", "pl": "Heli Pilot"},
    "tower_mortar": {"en": "Mortar Monkey", "pl": "Mortar Monkey"},
    "tower_dartling": {"en": "Dartling Gunner", "pl": "Dartling Gunner"},
    "tower_wizard": {"en": "Wizard Monkey", "pl": "Wizard Monkey"},
    "tower_super": {"en": "Super Monkey", "pl": "Super Monkey"},
    "tower_ninja": {"en": "Ninja Monkey", "pl": "Ninja Monkey"},
    "tower_alchemist": {"en": "Alchemist", "pl": "Alchemist (alchemik)"},
    "tower_druid": {"en": "Druid", "pl": "Druid"},
    "tower_banana": {"en": "Banana Farm", "pl": "Banana Farm"},
    "tower_spike": {"en": "Spike Factory", "pl": "Spike Factory"},
    "tower_village": {"en": "Monkey Village", "pl": "Monkey Village (wioska)"},
    "tower_engineer": {"en": "Engineer Monkey", "pl": "Engineer Monkey"},
    "strategy_help": {"en": "Advanced: the strategy as YAML text. The Monkeys tab edits the 'steps' part of it.",
                      "pl": "Zaawansowane: strategia jako tekst YAML. Zakładka Małpki edytuje jej część 'steps'."},
    "err_no_position": {"en": "Monkey '{name}' has no position - set it in the Monkeys tab.",
                        "pl": "Małpka '{name}' nie ma pozycji - ustaw ją w zakładce Małpki."},
    "err_invalid_path": {"en": "Monkey '{name}' has upgrades not allowed by the game: {path}",
                         "pl": "Małpka '{name}' ma ulepszenia niedozwolone w grze: {path}"},
    # --- strategy tab / zakładka strategii
    "tab_strategy": {"en": "3. Strategy (YAML)", "pl": "3. Strategia (YAML)"},
    "file": {"en": "File:", "pl": "Plik:"},
    "save": {"en": "Save", "pl": "Zapisz"},
    "save_as": {"en": "Save as…", "pl": "Zapisz jako…"},
    "err_steps": {"en": "'steps' must be a non-empty list", "pl": "'steps' musi być niepustą listą"},
    "err_unknown_tower": {"en": "Unknown tower: {tower}", "pl": "Nieznana wieża: {tower}"},
    "err_upgrade_first": {"en": "Upgrade before the tower is placed: {name}",
                          "pl": "Ulepszenie przed postawieniem wieży: {name}"},
    "strategy_error": {"en": "Strategy error:\n{err}", "pl": "Błąd w strategii:\n{err}"},
    "strategy_saved": {"en": "Strategy saved: {name}", "pl": "Zapisano strategię: {name}"},
    "file_name_prompt": {"en": "File name (.yaml):", "pl": "Nazwa pliku (.yaml):"},
    # --- run tab / zakładka uruchamiania
    "tab_run": {"en": "4. Run", "pl": "4. Uruchom"},
    "games": {"en": "Games (0 = endless):", "pl": "Gier (0 = bez końca):"},
    "start": {"en": "▶ Start", "pl": "▶ Start"},
    "pause": {"en": "⏸ Pause (F7)", "pl": "⏸ Pauza (F7)"},
    "stop": {"en": "■ Stop (F8)", "pl": "■ Stop (F8)"},
    "missing_templates": {"en": "Missing required templates:\n{names}\n\nStart anyway?",
                          "pl": "Brak wymaganych szablonów:\n{names}\n\nUruchomić mimo to?"},
    "bot_crashed": {"en": "Bot crashed: {err}", "pl": "Bot przerwał pracę: {err}"},
    "paused": {"en": "Paused.", "pl": "Pauza."},
    "resumed": {"en": "Resumed.", "pl": "Wznowiono."},
    "stats": {"en": "Games: {games} | wins: {wins} | losses: {losses} | timeouts: {timeouts} | "
                    "last game: {last:.1f} min | running: {hours:.2f} h",
              "pl": "Gry: {games} | wygrane: {wins} | przegrane: {losses} | zawieszenia: {timeouts} | "
                    "ostatnia gra: {last:.1f} min | czas pracy: {hours:.2f} h"},
    # --- advanced tab / zakładka zaawansowana
    "tab_advanced": {"en": "Advanced (config.yaml)", "pl": "Zaawansowane (config.yaml)"},
    "advanced_help": {"en": "Timings, hotkeys, post-game sequences",
                      "pl": "Czasy, skróty klawiszowe, sekwencje po grze"},
    "yaml_error": {"en": "YAML error:\n{err}", "pl": "Błąd YAML:\n{err}"},
    "config_saved": {"en": "config.yaml saved.", "pl": "Zapisano config.yaml."},
    # --- screenshot picker / wybór na zrzucie
    "picker_point_title": {"en": "Click a point", "pl": "Kliknij punkt"},
    "picker_rect_title": {"en": "Drag a rectangle", "pl": "Zaznacz prostokąt"},
    "picker_point_help": {"en": "Click the spot. Circles = towers already in the strategy.",
                          "pl": "Kliknij miejsce. Kółka = wieże już dodane w strategii."},
    "picker_rect_help": {"en": "Drag a SMALL, distinctive fragment (text/icon), then Save.",
                         "pl": "Zaznacz MAŁY, charakterystyczny fragment (napis/ikonę), potem Zapisz."},
    "refresh": {"en": "Refresh", "pl": "Odśwież"},
    "need_rect": {"en": "Drag a rectangle first.", "pl": "Najpierw zaznacz obszar."},
    "too_small": {"en": "Selection too small.", "pl": "Zaznaczony obszar jest za mały."},
}


def translate(lang: str, key: str, **fmt) -> str:
    entry = STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(lang) or entry["en"]
    return text.format(**fmt) if fmt else text


def default_language() -> str:
    """Polish if the system is Polish, English otherwise. / PL: Polski, jeśli system jest po polsku."""
    try:
        name = (locale.getlocale()[0] or "").lower()
    except ValueError:
        name = ""
    return "pl" if name.startswith("pl") or "polish" in name else "en"
