"""Strategy model used by the Monkeys tab: towers with upgrade paths <-> YAML `steps`.

PL: Model strategii dla zakładki Małpki: wieże ze ścieżkami ulepszeń <-> `steps` w YAML.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Monkey:
    tower: str
    name: str
    at: list[float] | None = None
    path: list[int] = field(default_factory=lambda: [0, 0, 0])


# ---------------------------------------------------------------------- upgrade rules / zasady ulepszeń
def is_valid_path(path: list[int]) -> bool:
    """BTD6 rules: at most two paths upgraded, only one of them above tier 2.

    PL: Zasady BTD6: ulepszone najwyżej dwie ścieżki, tylko jedna powyżej poziomu 2.
    """
    return (len(path) == 3 and all(0 <= p <= 5 for p in path)
            and sum(p > 0 for p in path) <= 2 and sum(p > 2 for p in path) <= 1)


def allowed_tiers(path: list[int], index: int) -> list[int]:
    """Tiers that can be chosen for path `index` without breaking the rules.

    PL: Poziomy, które można wybrać dla ścieżki `index` bez łamania zasad.
    """
    others = [p for i, p in enumerate(path) if i != index]
    if all(p > 0 for p in others):
        return [0]  # two other paths already used -> locked / PL: dwie inne ścieżki zajęte -> blokada
    top = 2 if any(p > 2 for p in others) else 5
    return list(range(top + 1))


# ---------------------------------------------------------------------- steps <-> monkeys
def monkeys_from_steps(steps: list[dict[str, Any]] | None) -> tuple[list[Monkey], bool]:
    """Build the monkey list; the flag says whether there were other step types (sell, wait...).

    PL: Buduje listę małpek; flaga mówi, czy były inne rodzaje kroków (sell, wait...).
    """
    monkeys: list[Monkey] = []
    by_name: dict[str, Monkey] = {}
    other = False
    for step in steps or []:
        if not isinstance(step, dict):
            other = True
        elif "place" in step:
            p = step["place"]
            at = p.get("at")
            monkey = Monkey(p["tower"], p.get("name", p["tower"]), list(at) if isinstance(at, list) else None)
            monkeys.append(monkey)
            by_name[monkey.name] = monkey
        elif "upgrade" in step and step["upgrade"].get("name") in by_name:
            target = by_name[step["upgrade"]["name"]]
            target.path = [min(5, a + b) for a, b in zip(target.path, step["upgrade"]["path"])]
        else:
            other = True
    return monkeys, other


def steps_yaml(monkeys: list[Monkey]) -> str:
    """YAML lines of the `steps:` block: place + upgrade for each monkey, in list order.

    PL: Linie YAML bloku `steps:`: postawienie + ulepszenie każdej małpki, w kolejności listy.
    """
    lines = []
    for m in monkeys:
        at = f"[{m.at[0]}, {m.at[1]}]" if m.at else "null"
        lines.append(f"  - place: {{tower: {m.tower}, name: {m.name}, at: {at}}}")
        if any(m.path):
            lines.append(f"  - upgrade: {{name: {m.name}, path: [{m.path[0]}, {m.path[1]}, {m.path[2]}]}}")
    return "\n".join(lines) + ("\n" if lines else "")


def unique_name(tower: str, taken: set[str]) -> str:
    if tower not in taken:
        return tower
    n = 2
    while f"{tower}{n}" in taken:
        n += 1
    return f"{tower}{n}"


def replace_steps(text: str, new_steps: str) -> str:
    """Replace the `steps:` block of a strategy text, keeping everything else (comments too).

    PL: Podmienia blok `steps:` w tekście strategii, zostawiając resztę (także komentarze).
    """
    lines = text.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if line.startswith("steps:")), None)
    if start is None:
        return text.rstrip("\n") + "\n\nsteps:\n" + new_steps
    end = start + 1
    while end < len(lines) and (not lines[end].strip() or lines[end][0] in " \t"):
        end += 1
    # Keep blank lines that separate the block from the next section. / PL: Zachowaj puste linie.
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    return "".join(lines[:start + 1]) + new_steps + "".join(lines[end:])
