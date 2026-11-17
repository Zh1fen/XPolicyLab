"""Compatibility facade for the shared evaluation catalog."""
from XPolicyLab.evaluation.catalog import Catalog, ROOT, ValidationError, integer
import shutil  # compatibility for callers that patch availability probes
