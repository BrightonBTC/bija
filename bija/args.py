import argparse

from bija.setup import setup

SETUP_PK = None
SETUP_PW = None

parser = argparse.ArgumentParser()

parser.add_argument("-s", "--setup", dest="setup", help="Load or create a new profile (private/public key pair)",
                    action='store_true')
parser.add_argument("-p", "--port", dest="port", help="Set the port,  default is 5000", default=5000, type=int)
parser.add_argument("-db", "--db", dest="db", help="Set the database - eg. {name}.sqlite,  default is bija",
                    default='bija', type=str)

args = parser.parse_args()

if args.setup:
    SETUP_PK, SETUP_PW = setup()
