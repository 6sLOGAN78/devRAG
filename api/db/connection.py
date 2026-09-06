import os
import pymysql
pymysql.install_as_MySQLdb()
from peewee import MySQLDatabase
from playhouse.pool import PooledMySQLDatabase
import sys

# Adjust python path to find common
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from common.settings import load_config

config_path = os.environ.get('RAGFLOW_CONFIG', 'conf/service_conf.yaml')
cfg = load_config(config_path)

db = PooledMySQLDatabase(
    cfg.mysql.db,
    max_connections=32,
    stale_timeout=300,
    host=cfg.mysql.host,
    port=cfg.mysql.port,
    user=cfg.mysql.user,
    password=cfg.mysql.password
)
