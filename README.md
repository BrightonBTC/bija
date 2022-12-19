# Bija Nostr Client

Python [Nostr](https://github.com/nostr-protocol/nostr) client built with Flask and PyQT6

This is experimental software in early development and comes without warranty.

If you want to give it a test run you can find early releases for Linux (Windows and OSX versions intended at a later date) on the [releases page](https://github.com/BrightonBTC/bija/releases) 

Or, to get it up and running yourself: 

```
git clone https://github.com/BrightonBTC/bija
cd bija
pip install -r ./requirements.txt
python3 cli.py
```

Or additionally to the above you could compile using pyinstaller:
* This should theoretically also work for OSX but is untested (please let me know if you have success!). Bija currently has some dependencies that are incompatible with Windows though.
```
pyinstaller cli.py --onefile -w -F --add-data "bija/templates:bija/templates" --add-data "bija/static:bija/static" --name "bija-nostr-client-v0.0.2-alpha"

```
