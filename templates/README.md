# Templates / Szablony

Small screenshots (`.png`) the bot uses to recognize game screens. Capture them in the GUI
(**Templates** tab) - they depend on your game language, so they are not shipped with the repo.
`templates.json` stores the game resolution of each capture, so they are rescaled automatically
on other screens (Full HD <-> 4K).

PL: Małe wycinki ekranu (`.png`), po których bot rozpoznaje ekrany gry. Wycinasz je w GUI
(zakładka **Szablony**) - zależą od języka gry, dlatego nie ma ich w repo.
`templates.json` zapamiętuje rozdzielczość gry dla każdego wycinka, więc są automatycznie
skalowane na innych ekranach (Full HD <-> 4K).

| File / Plik | What to capture / Co wyciąć | Required / Wymagany |
|---|---|---|
| `victory` | "Victory" text / napis „Victory” | yes / tak |
| `defeat` | defeat screen text / napis przegranej | yes / tak |
| `next` | "Next" button on the win screen / przycisk „Next” | yes / tak |
| `home` | home button after a game / przycisk domku | yes / tak |
| `play` | "Play" in the main menu / „Play” w menu | yes / tak |
| `expert` | Expert map tab / zakładka map Expert | no / nie |
| `map` | Infernal thumbnail / miniatura Infernal | yes / tak |
| `easy` | Easy difficulty / trudność Easy | yes / tak |
| `deflation` | Deflation mode / tryb Deflation | yes / tak |
| `ok` | "OK" in the rules popup / „OK” w okienku zasad | no / nie |
| `ingame` | static HUD element / stały element HUD | no (faster / szybciej) |
| `levelup` | level-up popup / okienko awansu | no / nie |
| `mk_point` | "Monkey Knowledge Point" text (no number) / napis bez liczby | no / nie |
| `restart` | Restart button on the defeat screen / Restart na ekranie przegranej | no / nie |

Tips / Wskazówki: capture a **small, distinctive** fragment (text, icon) without animated background.
PL: wycinaj **mały, charakterystyczny** fragment (napis, ikonę), bez animowanego tła.
