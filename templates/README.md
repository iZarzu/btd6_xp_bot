# Szablony obrazków

Tu trafiają małe wycinki ekranu (`.png`), po których bot rozpoznaje, co jest na ekranie.
Wycinasz je sam, bo zależą od Twojej rozdzielczości i języka gry:

```
python -m btd6bot capture victory
```

Potem F9 w lewym górnym i F9 w prawym dolnym rogu fragmentu.

| Plik            | Co wyciąć                                                   | Wymagany |
|-----------------|-------------------------------------------------------------|----------|
| `victory.png`   | napis „Victory” na ekranie wygranej                         | tak      |
| `defeat.png`    | napis/ekran przegranej                                      | tak      |
| `next.png`      | przycisk „Next” na ekranie wygranej                         | tak      |
| `home.png`      | przycisk domku (powrót do menu) po grze                     | tak      |
| `play.png`      | przycisk „Play” w menu głównym                              | tak      |
| `map.png`       | miniatura wybranej mapy na liście map                       | tak      |
| `hard.png`      | przycisk trudności (np. Hard)                               | tak      |
| `deflation.png` | przycisk trybu Deflation                                    | tak      |
| `ok.png`        | „OK” w okienku z zasadami trybu                             | nie      |
| `ingame.png`    | stały element interfejsu w grze (np. ikonka pieniędzy)       | nie, ale przyspiesza |
| `levelup.png`   | ekran/okienko awansu poziomu                                | nie      |
| `restart.png`, `confirm.png` | do szybszej pętli z restartem                  | nie      |

Wskazówki:
- Wycinaj **mały, charakterystyczny** fragment (napis, ikonę), bez animowanego tła.
- Sprawdzisz działanie poleceniem `python -m btd6bot test` - wypisze, które szablony widzi teraz na ekranie.
