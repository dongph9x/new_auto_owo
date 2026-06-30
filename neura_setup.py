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

import os
import sys
import subprocess
from importlib.metadata import version, PackageNotFoundError

def ensure_dependencies():
    target_hash = "20ae80b"
    try:
        if target_hash in version("discord.py-self"):
            return
    except:
        pass
    
    is_mobile = os.path.exists("/data/data/com.termux")
    print(f"\n[!] Missing or wrong library. Repairing (20ae80b)...")
    
    try:
        if is_mobile:
            subprocess.run(["pkg", "install", "git", "-y"], capture_output=True)
            
        subprocess.check_call([sys.executable, "-m", "pip", "uninstall", "-y", "discord.py", "discord.py-self"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.check_call([sys.executable, "-m", "pip", "install", "git+https://github.com/dolfies/discord.py-self@20ae80b398ec83fa272f0a96812140e14868c88"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("[+] Fixed. Restarting...\n")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        print(f"\n[X] Repair failed: {e}")
        print("[!] make sure git is installed.")
        print("[!] Try running: pip install git+https://github.com/dolfies/discord.py-self@20ae80b398ec83fa272f0a96812140e14868c88")
        input("\nPress Enter to exit...")
        sys.exit(1)

ensure_dependencies()

import asyncio
import json
import time
import platform
import re

def setup_ui_lib():
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        from rich.prompt import Prompt, Confirm
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
        return Console(), Table, Panel, Prompt, Confirm, Progress, SpinnerColumn, TextColumn, BarColumn
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "rich"], capture_output=True)
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        from rich.prompt import Prompt, Confirm
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
        return Console(), Table, Panel, Prompt, Confirm, Progress, SpinnerColumn, TextColumn, BarColumn

console, Table, Panel, Prompt, Confirm, Progress, SpinnerColumn, TextColumn, BarColumn = setup_ui_lib()

import core.state as state

neura_Ascii = """
 [red]      ▄      ▄███▄     ▄   █▄▄▄▄ ██  [/red]
 [red]      █      █▀   ▀     █  █  ▄▀ █ █ [/red]
 [red]      ██   █ ██▄▄    █   █ █▀▀▌  █▄▄█[/red]
 [red]      █ █  █ █▄   ▄▀ █   █ █  █  █  █[/red]
 [red]      █  █ █ ▀███▀   █▄ ▄█   █      █[/red]
 [red]      █   ██          ▀▀▀   ▀      █ [/red]
 [red]                                    ▀  [/red]
 [bold blue]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold blue]
 [bold cyan]   N E U R A   S E T U P      [+] Dev ROUTO (bot_1122) [+]   [/bold cyan]
 [bold blue]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold blue]
"""

def clean_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def is_termux():
    return os.path.exists("/data/data/com.termux")

async def verify_token(token, channel_ids=None):
    if not token or "." not in token:
        return False, "Invalid format", []
    
    import discord
    client = discord.Client()
    result = {"valid": False, "user": None, "channels": []}
    
    @client.event
    async def on_ready():
        result["valid"] = True
        result["user"] = f"{client.user.name}#{client.user.discriminator}" if client.user.discriminator != "0" else client.user.name
        
        if channel_ids:
            for cid in channel_ids:
                try:
                    ch = client.get_channel(int(cid))
                    if ch:
                        result["channels"].append(cid)
                except:
                    pass
        await client.close()

    try:
        await asyncio.wait_for(client.start(token), timeout=30)
    except asyncio.TimeoutError:
        await client.close()
        return False, "Validation Timeout", []
    except discord.LoginFailure:
        return False, "Invalid Token", []
    except Exception as e:
        return False, f"Error: {str(e)}", []

    if result["valid"]:
        return True, result["user"], result["channels"]
    return False, "Identity check failed", []

def run_bootstrap():
    clean_screen()
    console.print(neura_Ascii)
    
    mobile = is_termux()
    py_bin = sys.executable
    
    needed = []
    if os.path.exists("requirements.txt"):
        console.print("[cyan][*] Attempting to install requirements.txt...[/cyan]")
        try:
            content = ""
            for enc in ['utf-16', 'utf-8-sig', 'utf-8']:
                try:
                    with open("requirements.txt", "r", encoding=enc) as f:
                        content = f.read()
                    break
                except UnicodeError:
                    continue
            
            for line in content.splitlines():
                line = line.strip().replace('\x00', '')
                if line and not line.startswith("#"):
                    pkg = line.split("@")[0].split("==")[0].strip()
                    needed.append((pkg, line))
        except Exception as e:
            console.print(f"[red][!] Error reading requirements: {e}[/red]")

    heavy = [("numpy", "numpy"), ("pillow", "pillow"), ("onnxruntime", "onnxruntime")]
    for p, full in heavy:
        needed.append((p, p))

    to_install = []
    try:
        from importlib.metadata import distributions
        installed = {dist.metadata['Name'].lower().replace('-', '_') for dist in distributions()}
    except ImportError:
        import pkg_resources
        installed = {p.key.replace('-', '_') for p in pkg_resources.working_set}
    
    for name, full in needed:
        if name.lower().replace("-", "_") not in installed:
            to_install.append((name, full))

    if not to_install:
        console.print("[green][✓] Requirements already met. Environment is ready.[/green]")
        time.sleep(0.5)
        return

    if mobile:
        console.print("[yellow][*] Mobile detected. Preparing Termux environment...[/yellow]")
        subprocess.run(["pkg", "update", "-y"], capture_output=True)
        subprocess.run(["pkg", "upgrade", "-y"], capture_output=True)
        pkg_map = {"numpy": "python-numpy", "pillow": "python-pillow", "onnxruntime": "python-onnxruntime"}

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TextColumn("[progress.percentage]{task.percentage:>3.0f}%"), console=console) as prog:
        task = prog.add_task("Installing...", total=len(to_install))
        for name, full in to_install:
            prog.update(task, description=f"Processing {name}...")
            if mobile and name in pkg_map:
                subprocess.run(["pkg", "install", pkg_map[name], "-y"], capture_output=True)
            else:
                subprocess.run([py_bin, "-m", "pip", "install", full, "--quiet"], capture_output=True)
            prog.advance(task)

    console.print("\n[bold green][✓] Installed modules from requirements.txt successfully![/bold green]")
    time.sleep(1)



def load_accounts():
    path = os.path.join(state.CONFIG_DIR, 'accounts.json')
    if not os.path.exists(state.CONFIG_DIR): os.makedirs(state.CONFIG_DIR)
    if not os.path.exists(path): return []
    try:
        with open(path, 'r') as f:
            return json.load(f).get('accounts', [])
    except: return []

def save_accounts(acc_list):
    path = os.path.join(state.CONFIG_DIR, 'accounts.json')
    with open(path, 'w') as f:
        json.dump({"accounts": acc_list}, f, indent=4)

def show_accounts(acc_list):
    if not acc_list:
        console.print("[dim]You haven't added any accounts yet.[/dim]")
        return
    
    table = Table(border_style="red")
    table.add_column("No.", justify="center")
    table.add_column("Name")
    table.add_column("Token")
    table.add_column("Status", justify="center")

    for idx, acc in enumerate(acc_list):
        tk = acc['token']
        preview = f"{tk[:6]}...{tk[-4:]}" if len(tk) > 10 else tk
        active = "[green]Enabled[/green]" if acc.get('enabled', True) else "[red]Disabled[/red]"
        table.add_row(str(idx + 1), acc.get('name', 'User'), preview, active)
    
    console.print(table)

async def account_manager():
    accounts = load_accounts()
    while True:
        clean_screen()
        console.print(neura_Ascii)
        console.print("[bold white] ACCOUNT MANAGEMNT [/bold white]\n")
        show_accounts(accounts)
        
        console.print("\n[1] Add Account  [2] Remove  [3] Toggle  [4] Verify Tokens  [5] Back")
        act = Prompt.ask("\nAction", choices=["1", "2", "3", "4", "5"], default="5")
        
        if act == "1":
            name = Prompt.ask("Account Name (e.g. MainAccount)")
            token = Prompt.ask("Token").strip()
            if (token.startswith('"') and token.endswith('"')) or (token.startswith("'") and token.endswith("'")):
                token = token[1:-1]
            
            token_regex = r"^[A-Za-z0-9_\-\.]{24}\.[A-Za-z0-9_\-\.]{6}\.[A-Za-z0-9_\-\.]{27,}$"
            if not re.match(token_regex, token):
                console.print("[yellow][!] Warning: Token format looks unusual, but I'll save it anyway.[/yellow]")
                time.sleep(1)

            channels_raw = Prompt.ask("Channel IDs (space separated)")
            channel_ids = channels_raw.split()

            accounts.append({
                "name": name, 
                "token": token, 
                "channels": channel_ids, 
                "enabled": True
            })
            save_accounts(accounts)
            console.print("[bold green]Success! Account saved.[/bold green]")
            console.print("[dim]Use 'Verify Tokens' to check if it's active.[/dim]")
            time.sleep(2)
        elif act == "2":
            if not accounts: continue
            idx = int(Prompt.ask("ID to delete", default="1")) - 1
            if 0 <= idx < len(accounts):
                accounts.pop(idx)
                save_accounts(accounts)
                console.print("[red]Removed.[/red]")
            time.sleep(1)
        elif act == "3":
            if not accounts: continue
            idx = int(Prompt.ask("ID to toggle", default="1")) - 1
            if 0 <= idx < len(accounts):
                accounts[idx]['enabled'] = not accounts[idx].get('enabled', True)
                save_accounts(accounts)
            time.sleep(1)
        elif act == "4":
            if not accounts: continue
            
            console.print("\n[bold cyan]1.[/bold cyan] Verify All Enabled")
            console.print("[bold cyan]2.[/bold cyan] Verify Specific Account (by index)")
            v_choice = Prompt.ask("Choose", choices=["1", "2"], default="1")
            
            to_verify = []
            if v_choice == "1":
                to_verify = [(i, a) for i, a in enumerate(accounts) if a.get('enabled', True)]
            else:
                idx = int(Prompt.ask("Enter No.", default="1")) - 1
                if 0 <= idx < len(accounts):
                    to_verify = [(idx, accounts[idx])]
            
            if not to_verify:
                console.print("[yellow]No accounts to verify.[/yellow]")
                time.sleep(1)
                continue

            for idx, acc in to_verify:
                name = acc.get('name', f'Account {idx+1}')
                with console.status(f"[bold cyan]Verifying {name}..."):
                    try:
                        valid, user, v_channels = await verify_token(acc['token'], acc.get('channels', []))
                    except Exception as e:
                        valid, user, v_channels = False, str(e), []
                
                if valid:
                    console.print(f"[green][✓] {name}: Verified as {user}[/green]")
                    if v_channels:
                        acc['channels'] = v_channels  
                        save_accounts(accounts)
                else:
                    console.print(f"[red][!] {name}: Verification failed ({user})[/red]")
            
            input("\nVerification complete. Press Enter to return.")
        else: break

async def setup_menu():
    while True:
        clean_screen()
        console.print(neura_Ascii)
        
        console.print(" [bold cyan]1.[/bold cyan] Start NeuraSelf [dim][/dim]")
        console.print(" [bold cyan]2.[/bold cyan] Manage Accounts [yellow](Add/Edit your acc)[/yellow]")
        console.print(" [bold cyan]3.[/bold cyan] Repair Environment [yellow](Run this,if First time setup)(it install libraries)[/yellow]")
        console.print(" [bold cyan]4.[/bold cyan] Exit")
        
        choice = Prompt.ask("\nchoose : ", choices=["1", "2", "3", "4"], default="1")
        
        if choice == "1":
            console.print("\n[green][*] Running Neura-Self..[/green]")
            time.sleep(1)
            import neura
            await neura.main()
            break
        elif choice == "2":
            await account_manager()
        elif choice == "3":
            run_bootstrap()
            input("\nEverything is ready. Press Enter to go back.")
        else:
            console.print("\n[magenta]Thnkyou for using Neura-Self.[/magenta]")
            break

if __name__ == "__main__":
    run_bootstrap()
    asyncio.run(setup_menu())
