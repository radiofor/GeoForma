"""Run before freeze_support dispatch, including every frozen spawn child."""
from geoforma.process_bootstrap import configure_worker_diagnostics,worker_startup_stage
configure_worker_diagnostics()
worker_startup_stage('Configure bundled native library paths')
from environment._geoforma_runtime import configure
configure()
