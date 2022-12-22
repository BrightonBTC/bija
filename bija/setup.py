import re

from bip39 import bip39

from bija.helpers import is_hex_key, is_bech32_key, bech32_to_hex64, hex64_to_bech32
from python_nostr.nostr.key import PrivateKey


PK = None
PW = None

class bcolors:
    OKGREEN = '\033[92m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'


def setup():
    global PK, PW
    complete = False
    step = 1
    while not complete:
        if step == 1:
            print('Enter your private key or type "new" to create a new one')
            pk = input('Private key:')
            if pk.lower() == 'new':
                step = 2
            elif is_hex_key(pk):
                step = 2
                PK = pk
            elif is_bech32_key('nsec', pk):
                step = 2
                PK = bech32_to_hex64('nsec', pk)
            else:
                print(f"{bcolors.FAIL}That doesn\'t seem to be a valid key, use hex or nsec{bcolors.ENDC}")
        if step == 2:
            print('Enter a password. This will encrypt your stored private key and be required for login.')
            pw = input('Password:')
            if len(pw) > 0:
                print('Password created. you can use it directly when starting bija with the flag --pw')
                PW = pw
                step = 3
        if step == 3:
            print('done')
            if PK is None:
                pk = PrivateKey()
            else:
                pk = PrivateKey(bytes.fromhex(PK))
            PK = pk.hex()
            public_key = pk.public_key.hex()

            print('-----------------')
            print("Setup complete. Please backup your keys. Both hex and bech 32, and mnemonic encodings are provided:")
            print("If your not sure which to use then we recommend backing them all up")
            print(f"{bcolors.OKGREEN}Share your PUBLIC key with friends{bcolors.ENDC}")
            print(f"{bcolors.OKGREEN}Never share your PRIVATE key with anyone. Keep it safe{bcolors.ENDC}")
            print('-----------------')
            print(f"{bcolors.OKGREEN}Private key:{bcolors.ENDC}")

            print(f"{bcolors.OKBLUE}Mnemonic{bcolors.ENDC} ", "{}{}:{}".format(bcolors.OKCYAN, bip39.encode_bytes(bytes.fromhex(PK)), bcolors.ENDC))
            print(f"{bcolors.OKBLUE}HEX{bcolors.ENDC} ", PK)
            print(f"{bcolors.OKBLUE}Bech32{bcolors.ENDC} ", hex64_to_bech32('nsec', PK))
            print('-----------------')
            print(f"{bcolors.OKGREEN}Public key:{bcolors.ENDC}")
            print(f"{bcolors.OKBLUE}HEX{bcolors.ENDC} ", public_key)
            print(f"{bcolors.OKBLUE}Bech32{bcolors.ENDC} ", hex64_to_bech32('npub', public_key))
            print('-----------------')

            finish = input("I've backed up my keys. Type (y) to continue.")
            if finish.lower().strip() == 'y':
                complete = True

    return PK, PW
