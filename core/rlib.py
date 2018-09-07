import os
import core.p_engine as engine
from requests import get as http_get
PLUGINS_SUPPORT = True
try:
   from plugins.cunet import *
except: PLUGINS_SUPPORT = False
def get_engines():
    """
    Getting available plugins for Neutron
    """
    return {"engines":{
            "network":engine.net_engines,
            "boilers":engine.boiler_engines,
            "parsers":engine.parse_engines
    }}