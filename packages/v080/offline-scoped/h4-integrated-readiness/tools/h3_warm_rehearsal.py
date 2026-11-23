"""Prepare the accepted optional scripted session before its unchanged timed demo."""

from contextlib import closing

from quant_hermes_h3 import cli
from quant_hermes_h3.agent import LocalSession
from quant_hermes_h3.inbound import APP, CHAT, OPEN_ID, TENANT
from quant_hermes_h3.safety import isolated, restrict_python_network
from quant_hermes_h3.telemetry import Measurements

configure = cli.configure


def warm(home):
    configure(home)
    with closing(LocalSession((APP, TENANT, OPEN_ID, CHAT), Measurements(home / "warmup.sqlite"))):
        pass


if __name__ == "__main__":
    isolated()
    restrict_python_network()
    cli.configure = warm
    raise SystemExit(cli.main())
