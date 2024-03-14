
import configparser
import json
import logging
import os
import re
import uuid
from functools import cached_property

import boto3
import botocore
import botocore.exceptions
import botocore.client
from collections.abc import Iterable
from dataclasses import dataclass

from cloudknot import get_profile, get_region


import time
class IntConversionDescriptor:
    def __init__(self, *args, **kwargs):
        print(f"{args=}, {kwargs=}")

    def _mk(self):
        print(f"_mk()")
        return dict(name=self._name, time=time.time())

    def __set_name__(self, owner, name):
        print(f"__set_name__(): {owner=}, {name=}")
        self._name = "_" + name

    def __get__(self, obj, type):
        print(f"__get__(): {self=}, {obj=},{t=}, {type=}")
        if obj is None:
            print (f"__get__(): returning {None}=")
            return None
        return getattr(obj, self._name, self._mk())

    def __set__(self, obj, value):
        print(f"__set__: {self=}, {obj=}, {value=}")
        setattr(obj, self._name, value)

@dataclass(init=False, kw_only=True)
class InventoryItem:
    quantity_on_hand: IntConversionDescriptor = IntConversionDescriptor()

    def k(self, attr):
        print(f"{attr=}")
        return getattr(self, attr)

class IntConversionDescriptor:
    def __init__(self, *, default=None):
        self._client = default

    def _make_client(self, name: str) -> botocore.client.BaseClient:
        """Return a boto3 client."""
        return boto3.Session(profile_name=get_profile(fallback=None)).client(
            name, region_name=get_region()
        )
    def __set_name__(self, owner, name):
        self._name = "_" + name

    def __get__(self, obj, type):
        if obj is None:
            return self._default

        return getattr(obj, self._name, self._default)

    def __set__(self, obj, value):
        setattr(obj, self._name, int(value))

@dataclass
class InventoryItem:
    quantity_on_hand: IntConversionDescriptor = IntConversionDescriptor(default=100)


def _make_client(name: str) -> botocore.client.BaseClient:
    """Return a boto3 client."""
    return boto3.Session(profile_name=get_profile(fallback=None)).client(
        name, region_name=get_region()
    )


class ClientDict(dict):
    def __missing__(self, key):
        self[key] = {"client": key, "time": time.time()}
        return self[key]



class LoggedAccess:

    def __set_name__(self, owner, name):
        self.public_name = name
        self.private_name = '_' + name

    def __get__(self, obj, objtype=None):
        value = getattr(obj, self.private_name)
        logging.info('Accessing %r giving %r', self.public_name, value)
        return value

    def __set__(self, obj, value):
        logging.info('Updating %r to %r', self.public_name, value)
        setattr(obj, self.private_name, value)


C.x = property(getx, setx, delx, "I'm the 'x' property.")

cached_property("
class ClientCollection:
    """Class for keeping track of an item in inventory."""
    _client_names = ("batch", "cloudformation", "ecr", "ecs", "ec2", "iam", "s3")
    batch: botocore.client.BaseClient
    cloudformation: botocore.client.BaseClient
    ecr: botocore.client.BaseClient
    ecs: botocore.client.BaseClient
    ec2: botocore.client.BaseClient
    iam: botocore.client.BaseClient
    s3: botocore.client.BaseClient

    def __getattr_


    @staticmethod
    def _make_client(self, name: str ) -> botocore.client.BaseClient:
        """Return a boto3 client."""
        return boto3.Session(profile_name=get_profile(fallback=None)).client(
            name, region_name=get_region()
        )

    def __getattr__(self, item):
        x = super().__get
        if issubclass(self.__annotations__.get(item, None), botocore.client.BaseClient)):


    @property
    def batch(self) -> botocore.client.BaseClient:
        return self._batch

    @property
    def ecr(self) -> botocore.client.BaseClient:
        return self._ecr




def names() -> set[str]:
    """Return the names of the boto3 clients."""
    return set(_client_names)

def refresh(which: None | Iterable, max_pool: int = 10):
    """Refresh the boto3 clients dictionary."""
    with rlock:
        config = botocore.config.Config(max_pool_connections=max_pool)
        session = boto3.Session(profile_name=get_profile(fallback=None))
        for k in client_names:
            clients[k] = session.client(k, region_name=get_region(), config=config)

@dataclass
class _clients:
    """Class for keeping track of an item in inventory."""
    batch: botocore.client.BaseClient
    cloudformation: float
    ecr: int = 0

    def total_cost(self) -> float:
        return self.unit_price * self.quantity_on_hand

import contextlib

from ..config import get_config_file, rlock

client_names = ("batch", "cloudformation", "ecr", "ecs", "ec2", "iam", "s3")



"""module-level dictionary of boto3 clients.

Storing the boto3 clients in a module-level dictionary allows us to change
the region and profile and have those changes reflected globally.

Advanced users: if you want to use cloudknot and boto3 at the same time,
you should use these clients to ensure that you have the right profile
and region.
"""
clients = {
    k: boto3.Session(profile_name=get_profile(fallback=None)).client(
        k, region_name=get_region()
    )
    for k in client_names
}
