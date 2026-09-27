# BTD6 XP Bot - project conventions

- Code, identifiers and log messages in **English**; every comment/docstring has an English line
  followed by a `PL:` Polish line.
- README.md is bilingual (English section + Polish section) - keep both in sync.
- GUI texts live only in `btd6bot/i18n.py` (`en` + `pl`); never hard-code visible strings in `gui.py`.
- **Versioning** `X.Y.Z` in `btd6bot/__init__.py` (`__version__`, shown in the GUI bottom-right corner):
  bump **Z on every commit**; X and Y are changed only when the owner decides.
- Do not change user-editable files (`config.yaml`, `strategies/*.yaml`) unless needed - users
  edit them locally and `git pull` would conflict. Per-user GUI preferences go to `user_settings.json`
  (git-ignored).
- The game runs on Windows; WinAPI code must degrade gracefully elsewhere so tests can run on Linux.
