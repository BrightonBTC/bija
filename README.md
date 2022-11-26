Python/Flask [Nostr](https://github.com/nostr-protocol/nostr) client wrapped in QT 

This is experimental software in early development and comes without warranty.

If you want to give a try you can find an alpha release for Linux on the [releases page](https://github.com/BrightonBTC/bija/releases) 

Or, to get it up and running yourself you'll need to follow these steps: 


1) clone the repo and open it in a python 3.10 virtual env (using PyCharm or similar)

`git clone https://github.com/BrightonBTC/bija`

2) create a submodule for python-nostr and rename the dir

`cd bija`

`git submodule add https://github.com/BrightonBTC/python-nostr`

`git mv python-nostr/ python_nostr/`

3) install requirements

`pip install -r ../requirements.txt`

4) you may also need to install requirements for python-nostr

`pip install -r ../python_nostr/requirements.txt`

5) run cli.py

`python3 cli.py`
