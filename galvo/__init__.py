from .consts import *
from .controller import GalvoController

VERSION = "0.1.2"


def generate_job(generator):
    v = generator()

    def job(c):
        try:
            g = next(v)
            if isinstance(g, tuple):
                cmd = g[0]
                args = g[1:]
            else:
                cmd = g
                args = tuple()

            try:
                func = getattr(c, cmd)
                func(*args)
            except AttributeError:
                pass
            return False
        except StopIteration:
            return True

    return job
