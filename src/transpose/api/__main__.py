"""Package entry point so ``python -m transpose.api`` works under the Docker CMD."""

from transpose.api import main

if __name__ == "__main__":
    main()
