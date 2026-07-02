"""Print the OpenAPI schema as JSON.

Used by the frontend type generation step:
    make gen-types        (from the repo root)
"""

import json

from pulse.main import app


def main() -> None:
    print(json.dumps(app.openapi(), indent=2))


if __name__ == "__main__":
    main()
