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


def _pet_name_map(meta, info):
    """uuid -> readable label like 'Your bee' / 'Enemy gfish', disambiguated when two
    pets share a name."""
    labels = {}
    counts = {}
    for side, tag in (('player', 'Your'), ('enemy', 'Enemy')):
        for uid in (info.get(side, {}) or {}).get('team', []) or []:
            pet = meta.get(uid, {})
            name = _clean_emoji(pet.get('name') or (pet.get('info', {}) or {}).get('name') or '?')
            key = (tag, name)
            counts[key] = counts.get(key, 0) + 1
            label = f"{tag} {name}"
            if counts[key] > 1:
                label += f"#{counts[key]}"
            labels[uid] = label
    return labels


def _unwrap_log(entry):
    # A decoded log entry sometimes comes wrapped as {'metadata': <entry>}.
    if isinstance(entry, dict) and 'result' not in entry and 'metadata' in entry:
        return entry['metadata']
    return entry


def _iter_log_entries(battle):
    """Yield every decoded combat log entry (with its result dict) across all turns."""
    for turn in battle if isinstance(battle, list) else []:
        if not isinstance(turn, dict):
            continue
        for step in (turn.get('steps') or []):
            if not isinstance(step, dict):
                continue
            for e in (step.get('logs') or []):
                e = _unwrap_log(e)
                if isinstance(e, dict) and isinstance(e.get('result'), dict):
                    yield e


def _combat_stats(battle, meta, side_of, names):
    """Aggregate numbers the player asked to see: total base damage and total healing per
    side, and the single biggest hit — flagging whether it was a normal attack
    (componentId == 1) or came from a weapon/passive."""
    dmg = {'player': 0, 'enemy': 0}
    hp_heal = {'player': 0, 'enemy': 0}   # HP recovered (heal actions + mid-hit regen)
    wp_recover = {'player': 0, 'enemy': 0}  # WP/MP replenished (e.g. Energize passive)
    biggest = None            # (base, src, tgt, kind)
    biggest_weapon = None     # biggest hit that came from a weapon/passive (not a normal attack)

    for e in _iter_log_entries(battle):
        res = e['result']
        at = res.get('actionType')
        src_id = res.get('source') or e.get('source')
        tgt_id = res.get('target') or e.get('target')
        ts = res.get('targetStat') or {}
        prev, curr = ts.get('prev'), ts.get('curr')
        delta = (curr - prev) if isinstance(prev, (int, float)) and isinstance(curr, (int, float)) else None

        if at == 'damage':
            base = res.get('baseValue')
            comp = res.get('componentId')
            tag = (res.get('tag') or e.get('tag') or '').upper()
            s_side = side_of.get(src_id)
            if isinstance(base, (int, float)) and s_side in dmg:
                dmg[s_side] += base
                # A PHYS/MAGIC tag means an ordinary swing (even if the pet holds a weapon,
                # so componentId is that weapon's id). Only a different tag is a real
                # weapon/passive damage proc (a DoT like burn/poison, or a weapon active).
                if tag in ('PHYS', 'MAGIC', 'PHYSICAL', 'MAGICAL') or comp == 1 or comp == '1':
                    kind = "normal attack"
                else:
                    wobj = meta.get(comp) if isinstance(comp, str) else None
                    wname = (wobj.get('name') if isinstance(wobj, dict) else None) or tag or 'weapon/passive'
                    kind = f"{_clean_emoji(wname)} (weapon/passive)"
                hit = (base, names.get(src_id, '?'), names.get(tgt_id, '?'), kind)
                if biggest is None or base > biggest[0]:
                    biggest = hit
                if kind != "normal attack" and (biggest_weapon is None or base > biggest_weapon[0]):
                    biggest_weapon = hit
            # A target that NET-gained hp during a hit regenerated — credit its side (HP).
            if delta and delta > 0:
                t_side = side_of.get(tgt_id)
                if t_side in hp_heal:
                    hp_heal[t_side] += delta
        elif at == 'heal':
            if delta and delta > 0:
                t_side = side_of.get(tgt_id)
                if t_side in hp_heal:
                    hp_heal[t_side] += delta
        elif at == 'replenish':
            # WP/MP replenished (targetStat here is WP, not HP).
            if delta and delta > 0:
                t_side = side_of.get(tgt_id)
                if t_side in wp_recover:
                    wp_recover[t_side] += delta

    lines = ["COMBAT STATS:"]
    lines.append(f"  Total base damage dealt — You: {dmg['player']} | Enemy: {dmg['enemy']}")
    lines.append(f"  Total HP healed/regenerated — You: {hp_heal['player']} | Enemy: {hp_heal['enemy']}")
    lines.append(f"  Total WP replenished — You: {wp_recover['player']} | Enemy: {wp_recover['enemy']}")
    if biggest:
        lines.append(f"  Biggest single hit: {biggest[1]} → {biggest[2]}, base {biggest[0]} — {biggest[3]}")
    if biggest_weapon:
        lines.append(f"  Biggest weapon/passive hit: {biggest_weapon[1]} → {biggest_weapon[2]}, base {biggest_weapon[0]} — {biggest_weapon[3]}")
    else:
        lines.append("  Biggest weapon/passive hit: none — all damage came from normal attacks")
    return lines


