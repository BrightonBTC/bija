# Bija Nostr Client

Python [Nostr](https://github.com/nostr-protocol/nostr) client with backend that runs on a local flask server, and front end in your browser

*nb. earlier versions of Bija opened a Qt window. That's not currently available, you can only load the UI in a browser at this time.*

This is experimental software in early development and comes without warranty.

### Native Setup :snake:	

If you want to give it a test run you can find early releases for Linux (Windows and OSX versions intended at a later date) on the [releases page](https://github.com/BrightonBTC/bija/releases) 

Or, to get it up and running yourself: 

```
git clone --recurse-submodules https://github.com/BrightonBTC/bija
cd bija
pip install -r ./requirements.txt
python3 cli.py
```
*nb. requires python3.10+*

You can now access bija at http://localhost:5000

In the event that something else is running on port 5000 you can pass `--port XXXX` to cli.py and if you want to use/create a different db, for example if you want to manage multiple accounts then use `--db name` (default is called bija)

eg.

```
python3 cli.py --port 5001 --db mydb
```
Or additionally to the above you could compile using pyinstaller:
* This should theoretically also work for OSX but is untested (please let me know if you have success!). Bija currently has some dependencies that are incompatible with Windows though.
```
pyinstaller cli.py --onefile -w -F --add-data "bija/templates:bija/templates" --add-data "bija/static:bija/static" --name "bija-nostr-client"

```
### Docker Setup :whale2:

To setup Bija with docker, first clone the project:
```
git clone --recurse-submodules https://github.com/BrightonBTC/bija
cd bija
```

> **Warning**
> If you don't clone with --recurse-submodules, you must run git submodules update

Then just run docker-compose up and access Bija through the browser

```
docker-compose up
```

You can now access bija at http://localhost:5000

Enjoy :grinning: