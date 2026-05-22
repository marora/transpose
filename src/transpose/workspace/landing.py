"""Landing page generator — public re-export for the workspace package.

The canonical implementation lives in ``transpose.pipeline.workspace``
(TR-3 deliverable). This module is the stable public path that Dozer's
tests and any future callers should import from.

Usage::

    from transpose.workspace.landing import generate_landing_html
    html = generate_landing_html(metadata_dict)
"""

from transpose.pipeline.workspace import (
    generate_landing_html as generate_landing_html,  # noqa: F401
)

__all__ = ["generate_landing_html"]
