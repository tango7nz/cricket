"""Build the Carnies season page from stats/season.json.

Add a match to season.json, then run:

    python 2026-27/Carnies/stats/build_season.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(__file__).resolve().parent / "season.json"
OUT = ROOT / "season.md"

WICKET_DISMISSALS = {
    "bowled",
    "caught",
    "lbw",
    "run_out",
    "stumped",
    "caught_and_bowled",
    "hit_wicket",
}
BOWLER_WICKETS = WICKET_DISMISSALS - {"run_out"}
NOT_OUTS = {"not_out", "retired"}
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def load() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def extras_total(extras: dict) -> int:
    return extras["b"] + extras["lb"] + extras["w"] + extras["nb"]


def overs(balls: int) -> str:
    return f"{balls // 6}.{balls % 6}"


def num(value: float | None, places: int = 2) -> str:
    if value is None:
        return "-"
    return f"{value:.{places}f}"


def nice_date(iso: str, with_year: bool = True) -> str:
    year, month, day = (int(part) for part in iso.split("-"))
    if with_year:
        return f"{day} {MONTHS[month - 1]} {year}"
    return f"{day} {MONTHS[month - 1]}"


def short_date(iso: str) -> str:
    return nice_date(iso, with_year=False)


def clock(value: str) -> str:
    hour, minute = (int(part) for part in value.split(":")[:2])
    suffix = "pm" if hour >= 12 else "am"
    hour12 = hour % 12 or 12
    return f"{hour12}:{minute:02d}{suffix}"


def count_phrase(n: int, one: str, many: str | None = None) -> str:
    word = one if n == 1 else (many if many is not None else one + "s")
    return f"{n} {word}"


def join_and(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + ", and " + items[-1]


def overs_prose(balls: int) -> str:
    if balls % 6 == 0:
        return count_phrase(balls // 6, "over")
    return f"{overs(balls)} overs"


def balls_left_phrase(balls_left: int) -> str:
    if balls_left <= 0:
        return "no overs left"
    if balls_left % 6 == 0:
        return count_phrase(balls_left // 6, "over") + " left"
    return f"{overs(balls_left)} overs left"


def scoreline(innings: dict) -> str:
    return f"{innings['runs']}/{innings['wickets']} ({overs(innings['balls'])})"


def result_text(match: dict) -> str:
    word = {"win": "Won", "loss": "Lost", "tie": "Tied", "draw": "Drew", "no_result": "No result"}[
        match["result"]
    ]
    margin = match["margin"]
    if match["result"] == "no_result":
        return word
    if margin["type"] == "wickets":
        unit = "wicket" if margin["value"] == 1 else "wickets"
        return f"{word} by {margin['value']} {unit}"
    unit = "run" if margin["value"] == 1 else "runs"
    return f"{word} by {margin['value']} {unit}"


def marker(dismissal: str) -> str:
    if dismissal == "retired":
        return "\u2020"
    if dismissal == "not_out":
        return "*"
    return ""


def validate(data: dict) -> None:
    team = data["team"]
    seen_dates = set()
    for match in data["matches"]:
        if match["date"] in seen_dates:
            raise SystemExit(f"Duplicate match date {match['date']}")
        seen_dates.add(match["date"])
        xi = match["xi"]
        if len(xi) != data["players_per_side"] or len(set(xi)) != len(xi):
            raise SystemExit(f"{match['date']} does not have {data['players_per_side']} unique players")
        for label, innings, our_names in (
            ("batting", match["carnies_batting"], [b["name"] for b in match["carnies_batting"]["batters"]]),
            ("bowling", match["carnies_bowling"], [b["name"] for b in match["carnies_bowling"]["bowlers"]]),
        ):
            if any(name not in xi for name in our_names):
                raise SystemExit(f"{match['date']} {label} names a player outside the XI")
            if len(our_names) != len(set(our_names)):
                raise SystemExit(f"{match['date']} {label} repeats a player")
        check_batting(match)
        check_bowling(match)
        check_points(data, match)
        if "MacPherson" in json.dumps(match) or "Macpherson" in json.dumps(match):
            raise SystemExit(f"{match['date']} still uses MacPherson. The player is Hamish Johnson.")
    runs_for = sum(match["carnies_batting"]["runs"] for match in data["matches"])
    runs_against = sum(match["carnies_bowling"]["runs"] for match in data["matches"])
    points = sum(match["points"] for match in data["matches"])
    ours = next(row for row in data["ladder"] if row["team"] == team)
    data["_check"] = {
        "runs_for": runs_for,
        "runs_against": runs_against,
        "points": points,
        "ladder_agrees": (
            ours["runs_for"] == runs_for
            and ours["runs_against"] == runs_against
            and ours["points"] == points
            and ours["played"] == len(data["matches"])
            and ours["won"] == sum(match["result"] == "win" for match in data["matches"])
            and ours["lost"] == sum(match["result"] == "loss" for match in data["matches"])
        ),
    }


def check_batting(match: dict) -> None:
    innings = match["carnies_batting"]
    batters = innings["batters"]
    total = sum(batter["runs"] for batter in batters) + extras_total(innings["extras"])
    if total != innings["runs"]:
        raise SystemExit(f"{match['date']} batting adds to {total}, card says {innings['runs']}")
    wickets = sum(batter["dismissal"] in WICKET_DISMISSALS for batter in batters)
    if wickets != innings["wickets"]:
        raise SystemExit(f"{match['date']} batting wickets add to {wickets}, card says {innings['wickets']}")
    if innings["wickets"] > 7:
        raise SystemExit(f"{match['date']} shows more than 7 wickets in an 8-a-side innings")


def check_bowling(match: dict) -> None:
    innings = match["carnies_bowling"]
    bowlers = innings["bowlers"]
    batters = innings["batters"]
    total = sum(batter["runs"] for batter in batters) + extras_total(innings["extras"])
    if total != innings["runs"]:
        raise SystemExit(f"{match['date']} opposition batting adds to {total}, card says {innings['runs']}")
    wickets = sum(batter["dismissal"] in WICKET_DISMISSALS for batter in batters)
    if wickets != innings["wickets"]:
        raise SystemExit(f"{match['date']} opposition wickets add to {wickets}, card says {innings['wickets']}")
    bowler_wickets = sum(bowler["wickets"] for bowler in bowlers)
    run_outs = sum(batter["dismissal"] == "run_out" for batter in batters)
    credited = sum(batter["dismissal"] in BOWLER_WICKETS for batter in batters)
    if bowler_wickets != credited:
        raise SystemExit(
            f"{match['date']} bowling analysis has {bowler_wickets} wickets, dismissals credit {credited}"
        )
    if bowler_wickets + run_outs != innings["wickets"]:
        raise SystemExit(f"{match['date']} bowling wickets plus run-outs do not match the total")
    bowler_runs = sum(bowler["runs"] for bowler in bowlers)
    expected = innings["runs"] - innings["extras"]["b"] - innings["extras"]["lb"]
    if bowler_runs != expected:
        raise SystemExit(
            f"{match['date']} bowlers conceded {bowler_runs}, expected {expected} after byes and leg byes"
        )
    if sum(bowler["balls"] for bowler in bowlers) != innings["balls"]:
        raise SystemExit(f"{match['date']} bowling balls do not add up to the innings")


def check_points(data: dict, match: dict) -> None:
    rules = data["points"]
    result = match["result"]
    if result == "win":
        if match["batted"] == "second":
            bonus = match["carnies_batting"]["wickets"] <= rules["bonus_wickets"]
        else:
            margin = match["margin"]
            bonus = margin["type"] == "runs" and margin["value"] >= rules["bonus_runs"]
        expected = rules["win"] + (1 if bonus else 0)
    elif result == "loss":
        bonus = False
        expected = 0
    elif result in {"tie", "draw", "no_result"}:
        bonus = False
        expected = rules["draw"]
    else:
        raise SystemExit(f"Unknown result {result}")
    if match["bonus"] is not bonus or match["points"] != expected:
        raise SystemExit(
            f"{match['date']} points are {match['points']} (bonus {match['bonus']}), expected {expected} (bonus {bonus})"
        )


def batting_table(data: dict) -> tuple[list[str], list[dict]]:
    players: dict[str, dict] = {}
    for match in data["matches"]:
        played = set(match["xi"])
        faced = {batter["name"] for batter in match["carnies_batting"]["batters"]}
        for name in played:
            players.setdefault(name, {"name": name, "cells": {}, "innings": []})
        for batter in match["carnies_batting"]["batters"]:
            cell = f"{batter['runs']}{marker(batter['dismissal'])}"
            players[batter["name"]]["cells"][match["date"]] = cell
            players[batter["name"]]["innings"].append(batter)
        for name in played - faced:
            players[name]["cells"][match["date"]] = "dnb"
    rows = []
    for player in players.values():
        innings = player["innings"]
        if not innings:
            continue
        runs = sum(item["runs"] for item in innings)
        balls = sum(item["balls"] for item in innings)
        dismissals = sum(item["dismissal"] in WICKET_DISMISSALS for item in innings)
        not_outs = len(innings) - dismissals
        best = max(innings, key=lambda item: (item["runs"], item["dismissal"] in NOT_OUTS))
        rows.append(
            {
                "name": player["name"],
                "cells": player["cells"],
                "inns": len(innings),
                "not_outs": not_outs,
                "runs": runs,
                "balls": balls,
                "high": f"{best['runs']}{marker(best['dismissal'])}",
                "average": None if dismissals == 0 else runs / dismissals,
                "strike": None if balls == 0 else runs / balls * 100,
                "fifties": sum(item["runs"] >= 50 for item in innings),
                "fours": sum(item["fours"] for item in innings),
                "sixes": sum(item["sixes"] for item in innings),
                "ducks": [
                    item
                    for item in innings
                    if item["runs"] == 0 and item["dismissal"] in WICKET_DISMISSALS
                ],
            }
        )
    rows.sort(key=lambda row: (-row["runs"], -(row["average"] or -1), row["name"]))
    return [short_date(match["date"]) for match in data["matches"]], rows


def bowling_table(data: dict) -> tuple[list[str], list[dict]]:
    players: dict[str, dict] = {}
    for match in data["matches"]:
        played = set(match["xi"])
        bowled = {bowler["name"] for bowler in match["carnies_bowling"]["bowlers"]}
        for name in played:
            players.setdefault(name, {"name": name, "cells": {}, "spells": []})
        for bowler in match["carnies_bowling"]["bowlers"]:
            players[bowler["name"]]["cells"][match["date"]] = f"{bowler['wickets']}/{bowler['runs']}"
            players[bowler["name"]]["spells"].append({**bowler, "date": match["date"], "opponent": match["opponent"]})
        for name in played - bowled:
            players[name]["cells"][match["date"]] = "-"
    rows = []
    for player in players.values():
        spells = player["spells"]
        if not spells:
            continue
        balls = sum(spell["balls"] for spell in spells)
        runs = sum(spell["runs"] for spell in spells)
        wickets = sum(spell["wickets"] for spell in spells)
        best = max(spells, key=lambda spell: (spell["wickets"], -spell["runs"], -spell["balls"]))
        rows.append(
            {
                "name": player["name"],
                "cells": player["cells"],
                "games": len(player["cells"]),
                "balls": balls,
                "maidens": sum(spell["maidens"] for spell in spells),
                "runs": runs,
                "wickets": wickets,
                "dots": sum(spell["dots"] for spell in spells),
                "average": None if wickets == 0 else runs / wickets,
                "economy": None if balls == 0 else runs / balls * 6,
                "best": f"{best['wickets']}/{best['runs']}",
                "best_spell": best,
                "spells": spells,
            }
        )
    rows.sort(key=lambda row: (-row["wickets"], row["average"] if row["average"] is not None else 10**9, row["economy"] or 0, row["name"]))
    return [short_date(match["date"]) for match in data["matches"]], rows


FIELD_LABELS = (
    ("catches", "catch", "catches"),
    ("run_outs", "run-out", "run-outs"),
    ("stumpings", "stumping", "stumpings"),
)


def fielding(data: dict) -> tuple[list[dict], list[str]]:
    counts: dict[str, dict] = {}
    outside: dict[str, dict[str, list[str]]] = {}
    xi_all = {name for match in data["matches"] for name in match["xi"]}
    for match in data["matches"]:
        for batter in match["carnies_bowling"]["batters"]:
            credited = fielding_credit(batter)
            if credited is None:
                continue
            name, key = credited
            credit(counts, name, key)
            if name not in xi_all:
                outside.setdefault(name, {}).setdefault(key, []).append(match["opponent"])
    known = []
    for name, row in counts.items():
        if name not in xi_all:
            continue
        known.append({"name": name, **row})
    known.sort(key=lambda row: (-row["catches"], -row["stumpings"], -row["run_outs"], row["name"]))
    notes = [outside_note(name, events) for name, events in outside.items()]
    return known, notes


def fielding_credit(batter: dict) -> tuple[str, str] | None:
    kind = batter["dismissal"]
    if kind == "caught":
        return batter["fielder"], "catches"
    if kind == "caught_and_bowled":
        return batter["bowler"], "catches"
    if kind == "run_out":
        return batter.get("fielder", ""), "run_outs"
    if kind == "stumped":
        return batter.get("fielder", ""), "stumpings"
    return None


def outside_note(name: str, events: dict[str, list[str]]) -> str:
    parts = []
    total = 0
    for key, one, many in FIELD_LABELS:
        opponents = events.get(key, [])
        if not opponents:
            continue
        total += len(opponents)
        seen = list(dict.fromkeys(opponents))
        where = join_and(seen)
        if len(opponents) == 1:
            parts.append(f"a {one} against {where}")
        else:
            parts.append(f"{len(opponents)} {many} against {where}")
    listed = join_and(parts)
    stays = "it stays" if total == 1 else "they stay"
    who = name if name else "An unnamed fielder"
    return (
        f"{who} is credited with {listed} and does not appear in a Carnies eight, "
        f"so {stays} off the player table."
    )


def credit(counts: dict, name: str, key: str) -> None:
    row = counts.setdefault(name, {"catches": 0, "run_outs": 0, "stumpings": 0})
    row[key] += 1


def highlights_table(batters: list[dict], bowlers: list[dict]) -> str | None:
    by_name: dict[str, dict] = {}
    for row in batters:
        by_name[row["name"]] = {
            "name": row["name"],
            "fifties": row["fifties"],
            "ducks": len(row["ducks"]),
            "three_wicket_games": 0,
            "sixes": row["sixes"],
        }
    for row in bowlers:
        entry = by_name.setdefault(
            row["name"],
            {"name": row["name"], "fifties": 0, "ducks": 0, "three_wicket_games": 0, "sixes": 0},
        )
        entry["three_wicket_games"] = sum(spell["wickets"] >= 3 for spell in row["spells"])
    rows = [
        row
        for row in by_name.values()
        if row["fifties"] or row["ducks"] or row["three_wicket_games"] or row["sixes"]
    ]
    if not rows:
        return None
    rows.sort(key=lambda row: (-row["fifties"], -row["sixes"], -row["three_wicket_games"], row["name"]))
    body = [
        [
            row["name"],
            str(row["fifties"]),
            str(row["sixes"]),
            str(row["three_wicket_games"]),
            str(row["ducks"]),
        ]
        for row in rows
    ]
    return table(["Player", "50's", "6's", "3 wickets", "Ducks"], body)


def table(headers: list[str], rows: list[list[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    rule = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, rule, *body])


def innings_notes(data: dict, batters: list[dict], bowlers: list[dict]) -> list[str]:
    notes = []
    fifties = []
    ducks = []
    for match in data["matches"]:
        when = f"{short_date(match['date'])} against {match['opponent']}"
        for batter in match["carnies_batting"]["batters"]:
            if batter["runs"] >= 50:
                fifties.append({**batter, "when": when, "opponent": match["opponent"]})
            if batter["runs"] == 0 and batter["dismissal"] in WICKET_DISMISSALS:
                how = "run out" if batter["dismissal"] == "run_out" else batter["dismissal"].replace("_", " ")
                ducks.append({**batter, "when": when, "opponent": match["opponent"], "how": how})
    if fifties:
        notes.append(fifty_note(data, fifties))
    if ducks:
        notes.append("Ducks: " + "; ".join(duck_phrase(item) for item in ducks) + ".")
    six_hitters = [row for row in batters if row["sixes"]]
    if six_hitters:
        detail = ", ".join(f"{row['name']} {row['sixes']}" for row in six_hitters)
        total = sum(row["sixes"] for row in six_hitters)
        notes.append(f"{total} sixes: {detail}.")
    quick = []
    for match in data["matches"]:
        for batter in match["carnies_batting"]["batters"]:
            if batter["balls"] >= 10:
                quick.append((batter["runs"] / batter["balls"], batter, match))
    if quick:
        _, batter, match = max(quick, key=lambda item: item[0])
        rate = batter["runs"] / batter["balls"] * 100
        notes.append(
            f"Fastest innings of 10 balls or more: {batter['name']}, {batter['runs']} off {batter['balls']} against {match['opponent']}, strike rate {rate:.1f}."
        )
    wicket_spells = [row["best_spell"] | {"name": row["name"]} for row in bowlers if row["wickets"]]
    if wicket_spells:
        spell = max(wicket_spells, key=lambda item: (item["wickets"], -item["runs"]))
        notes.append(
            f"Best bowling spell: {spell['name']}, {spell['wickets']}/{spell['runs']} off {overs_prose(spell['balls'])} against {spell['opponent']}."
        )
    qualified = [row for row in bowlers if row["balls"] >= 12]
    if qualified:
        notes.append(dot_note(qualified))
    maidens = sum(row["maidens"] for row in bowlers)
    if maidens == 0:
        notes.append("Nobody has bowled a maiden yet.")
    else:
        notes.append(f"Maidens bowled: {maidens}.")
    short = []
    for match in data["matches"]:
        if match["result"] == "win" and match["batted"] == "first" and not match["bonus"]:
            need = data["points"]["bonus_runs"]
            got = match["margin"]["value"]
            short.append(f"the {got}-run win over {match['opponent']} was {need - got} short of the bonus")
    earned = [
        match["opponent"]
        for match in data["matches"]
        if match["bonus"] and match["batted"] == "second"
    ]
    bonus_bits = []
    if earned:
        bonus_bits.append("chase bonus picked up against " + " and ".join(earned))
    if short:
        bonus_bits.append("; ".join(short))
    if bonus_bits:
        notes.append("Bonus points: " + "; ".join(bonus_bits) + ".")
    extras_for = sum(extras_total(match["carnies_batting"]["extras"]) for match in data["matches"])
    extras_against = sum(extras_total(match["carnies_bowling"]["extras"]) for match in data["matches"])
    runs_for = sum(match["carnies_batting"]["runs"] for match in data["matches"])
    runs_against = sum(match["carnies_bowling"]["runs"] for match in data["matches"])
    notes.append(
        f"Extras make up {extras_for} of the {runs_for} runs Carnies have scored, and {extras_against} of the {runs_against} they have conceded."
    )
    ever_present = appearance_note(data, batters)
    if ever_present:
        notes.append(ever_present)
    return notes


def fifty_note(data: dict, fifties: list[dict]) -> str:
    retire_at = data["retire_after"]
    all_retired = all(item["dismissal"] == "retired" and item["runs"] == retire_at for item in fifties)
    pieces = []
    for item in fifties:
        piece = f"{item['name']} {item['runs']} off {item['balls']} on {item['when']}"
        if not all_retired:
            if item["dismissal"] == "retired":
                how = "retired"
            elif item["dismissal"] == "not_out":
                how = "not out"
            else:
                how = "out"
            piece += f" ({how})"
        pieces.append(piece)
    lead = f"Fifties so far, each retired on {retire_at}: " if all_retired else "Fifties: "
    return lead + "; ".join(pieces) + "."


def duck_phrase(item: dict) -> str:
    if item["balls"] == 1:
        return f"{item['name']}, {item['how']} first ball on {item['when']}"
    return f"{item['name']}, {item['how']} for a duck off {item['balls']} on {item['when']}"


def dot_note(qualified: list[dict]) -> str:
    by_rate = max(qualified, key=lambda row: row["dots"] / row["balls"])
    by_count = max(qualified, key=lambda row: row["dots"])
    rate = by_rate["dots"] / by_rate["balls"] * 100
    lead = (
        f"Dot balls, among bowlers with at least two overs: {by_rate['name']} has the best rate, "
        f"{by_rate['dots']} in {by_rate['balls']} balls ({rate:.0f}%)."
    )
    if by_rate["name"] == by_count["name"]:
        return lead
    return f"{lead} {by_count['name']} has bowled the most dots, {by_count['dots']}."


def appearance_note(data: dict, batters: list[dict]) -> str | None:
    played = len(data["matches"])
    if played < 2:
        return None
    counts: dict[str, int] = {}
    for match in data["matches"]:
        for name in match["xi"]:
            counts[name] = counts.get(name, 0) + 1
    runs = {row["name"]: row["runs"] for row in batters}
    names = [name for name, games in counts.items() if games == played]
    if not names:
        return None
    names.sort(key=lambda name: (-runs.get(name, -1), name))
    return "Played every game: " + ", ".join(names) + "."


def render(data: dict) -> str:
    _dates, batters = batting_table(data)
    _, bowlers = bowling_table(data)
    fielders, field_notes = fielding(data)
    notes = innings_notes(data, batters, bowlers)
    ladder = data["ladder"]
    place = next(index for index, row in enumerate(ladder, start=1) if row["team"] == data["team"])
    ours = ladder[place - 1]
    lines = [
        f"# {data['team']}, {data['season']}",
        "",
        (
            f"{record_sentence(data)} "
            f"On the PlayHQ ladder at {nice_date(data['ladder_as_of'])}, Carnies are {place_word(place)}."
        ),
        "",
    ]
    tie = tie_paragraph(data, ladder, ours)
    if tie:
        lines.extend([tie, ""])
    upcoming = next_game_sentence(data)
    if upcoming:
        lines.extend([upcoming, ""])
    lines.extend(
        [
        "## Most runs",
        "",
        leader_sentence(batters),
        "",
        "The trophy is the run total. An average does not break the tie, and a retirement keeps the runs.",
        "",
        batting_markdown(data["matches"], batters),
        "",
        "\u2020 retired after passing 50, and counted as not out. * not out at the end of the innings. dnb means he was in the side and did not bat. A blank cell means he was not in the side.",
        "",
        "## Most wickets",
        "",
        bowling_leader_sentence(bowlers, data.get("max_overs_per_bowler")),
        "",
        "The trophy is wickets credited to a bowler. A run-out is not a bowling wicket. Caught and bowled counts.",
        "",
        bowling_markdown(data["matches"], bowlers),
        "",
        "A figure in a match column is wickets/runs. - means he played and did not bowl. A blank cell means he was not in the side.",
        "",
        "## In the field",
        "",
        ]
    )
    if fielders:
        lines.append(
            table(
                ["Player", "Catches", "Run outs", "Stumpings"],
                [[row["name"], str(row["catches"]), str(row["run_outs"]), str(row["stumpings"])] for row in fielders],
            )
        )
        lines.append("")
        lines.append("Caught and bowled is counted as a catch.")
    else:
        lines.append("No catches, run-outs, or stumpings credited to a Carnies player yet.")
    for note in field_notes:
        lines.extend(["", note])
    lines.extend(["", "## Results", ""])
    result_rows = []
    for match in data["matches"]:
        result_rows.append(
            [
                nice_date(match["date"], with_year=False),
                match["opponent"],
                match["venue"],
                scoreline(match["carnies_batting"]),
                scoreline(match["carnies_bowling"]),
                result_text(match),
                str(match["points"]) + (" incl. bonus" if match["bonus"] else ""),
            ]
        )
    lines.append(table(["Date", "Opponent", "Ground", "Carnies", "Opposition", "Result", "Points"], result_rows))
    lines.extend(["", "Seven wickets is all out. Grounds left blank on a card are filled from PlayHQ.", ""])
    for match in data["matches"]:
        lines.append(f"**{nice_date(match['date'], with_year=False)} against {match['opponent']}.** {match['story']}")
        lines.append("")
        lines.append(f"Scorecard: [{Path(match['card']).name}](<{match['card']}>)")
        lines.append("")
    lines.extend(
        [
            "## Ladder",
            "",
            f"PlayHQ, {data['competition']}, as at {nice_date(data['ladder_as_of'])}.",
            "",
        ]
    )
    ladder_rows = []
    for index, row in enumerate(ladder, start=1):
        name = f"**{row['team']}**" if row["team"] == data["team"] else row["team"]
        ladder_rows.append(
            [
                str(index),
                name,
                str(row["played"]),
                str(row["won"]),
                str(row["lost"]),
                str(row["bonus"]),
                str(row["points"]),
                str(row["runs_for"]),
                str(row["runs_against"]),
            ]
        )
    lines.append(table(["", "Team", "P", "W", "L", "Bonus", "Pts", "For", "Against"], ladder_rows))
    if not data["_check"]["ladder_agrees"]:
        lines.extend(
            [
                "",
                (
                    f"The Carnies row above does not match the cards. From the scorecards: "
                    f"{data['_check']['points']} points, {data['_check']['runs_for']} runs for, "
                    f"{data['_check']['runs_against']} against."
                ),
            ]
        )
    lines.extend(["", "## Worth a mention", ""])
    highlights = highlights_table(batters, bowlers)
    if highlights:
        lines.append(highlights)
        lines.extend(
            [
                "",
                "A fifty is 50 or more, including a retirement. 3 wickets means 3 or more in a match. A duck is out for 0.",
                "",
            ]
        )
    for note in notes:
        lines.append(f"- {note}")
    lines.extend(["", "## Still to play", "", f"Carnies fixtures on PlayHQ as at {nice_date(data['ladder_as_of'])}.", ""])
    fixture_rows = []
    for fixture in data["fixtures"]:
        home = "Carnies" if fixture["home"] == data["team"] else fixture["home"]
        away = "Carnies" if fixture["away"] == data["team"] else fixture["away"]
        fixture_rows.append(
            [
                f"R{fixture['round']}",
                nice_date(fixture["date"]),
                clock(fixture["time"]),
                f"{home} v {away}",
                fixture["venue"],
            ]
        )
    lines.append(table(["Round", "Date", "Time", "Match", "Ground"], fixture_rows))
    alias_note = playhq_name_note(data)
    if alias_note:
        lines.extend(["", alias_note])
    cap = data.get("max_overs_per_bowler")
    cap_sentence = f" A bowler can bowl {cap} overs in a full game." if cap else ""
    lines.extend(
        [
            "",
            "## How this is counted",
            "",
            "Carnies play 8 a side, so a side is all out at 7 wickets. A batter retires once the score passes 50, and can return, in retirement order, only after the rest of the side is out apart from the last batter. A retirement is not a dismissal and it is not a wicket lost."
            + cap_sentence,
            "",
            "A win is 6 points. A draw, tie, or rain-off is 3. The winner gets one bonus point for a first-innings win by 40 or more, or for a chase in which they lose 3 wickets or fewer.",
            "",
            "Batting average is runs divided by dismissals. Bowling average is runs conceded divided by wickets. Economy is runs per over. The two trophies at the end of the year are most runs and most wickets. Nothing else breaks those ties unless the club says so.",
            "",
            "Scorecards live in `Scorecards/`. This page is built from `stats/season.json`.",
            "",
        ]
    )
    return "\n".join(lines)


def record_sentence(data: dict) -> str:
    matches = data["matches"]
    played = len(matches)
    won = sum(match["result"] == "win" for match in matches)
    lost = sum(match["result"] == "loss" for match in matches)
    other = played - won - lost
    bits = [count_phrase(won, "win"), count_phrase(lost, "loss", "losses")]
    if other:
        bits.append(count_phrase(other, "draw, tie, or no result", "draws, ties, or no results"))
    return (
        f"{count_phrase(played, 'game')} played, {join_and(bits)}, "
        f"{count_phrase(data['_check']['points'], 'point')}."
    )


def tie_paragraph(data: dict, ladder: list[dict], ours: dict) -> str | None:
    tied = [row for row in ladder if row["points"] == ours["points"]]
    if len(tied) < 2:
        return None
    same_games = len({row["played"] for row in tied}) == 1
    bits = []
    for row in tied:
        label = "Carnies" if row["team"] == data["team"] else row["team"]
        if same_games:
            bits.append(f"{label} {row['runs_for']}")
        else:
            bits.append(f"{label} {row['runs_for']} from {count_phrase(row['played'], 'game')}")
    text = (
        f"{len(tied)} teams are level on {ours['points']} points. "
        "PlayHQ sorts that by runs scored, then wickets taken. "
        f"Runs scored: {join_and(bits)}."
    )
    unbeaten = [
        row["team"]
        for row in tied
        if row["team"] != data["team"] and row["lost"] == 0 and row["won"] == row["played"] and row["played"] > 0
    ]
    if unbeaten:
        verb = "is" if len(unbeaten) == 1 else "are"
        text += f" {join_and(unbeaten)} {verb} unbeaten."
    return text


def next_game_sentence(data: dict) -> str | None:
    fixtures = data.get("fixtures") or []
    if not fixtures:
        return None
    fixture = fixtures[0]
    home = "Carnies" if fixture["home"] == data["team"] else fixture["home"]
    away = "Carnies" if fixture["away"] == data["team"] else fixture["away"]
    return (
        f"Next game: {nice_date(fixture['date'])}, {home} v {away} at {fixture['venue']}, {clock(fixture['time'])}."
    )


def playhq_name_note(data: dict) -> str | None:
    fixture_names = {name for fixture in data["fixtures"] for name in (fixture["home"], fixture["away"])}
    notes = []
    seen = set()
    for match in data["matches"]:
        card_name = match["opponent"]
        hq_name = match.get("playhq_opponent")
        if not hq_name or hq_name == card_name or hq_name in seen or hq_name not in fixture_names:
            continue
        seen.add(hq_name)
        notes.append(f"{hq_name} is {card_name} on the cards")
    if not notes:
        return None
    return "PlayHQ names in this draw: " + "; ".join(notes) + "."


def place_word(place: int) -> str:
    names = {1: "first", 2: "second", 3: "third"}
    return names.get(place, f"{place}th")


def leader_sentence(batters: list[dict]) -> str:
    if not batters:
        return "No batting yet."
    leader = batters[0]
    if len(batters) == 1:
        return f"{leader['name']} has {leader['runs']} runs."
    nxt = batters[1]
    gap = leader["runs"] - nxt["runs"]
    return (
        f"{leader['name']} leads with {leader['runs']}. "
        f"{nxt['name']} is next with {nxt['runs']}, {gap} behind."
    )


def bowling_leader_sentence(bowlers: list[dict], cap: int | None) -> str:
    if not bowlers:
        return "No bowling yet."
    leader = bowlers[0]
    rivals = [row for row in bowlers[1:] if leader["wickets"] > 0 and row["wickets"] == leader["wickets"]]
    if rivals:
        names = join_and([leader["name"], *[row["name"] for row in rivals]])
        sentence = f"{names} are level on {count_phrase(leader['wickets'], 'wicket')}."
        if cap and len(rivals) == 1:
            sentence += " " + overs_bank(leader, rivals[0], cap)
        return sentence
    nxt = next((row for row in bowlers[1:] if row["wickets"]), None)
    if nxt is None:
        return f"{leader['name']} has {count_phrase(leader['wickets'], 'wicket')}."
    sentence = (
        f"{leader['name']} leads with {count_phrase(leader['wickets'], 'wicket')} from {overs_prose(leader['balls'])}. "
        f"{nxt['name']} has {nxt['wickets']} from {overs_prose(nxt['balls'])}."
    )
    if cap:
        sentence += " " + overs_bank(leader, nxt, cap)
    return sentence


def overs_bank(leader: dict, nxt: dict, cap: int) -> str:
    def left(row: dict) -> int:
        return row["games"] * cap * 6 - row["balls"]

    return (
        f"The cap is {cap} overs a game. From the games played so far, "
        f"{leader['name']} has {balls_left_phrase(left(leader))} and "
        f"{nxt['name']} has {balls_left_phrase(left(nxt))}."
    )


def batting_markdown(matches: list[dict], rows: list[dict]) -> str:
    headers = ["Player", *[short_date(match["date"]) for match in matches], "I", "NO", "Runs", "HS", "Ave", "SR", "50", "4s", "6s"]
    body = []
    for row in rows:
        body.append(
            [
                row["name"],
                *[row["cells"].get(match["date"], "") for match in matches],
                str(row["inns"]),
                str(row["not_outs"]),
                str(row["runs"]),
                row["high"],
                num(row["average"]),
                num(row["strike"], 1),
                str(row["fifties"]),
                str(row["fours"]),
                str(row["sixes"]),
            ]
        )
    return table(headers, body)


def bowling_markdown(matches: list[dict], rows: list[dict]) -> str:
    headers = ["Player", *[short_date(match["date"]) for match in matches], "O", "M", "R", "W", "Ave", "Econ", "Best"]
    body = []
    for row in rows:
        body.append(
            [
                row["name"],
                *[row["cells"].get(match["date"], "") for match in matches],
                overs(row["balls"]),
                str(row["maidens"]),
                str(row["runs"]),
                str(row["wickets"]),
                num(row["average"]),
                num(row["economy"]),
                row["best"],
            ]
        )
    return table(headers, body)


def main() -> None:
    data = load()
    validate(data)
    text = render(data)
    OUT.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
