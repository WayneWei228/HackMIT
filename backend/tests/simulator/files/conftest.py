import pytest

from trueup.ingest.readers import read_text
from trueup.simulator import generator
from trueup.simulator.files.build import build_universe
from trueup.simulator.files.common import CLOSE
from trueup.simulator.files.world_view import WorldView

SEED = 42


@pytest.fixture(scope="module")
def world():
    return generator.generate(SEED)


@pytest.fixture(scope="module")
def view(world):
    return WorldView(world, CLOSE)


@pytest.fixture(scope="module")
def built(world, tmp_path_factory):
    out = tmp_path_factory.mktemp("universe")
    universe, truth = build_universe(world, SEED, out)
    return universe, truth, out


@pytest.fixture(scope="module")
def texts(built):
    """file_id -> extracted text for every rendered file."""
    universe, _, out = built
    return {f.file_id: read_text(out / f.path) for f in universe.files}


@pytest.fixture(scope="module")
def case_texts(built, texts):
    universe, truth, _ = built

    def pick(vendor_name, roles=None, in_universe=True):
        case = next(c for c in universe.cases if c.vendor_name == vendor_name)
        chosen = {}
        for entry in truth.for_case(case.case_id):
            if in_universe and not entry.in_universe:
                continue
            if roles is not None and entry.role not in roles:
                continue
            chosen[entry.file_id] = texts[entry.file_id]
        return chosen

    return pick
