"""Substitusi ketat: template hanya menerima variabel environment yang tersedia."""
import json
import os
from pathlib import Path
from string import Template
import sys

if __name__ == '__main__':
    values = dict(os.environ)
    values['SHARED_DIR_JSON'] = json.dumps(values['SHARED_DIR'])
    print(Template(Path(sys.argv[1]).read_text()).substitute(values), end='')
