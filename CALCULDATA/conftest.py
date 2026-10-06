# -*- coding: utf-8 -*-
"""Configuration pytest : rend les modules du dossier importables par les tests."""

import os
import sys

RACINE = os.path.dirname(os.path.abspath(__file__))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)
