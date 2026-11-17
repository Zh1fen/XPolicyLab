"""One module identity for public legacy aliases, independent of import order."""
import importlib
import importlib.abc
import importlib.util
import importlib.machinery
from pathlib import Path
import sys


class AliasLoader(importlib.abc.Loader):
    def __init__(self, canonical):
        self.canonical = canonical

    def create_module(self, spec):
        return importlib.import_module(self.canonical)

    def exec_module(self, module):
        pass


class AliasFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        parts = fullname.split('.')
        if parts[0] in {'environment', 'evaluation', 'utils'}:
            # Do not hijack a model vendor's unrelated top-level `utils` package.
            candidate = importlib.machinery.PathFinder.find_spec(fullname, path)
            owner = Path(__file__).resolve().parent / parts[0]
            if candidate is not None:
                locations = ([candidate.origin] if candidate.origin and candidate.origin != 'namespace'
                             else list(candidate.submodule_search_locations or []))
                if any(not Path(location).resolve().is_relative_to(owner) for location in locations):
                    return None
            canonical = 'XPolicyLab.' + fullname
        elif fullname == 'XPolicyLab.client_server' or fullname.startswith('XPolicyLab.client_server.'):
            canonical = fullname[len('XPolicyLab.'):]
        else:
            return None
        module = importlib.import_module(canonical)
        return importlib.util.spec_from_loader(fullname, AliasLoader(canonical), is_package=hasattr(module, '__path__'))


def install():
    if not any(type(finder).__name__ == 'AliasFinder' and type(finder).__module__.endswith('_robolab_compat') for finder in sys.meta_path):
        sys.meta_path.insert(0, AliasFinder())
