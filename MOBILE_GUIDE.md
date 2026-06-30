# NeuraSelf - Mobile Guide (Termux)

Run NeuraSelf on your Android phone with ease using Termux. Follow these simple steps to get started!

## 1. Pre requirements

Before starting, you **MUST** install these two apps from F-Droid (do NOT use Play Store):

1. **[Termux App](https://f-droid.org/repo/com.termux_118.apk)** (The Terminal)
2. **[Termux:API App](https://f-droid.org/en/packages/com.termux.api/)** (For Notifications/Vibration)

> [!IMPORTANT]
> After installing **Termux:API**, go to your Phone Settings > Apps > Termux:API and ensure **Notifications Permission** is granted.

---

## 2. Fast Installation

Open **Termux** and copy-paste this entire block to set everything up at once:

```bash
pkg update && pkg upgrade -y && termux-setup-storage && pkg install python -y && pkg install git -y && pkg install termux-api -y && cd storage/downloads && git clone https://github.com/routo-loop/neura-self && cd neura-self && python neura_setup.py && python neura.py
```

*When it asks for storage permission, click **Allow**.*

---

## 3. How to Re-run

Next time you want to start the bot, simply run:

```bash
cd storage/downloads/neura-self && python neura.py
```

---

## 4. Mobile Settings

To get the most out of your mobile experience (Vibrations/Notifications), make sure `config/settings.json` has these enabled:

```json
"mobile": {
    "enabled": true,
    "toast": {
        "enabled": true,
        "position": "middle"
    },
    "vibrate": {
        "enabled": true,
        "time": 0.5
    }
}
```

* **Toast:** Shows popup alerts on your screen.
* **Vibrate:** Your phone will vibrate when a **Captcha** or **Ban** is detected!
