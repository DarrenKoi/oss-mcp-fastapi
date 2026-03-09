# Office Testing Memory

Use this file to remember non-sensitive office testing constraints for this repo.

## Confirmed

- Home development happens on macOS or Windows.
- Home development should not depend on local Redis, MongoDB, or OpenSearch instances.
- New or edited code should be verified at home with mocking data first.
- Office testing happens on Windows.
- Office Python version is 3.11.
- Office testing may use Redis, MongoDB, and OpenSearch.
- Office cloud uses separate DEV/STG/PRD API base URLs; choose one via environment variables and do not commit hostnames.
- Production runs on Linux.
- Integration tests must avoid hardcoded secrets or hostnames in source control.

## Assumptions To Confirm

- Office virtual environment workflow.
- Whether office tests run from PowerShell, `cmd.exe`, Git Bash, or WSL.
- How office service endpoints are supplied: environment variables, `.env`, VPN, or another mechanism.
- Whether Docker is available at the office for optional local dependencies.
- Whether there are existing shared test databases, indices, or namespaces that tests should use.
- Whether outbound network or proxy restrictions affect package install or service access.

## Preferred Testing Policy

1. At home, run mock-first `pytest` coverage and service-free FastAPI tests.
2. Keep real-service integration tests under `tests/` so they can run in the office.
3. Gate office integration tests with markers and environment-variable checks so they skip cleanly at home.
4. Keep tests portable across macOS, Windows, and Linux.

## Update Rule

When the user confirms new office details, append or edit this file and keep only non-sensitive information here.
