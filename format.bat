@REM Lint & sort imports
ruff check --select F401,F841,I --fix .

@REM Format code
ruff format