_NORMAL_TAGS = ('PHYS', 'MAGIC', 'PHYSICAL', 'MAGICAL')


def _damage_taken_per_pet(battle):
    """Gross HP each pet lost to incoming damage (sum of negative net deltas on damage
    hits). Used to judge how well a heal passive kept up with the punishment."""
    taken = {}
    for e in _iter_log_entries(battle):
        res = e['result']
        if res.get('actionType') != 'damage':
            continue
        tgt = res.get('target') or e.get('target')
        ts = res.get('targetStat') or {}
        prev, curr = ts.get('prev'), ts.get('curr')
        if isinstance(prev, (int, float)) and isinstance(curr, (int, float)) and curr < prev:
            taken[tgt] = taken.get(tgt, 0) + (prev - curr)
    return taken


def _effect_breakdown(battle, meta, side_of, names):
    """Break results down by the specific passive/weapon effect, and judge its in-battle
    effectiveness (e.g. a heal vs how much damage its target took), so the AI can weigh how
    much each passive actually mattered — single-target vs whole-team, kept up or not."""
    taken = _damage_taken_per_pet(battle)
    groups = {}  # (side, name, kind, unit) -> {'amount','procs','targets':set,'target_ids':set}

    for e in _iter_log_entries(battle):
        res = e['result']
        at = res.get('actionType')
        tag = (res.get('tag') or e.get('tag') or '')
        is_passive_dmg = (at == 'damage' and tag.upper() not in _NORMAL_TAGS)
        if at not in ('heal', 'replenish', 'apply_buff') and not is_passive_dmg:
            continue
        comp = res.get('buffComponentId') or res.get('componentId')
        obj = meta.get(comp) if isinstance(comp, str) else None
        name = (obj.get('name') if isinstance(obj, dict) else None) or tag or 'effect'
        name = _clean_emoji(name)
        src = res.get('source') or e.get('source')
        tgt = res.get('target') or e.get('target')
        side = side_of.get(src) or side_of.get(tgt)
        ts = res.get('targetStat') or {}
        prev, curr = ts.get('prev'), ts.get('curr')
        delta = (curr - prev) if isinstance(prev, (int, float)) and isinstance(curr, (int, float)) else None

        if at == 'heal':
            kind = 'healed'
            unit = 'HP'
            amt = delta if delta and delta > 0 else 0
        elif at == 'replenish':
            kind = 'replenished'
            unit = 'WP'
            amt = delta if delta and delta > 0 else 0
        elif at == 'apply_buff':
            kind = 'buff'
            unit = ''
            amt = 0
        else:
            kind = 'DoT dmg'
            unit = 'base'
            amt = res.get('baseValue') if isinstance(res.get('baseValue'), (int, float)) else 0

        key = (side, name, kind, unit)
        g = groups.setdefault(key, {'amount': 0, 'procs': 0, 'targets': set(), 'target_ids': set()})
        g['amount'] += amt
        g['procs'] += 1
        if tgt in names:
            g['targets'].add(names[tgt])
        if tgt is not None:
            g['target_ids'].add(tgt)

    if not groups:
        return []

    # 1) Full listing first — every passive/weapon effect and what it did.
    listing = ["PASSIVE & WEAPON EFFECTS:"]
    # 2) Then a separate effectiveness read on those effects.
    effectiveness = []
    for (side, name, kind, unit), g in sorted(groups.items(), key=lambda kv: (kv[0][0] or '', -kv[1]['amount'])):
        who = 'You' if side == 'player' else ('Enemy' if side == 'enemy' else '?')
        tgts = sorted(g['targets'])
        scope = tgts[0] if len(tgts) == 1 else (f"whole team ({', '.join(tgts)})" if len(tgts) > 1 else "?")
        if unit:
            listing.append(f"  {who} {name} — {kind} {g['amount']} {unit} ({g['procs']}x) → {scope}")
        else:
            listing.append(f"  {who} {name} — {kind} ({g['procs']}x) → {scope}")

        # Effectiveness: for a heal, how much of the target's incoming damage it offset.
        if kind == 'healed' and g['amount'] > 0:
            dmg_on_targets = sum(taken.get(tid, 0) for tid in g['target_ids'])
            if dmg_on_targets > 0:
                pct = round(100 * g['amount'] / dmg_on_targets)
                verdict = "kept up with the damage" if pct >= 80 else (
                    "helped but not enough" if pct >= 40 else "far too little to matter")
                span = scope if len(tgts) == 1 else f"its targets ({', '.join(tgts)})"
                effectiveness.append(
                    f"  {who} {name}: healed {g['amount']} HP vs {dmg_on_targets} HP damage taken "
                    f"by {span} → offset {pct}% ({verdict})")

    lines = list(listing)
    if effectiveness:
        lines.append("PASSIVE EFFECTIVENESS:")
        lines.extend(effectiveness)
    return lines


