import redis

import config


class Singleton(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(
                Singleton, cls
            ).__call__(*args, **kwargs)
        return cls._instances[cls]


class Redis(metaclass=Singleton):

    def __init__(self):
        self.pool = redis.ConnectionPool(
            host=config.REDIS["host"],
            port=config.REDIS["port"],
            password=config.REDIS["password"],
        )

    @property
    def conn(self):
        if not hasattr(self, "_conn"):
            self._getConnection()
        return self._conn

    def _getConnection(self):
        self._conn = redis.Redis(connection_pool=self.pool)

    def set(self, name, value, ttl):
        self.conn.set(
            name=name,
            value=value,
            ex=ttl,
        )

    def get(self, name):
        return self.conn.get(
            name=name,
        )


def initialize():
    Redis()
