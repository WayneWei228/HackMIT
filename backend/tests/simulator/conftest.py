import pytest

from trueup.simulator import generator


@pytest.fixture(scope="module")
def sim_world():
    return generator.generate(42)


@pytest.fixture
def corrupt(sim_world):
    """A private deep copy of the generated world that a test may damage."""
    return sim_world.model_copy(deep=True)


@pytest.fixture
def sim(sim_world):
    from trueup.simulator.simulator import Simulator

    return Simulator.from_world(sim_world)
