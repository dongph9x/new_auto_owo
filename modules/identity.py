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

import re
import unicodedata

class IdentityManager:
    def __init__(self, bot):
        self.bot = bot
        self.generic_patterns = [
            "are you a real human", "complete your captcha",
            "verify that you are human", "please use the link below",
            "beep boop", "i am back with", "i will be back in",
            "please include your password"
        ] # these owo mssgs does not contain our name , and some for security 

    def clean_text(self, text):
        if not text: return ""
        clean = "".join(ch for ch in text if unicodedata.category(ch)[0] != 'C')
        clean = clean.replace('\u200b', '').replace('\u200c', '').replace('\u200d', '').replace('\ufeff', '')
        return clean.lower().strip()

    def _normalize(self, text):
        """Decorative Discord nicknames often use Unicode "fancy font" letters
        (Mathematical Alphanumeric Symbols etc.) that look like Latin letters but
        don't share a lowercase mapping with them, so plain .lower() leaves them
        untouched and identifier matching silently fails. NFKD decomposes them back
        to their plain Latin base (e.g. "\ud835\udd72\ud835\udd8e\ud835\udd86\u0301\ud835\udd92" -> "Giam"), which we then lowercase
        and strip punctuation from like before.
        """
        if not text: return ""
        decomposed = unicodedata.normalize('NFKD', text)
        no_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
        return re.sub(r'[^\w\s]', '', no_marks.lower()).strip()

    def get_clean_identifiers(self, message=None):
        """This account's name / display name / configured identifiers / guild
        nickname, all NFKD-normalized for matching. `message` is only needed to
        pick up the per-guild nickname."""
        idents = [self.bot.user.name, self.bot.display_name] + getattr(self.bot, 'identifiers', [])
        clean_idents = set()
        for i in idents:
            ci = self._normalize(i)
            if ci and len(ci) >= 2: clean_idents.add(ci)

        if message is not None and message.guild:
            member = message.guild.get_member(self.bot.user.id)
            if member and member.nick:
                clean_nick = self._normalize(member.nick)
                if clean_nick: clean_idents.add(clean_nick)
        return clean_idents

    def text_is_for_me(self, text, message=None):
        """Identity check against an already-extracted blob of text. Needed because
        OwO's newer Components V2 messages (battle results etc.) keep their text in
        `message.components` (TextDisplay), where `message.content`/`embeds` — the only
        places is_message_for_me looks — are empty. Callers that have already flattened
        the full message text (e.g. BattleLogger._full_text) use this instead."""
        norm = self._normalize(text)
        if not norm: return False
        for ident in self.get_clean_identifiers(message):
            if re.search(rf"\b{re.escape(ident)}\b", norm): return True
            if ident in norm and len(ident) > 3: return True
        return False

    def is_message_for_me(self, message, role="any", keyword=None):
        if not message: return False

        if self.bot.user.mentioned_in(message):
            return True
        clean_idents = self.get_clean_identifiers(message)

        content = self._normalize(message.content or "")
        if role == "header":
            first_line = content.split('\n')[0]
            header_texts = [first_line]
            if message.embeds:
                for em in message.embeds:
                    if em.title: header_texts.append(self._normalize(em.title))
                    if em.author and em.author.name: header_texts.append(self._normalize(em.author.name))
                    if em.description: header_texts.append(self._normalize(em.description.split('\n')[0]))
            
            for text in header_texts:
                for ident in clean_idents:
                    if re.search(rf"\b{re.escape(ident)}(?:'s)?\b", text): return True
            return False

        if role in ["source", "target"] and keyword:
            keyword = keyword.lower()
            if keyword in content:
                parts = content.split(keyword, 1)
                check_text = parts[0] if role == "source" else parts[1]
                for ident in clean_idents:
                    if re.search(rf"\b{re.escape(ident)}\b", check_text): return True
            return False
        texts = [content]
        if message.embeds:
            for em in message.embeds:
                fields_text = " ".join([f"{f.name} {f.value}" for f in em.fields])
                texts.append(self._normalize(f"{em.title or ''} {em.author.name if em.author else ''} {em.description or ''} {fields_text}"))

        for text in texts:
            for ident in clean_idents:
                if re.search(rf"\b{re.escape(ident)}\b", text, re.I):
                    return True
                if ident in text and len(ident) > 3:
                    return True

        full_visible_text = " ".join(texts)
        if any(pat in full_visible_text for pat in self.generic_patterns):
            ''' In dm, these are always for us. In guild, we assume they are for us 
            if we are mentioned or if any of our names appear'''
            if not message.guild or self.bot.user.mentioned_in(message):
                return True
            for ident in clean_idents:
                if ident in full_visible_text: return True
            return False

        return False
