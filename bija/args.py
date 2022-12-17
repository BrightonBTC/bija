import argparse

parser = argparse.ArgumentParser()
parser.add_argument("-n", "--noqt", dest="noqt", help="No Qt Window, run in your browser instead", action='store_true')
parser.add_argument("-p", "--port", dest="port", help="Set the port,  default is 5000", default=5000, type=int)
parser.add_argument("-db", "--db", dest="db", help="Set the database - eg. {name}.sqlite,  default is bija",
                    default='bija', type=str)

args = parser.parse_args()
