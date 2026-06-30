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

import asyncio
import random
import time
import traceback

class NeuraHuman:
    last_break_check = time.time()
    break_lock = asyncio.Lock()
    is_on_break = False
    
    @staticmethod
    async def neura_send(bot, channel, content):
        start_time = time.time()
        
        if NeuraHuman.is_on_break:
            bot.log("STEALTH", "Waiting for existing break to finish...")
            while NeuraHuman.is_on_break:
                await asyncio.sleep(1)
        
        stealth_cfg = bot.config.get('stealth', {})
        hb_cfg = stealth_cfg.get('human_break', {})
        hb_enabled = hb_cfg.get('enabled', True)
        hb_duration = hb_cfg.get('duration_min', 10) * 60
        hb_interval = hb_cfg.get('interval_min', 45) * 60

        runtime = time.time() - NeuraHuman.last_break_check
        if hb_enabled and runtime > hb_interval: 
            async with NeuraHuman.break_lock:
                if time.time() - NeuraHuman.last_break_check > hb_interval and not NeuraHuman.is_on_break:
                    NeuraHuman.is_on_break = True
                    start_break_time = time.time()
                    bot.log("STEALTH", f"Pausing for {int(hb_duration/60)}mins for human behaviour (Break Time)")
                    try:
                        while NeuraHuman.is_on_break:
                            curr_stealth = bot.config.get('stealth', {})
                            curr_hb = curr_stealth.get('human_break', {})
                            
                            if not curr_hb.get('enabled', True):
                                bot.log("STEALTH", "Break interrupted: Human Break disabled in settings.")
                                break
                            
                            curr_duration = curr_hb.get('duration_min', 10) * 60
                            if time.time() - start_break_time >= curr_duration:
                                break
                                
                            await asyncio.sleep(1)
                    finally:
                        NeuraHuman.last_break_check = time.time()
                        NeuraHuman.is_on_break = False
                        bot.log("STEALTH", "Break finished. Resuming operations.")
                elif NeuraHuman.is_on_break:
                     while NeuraHuman.is_on_break:
                        await asyncio.sleep(1)

        stealth_cfg = bot.config.get('stealth', {})
        if not isinstance(stealth_cfg, dict):
            stealth_cfg = {}
        config = stealth_cfg.get('typing', {})
        if not isinstance(config, dict):
            config = {}

        if not config.get('enabled', False):
            try:
                await channel.send(content)
                return True
            except:
                return False
        
        reaction_min = config.get('reaction_min', 1.0)
        reaction_max = config.get('reaction_max', 3.0)
        mistake_rate = config.get('mistake_rate', 5)
        extra_delay = config.get('extra_delay', 0)
        
        if isinstance(mistake_rate, (int, float)) and mistake_rate > 1:
            mistake_rate /= 100.0

        reaction_time = random.uniform(reaction_min if isinstance(reaction_min, (int, float)) else 1.0, 
                                       reaction_max if isinstance(reaction_max, (int, float)) else 3.0)
        if reaction_time > 0.1:
            await asyncio.sleep(reaction_time)

        try:
            async with channel.typing():
                chars = list(str(content))
                i = 0
                typo_count = 0
                
                start_time = time.time()
                
                while i < len(chars):
                    if bot.paused:
                        return False
                    char = chars[i]
                    delay = random.uniform(0.02, 0.08)
                    if char in ".,!?;": delay += random.uniform(0.1, 0.2)
                    
                    if isinstance(mistake_rate, (int, float)) and random.random() < mistake_rate and i < len(chars) - 1:
                        typo_count += 1
                        await asyncio.sleep(random.uniform(0.1, 0.2)) 
                        await asyncio.sleep(random.uniform(0.2, 0.5))
                        await asyncio.sleep(random.uniform(0.1, 0.2))
                    
                    await asyncio.sleep(delay)
                    i += 1
                
                enter_delay = random.uniform(0.3, 0.7) + (random.uniform(0, extra_delay) if isinstance(extra_delay, (int, float)) and extra_delay > 0 else 0)
                await asyncio.sleep(enter_delay)
                
                total_time = round(time.time() - start_time, 2)
                if typo_count > 0:
                    bot.log("STEALTH", f"Typing: {total_time}s (Simulated {typo_count} typos)")
                
                await channel.send(content)
                return True
        except Exception:
            try:
                await channel.send(content)
                return True
            except Exception as final_e:
                bot.log("ERROR", f"Critical send failure: {final_e}")
                return False
    
    @staticmethod
    def neura_calculate_typing_speed(text, wpm=55):
        return (len(text) / 5) / wpm * 60