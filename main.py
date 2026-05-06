#!/usr/bin/env python3
import logging

import customtkinter as ctk

from converter.optional_deps import initialize as init_deps
from converter.handlers import build_registry
from ui.app import App

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def main() -> None:
    deps = init_deps()
    registry = build_registry(deps)

    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")

    app = App(registry, deps)
    app.mainloop()


if __name__ == "__main__":
    main()
