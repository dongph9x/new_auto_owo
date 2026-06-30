<div align="center">
  <h1>NeuraSelf</h1>
  
  <img src="https://readme-typing-svg.herokuapp.com/?font=Pacifico&size=40&pause=1000&color=FF0000&center=true&vCenter=true&random=false&width=600&lines=Advanced+OwO+Automation;Built+by+ROUTO" alt="NeuraSelf">
  
  <br/>
  <br/>

  <a href="https://discord.gg/XQS473Scfe">
    <img src="https://invidget.switchblade.xyz/XQS473Scfe" alt="Discord Community"/>
  </a>
  
  <br/>
  <br/>

  <img src="https://img.shields.io/badge/NeuraSelf-Advanced_Automation-red?style=for-the-badge&logo=discord&logoColor=white" />
  <img src="https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/License-Private-green?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Status-Active-success?style=for-the-badge" />
  
  <br/>
  <br/>

  <img src="https://img.shields.io/badge/discord.py--self-Latest-5865F2?style=flat-square&logo=discord&logoColor=white" />
  <img src="https://img.shields.io/badge/Flask-2.3.0-000000?style=flat-square&logo=flask&logoColor=white" />
  <img src="https://img.shields.io/badge/aiohttp-3.12.15-2C5BB4?style=flat-square&logo=aiohttp&logoColor=white" />

</div>

---

> [!IMPORTANT]
> WE ARE NOT responsible if you get banned using our selfbots. Selfbots are against Discord ToS and break OwO bot rules. Use only in private servers and do not openly share that you are using automation.

## What is NeuraSelf?

**NeuraSelf** is a powerful automation tool designed for Discord's OwO bot. It features human-like behavior, multi-layer security, and a premium web dashboard for real-time monitoring.

---

## Key Features

- **Auto HuntBot Solve**: Automatically solves HuntBot captchas using advanced image recognition.
- **AutoSolvers**: Solve-Captchas both Web captcha(Yes-Captcha Api paid) and letterimage captcha(onnx model free).
- **Advanced AutoGems**: Intelligent gem sets (Fabled/Legendary) or mixed tiers.
- **Mobile Support**: Fully functional on Android (Termux) with vibrations and toasts.
- **Multi-Account**: Run unlimited accounts simultaneously with independent configs.
- **Dynamic Quest Intelligence**: Auto-completes checklists and tracks progression.
- **Stealth**: Realistic typing simulation with mistakes and backspacing.
- **Premium Dashboard**: Real-time stats, charts, and live configuration editor.
- **Security System**: Auto-pauses on detection, captchas, or OwO captcha DMs.


---

## Installation

### Windows (PC)

1. Download & Install **Python 3.10+**.
2. Clone the repository:

    ```bash
    git clone https://github.com/routo-loop/neura-self
    cd neura-self
    ```

3. Install **Requirements** and Add **accounts**:

    ```bash
    python neura_setup.py
    ```

4. **Start the Bot:**

    ```bash
    python neura.py
    ```

### Android (Termux)

Please see the [MOBILE_GUIDE.md](MOBILE_GUIDE.md) file for detailed Termux instructions.

- **Requirement:** You must install the **Termux:API** app from F-Droid for mobile features to work.

---

## Configuration

NeuraSelf uses two main configuration files in the `config/` folder.

### 1. config/accounts.json (Multi-Account Setup)

This is where you define your accounts. You can add as many as you want!

**Template:**

```json
{
    "accounts": [
        {
            "token": "YOUR_FIRST_ACCOUNT_TOKEN",
            "channels": ["CHANNEL_ID_1", "CHANNEL_ID_2"],
            "enabled": true
        },
        {
            "token": "YOUR_SECOND_ACCOUNT_TOKEN",
            "channels": ["CHANNEL_ID_3", "CHANNEL_ID_4"],
            "enabled": true
        }
    ]
}
```

- **token**: Your Discord account token.

- **channels**: A list of Channel IDs to use. If you put multiple, the bot will rotate between them.
- **enabled**: Set to `true` to run this account, or `false` to skip it.

### 2. config/settings.json (Behavior)

This file controls the global settings for all bots.

- **Stealth**: Typing speed, mistake rates.
- **Cooldowns**: Custom delays between commands.
- **Features**: Enable/Disable Gem usage, Auto-Sell, etc.
- Then when you run your selfbot with token or tokens so it will create copy of settings.json
with id for specific account like settings_123456.json and it will create multiple if you have 
multiple accounts and then you can adjust settings for specific account.

---

## Dashboard

Once the bot is running, you can access the beautiful dashboard at:

**<http://localhost:8000>**

---

## Disclaimer

This tool is for **educational purposes only**. Using self-bots violates Discord's Terms of Service and may result in account termination.

<div align="center">

### NeuraSelf

**Advanced OwO Bot Grinder ** • Built by **ROUTO** • Made with ❤️

**Star this project if you find it useful!**

</div>
