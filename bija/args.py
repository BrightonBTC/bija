import argparse
import logging

from bija.setup import setup

SETUP_PK = None
SETUP_PW = None
LOGGING_LEVEL = logging.ERROR

parser = argparse.ArgumentParser()

parser.add_argument("-s", "--setup", dest="setup", help="Load or create a new profile (private/public key pair)",
                    action='store_true')
parser.add_argument("-d", "--debug", dest="debug", help="When set debug messages will printed to the terminal",
                    action='store_true')
parser.add_argument("-p", "--port", dest="port", help="Set the port,  default is 5000", default=5000, type=int)
parser.add_argument("-db", "--db", dest="db", help="Set the database - eg. {name}.sqlite,  default is bija",
                    default='bija', type=str)

args = parser.parse_args()

if args.setup:
    SETUP_PK, SETUP_PW = setup()

if args.debug:
    LOGGING_LEVEL = logging.INFO