def _key_events(battle, meta, info, names, side_of):
    """Surface the signals that explain a loss: which of your pets died and when (and
    whether it was a one-turn burst), whether a weapon-pet ran out of WP to use its weapon
    (mana starvation), and any crowd-control (stun/taunt/debuff) the enemy landed on you."""
    turns = [t for t in battle if isinstance(t, dict) and isinstance(t.get('state'), dict)]
    turns.sort(key=lambda t: t.get('turn', 0) if isinstance(t.get('turn'), int) else 0)
    player_ids = (info.get('player', {}) or {}).get('team', []) or []

    deaths, mana, cc = [], [], []

    for uid in player_ids:
        nm = names.get(uid, '?')
        maxhp = None
        prev = None
        for t in turns:
            hp = (t['state'].get(uid) or {}).get('hp')
            if not isinstance(hp, (int, float)):
                continue
            if maxhp is None:
                maxhp = hp
            if hp == 0:
                tn = t.get('turn')
                if prev is not None and maxhp and prev > 0.5 * maxhp:
                    deaths.append(f"{nm} died turn {tn} ({prev}→0 HP in one turn — burst)")
                else:
                    deaths.append(f"{nm} died turn {tn}")
                break
            prev = hp

    # Gather every WP observation per pet (turn- AND step-level states) and count how many
    # times each pet actually fired its weapon — a weapon that fired wasn't mana-starved.
    wp_seen = {}
    weapon_fires = {}
    for t in turns:
        for uid, sv in (t.get('state') or {}).items():
            if isinstance(sv, dict) and isinstance(sv.get('wp'), (int, float)):
                wp_seen.setdefault(uid, []).append(sv['wp'])
        for step in (t.get('steps') or []):
            if isinstance(step, dict):
                for uid, sv in (step.get('state') or {}).items():
                    if isinstance(sv, dict) and isinstance(sv.get('wp'), (int, float)):
                        wp_seen.setdefault(uid, []).append(sv['wp'])
    for e in _iter_log_entries(battle):
        res = e['result']
        if res.get('actionType') in ('use_wp', 'apply_buff'):
            src = res.get('source') or e.get('source')
            weapon_fires[src] = weapon_fires.get(src, 0) + 1

    for uid in player_ids:
        pet = meta.get(uid, {})
        st = pet.get('stats', {}) or {}
        wid = st.get('weapon') or pet.get('weapon')
        weapon = meta.get(wid) if isinstance(wid, str) else None
        if not isinstance(weapon, dict):
            continue
        cost = weapon.get('manaCost')
        wps = wp_seen.get(uid) or []
        nm = names.get(uid, '?')
        wn = _clean_emoji(weapon.get('name') or 'weapon')
        fires = weapon_fires.get(uid, 0)
        wp_hi = max(wps) if wps else '?'
        if fires > 0:
            mana.append(f"{nm}: used {wn} {fires}x (WP up to {wp_hi}, cost {cost}) — mana OK")
        elif isinstance(cost, (int, float)) and wps and max(wps) < cost:
            mana.append(f"{nm}: never used {wn} — WP capped at {wp_hi} < {cost} cost → mana-starved")
        else:
            mana.append(f"{nm}: did not use {wn} (WP up to {wp_hi}, cost {cost})")

    for e in _iter_log_entries(battle):
        res = e['result']
        if res.get('actionType') != 'apply_buff':
            continue
        bid = res.get('buffComponentId') or res.get('componentId')
        bobj = meta.get(bid) if isinstance(bid, str) else None
        if not isinstance(bobj, dict):
            continue
        if bobj.get('stun') or bobj.get('taunting') or bobj.get('debuff'):
            tgt = res.get('target')
            if side_of.get(tgt) == 'player':  # crowd control landed on us
                kind = 'stun' if bobj.get('stun') else ('taunt' if bobj.get('taunting') else 'debuff')
                cc.append(f"{names.get(res.get('source'), '?')} {kind}'d {names.get(tgt, '?')} with {_clean_emoji(bobj.get('name') or '')}")

    if not (deaths or mana or cc):
        return []
    lines = ["KEY EVENTS (your side):"]
    for d in deaths:
        lines.append(f"  {d}")
    for m in mana:
        lines.append(f"  Mana — {m}")
    if cc:
        for c in cc:
            lines.append(f"  CC — {c}")
    else:
        lines.append("  CC — enemy landed no stun/taunt/debuff on you")
    return lines


