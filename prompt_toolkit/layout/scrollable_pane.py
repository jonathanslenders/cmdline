from typing import List, Optional

from prompt_toolkit.data_structures import Point
from prompt_toolkit.filters import FilterOrBool, to_filter
from prompt_toolkit.key_binding import KeyBindingsBase

from .containers import Container, ScrollOffsets
from .dimension import AnyDimension, Dimension, to_dimension
from .mouse_handlers import MouseHandlers
from .screen import Char, Screen, WritePosition

__all__ = ["ScrollablePane"]

# Never go beyond this height, because performance will degrade.
MAX_AVAILABLE_HEIGHT = 10_000


class ScrollablePane(Container):
    """
    Container widget that exposes a larger virtual screen to its content and
    displays it in a vertical scrollbale region.

    Typically this is wrapped in a large `HSplit` container. Make sure in that
    case to not specify a `height` dimension of the `HSplit`, so that it will
    scale according to the content.

    .. note::

        If you want to display a completion menu for widgets in this
        `ScrollablePane`, then it's still a good practice to use a
        `FloatContainer` with a `CompletionMenu` in a `Float` at the top-level
        of the layout hierarchy, rather then nesting a `FloatContainer` in this
        `ScrollablePane`. (Otherwise, it's possible that the completion menu
        is clipped.)

    :param content: The content container.
    :param scrolloffset: Try to keep the cursor within this distance from the
        top/bottom (left/right offset is not used).
    :param keep_cursor_visible: When `True`, automatically scroll the pane so
        that the cursor (of the focused window) is always visible.
    :param keep_focused_window_visible: When `True`, automatically scroll th e
        pane so that the focused window is visible, or as much visible as
        possible if it doen't completely fit the screen.
    :param max_available_height: Always constraint the height to this amount
        for performance reasons.
    :param width: When given, use this width instead of looking at the children.
    :param height: When given, use this height instead of looking at the children.
    """

    def __init__(
        self,
        content: Container,
        scroll_offsets: Optional[ScrollOffsets] = None,
        keep_cursor_visible: FilterOrBool = True,
        keep_focused_window_visible: FilterOrBool = True,
        max_available_height: int = MAX_AVAILABLE_HEIGHT,
        width: AnyDimension = None,
        height: AnyDimension = None,
    ) -> None:
        self.content = content
        self.scroll_offsets = scroll_offsets or ScrollOffsets(top=1, bottom=1)
        self.keep_cursor_visible = to_filter(keep_cursor_visible)
        self.keep_focused_window_visible = to_filter(keep_focused_window_visible)
        self.max_available_height = max_available_height
        self.width = width
        self.height = height

        self.vertical_scroll = 0

    def __repr__(self) -> str:
        return f"ScrollablePane({self.content!r})"

    def reset(self) -> None:
        self.content.reset()

    def preferred_width(self, max_available_width: int) -> Dimension:
        if self.width is not None:
            return to_dimension(self.width)

        # We're only scrolling vertical. So the preferred width is equal to
        # that of the content.
        return self.content.preferred_width(max_available_width)

    def preferred_height(self, width: int, max_available_height: int) -> Dimension:
        if self.height is not None:
            return to_dimension(self.height)

        # Prefer a height large enough so that it fits all the content. If not,
        # we'll make the pane scrollable.
        dimension = self.content.preferred_height(width, self.max_available_height)

        # Only take 'preferred' into account. Min/max can be anything.
        return Dimension(min=0, preferred=dimension.preferred)

    def write_to_screen(
        self,
        screen: Screen,
        mouse_handlers: MouseHandlers,
        write_position: WritePosition,
        parent_style: str,
        erase_bg: bool,
        z_index: Optional[int],
    ) -> None:
        # Compute preferred height again.
        virtual_height = self.content.preferred_height(
            write_position.width, self.max_available_height
        ).preferred
        virtual_width = write_position.width

        # Ensure virtual height is at least the available height.
        virtual_height = max(virtual_height, write_position.height)
        virtual_height = min(virtual_height, self.max_available_height)

        # First, write the content to a virtual screen, then copy over the
        # visible part to the real screen.
        temp_screen = Screen(default_char=Char(char=" ", style=parent_style))
        temp_write_position = WritePosition(
            xpos=0, ypos=0, width=virtual_width, height=virtual_height
        )

        temp_mouse_handlers = MouseHandlers()

        self.content.write_to_screen(
            temp_screen,
            temp_mouse_handlers,
            temp_write_position,
            parent_style,
            erase_bg,
            z_index,
        )
        temp_screen.draw_all_floats()

        # TODO: draw scrollbar?

        # If anything in the virtual screen is focused, move vertical scroll to
        from prompt_toolkit.application import get_app

        focused_window = get_app().layout.current_window

        try:
            visible_win_write_pos = temp_screen.visible_windows_to_write_positions[
                focused_window
            ]
        except KeyError:
            pass  # No window focused here. Don't scroll.
        else:
            # Make sure this window is visible.
            self._make_window_visible(
                write_position.height,
                virtual_height,
                visible_win_write_pos,
                temp_screen.cursor_positions.get(focused_window),
            )

        # Copy over virtual screen and zero width escapes to real screen.
        ypos = write_position.ypos
        xpos = write_position.xpos

        for y in range(write_position.height):
            temp_row = temp_screen.data_buffer[y + self.vertical_scroll]
            row = screen.data_buffer[y + ypos]
            temp_zero_width_escapes = temp_screen.zero_width_escapes[
                y + self.vertical_scroll
            ]
            zero_width_escapes = screen.zero_width_escapes[y + ypos]

            for x in range(write_position.width):
                row[x + xpos] = temp_row[x]

                if x in temp_zero_width_escapes:
                    zero_width_escapes[x + xpos] = temp_zero_width_escapes[x]

        # Set screen.width/height.
        screen.width = max(screen.width, xpos + write_position.width)
        screen.height = max(screen.height, ypos + write_position.height)

        for win, write_pos in temp_screen.visible_windows_to_write_positions.items():
            screen.visible_windows_to_write_positions[win] = WritePosition(
                xpos=write_pos.xpos + xpos,
                ypos=write_pos.ypos + ypos - self.vertical_scroll,
                # TODO: if the window is only partly visible, then truncate width/height.
                #       This could be important if we have nested ScrollablePanes.
                height=write_pos.height,
                width=write_pos.width,
            )

        if temp_screen.show_cursor:
            screen.show_cursor = True

        # Copy over cursor positions.
        for window, point in temp_screen.cursor_positions.items():
            screen.cursor_positions[window] = Point(
                x=point.x + xpos, y=point.y + ypos - self.vertical_scroll
            )

        # Copy over menu positions.
        for window, point in temp_screen.menu_positions.items():
            screen.menu_positions[window] = Point(
                x=point.x + xpos, y=point.y + ypos - self.vertical_scroll
            )

    def is_modal(self) -> bool:
        return self.content.is_modal()

    def get_key_bindings(self) -> Optional[KeyBindingsBase]:
        return self.content.get_key_bindings()

    def get_children(self) -> List["Container"]:
        return [self.content]

    def _make_window_visible(
        self,
        visible_height: int,
        virtual_height: int,
        visible_win_write_pos: WritePosition,
        cursor_position: Optional[Point],
    ) -> None:
        """
        Scroll the scrollable pane, so that this window becomes visible.

        :param visible_height: Height of this `ScrollablePane` that is rendered.
        :param virtual_height: Height of the virtual, temp screen.
        :param visible_win_write_pos: `WritePosition` of the nested window on the
            temp screen.
        :param cursor_position: The location of the cursor position of this
            window on the temp screen.
        """
        # Start with maximum allowed scroll range, and then reduce according to
        # the focused window and cursor position.
        min_scroll = 0
        max_scroll = virtual_height - visible_height

        if self.keep_cursor_visible():
            # Reduce min/max scroll according to the cursor in the focused window.
            if cursor_position is not None:
                offsets = self.scroll_offsets
                cpos_min_scroll = (
                    cursor_position.y - visible_height + 1 + offsets.bottom
                )
                cpos_max_scroll = cursor_position.y - offsets.top
                min_scroll = max(min_scroll, cpos_min_scroll)
                max_scroll = max(0, min(max_scroll, cpos_max_scroll))

        if self.keep_focused_window_visible():
            # Reduce min/max scroll according to focused window position.
            # If the window is small enough, bot the top and bottom of the window
            # should be visible.
            if visible_win_write_pos.height <= visible_height:
                window_min_scroll = (
                    visible_win_write_pos.ypos
                    + visible_win_write_pos.height
                    - visible_height
                )
                window_max_scroll = visible_win_write_pos.ypos
            else:
                # Window does not fit on the screen. Make sure at least the whole
                # screen is occupied with this window, and nothing else is shown.
                window_min_scroll = visible_win_write_pos.ypos
                window_max_scroll = (
                    visible_win_write_pos.ypos
                    + visible_win_write_pos.height
                    - visible_height
                )

            min_scroll = max(min_scroll, window_min_scroll)
            max_scroll = min(max_scroll, window_max_scroll)

        if min_scroll > max_scroll:
            min_scroll = max_scroll  # Should not happen.

        # Finally, properly clip the vertical scroll.
        if self.vertical_scroll > max_scroll:
            self.vertical_scroll = max_scroll
        if self.vertical_scroll < min_scroll:
            self.vertical_scroll = min_scroll
