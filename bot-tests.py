import pytest
from pingpongbot import *


def test_something():
    init()
    response = handle_command("challenge", TEST_CHANNEL, TEST_USER)
    print(response)


