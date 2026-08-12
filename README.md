# Google Photos Downloader: Bulk Export Your Photos

> A Python desktop app that bulk downloads Google Photos from a spreadsheet of links. Parallel downloads, automatic retries, duplicate detection and a simple Tkinter interface. No command line required.

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Tkinter GUI](https://img.shields.io/badge/GUI-Tkinter-4584b6?style=for-the-badge)](https://docs.python.org/3/library/tkinter.html)
[![Platform](https://img.shields.io/badge/Platform-Windows_|_macOS_|_Linux-lightgrey?style=for-the-badge)](#)

## What it does

Exporting a large photo library one file at a time is painful, and Google Takeout gives you archives rather than the specific set you actually want. This tool takes a spreadsheet of photo links and downloads every one of them in parallel into a folder you choose, with a live progress log.

## Features

- **Bulk downloads**: point it at a CSV or Excel file of links and walk away
- **Parallel transfers**: multi-threaded downloading, far faster than sequential
- **Duplicate detection**: hash-based checking so the same photo is never saved twice
- **Automatic retries**: transient network failures are retried rather than dropped
- **Live progress**: real-time progress bar and scrolling log inside the app
- **Full logging**: every run writes a timestamped log file for auditing
- **Desktop GUI**: file pickers and buttons, no terminal needed

## Getting started

### Prerequisites

- Python 3.9 or newer

### Installation

```bash
git clone https://github.com/AnubhavChaturvedi-GitHub/google-photos-downloader.git
cd google-photos-downloader
pip install requests pandas
```

### Run it

```bash
python auto.py
```

## Usage

1. Prepare a spreadsheet (CSV or Excel) with a column of photo URLs.
2. Launch the app and select that file.
3. Choose the destination folder.
4. Click start and watch the progress log.

Finished files land in your chosen folder, and a `photo_downloader_<timestamp>.log` records exactly what happened.

## Build a standalone executable

An `auto.spec` file is included for PyInstaller:

```bash
pip install pyinstaller
pyinstaller auto.spec
```

The packaged app appears in `dist/`.

## Tech stack

Python, Tkinter, Requests, pandas, ThreadPoolExecutor, hashlib.

## Note

Use this only to download photos you own or have permission to access. Respect Google's terms of service.

## Contributing

Issues and pull requests are welcome.

## License

See the repository license file.

## Author

**Anubhav Chaturvedi**, founder of [NetHyTech](https://www.youtube.com/@NetHyTech), a developer community of 30,000+ members.

[![YouTube](https://img.shields.io/badge/YouTube-NetHyTech-FF0000?style=flat-square&logo=youtube&logoColor=white)](https://www.youtube.com/@NetHyTech)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0A66C2?style=flat-square&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/anubhav-chaturvedi-/)

If this project saved you time, a star on the repo helps other people find it.
