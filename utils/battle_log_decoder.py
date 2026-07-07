# This file is part of NeuraSelf-UwU.
# Copyright (c) 2025-Present Routo
#
# NeuraSelf-UwU is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with NeuraSelf-UwU. If not, see <https://www.gnu.org/licenses/>.

"""Decode owobot's "v2" battle-log replay (from logs.owobot.com/logs/<uuid>) into a
plain nested structure, then flatten it into a compact human-readable summary that an
AI can reason about (both teams' pets, levels, stats, weapons, and passive effects).

The v2 format is a dictionary-compressed graph: `logs` is a JSON string of
`[dictionary, root_ref]` where `dictionary` is a flat list of tokens and `root_ref` is
a base62 index into it. Tokens are either literal JSON values or reference tokens:
  a|i|j|...   array whose elements are dictionary entries at base62 indices i, j, ...
  o|k|v|v|... object: k is an array-ref of key names, the rest are value refs (columnar)
  n|x         number (plain digits, else base62 int)
  b|T / b|F   boolean
Reverse-engineered from owobot.com's JS bundle (getBattleLog + BattleLogPage chunk).
"""

import json
import re

_ALPH = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'

# <:name:1234567890> / <a:name:1234567890>  ->  :name:  (keep the name, drop the noise)
_EMOJI_RE = re.compile(r'<a?:([a-zA-Z0-9_]+):\d+>')


def _clean_emoji(text):
    if not isinstance(text, str):
        return text
    return _EMOJI_RE.sub(r':\1:', text)


def _b62(s):
    n = 0
    for ch in s:
        n = n * 62 + _ALPH.index(ch)
    return n


def _num(s):
    if s.lstrip('-').isdigit():
        return int(s)
    try:
        return _b62(s)
    except Exception:
        return s


def decode_v2(raw):
    """Decode a raw battle-log payload (dict with a 'logs' string, or the logs string
    itself, or an already-parsed [dict, root]) into the plain battle object. Returns a
    dict, or None if it doesn't look like a v2 log."""
    try:
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, dict):
            logs = raw.get('logs')
            if logs is None:
                return None
            arr = json.loads(logs) if isinstance(logs, str) else logs
        else:
            arr = raw
        if not (isinstance(arr, list) and len(arr) == 2 and isinstance(arr[0], list)):
            return None
        dic, root = arr[0], arr[1]
    except Exception:
        return None

    memo = {}

    def resolve(idx):
        if idx in memo:
            return memo[idx]
        tok = dic[idx]
        if not isinstance(tok, str):
            memo[idx] = tok
            return tok
        if len(tok) >= 2 and tok[1] == '|' and tok[0] in 'aonb':
            typ = tok[0]
            parts = tok.split('|')[1:]
            if typ == 'b':
                v = (parts[0] == 'T')
                memo[idx] = v
                return v
            if typ == 'n':
                v = _num(parts[0])
                memo[idx] = v
                return v
            if typ == 'a':
                arr_out = []
                memo[idx] = arr_out
                for p in parts:
                    arr_out.append(resolve(_b62(p)))
                return arr_out
            if typ == 'o':
                obj = {}
                memo[idx] = obj
                keys = resolve(_b62(parts[0]))
                if isinstance(keys, list):
                    for i, vref in enumerate(parts[1:]):
                        if i < len(keys):
                            obj[keys[i]] = resolve(_b62(vref))
                return obj
        memo[idx] = tok
        return tok

    try:
        return resolve(_b62(root))
    except Exception:
        return None


def _stat(pet_stats, key):
    v = pet_stats.get(key)
    if isinstance(v, dict):
        return v.get('current', v.get('base'))
    return v


def _describe_pet(meta, pet_uuid):
    pet = meta.get(pet_uuid)
    if not isinstance(pet, dict):
        return None
    st = pet.get('stats', {}) or {}
    name = _clean_emoji(pet.get('name') or (pet.get('info', {}) or {}).get('name') or '?')
    rank = ((pet.get('info', {}) or {}).get('rank', {}) or {}).get('name')
    level = st.get('level')
    hp = _stat(st, 'hp'); att = _stat(st, 'att'); mag = _stat(st, 'mag')
    pr = _stat(st, 'pr'); mr = _stat(st, 'mr'); wp = _stat(st, 'wp')

    parts = [f"{name}"]
    if rank:
        parts[0] += f" ({rank})"
    if level is not None:
        parts.append(f"L{level}")
    statbits = []
    for label, val in (("hp", hp), ("att", att), ("mag", mag), ("pr", pr), ("mr", mr), ("wp", wp)):
        if val is not None:
            statbits.append(f"{label}{val}")
    if statbits:
        parts.append("/".join(statbits))

    # Weapon: pet.stats.weapon (or pet.weapon) is a componentId -> weapon object in meta.
    wid = st.get('weapon') or pet.get('weapon')
    weapon = meta.get(wid) if isinstance(wid, str) else None
    if isinstance(weapon, dict):
        wname = weapon.get('name') or weapon.get('fullName') or '?'
        wrank = (weapon.get('rank', {}) or {}).get('name')
        wdesc = _clean_emoji(weapon.get('description'))
        wtxt = f"weapon: {wname}"
        if wrank:
            wtxt += f" [{wrank}]"
        if wdesc:
            wtxt += f' — "{wdesc}"'
        # Resolve passive effect descriptions (list of componentIds -> objects with description).
        passive_descs = []
        for pid in (weapon.get('passives') or []):
            pobj = meta.get(pid) if isinstance(pid, str) else None
            if isinstance(pobj, dict) and pobj.get('description'):
                pn = pobj.get('name') or ''
                passive_descs.append(_clean_emoji(f'{pn}: {pobj["description"]}'.strip(': ')))
        if passive_descs:
            wtxt += " | passives: " + "; ".join(passive_descs)
        parts.append(wtxt)
    else:
        parts.append("no weapon")

    return " · ".join(parts)


def summarize_battle(raw):
    """Turn a raw v2 battle-log into compact readable text for AI analysis. Returns the
    summary string, or None if the log can't be decoded."""
    battle = decode_v2(raw)
    if not isinstance(battle, dict):
        return None
    meta = battle.get('metadata', battle)
    info = meta.get('info', {}) if isinstance(meta, dict) else {}
    if not info:
        return None

    player = info.get('player', {}) or {}
    enemy = info.get('enemy', {}) or {}
    winner = info.get('winner')
    turns = info.get('turns')

    lines = []
    outcome = "LOSS" if winner == 'enemy' else ("WIN" if winner == 'player' else str(winner))
    lines.append(f"Result: {outcome} in {turns} turns.")
    if player.get('streak') is not None:
        lines.append(f"Your win streak at this battle: {player.get('streak')}.")

    lines.append(f"YOUR TEAM ({player.get('name', 'you')}):")
    for uid in (player.get('team') or []):
        desc = _describe_pet(meta, uid)
        if desc:
            lines.append(f"  - {desc}")

    lines.append(f"ENEMY TEAM ({enemy.get('name', 'enemy')}):")
    for uid in (enemy.get('team') or []):
        desc = _describe_pet(meta, uid)
        if desc:
            lines.append(f"  - {desc}")

    return "\n".join(lines)