def _narrate_battle(battle, meta, names, max_lines=60):
    """Turn-by-turn combat lines: who hit whom for how much, heals, and buffs/effects —
    using the clean prev/curr HP snapshots (no float decoding needed)."""
    lines = []
    for turn in battle if isinstance(battle, list) else []:
        if not isinstance(turn, dict) or turn.get('initial'):
            continue
        tnum = turn.get('turn')
        turn_lines = []
        for step in (turn.get('steps') or []):
            if not isinstance(step, dict):
                continue
            for e in (step.get('logs') or []):
                e = _unwrap_log(e)
                if not isinstance(e, dict):
                    continue
                res = e.get('result') or {}
                if not isinstance(res, dict):
                    continue
                at = res.get('actionType')
                tag = res.get('tag') or e.get('tag') or ''
                src = names.get(res.get('source') or e.get('source'), '?')
                tgt = names.get(res.get('target') or e.get('target'), '?')
                ts = res.get('targetStat') or {}
                prev, curr = ts.get('prev'), ts.get('curr')
                delta = None
                if isinstance(prev, (int, float)) and isinstance(curr, (int, float)):
                    delta = curr - prev
                # HP transition prev->curr is always accurate; show a signed Δ and let the
                # reader interpret (net includes any regen that fired the same step).
                d = f" (Δ{'+' if delta and delta > 0 else ''}{delta})" if delta is not None else ""
                if at == 'damage':
                    dt = res.get('damageType', '')
                    base = res.get('baseValue')
                    base_s = f", base {base}" if isinstance(base, (int, float)) else ""
                    turn_lines.append(f"{src} → {tgt} {dt} hit: hp {prev}→{curr}{d}{base_s}")
                elif at == 'heal':
                    turn_lines.append(f"{tgt} healed [{tag}]: hp {prev}→{curr}{d}")
                elif at == 'apply_buff':
                    bid = res.get('buffComponentId') or res.get('componentId')
                    bobj = meta.get(bid) if isinstance(bid, str) else None
                    bname = (bobj.get('name') if isinstance(bobj, dict) else None) or res.get('tag') or 'buff'
                    dur = res.get('duration')
                    dur_s = f" {dur}t" if dur else ""
                    turn_lines.append(f"{src} applied {_clean_emoji(bname)} to {tgt}{dur_s}")
        if turn_lines:
            lines.append(f"Turn {tnum}:")
            lines.extend("  " + l for l in turn_lines)
        if len(lines) >= max_lines:
            lines.append("  ... (truncated)")
            break
    return lines


def summarize_battle(raw):
    """Turn a raw v2 battle-log into compact readable text for AI analysis. Returns the
    summary string, or None if the log can't be decoded."""
    decoded = decode_v2(raw)
    if not isinstance(decoded, dict):
        return None
    meta = decoded.get('metadata', decoded)
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

    # Turn-by-turn combat + the aggregate stats the player wants (totals, biggest hit).
    battle_turns = decoded.get('battle')
    if battle_turns:
        names = _pet_name_map(meta, info)
        side_of = {}
        for side in ('player', 'enemy'):
            for uid in (info.get(side, {}) or {}).get('team', []) or []:
                side_of[uid] = side
        lines.extend(_combat_stats(battle_turns, meta, side_of, names))
        lines.extend(_effect_breakdown(battle_turns, meta, side_of, names))
        lines.extend(_key_events(battle_turns, meta, info, names, side_of))
        narration = _narrate_battle(battle_turns, meta, names)
        if narration:
            lines.append("COMBAT LOG:")
            lines.extend(narration)

    return "\n".join(lines)
