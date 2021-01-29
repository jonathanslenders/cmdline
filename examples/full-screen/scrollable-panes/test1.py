#!/usr/bin/env python
"""
A simple example of a scrollable pane.
"""
from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, ScrollablePane
from prompt_toolkit.widgets import Frame, Label


# Event handlers for all the buttons.


def exit(event) -> None:
    get_app().exit()


# Combine all the widgets in a UI.
# The `Box` object ensures that padding will be inserted around the containing
# widget. It adapts automatically, unless an explicit `padding` amount is given.
root_container = Frame(
    ScrollablePane(HSplit([Frame(Label(text=f"label-{i}")) for i in range(20)]))
)

layout = Layout(container=root_container)


# Key bindings.
kb = KeyBindings()
kb.add("c-c")(exit)


# Build a main application object.
application = Application(layout=layout, key_bindings=kb, full_screen=True)


def main():
    application.run()


if __name__ == "__main__":
    main()
