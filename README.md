# ⚠️ This Repository Has Moved

> **This repository (`VRRAPI-HACS`) is now archived and no longer maintained.**

---

## 🚀 New Repository

All development continues at:

### **[NerdySoftPaw/hacs-publictransport](https://github.com/NerdySoftPaw/hacs-publictransport)**

[![GitHub Release](https://img.shields.io/github/release/NerdySoftPaw/hacs-publictransport.svg?style=for-the-badge)](https://github.com/NerdySoftPaw/hacs-publictransport/releases)
[![Documentation](https://img.shields.io/badge/docs-readthedocs-blue.svg?style=for-the-badge)](https://hacs-publictransport.readthedocs.io/)

---

## 📦 Migration Guide

Your configuration will be **automatically preserved**. Just follow these steps:

### Step 1: Add the New Repository

1. Open **HACS** → **Integrations**
2. Click the three dots (⋮) in the top right corner
3. Select **Custom repositories**
4. Add the URL:
   ```
   https://github.com/NerdySoftPaw/hacs-publictransport
   ```
5. Select type: **Integration**
6. Click **ADD**

### Step 2: Download the New Version

1. Search for "Public Transport" in HACS
2. Click on **Public Transport Departures**
3. Click **Download**

### Step 3: Remove the Old Repository (Optional)

1. In HACS, find the old "VRR" entry
2. Click the three dots (⋮) → **Remove**

### Step 4: Restart Home Assistant

Go to **Settings** → **System** → **Restart**

### Done! ✅

Your sensors, configuration, and history are preserved automatically.

---

## 🆕 What's New in the New Repository?

| Feature | Old (VRRAPI-HACS) | New (hacs-publictransport) |
|---------|-------------------|----------------------------|
| **Providers** | VRR only | VRR, KVV, HVV, Trafiklab, NTA |
| **Countries** | 🇩🇪 Germany | 🇩🇪 🇸🇪 🇮🇪 Germany, Sweden, Ireland |
| **Fuzzy Search** | ❌ | ✅ Typo-tolerant stop search |
| **API Caching** | ❌ | ✅ 5-minute cache |
| **Documentation** | GitHub only | [ReadTheDocs](https://hacs-publictransport.readthedocs.io/) |

---

## 📚 Documentation

Full documentation is available at:

**https://hacs-publictransport.readthedocs.io/**

---

## ❓ Support

For issues with the **new** repository:
- 🐛 [Issue Tracker](https://github.com/NerdySoftPaw/hacs-publictransport/issues)
- 💬 [Discussions](https://github.com/NerdySoftPaw/hacs-publictransport/discussions)

---

**Thank you for using this integration!** 🚉
